import asyncio
import os
from pathlib import Path

from loguru import logger

from lesia.vocab_list import VocabList

from .constants import INTER_FILE_TRANSLATION_DELAY_SECONDS 
from .prompts import prompt4

from .enums import Language
from .helpers import divide_into_chunks, extract_translated_from_response
from .errors import TranslationProcessError


# TODO:
# Configure the API key
try:
    LLM_API_KEY = os.getenv("LLM_API_KEY")
    # if not LLM_API_KEY:
    #     logger.warning("LLM_API_KEY environment variable not set. Translation will fail.")
    LLM_REASONING_API_KEY = os.getenv("LLM_REASONING_API_KEY") or LLM_API_KEY
except Exception as e:
    logger.error(f"Error configuring LLM api key: {e}")

def _sanitize_invalid_ssl_env_paths() -> None:
    """
    Removes invalid SSL certificate env vars that break google-genai client
    initialization and can trigger noisy async cleanup exceptions.
    """
    for env_var in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"):
        env_value = os.getenv(env_var)
        if not env_value:
            continue
        if Path(env_value).is_file():
            continue
        logger.warning(
            "{} points to a missing file ({}). Unsetting it.",
            env_var,
            env_value,
        )
        os.environ.pop(env_var, None)


_sanitize_invalid_ssl_env_paths()


def get_default_prompt_text() -> str:
    """Returns the default prompt"""
    return prompt4


def_prompt_template = get_default_prompt_text()

def _prepare_prompt_for_content_type(prompt_template: str, content_type: str) -> str:
    """
    Replaces the content type placeholder with the given document type
    """
    return prompt_template.replace("[CONTENT_TYPE]", str(content_type))

def _prepare_prompt_for_translation_example(prompt_template: str, src_ex: str, tgt_ex: str) -> str:
    """Replaces the language placeholder in the prompt."""
    return prompt_template.replace("[OLD_SRC]", src_ex).replace("[OLD_TGT]", tgt_ex)

def _prepare_prompt_for_language(prompt_template: str, target_language: Language, source_language: Language | None = None) -> str:
    """Replaces the language placeholder in the prompt."""
    if source_language is not None:
        prompt_template = prompt_template.replace("[SOURCE_LANGUAGE]", str(source_language))
    return prompt_template.replace("[TARGET_LANGUAGE]", str(target_language))

def _prepare_prompt_for_vocab_list(prompt: str, vocab_list: VocabList | None) -> str:
    """Replaces the language placeholder in the prompt."""
    str_to_put = ""
    if vocab_list is not None:
        str_to_put = vocab_list.compile_into_llm_vocab_list()
    return _paste_vocabulary_into_prompt(prompt, str_to_put)

def _paste_vocabulary_into_prompt(prompt_template: str, vocabulary: str) -> str:
    return prompt_template.replace("[CUSTOM_VOCABULARY]", str(vocabulary))

async def _ask_gemini_model(full_prompt_message: str, model_name: str = "gemini-2.5-flash-preview-05-20") -> str:
    """
    Asks the Gemini model for a translation.
    The default model_name is "gemini-2.0-flash"
    """
    if not LLM_API_KEY: # Re-check in case it wasn't set at module load
        raise EnvironmentError("LLM_API_KEY environment variable must be set for translation.")

    from google import genai
    from google.genai import types as g_types
    client = genai.Client(api_key=LLM_API_KEY)

    try:
        contents = g_types.Content(
                role='user',
                parts=[g_types.Part.from_text(text=full_prompt_message)]
        )
        

        # print(f"DEBUG: Sending to Gemini: {full_prompt_message[:200]}...") # Log request start

        await asyncio.sleep(INTER_FILE_TRANSLATION_DELAY_SECONDS)
        response = client.models.generate_content(
                model=model_name,
                contents=contents
        )

        # print(f"DEBUG: Received from Gemini: {response.text[:200]}...") # Log response start
        
        return response.text or "" 
    
    except Exception as e:
        logger.error(f"Error communicating with Gemini API: {e}")
        raise TranslationProcessError(f"Gemini API call failed: {e}", original_exception=e)

async def _ask_aristote(full_prompt_message: str) -> str:
    import requests
    aristote_API_ENDPOINT = "https://aristote-dispatcher.mydocker-run-vd.centralesupelec.fr/v1/chat/completions"
    model = "casperhansen/llama-3.3-70b-instruct-awq" # Nom du modèle à utiliser
    data = {
    "model": model, 
    "messages": [{"role": "user", "content":full_prompt_message}],  #remplir content avec votre message
    }
    response = requests.post(aristote_API_ENDPOINT, json=data)
    return response.json().get("choices")[0].get("message").get("content")

def finalize_prompt(prompt: str, contents_to_translate: str) -> str:
   return f"{prompt}\n<document>\n{contents_to_translate}\n</document>"

def finalize_xml_prompt(prompt: str, contents_to_translate: str) -> str:
   # return f"{prompt}\n{contents_to_translate}\n"
   return prompt.replace("[SRC]", contents_to_translate)

async def translate_chunk_with_prompt(prompt: str, chunk: str, is_xml: bool = False) -> str:
    """
    Translates the given chunk of text using the given prompt
    """
    final_message_to_model = finalize_prompt(prompt, chunk) if not is_xml else finalize_xml_prompt(prompt, chunk)
    
    translated_response_text = await _ask_gemini_model(final_message_to_model, "gemini-2.0-flash")
    logger.debug("Model response received ({} chars).", len(translated_response_text))
    
    return extract_translated_from_response(translated_response_text)


async def translate_chunk_async(text_chunk: str, target_language: Language, vocab_list: VocabList | None) -> str:
    """Translates a single chunk of text asynchronously."""
    prompt_for_lang = _prepare_prompt_for_language(def_prompt_template, target_language)
    prompt_for_lang = _prepare_prompt_for_vocab_list(prompt_for_lang, vocab_list)
    
    return await translate_chunk_with_prompt(prompt_for_lang, text_chunk)

async def translate_contents_async(contents: str, target_language: Language, lines_per_chunk: int = 50, vocab_list: VocabList | None = None) -> str:
    """
    Translates the given string contents asynchronously, handling chunking.
    Includes a delay between chunk translations for rate limiting.
    """
    if not contents.strip():
        return ""

    chunks = divide_into_chunks(contents, lines_per_chunk)
    translated_chunks: list[str] = []

    # Rate limiting: Delay between chunks
    # The Rust code had sleep(5) inside ask_gemini_model (for each chunk indirectly)
    # and then an additional sleep(8) in translate_file_helper (after each file).
    # This suggests a need for delays.
    INTER_CHUNK_DELAY_SECONDS = 5 # Corresponds to the sleep in ask_gemini_model

    for i, chunk in enumerate(chunks):
        if not chunk.strip(): # Skip empty chunks
            translated_chunks.append(chunk) # Preserve empty lines if they form a chunk
            continue

        translated_chunk = await translate_chunk_async(chunk, target_language, vocab_list)
        translated_chunks.append(translated_chunk)
        
        if i < len(chunks) - 1: # If not the last chunk
            print(f"Translated chunk {i+1}/{len(chunks)}. Waiting for {INTER_CHUNK_DELAY_SECONDS}s...")
            
    return "".join(translated_chunks)
