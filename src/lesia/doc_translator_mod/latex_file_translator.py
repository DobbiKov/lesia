from unified_model_caller import LLMCaller
from ..prompts import prompt4
from pathlib import Path

from lesia.doc_translator_mod.latex_chunker import split_latex_document_into_chunks
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
from ..enums import ChunkType, DocumentType, Language
from ..helpers import calculate_checksum
from lesia.errors import ChunkTranslationFailed
from loguru import logger


def _format_metadata_block(metadata: dict[str, str]) -> str:
    """Formats a dictionary into a LaTeX comment metadata block."""
    lines = ["% --- CHUNK_METADATA_START ---"]
    for key, value in metadata.items():
        lines.append(f"% {key}: {value}")
    lines.append("% --- CHUNK_METADATA_END ---")
    return "\n".join(lines) + "\n" # Add a newline at the end for separation

def compile_latex_cells_with_lines(cells: list[dict]) -> tuple[str, list[int]]:
    """Compiles latex cells into file contents; also returns the 1-based line
    where each cell's source starts in the compiled output."""
    res = ""
    start_lines: list[int] = []
    for cell in cells:
        res += _format_metadata_block(cell["metadata"])
        start_lines.append(res.count("\n") + 1)
        res += cell["source"]
    return res, start_lines


def compile_latex_cells(cells: list[dict]) -> str:
    """Takes a list of latex cells and compiles a final file contents and returns it in string format."""
    return compile_latex_cells_with_lines(cells)[0]

def get_latex_cells(source_file_path: Path) -> list[dict]:
    """Get's a path to the file and returns it in the cells format"""
    latex_document_string = ""
    with open(source_file_path, "r") as f:
        latex_document_string = f.read()

    chunk_list = split_latex_document_into_chunks(latex_document_string)

    cells = []
    # dividing into cells
    for chunk in chunk_list:
        contents = chunk["content"]
        cell = {
                "metadata": {},
                "source": contents
                }
        cells.append(cell)

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
    """Handler for a latex file-to-file translation"""
    from lesia.translation_cache.cache_rebuilder import read_existing_target_metadata
    from lesia.enums import DocumentType as _DT
    existing_meta = read_existing_target_metadata(target_file_path, _DT.LaTeX)
    tr = build_translator_with_model(root_path, llm_caller, reasoning_caller, xml_retries_before_reasoning)

    cells = get_latex_cells(source_file_path)
    source_text = source_file_path.read_text(encoding="utf-8")
    src_start_lines = locate_chunk_start_lines(source_text, [c["source"] for c in cells])

    failures: list[ChunkFailure] = []
    for i in range(len(cells)):
        cell = cells[i]
        cells[i] = await translate_chunk_async(cell, source_language, target_language, relative_path, vocab_list, tr, existing_meta, failures=failures, chunk_index=i + 1)

    compiled, tgt_start_lines = compile_latex_cells_with_lines(cells)
    with open(target_file_path, "w") as f:
        f.write(compiled)

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
   """Handler for a latex chunk translation"""
   src_txt = cell["source"]
   logger.debug(f"{src_txt}")
   checksum = calculate_checksum(src_txt)

   cell["metadata"]["src_checksum"] = checksum

   try:
       translated, from_cache = await translate_any_chunk_async(src_txt, source_language, target_language, relative_path, vocab_list, tr)
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

def get_latex_prompt_text() -> str:
    """Returns the default prompt for translating LaTeX documents"""
    return prompt4

async def translate_any_chunk_async(
    contents: str,
    source_language: Language,
    target_language: Language,
    relative_path: str,
    vocab_list: VocabList | None,
    tr: ChunkTranslator,
) -> tuple[str, bool]:
    meta = Meta(contents, source_language, target_language, DocumentType.LaTeX, ChunkType.LaTeX, vocab_list, relative_path)
    return await tr.translate_or_fetch(meta)
