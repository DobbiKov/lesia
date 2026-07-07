from unified_model_caller import LLMCaller
from ..prompts import prompt_jupyter_code, prompt_jupyter_md 
from pathlib import Path

from lesia.translator_retrieval import ChunkTranslator, CodeMeta, Meta, TranslationStats, build_translator_with_model
from lesia.errors import ChunkTranslationFailed
from lesia.vocab_list import VocabList
from ..enums import ChunkType, DocumentType, Language
from ..helpers import calculate_checksum
import jupytext

async def translate_notebook_async(
    root_path: Path,
    source_file_path: Path,
    source_language: Language,
    target_file_path: Path,
    target_language: Language,
    vocab_list: VocabList | None,
    llm_caller: LLMCaller,
    relative_path: str,
    reasoning_caller: LLMCaller | None = None,
    xml_retries_before_reasoning: int = 2,
) -> TranslationStats:
    from lesia.translation_cache.cache_rebuilder import read_existing_target_metadata
    from lesia.enums import DocumentType as _DT
    existing_meta = read_existing_target_metadata(target_file_path, _DT.JupyterNotebook)
    tr = build_translator_with_model(root_path, llm_caller, reasoning_caller, xml_retries_before_reasoning)

    nb = jupytext.read(source_file_path)
    for i in range(len(nb.cells)):
        nb.cells[i] = await translate_jupyter_cell_async(nb.cells[i], source_language, target_language, vocab_list, tr, relative_path, existing_meta)
    jupytext.write(nb, target_file_path, fmt={"notebook_metadata_filter": "all"})

    return tr.stats

async def translate_jupyter_cell_async(
    cell: dict,
    source_language: Language,
    target_language: Language,
    vocab_list: VocabList | None,
    tr: ChunkTranslator,
    relative_path: str,
    existing_meta: dict[str, dict] | None = None,
) -> dict:
    src_txt = cell["source"]
    cell_type = cell["cell_type"]
    checksum = calculate_checksum(src_txt)

    cell.setdefault("metadata", {})
    cell["metadata"].setdefault("tags", [])
    cell["metadata"]["src_checksum"] = checksum

    try:
        if cell_type == "code":
            translated, from_cache = await translate_code_cell_async(src_txt, source_language, target_language, vocab_list, tr, relative_path)
        else:
            translated, from_cache = await translate_markdown_cell_async(src_txt, source_language, target_language, vocab_list, tr, relative_path)
        cell["source"] = translated
        tags = cell["metadata"]["tags"]
        if not from_cache:
            if "needs_review" not in tags:
                tags.append("needs_review")
        elif existing_meta and "needs_review" in (existing_meta.get(checksum) or {}).get("tags", []):
            if "needs_review" not in tags:
                tags.append("needs_review")
    except ChunkTranslationFailed as exc:
        tags = cell["metadata"].setdefault("tags", [])
        if "not-translated-due-to-exception" not in tags:
            tags.append("not-translated-due-to-exception")
        cell["metadata"]["not-translated-due-to-exception"] = "True"
        cell["source"] = exc.chunk

    return cell


def get_markdown_prompt_text() -> str:
    """Returns the default prompt for translating markdown prompt of the jupyter notebook"""
    return prompt_jupyter_md

def get_code_prompt_text() -> str:
    """Returns the default prompt for translating code part of the jupyter notebook"""
    return prompt_jupyter_code

async def translate_markdown_cell_async(
    contents: str,
    source_language: Language,
    target_language: Language,
    vocab_list: VocabList | None,
    tr: ChunkTranslator,
    relative_path: str,
) -> tuple[str, bool]:
    meta = Meta(contents, source_language, target_language, DocumentType.JupyterNotebook, ChunkType.Myst, vocab_list, relative_path)
    return await tr.translate_or_fetch(meta)


async def translate_code_cell_async(
    contents: str,
    source_language: Language,
    target_language: Language,
    vocab_list: VocabList | None,
    tr: ChunkTranslator,
    relative_path: str,
) -> tuple[str, bool]:
    meta = CodeMeta(contents, source_language, target_language, DocumentType.JupyterNotebook, ChunkType.Code, vocab_list, relative_path, "python") # TODO: the language must be set accordingly to the cell
    return await tr.translate_or_fetch(meta)
