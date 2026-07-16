from __future__ import annotations

from pathlib import Path

from loguru import logger
from unified_model_caller import LLMCaller

from lesia.doc_translator_mod.typst_chunker import split_typst_document_into_chunks
from lesia.enums import ChunkType, DocumentType, Language
from lesia.errors import ChunkTranslationFailed
from lesia.helpers import calculate_checksum
from lesia.translator_retrieval import (
    ChunkFailure,
    ChunkTranslator,
    Meta,
    TranslationStats,
    build_translator_with_model,
    chunk_failure_from_exception,
    fill_failure_locations,
    locate_chunk_start_lines,
)
from lesia.vocab_list import VocabList


def _format_metadata_block(metadata: dict[str, str]) -> str:
    lines = ["// --- CHUNK_METADATA_START ---"]
    for key, value in metadata.items():
        lines.append(f"// {key}: {value}")
    lines.append("// --- CHUNK_METADATA_END ---")
    return "\n".join(lines) + "\n"


def compile_typst_cells_with_lines(cells: list[dict]) -> tuple[str, list[int]]:
    """Compiles Typst cells into file contents; also returns the 1-based line
    where each cell's source starts in the compiled output."""
    result = ""
    start_lines: list[int] = []
    for cell in cells:
        if result and not result.endswith("\n"):
            result += "\n"
        result += _format_metadata_block(cell["metadata"])
        start_lines.append(result.count("\n") + 1)
        result += cell["source"]
    return result, start_lines


def compile_typst_cells(cells: list[dict]) -> str:
    return compile_typst_cells_with_lines(cells)[0]


def get_typst_cells(source_file_path: Path) -> list[dict]:
    with open(source_file_path, "r", encoding="utf-8") as file:
        source = file.read()

    chunk_list = split_typst_document_into_chunks(source)
    cells = []
    for chunk in chunk_list:
        cells.append({"metadata": {}, "source": chunk["content"]})
    return cells


async def translate_file_async(
    root_path: Path,
    source_file_path: Path,
    source_language: Language,
    target_file_path: Path,
    target_language: Language,
    relative_path: str,
    vocab_list: VocabList | None,
    llm_caller: LLMCaller,
    reasoning_caller: LLMCaller | None = None,
    xml_retries_before_reasoning: int = 2,
) -> TranslationStats:
    from lesia.translation_cache.cache_rebuilder import read_existing_target_metadata
    from lesia.enums import DocumentType as _DT
    existing_meta = read_existing_target_metadata(target_file_path, _DT.Typst)
    tr = build_translator_with_model(root_path, llm_caller, reasoning_caller, xml_retries_before_reasoning)

    cells = get_typst_cells(source_file_path)
    source_text = source_file_path.read_text(encoding="utf-8")
    src_start_lines = locate_chunk_start_lines(source_text, [c["source"] for c in cells])

    failures: list[ChunkFailure] = []
    for index in range(len(cells)):
        cell = cells[index]
        cells[index] = await translate_chunk_async(
            cell,
            source_language,
            target_language,
            relative_path,
            vocab_list,
            tr,
            existing_meta,
            failures=failures,
            chunk_index=index + 1,
        )

    compiled, tgt_start_lines = compile_typst_cells_with_lines(cells)
    with open(target_file_path, "w", encoding="utf-8") as file:
        file.write(compiled)

    fill_failure_locations(failures, root_path, source_file_path, target_file_path, src_start_lines, tgt_start_lines)
    tr.stats.failures.extend(failures)
    return tr.stats


async def translate_chunk_async(
    cell: dict,
    source_language: Language,
    target_language: Language,
    relative_path: str,
    vocab_list: VocabList | None,
    tr: ChunkTranslator,
    existing_meta: dict[str, dict] | None = None,
    failures: list[ChunkFailure] | None = None,
    chunk_index: int = 0,
) -> dict:
    src_txt = cell["source"]
    logger.debug(f"{src_txt}")
    checksum = calculate_checksum(src_txt)

    cell["metadata"]["src_checksum"] = checksum

    try:
        translated, from_cache = await translate_any_chunk_async(
            src_txt,
            source_language,
            target_language,
            relative_path,
            vocab_list,
            tr,
        )
        cell["source"] = translated
        if not from_cache:
            cell["metadata"]["needs_review"] = "True"
            if getattr(tr, "last_translation_service", None):
                cell["metadata"]["translation_service"] = tr.last_translation_service
            if getattr(tr, "last_translation_model", None):
                cell["metadata"]["translation_model"] = tr.last_translation_model
        else:
            prev_meta = (existing_meta or {}).get(checksum) or {}
            if prev_meta.get("needs_review") == "True":
                cell["metadata"]["needs_review"] = "True"
            for key in ("translation_service", "translation_model"):
                if prev_meta.get(key):
                    cell["metadata"][key] = prev_meta[key]
    except ChunkTranslationFailed as exc:
        cell["metadata"]["not-translated-due-to-exception"] = "True"
        cell["source"] = exc.chunk
        if failures is not None:
            failures.append(chunk_failure_from_exception(chunk_index, exc))

    return cell


async def translate_any_chunk_async(
    contents: str,
    source_language: Language,
    target_language: Language,
    relative_path: str,
    vocab_list: VocabList | None,
    tr: ChunkTranslator,
) -> tuple[str, bool]:
    meta = Meta(
        contents,
        source_language,
        target_language,
        DocumentType.Typst,
        ChunkType.Typst,
        vocab_list,
        relative_path,
    )
    return await tr.translate_or_fetch(meta)
