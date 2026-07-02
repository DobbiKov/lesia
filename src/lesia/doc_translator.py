from loguru import logger
from unified_model_caller import LLMCaller

from lesia.doc_translator_mod import myst_file_translator
from lesia.vocab_list import VocabList
from .enums import DocumentType, Language
from .translator import LLM_API_KEY, LLM_REASONING_API_KEY, translate_contents_async
from .helpers import read_string_from_file, analyze_document_type
from .errors import TranslationProcessError
from .doc_translator_mod.notebook_file_translator import translate_notebook_async
from pathlib import Path
from .doc_translator_mod import latex_file_translator, typst_file_translator

async def translate_file_async(source_path: Path, target_language: Language, vocab_list: VocabList | None) -> str:
    """Reads a file, translates its content asynchronously, and returns the translated content."""
    file_contents = read_string_from_file(source_path)
    return await translate_contents_async(file_contents, target_language, 50, vocab_list)


async def translate_file_to_file_async(
    root_path: Path,
    source_path: Path,
    source_language: Language,
    target_path: Path,
    target_language: Language,
    relative_path: str,
    vocab_list: VocabList | None,
    llm_service: str,
    llm_model: str,
    llm_reasoning_service: str | None = None,
    llm_reasoning_model: str | None = None,
    use_reasoning_model: bool = False,
    xml_retries_before_reasoning: int = 2,
) -> None:
    """Translates a file and writes the result to another file asynchronously."""
    doc_type = analyze_document_type(source_path)
    logger.trace(doc_type)
    main_api_key = (LLM_REASONING_API_KEY or LLM_API_KEY) if use_reasoning_model else LLM_API_KEY
    llm_caller = LLMCaller(llm_service, llm_model, main_api_key or "")
    reasoning_caller = None
    if not main_api_key and llm_caller.requires_token():
        key_name = "LLM_REASONING_API_KEY" if use_reasoning_model else "LLM_API_KEY"
        raise TranslationProcessError(f"{key_name} environment variable is not set but is required for service '{llm_service}'.", original_exception=None)
    if llm_reasoning_service and llm_reasoning_model:
        reasoning_caller = LLMCaller(llm_reasoning_service, llm_reasoning_model, LLM_REASONING_API_KEY or "")
        if not LLM_REASONING_API_KEY and reasoning_caller.requires_token():
            raise TranslationProcessError(f"LLM_REASONING_API_KEY (and LLM_API_KEY) environment variable is not set but is required for reasoning service '{llm_reasoning_service}'.", original_exception=None)
    try:
        if doc_type == DocumentType.JupyterNotebook:
            logger.debug("translate jupyter")
            await translate_notebook_async(root_path, source_path, source_language, target_path, target_language, vocab_list, llm_caller, relative_path, reasoning_caller=reasoning_caller, xml_retries_before_reasoning=xml_retries_before_reasoning)
        elif doc_type == DocumentType.Markdown:
            logger.debug("translate markdown")
            await myst_file_translator.translate_file_async(root_path, source_path, source_language, target_path, target_language, relative_path, vocab_list, llm_caller, reasoning_caller=reasoning_caller, xml_retries_before_reasoning=xml_retries_before_reasoning)
        elif doc_type == DocumentType.LaTeX:
            logger.trace("translate latex")
            await latex_file_translator.translate_file_async(root_path, source_path, source_language, target_path, target_language, relative_path, vocab_list, llm_caller, reasoning_caller=reasoning_caller, xml_retries_before_reasoning=xml_retries_before_reasoning)
        elif doc_type == DocumentType.Typst:
            logger.debug("translate typst")
            await typst_file_translator.translate_file_async(
                root_path,
                source_path,
                source_language,
                target_path,
                target_language,
                relative_path,
                vocab_list,
                llm_caller,
                reasoning_caller=reasoning_caller,
                xml_retries_before_reasoning=xml_retries_before_reasoning,
            )
        else: # any other type
            logger.debug("other type? lol")
            translated_content = await translate_file_async(source_path, target_language, vocab_list)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(translated_content, encoding="utf-8")
    except IOError as e:
        raise TranslationProcessError(f"Failed to write translated file {target_path}: {e}", original_exception=e)
