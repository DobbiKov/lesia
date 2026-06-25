from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Iterable, List, Optional

from lesia.constants import CONF_DIR
from lesia.enums import DocumentType

def calculate_checksum(contents: str) -> str:
    """
    Returns a checksum of the provided contents
    """
    return hashlib.sha256(contents.encode('utf-8')).hexdigest()

def normalize_relative_path(path: Path | str) -> str:
    """Converts any Path-like input to a normalized POSIX relative string."""
    if isinstance(path, Path):
        return path.as_posix()
    return Path(path).as_posix()

def calculate_path_checksum(relative_path: str | Path) -> str:
    """Returns a checksum for a normalized relative path string."""
    normalized = normalize_relative_path(relative_path)
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()

def ensure_dir_exists(path: Path) -> None:
    if not os.path.exists(path):
        os.mkdir(path)
        return
    if not path.is_dir():
        os.mkdir(path)
        return

def find_dir_upwards(start_path: Path, dir_name: str) -> Optional[Path]:
    """
    Search the given directory and each parent directory for `dir_name`.
    Returns the full path to the first match, or `None` if nothing is found.
    """
    current_dir = start_path.resolve()
    if not current_dir.is_dir():
        current_dir = current_dir.parent

    while current_dir:
        candidate = current_dir / dir_name
        if candidate.is_dir():
            return candidate
        
        if current_dir == current_dir.parent:  # Reached filesystem root
            break
        current_dir = current_dir.parent
    
    return None

def find_file_upwards(start_path: Path, file_name: str) -> Optional[Path]:
    """
    Search the given directory and each parent directory for `file_name`.
    Returns the full path to the first match, or `None` if nothing is found.
    """
    current_dir = start_path.resolve()
    if not current_dir.is_dir():
        current_dir = current_dir.parent

    while current_dir:
        candidate = current_dir / file_name
        if candidate.is_file():
            return candidate
        
        if current_dir == current_dir.parent:  # Reached filesystem root
            break
        current_dir = current_dir.parent
    
    return None

def divide_into_chunks(text: str, lines_per_chunk: int) -> List[str]:
    """
    Takes a text, divides it into chunks (each chunk containing at most
    `lines_per_chunk` number of lines) and returns the list of such chunks.
    """
    if not text or lines_per_chunk <= 0:
        return [text] if text else []

    lines = text.splitlines(keepends=True) # keepends=True to preserve newline chars
    if not lines: # Handle empty string or string with no newlines if splitlines returns empty
        return [text] if text.strip() else []


    chunks: List[str] = []
    current_chunk_lines: List[str] = []
    
    for i, line in enumerate(lines):
        current_chunk_lines.append(line)
        if (i + 1) % lines_per_chunk == 0:
            chunks.append("".join(current_chunk_lines))
            current_chunk_lines = []
            
    if current_chunk_lines:
        chunks.append("".join(current_chunk_lines))
        
    # If original text had no newlines but lines_per_chunk > 0
    if not chunks and text:
        return [text]

    return chunks


def extract_text_between_tags(text: str, start_tag: str, end_tag: str) -> str:
    """
    Extracts content between the first occurrence of start_tag and its corresponding end_tag.
    Handles nested tags superficially by finding the first start and then the first end.
    Rust version was specific to <output>
    """
    start_index = text.find(start_tag)
    if start_index == -1:
        return ""
    
    start_index += len(start_tag)
    
    end_index = text.find(end_tag, start_index)
    if end_index == -1:
        # If end_tag is not found after start_tag, maybe return content till end or empty
        return text[start_index:] # Or "" if strict matching is needed

    return text[start_index:end_index].strip()

    
def extract_translated_from_response(message: str) -> str:
    """
    1. Looks for <output> tags. If found, returns content *inside* tags (stripping tags and leading \n).
    2. If <output> not found, looks for <document> tags. Returns content *including* the tags.
    3. Returns empty string if neither are found.
    """
    
    if "<output>" in message:
        res_list = []
        current_pos = 0
        while True:
            start_idx = message.find("<output>", current_pos)
            if start_idx == -1:
                break
            start_idx += len("<output>")
            
            end_idx = message.find("</output>", start_idx)
            if end_idx == -1: 
                # No closing tag: take the rest of the string
                segment = message[start_idx:]
                if segment.startswith("\n"):
                     segment = segment[1:]
                res_list.append(segment)
                break 

            segment = message[start_idx:end_idx]
            if segment.startswith("\n"):
                segment = segment[1:]
            res_list.append(segment)
            current_pos = end_idx + len("</output>")
            
        return "".join(res_list)

    elif "<document>" in message:
        res_list = []
        current_pos = 0
        while True:
            start_idx = message.find("<document>", current_pos)
            if start_idx == -1:
                break
            
            # Note: We do NOT add len("<document>") to start_idx because 
            # we want to include the tag in the result.

            end_idx = message.find("</document>", start_idx)
            if end_idx == -1:
                # No closing tag: take the rest of the string (including the opening tag)
                segment = message[start_idx:]
                res_list.append(segment)
                break 

            # Calculate the end position to include "</document>"
            end_pos = end_idx + len("</document>")
            
            segment = message[start_idx:end_pos]
            # We do NOT strip startswith("\n") here to preserve exact document structure
            res_list.append(segment)
            
            current_pos = end_pos

        return "".join(res_list)

    return ""


def read_string_from_file(path: Path) -> str:
    """Reads file and returns its contents in String format."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise
    except Exception as e:
        raise IOError(f"Could not read file {path}: {e}") from e

def has_jupytext_header_in_file(file_path: Path) -> bool:
    """
    Checks if a given .md file explicitly contains a Jupytext YAML header
    that identifies it as a Jupytext notebook representation.
    This method tries to read the header directly to avoid influence from
    global Jupytext configurations.

    Args:
        file_path (str): The path to the .md file.

    Returns:
        bool: True if the .md file has a YAML header with
              'jupytext.text_representation' defined, False otherwise.
    """
    if not os.path.isfile(file_path):
        return False

    header_content = []
    in_yaml_header = False
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                # Standard YAML header is --- on first line, then content, then ---
                if i == 0 and line.strip() == '---':
                    in_yaml_header = True
                    continue # Skip the first '---'
                
                if in_yaml_header:
                    if line.strip() == '---': # End of YAML block
                        break
                    header_content.append(line)
                    if i > 30: # Don't read too much if header is malformed or very long
                        # print(f"Warning: YAML header in '{file_path}' seems very long, stopping parse.")
                        return False # Or indicate a malformed header
                else:
                    # If the first line wasn't '---', there's no standard YAML header we're looking for.
                    break 
            
            if not in_yaml_header or not header_content:
                return False # No YAML header found or it was empty

            header_yaml_str = "".join(header_content)

            try:
                import yaml
                metadata = yaml.safe_load(header_yaml_str)
                if isinstance(metadata, dict) and \
                   'jupytext' in metadata and \
                   isinstance(metadata.get('jupytext'), dict) and \
                   'text_representation' in metadata.get('jupytext', {}):
                    # Further check if text_representation itself is a dict and has expected keys
                    tr = metadata['jupytext']['text_representation']
                    if isinstance(tr, dict) and 'extension' in tr and 'format_name' in tr:
                        return True
                return False
            except yaml.YAMLError:
                # print(f"Warning: Could not parse YAML header in '{file_path}'.")
                return False # Malformed YAML

    except Exception:
        # print(f"Error reading or processing file '{file_path}': {e}")
        return False

def is_jupyter_markdown(path: Path) -> bool:
    return has_jupytext_header_in_file(path)

def analyze_document_type(path: Path) -> DocumentType:
    extension = path.suffix.lstrip('.')
    if extension == "tex":
        return DocumentType.LaTeX
    if extension == "ipynb":
        return DocumentType.JupyterNotebook
    if extension == "md": # analyze if it is a jupyter or a usual markdown
        if is_jupyter_markdown(path):
            return DocumentType.JupyterNotebook
        return DocumentType.Markdown
    if extension == "typ":
        return DocumentType.Typst
    return DocumentType.Other

def get_config_dir_from_root(root_path: Path) -> Path:
    return root_path / CONF_DIR

def copy_tree_contents(
    src: Path,
    dst: Path,
    *,
    ignore: Iterable[Path] = (),
    follow_symlinks: bool = False,
) -> None:
    """
    Recursively copy the *contents* of *src* into *dst*, skipping anything listed
    in *ignore* (files **or** directories at any depth).

    Parameters
    ----------
    src : Path
        Directory whose contents will be copied.
    dst : Path
        Target directory. It is created if necessary.
    ignore : Iterable[Path], default ()
        Paths to exclude. Each entry may be absolute or relative to *src*.
        Ignoring a directory automatically excludes its whole sub-tree.
    follow_symlinks : bool, default False
        Whether to dereference symlinks.  If False, links themselves are copied.
    """
    src, dst = Path(src), Path(dst)

    if not src.is_dir():
        raise ValueError(f"{src!s} is not an existing directory")

    ignore_set: set[Path] = set()
    for p in ignore:
        if not p.exists():
            continue

        p_res = p.resolve()
        if not p_res.is_relative_to(src):
            continue
        ignore_set.add(p_res)

    def _skip(path: Path) -> bool:
        """Return True if *path* or any parent is to be ignored."""
        path = path.resolve()
        return any(parent in ignore_set for parent in (path, *path.parents))

    dst.mkdir(parents=True, exist_ok=True)

    for dirpath, dirnames, filenames in os.walk(src, followlinks=follow_symlinks):
        current_dir = Path(dirpath)

        if _skip(current_dir):
            dirnames[:] = []        
            continue

        rel_dir = current_dir.relative_to(src)
        target_dir = dst / rel_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        dirnames[:] = [d for d in dirnames if not _skip(current_dir / d)]

        for fname in filenames:
            src_file = current_dir / fname
            if _skip(src_file):
                continue
            shutil.copy2(
                src_file,
                target_dir / fname,
                follow_symlinks=follow_symlinks,
            )
