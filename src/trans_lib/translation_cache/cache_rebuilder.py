from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from trans_lib.enums import DocumentType
from trans_lib.helpers import calculate_checksum

if TYPE_CHECKING:
    from typing import Dict, Iterable, Tuple


@dataclass
class RecoveredChunkPair:
    """Container for a recovered translation pair."""

    src_checksum: str
    src_text: str
    tgt_text: str


def collect_translation_pairs(
    source_path: Path,
    target_path: Path,
    doc_type: DocumentType,
) -> list[RecoveredChunkPair]:
    """Builds translation pairs for a file using on-disk metadata and contents."""
    if doc_type == DocumentType.Other:
        logger.warning(
            "Skipping {} – document type {} does not embed metadata, cannot rebuild chunks.",
            target_path,
            doc_type,
        )
        return []

    src_chunks = _build_source_chunk_map(source_path, doc_type)
    if not src_chunks:
        logger.warning("No chunks detected for {}, skipping rebuild.", source_path)
        return []

    recovered: list[RecoveredChunkPair] = []
    for checksum, tgt_text in _iter_target_chunks(target_path, doc_type):
        src_text = src_chunks.get(checksum)
        if src_text is None:
            logger.warning(
                "Target chunk in {} references missing checksum {}; source file may have changed.",
                target_path,
                checksum,
            )
            continue
        recovered.append(RecoveredChunkPair(src_checksum=checksum, src_text=src_text, tgt_text=tgt_text))
    return recovered


def _build_source_chunk_map(source_path: Path, doc_type: DocumentType) -> Dict[str, str]:
    builders: dict[DocumentType, callable[[Path], Dict[str, str]]] = {
        DocumentType.JupyterNotebook: _build_notebook_source_map,
        DocumentType.Markdown: _build_myst_source_map,
        DocumentType.LaTeX: _build_latex_source_map,
        DocumentType.Typst: _build_typst_source_map,
    }
    builder = builders.get(doc_type)
    if builder is None:
        return {}
    return builder(source_path)


def _build_notebook_source_map(source_path: Path) -> Dict[str, str]:
    import jupytext
    nb = jupytext.read(source_path)
    chunks: Dict[str, str] = {}
    for cell in nb.cells:
        src_txt = _extract_notebook_cell_source(cell)
        checksum = calculate_checksum(src_txt)
        chunks.setdefault(checksum, src_txt)
    return chunks


def _build_myst_source_map(source_path: Path) -> Dict[str, str]:
    from trans_lib.doc_translator_mod.myst_file_translator import get_myst_cells
    chunks: Dict[str, str] = {}
    for cell in get_myst_cells(source_path):
        src_txt = cell.get("source", "")
        checksum = calculate_checksum(src_txt)
        chunks.setdefault(checksum, src_txt)
    return chunks


def _build_latex_source_map(source_path: Path) -> Dict[str, str]:
    from trans_lib.doc_translator_mod.latex_file_translator import get_latex_cells
    chunks: Dict[str, str] = {}
    for cell in get_latex_cells(source_path):
        src_txt = cell.get("source", "")
        checksum = calculate_checksum(src_txt)
        chunks.setdefault(checksum, src_txt)
    return chunks


def _build_typst_source_map(source_path: Path) -> Dict[str, str]:
    from trans_lib.doc_translator_mod.typst_file_translator import get_typst_cells
    chunks: Dict[str, str] = {}
    for cell in get_typst_cells(source_path):
        src_txt = cell.get("source", "")
        checksum = calculate_checksum(src_txt)
        chunks.setdefault(checksum, src_txt)
    return chunks


def read_existing_target_metadata(
    target_path: Path,
    doc_type: DocumentType,
) -> Dict[str, dict]:
    """Returns a map of src_checksum -> metadata dict from an existing translated file.

    Used to preserve metadata (e.g. needs_review) from a prior translation run.
    Returns an empty dict if the file does not exist or the doc type is unsupported.
    """
    if not target_path.exists():
        return {}

    readers: dict[DocumentType, callable] = {
        DocumentType.JupyterNotebook: _read_notebook_target_metadata,
        DocumentType.Markdown: _read_myst_target_metadata,
        DocumentType.LaTeX: _read_latex_target_metadata,
        DocumentType.Typst: _read_typst_target_metadata,
    }
    reader = readers.get(doc_type)
    if reader is None:
        return {}
    try:
        return reader(target_path)
    except Exception:
        logger.warning("Could not read existing target metadata from {}", target_path)
        return {}


def _read_notebook_target_metadata(target_path: Path) -> Dict[str, dict]:
    import jupytext
    nb = jupytext.read(target_path)
    result: Dict[str, dict] = {}
    for cell in nb.cells:
        metadata = cell.get("metadata") or {}
        checksum = metadata.get("src_checksum")
        if checksum:
            result.setdefault(checksum, metadata)
    return result


def _read_myst_target_metadata(target_path: Path) -> Dict[str, dict]:
    from trans_lib.doc_translator_mod.myst_file_translator import read_chunks_with_metadata_from_myst
    result: Dict[str, dict] = {}
    for cell in read_chunks_with_metadata_from_myst(target_path):
        checksum = cell.get("src_checksum")
        if checksum:
            result.setdefault(checksum, cell)
    return result


def _read_latex_target_metadata(target_path: Path) -> Dict[str, dict]:
    from trans_lib.doc_translator_mod.latex_chunker import read_chunks_with_metadata_from_latex
    result: Dict[str, dict] = {}
    for cell in read_chunks_with_metadata_from_latex(target_path):
        checksum = cell.get("src_checksum")
        if checksum:
            result.setdefault(checksum, cell)
    return result


def _read_typst_target_metadata(target_path: Path) -> Dict[str, dict]:
    from trans_lib.doc_translator_mod.typst_chunker import read_chunks_with_metadata_from_typst
    result: Dict[str, dict] = {}
    for cell in read_chunks_with_metadata_from_typst(target_path):
        checksum = cell.get("src_checksum")
        if checksum:
            result.setdefault(checksum, cell)
    return result


def _iter_target_chunks(target_path: Path, doc_type: DocumentType) -> Iterable[Tuple[str, str]]:
    readers: dict[DocumentType, callable[[Path], Iterable[Tuple[str, str]]]] = {
        DocumentType.JupyterNotebook: _iter_notebook_target_chunks,
        DocumentType.Markdown: _iter_myst_target_chunks,
        DocumentType.LaTeX: _iter_latex_target_chunks,
        DocumentType.Typst: _iter_typst_target_chunks,
    }
    reader = readers.get(doc_type)
    if reader is None:
        return []
    return reader(target_path)


def _iter_notebook_target_chunks(target_path: Path) -> Iterable[Tuple[str, str]]:
    import jupytext
    nb = jupytext.read(target_path)
    for cell in nb.cells:
        metadata = cell.get("metadata") or {}
        checksum = metadata.get("src_checksum")
        if not checksum:
            continue
        yield checksum, _extract_notebook_cell_source(cell)


def _iter_myst_target_chunks(target_path: Path) -> Iterable[Tuple[str, str]]:
    from trans_lib.doc_translator_mod.myst_file_translator import read_chunks_with_metadata_from_myst
    for cell in read_chunks_with_metadata_from_myst(target_path):
        checksum = cell.get("src_checksum")
        if not checksum:
            continue
        yield checksum, cell.get("source", "")


def _iter_latex_target_chunks(target_path: Path) -> Iterable[Tuple[str, str]]:
    from trans_lib.doc_translator_mod.latex_chunker import read_chunks_with_metadata_from_latex
    for cell in read_chunks_with_metadata_from_latex(target_path):
        checksum = cell.get("src_checksum")
        if not checksum:
            continue
        yield checksum, cell.get("source", "")


def _iter_typst_target_chunks(target_path: Path) -> Iterable[Tuple[str, str]]:
    from trans_lib.doc_translator_mod.typst_chunker import read_chunks_with_metadata_from_typst
    for cell in read_chunks_with_metadata_from_typst(target_path):
        checksum = cell.get("src_checksum")
        if not checksum:
            continue
        yield checksum, cell.get("source", "")


def _extract_notebook_cell_source(cell: dict) -> str:
    src = cell.get("source", "")
    if isinstance(src, list):
        return "".join(str(part) for part in src)
    return str(src)
