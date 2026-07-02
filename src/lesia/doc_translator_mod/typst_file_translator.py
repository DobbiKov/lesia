from __future__ import annotations

from pathlib import Path

from loguru import logger
from unified_model_caller import LLMCaller

from lesia.doc_translator_mod.typst_chunker import split_typst_document_into_chunks
from lesia.enums import ChunkType, DocumentType, Language
from lesia.errors import ChunkTranslationFailed
from lesia.helpers import calculate_checksum
from lesia.translator_retrieval import ChunkTranslator, Meta, build_translator_with_model
from lesia.vocab_list import VocabList


def _format_metadata_block(metadata: dict[str, str]) -> str:
    lines = ["// --- CHUNK_METADATA_START ---"]
    for key, value in metadata.items():
        lines.append(f"// {key}: {value}")
    lines.append("// --- CHUNK_METADATA_END ---")
    return "\n".join(lines) + "\n"


def compile_typst_cells(cells: list[dict]) -> str:
    result = ""
    for cell in cells:
        if result and not result.endswith("\n"):
            result += "\n"
        result += _format_metadata_block(cell["metadata"])
        result += cell["source"]
    return result


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
) -> None:
    from lesia.translation_cache.cache_rebuilder import read_existing_target_metadata
    from lesia.enums import DocumentType as _DT
    existing_meta = read_existing_target_metadata(target_file_path, _DT.Typst)
    tr = build_translator_with_model(root_path, llm_caller, reasoning_caller, xml_retries_before_reasoning)

    cells = get_typst_cells(source_file_path)

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
        )

    with open(target_file_path, "w", encoding="utf-8") as file:
        file.write(compile_typst_cells(cells))


async def translate_chunk_async(
    cell: dict,
    source_language: Language,
    target_language: Language,
    relative_path: str,
    vocab_list: VocabList | None,
    tr: ChunkTranslator,
    existing_meta: dict[str, dict] | None = None,
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
        elif existing_meta and (existing_meta.get(checksum) or {}).get("needs_review") == "True":
            cell["metadata"]["needs_review"] = "True"
    except ChunkTranslationFailed as exc:
        cell["metadata"]["not-translated-due-to-exception"] = "True"
        cell["source"] = exc.chunk

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
