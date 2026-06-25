import re
from pathlib import Path

from loguru import logger
from unified_model_caller import LLMCaller
from lesia.doc_translator_mod.myst_chunker import split_myst_document_into_chunks
from lesia.enums import ChunkType, DocumentType, Language
from lesia.helpers import calculate_checksum
from lesia.errors import ChunkTranslationFailed
from lesia.translator_retrieval import ChunkTranslator, Meta, build_translator_with_model
from lesia.vocab_list import VocabList


def _format_metadata_block(metadata: dict[str, str]) -> str:
    """Formats a dictionary into a LaTeX comment metadata block."""
    lines = ["\n<!-- --- CHUNK_METADATA_START ---"]
    for key, value in metadata.items():
        lines.append(f"% {key}: {value}")
    lines.append(" --- CHUNK_METADATA_END --- -->")
    return "\n".join(lines) + "\n" # Add a newline at the end for separation


def compile_myst_cells(cells: list[dict]) -> str:
    """Takes a list of MyST cells and compiles a final file contents and returns it in string format."""
    res = ""
    for cell in cells:
        temp_res = _format_metadata_block(cell["metadata"])
        temp_res += cell["source"]
        res += temp_res
    return res

def get_myst_cells(source_file_path: Path) -> list[dict]:
    """Get's a path to the file and returns it in the cells format"""
    source_text = ""
    with open(source_file_path, "r") as f:
        source_text = f.read()

    chunk_list = split_myst_document_into_chunks(source_text)

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
) -> None:
    """Handler for a latex file-to-file translation"""
    from lesia.translation_cache.cache_rebuilder import read_existing_target_metadata
    from lesia.enums import DocumentType as _DT
    existing_meta = read_existing_target_metadata(target_file_path, _DT.Markdown)
    tr = build_translator_with_model(root_path, llm_caller, reasoning_caller)

    cells = get_myst_cells(source_file_path)

    for i in range(len(cells)):
        cell = cells[i]
        cells[i] = await translate_chunk_async(cell, source_language, target_language, relative_path, vocab_list, tr, existing_meta)

    with open(target_file_path, "w") as f:
        f.write(compile_myst_cells(cells))


async def translate_chunk_async(
    cell: dict,
    source_language: Language,
    target_language: Language,
    relative_path: str,
    vocab_list: VocabList | None,
    tr: ChunkTranslator,
    existing_meta: dict[str, dict] | None = None,
) -> dict:
   """Handler for a myst chunk translation"""
   src_txt = cell["source"]
   logger.debug(f"{src_txt}")
   checksum = calculate_checksum(src_txt)

   cell["metadata"]["src_checksum"] = checksum

   try:
       translated, from_cache = await translate_any_chunk_async(src_txt, source_language, target_language, relative_path, vocab_list, tr)
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
    meta = Meta(contents, source_language, target_language, DocumentType.Markdown, ChunkType.Myst, vocab_list, relative_path)
    return await tr.translate_or_fetch(meta)


# corr
def _parse_metadata_block(block_str: str) -> dict[str, str]:
    """Parses a MyST comment metadata block string into a dictionary."""
    metadata = {}
    lines = block_str.splitlines()
    for line in lines:
        line = line.strip()
        if line.startswith('<!--'):
            line = line[4:].strip() # Remove the comment char
            if line.startswith('--- CHUNK_METADATA_START ---') or \
               line.startswith('--- CHUNK_METADATA_END ---'):
                continue # Skip the delimiters
            
        if line.startswith('%'):
            line = line[1:].strip() # Remove the comment char
            if ':' in line:
                key, value = line.split(':', 1) # Split only on first column
                metadata[key.strip()] = value.strip()
    return metadata

def read_chunks_with_metadata_from_myst(
    filepath: Path 
) -> list[dict]:
    """
    Reads a MyST/Markdown file containing metadata blocks and splits it into chunks.
    Returns a list of dictionaries, each with 'source' and 'metadata' keys.
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        full_content = f.read()

    chunks_data: list[dict] = []
    
    METADATA_BLOCK_REGEX = re.compile(
        r'(?s)(<!-- --- CHUNK_METADATA_START ---\n.*?\n --- CHUNK_METADATA_END --- -->\n)'
    )

    parts = METADATA_BLOCK_REGEX.split(full_content)
    logger.debug("Split MyST content into {} parts.", len(parts))

    current_chunk_content = ""
    current_metadata: dict[str, str] = {}

    start_index = 0
    if not parts[0].strip():
        start_index = 1
        # If the file starts with metadata, parts[1] will be the first metadata block
        if len(parts) > 1:
            current_metadata = _parse_metadata_block(parts[1])
            start_index = 2 # Start processing content from here

    for i in range(start_index, len(parts)):
        part = parts[i]
        
        if i % 2 == 1: # This is a metadata block (odd index)
            # Store the previous chunk's data if we had content
            if current_chunk_content.strip():
                chunks_data.append({
                    "source": current_chunk_content.strip(),
                    **current_metadata # Unpack current_metadata into the dict
                })
            current_metadata = _parse_metadata_block(part)
            current_chunk_content = "" # Reset content for the new chunk
        else: # This is a content block (even index)
            current_chunk_content += part

    # Add the very last chunk's data if there's any accumulated content
    if current_chunk_content.strip():
        chunks_data.append({
            "source": current_chunk_content.strip(),
            **current_metadata
        })

    return chunks_data
