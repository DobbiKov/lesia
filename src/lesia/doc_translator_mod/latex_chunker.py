import re
from pylatexenc.latexwalker import LatexWalker, LatexMacroNode, LatexEnvironmentNode
from typing import Any, Optional
from pathlib import Path

# Macros that should still become standalone chunks even though they have arguments
BLOCK_LEVEL_MACROS_WITH_ARGS = {
    "section",
    "subsection",
    "subsubsection",
    "chapter",
    "part",
    "paragraph",
    "subparagraph",
    "title",
    "maketitle",
}

# Upper bound for inline chunks so paragraphs with inline macros stay together but do not grow without limit
MAX_INLINE_CHUNK_LENGTH = 600


def _get_node_full_span(node: Any, original_latex_string: str) -> tuple[int, int]:
    """Calculates full character span (start_pos, end_pos) of a LaTeX node."""
    start_pos = node.pos
    end_pos = node.pos + node.len

    if isinstance(node, LatexMacroNode):
        if node.nodeargd is not None and node.nodeargd.argnlist:
            last_arg_node = node.nodeargd.argnlist[-1]
            if last_arg_node is not None:
                end_pos = last_arg_node.pos + last_arg_node.len

    end_pos = min(end_pos, len(original_latex_string))
    return start_pos, end_pos


def _chunk_nodelist(
    nodelist: list[Any],
    original_latex_string: str,
    base_start_offset: int,
    end_offset_limit: int,
) -> list[str]:
    """Chunks a pylatexenc nodelist while keeping inline macros within paragraphs."""
    chunks_raw: list[str] = []
    current_chunk_start_pos = base_start_offset

    between_nodes: list[str] = []
    between_nodes_length = 0

    def flush_between_nodes() -> None:
        nonlocal between_nodes_length
        if not between_nodes:
            return
        combined = "".join(between_nodes).strip()
        if combined:
            chunks_raw.append(combined)
        between_nodes.clear()
        between_nodes_length = 0

    def append_to_between_nodes(segment: str) -> None:
        nonlocal between_nodes_length
        if not segment:
            return
        between_nodes.append(segment)
        between_nodes_length += len(segment)
        if between_nodes_length >= MAX_INLINE_CHUNK_LENGTH:
            flush_between_nodes()

    i = 0
    while i < len(nodelist):
        node = nodelist[i]
        node_full_span_start, node_full_span_end = _get_node_full_span(node, original_latex_string)

        if node_full_span_start >= end_offset_limit:
            break

        if node_full_span_start > current_chunk_start_pos:
            raw_text_before = original_latex_string[current_chunk_start_pos:node_full_span_start]
            paragraphs = re.split(r"\n\s*\n+", raw_text_before)
            for idx, para in enumerate(paragraphs):
                if not para.strip():
                    continue
                append_to_between_nodes(para)
                if len(paragraphs) > 1 and idx < len(paragraphs) - 1:
                    flush_between_nodes()
            if re.search(r"\n\s*\n+$", raw_text_before):
                flush_between_nodes()

        current_chunk_start_pos = node_full_span_start

        if isinstance(node, LatexEnvironmentNode):
            flush_between_nodes()
            chunk_content = original_latex_string[node_full_span_start:node_full_span_end].strip()
            if chunk_content:
                chunks_raw.append(chunk_content)
            current_chunk_start_pos = node_full_span_end
            i += 1
            continue

        if isinstance(node, LatexMacroNode):
            chunk_content = original_latex_string[node_full_span_start:node_full_span_end]
            macro_name = getattr(node, "macroname", None)
            if (
                macro_name
                and node.nodeargd is not None
                and node.nodeargd.argnlist
                and macro_name in BLOCK_LEVEL_MACROS_WITH_ARGS
            ):
                flush_between_nodes()
                chunk_stripped = chunk_content.strip()
                if chunk_stripped:
                    chunks_raw.append(chunk_stripped)
            else:
                append_to_between_nodes(chunk_content)
            current_chunk_start_pos = node_full_span_end
            i += 1
            continue

        chunk_content = original_latex_string[node_full_span_start:node_full_span_end]
        if chunk_content:
            append_to_between_nodes(chunk_content)
        current_chunk_start_pos = node_full_span_end
        i += 1

    if current_chunk_start_pos < end_offset_limit:
        trailing = original_latex_string[current_chunk_start_pos:end_offset_limit]
        if trailing.strip():
            append_to_between_nodes(trailing)

    flush_between_nodes()
    return chunks_raw


def split_latex_document_into_chunks(latex_document_string: str) -> list[dict[str, Any]]:
    """Split LaTeX document into structured chunks with preamble/body separation."""
    lw = LatexWalker(latex_document_string)
    full_nodelist, _, _ = lw.get_latex_nodes()

    all_chunks: list[dict[str, Any]] = []
    document_env_node: Optional[LatexEnvironmentNode] = None

    for node in full_nodelist:
        if isinstance(node, LatexEnvironmentNode) and node.environmentname == "document":
            document_env_node = node
            break

    if document_env_node is not None:
        BEGIN_DOC_MACRO_LEN = len(r"\begin{document}")
        END_DOC_MACRO_LEN = len(r"\end{document}")

        preamble_end_pos = document_env_node.pos
        preamble_content = latex_document_string[:preamble_end_pos].strip()
        if preamble_content:
            all_chunks.append({
                "id": "preamble_001",
                "content": preamble_content,
                "chunk_type": "preamble",
            })

        if document_env_node.pos is None:
            document_env_node.pos = 0
        if document_env_node.len is None:
            document_env_node.len = 0

        begin_doc_raw = latex_document_string[
            document_env_node.pos : document_env_node.pos + BEGIN_DOC_MACRO_LEN
        ].strip()
        if begin_doc_raw:
            all_chunks.append({
                "id": "begin_document_macro",
                "content": begin_doc_raw,
                "chunk_type": "macro_declaration",
            })

        doc_body_start_pos = document_env_node.pos + BEGIN_DOC_MACRO_LEN
        doc_body_end_pos = (document_env_node.pos + document_env_node.len) - END_DOC_MACRO_LEN

        if document_env_node.nodelist:
            doc_body_chunks = _chunk_nodelist(
                document_env_node.nodelist,
                latex_document_string,
                base_start_offset=doc_body_start_pos,
                end_offset_limit=doc_body_end_pos,
            )
            for chunk_content in doc_body_chunks:
                all_chunks.append(
                    {
                        "id": f"doc_body_{len(all_chunks)}",
                        "content": chunk_content,
                        "chunk_type": "content",
                    }
                )

        end_doc_raw = latex_document_string[
            doc_body_end_pos : doc_body_end_pos + END_DOC_MACRO_LEN
        ].strip()
        if end_doc_raw:
            all_chunks.append({
                "id": "end_document_macro",
                "content": end_doc_raw,
                "chunk_type": "macro_declaration",
            })
    else:
        doc_chunks = _chunk_nodelist(
            full_nodelist,
            latex_document_string,
            base_start_offset=0,
            end_offset_limit=len(latex_document_string),
        )
        for chunk_content in doc_chunks:
            all_chunks.append(
                {
                    "id": f"auto_chunk_{len(all_chunks)}",
                    "content": chunk_content,
                    "chunk_type": "content",
                }
            )

    for i, chunk in enumerate(all_chunks):
        if not chunk.get("id"):
            chunk["id"] = f"auto_chunk_{i + 1}"

    return all_chunks


def _parse_metadata_block(block_str: str) -> dict[str, str]:
    """Parse a LaTeX comment metadata block into a dictionary."""
    metadata: dict[str, str] = {}
    for line in block_str.splitlines():
        line = line.strip()
        if line.startswith("%"):
            line = line[1:].strip()
            if line.startswith("--- CHUNK_METADATA_START ---") or line.startswith(
                "--- CHUNK_METADATA_END ---"
            ):
                continue
            if ":" in line:
                key, value = line.split(":", 1)
                metadata[key.strip()] = value.strip()
    return metadata


def read_chunks_with_metadata_from_latex(filepath: Path) -> list[dict]:
    """Read a LaTeX file containing metadata comment blocks and return chunks."""
    with open(filepath, "r", encoding="utf-8") as f:
        full_content = f.read()

    chunks_data: list[dict] = []
    metadata_pattern = re.compile(
        r"(?s)(% --- CHUNK_METADATA_START ---\n.*?\n% --- CHUNK_METADATA_END ---\n)"
    )

    parts = metadata_pattern.split(full_content)
    current_chunk_content = ""
    current_metadata: dict[str, str] = {}

    start_index = 0
    if not parts[0].strip() and len(parts) > 1:
        current_metadata = _parse_metadata_block(parts[1])
        start_index = 2

    for i in range(start_index, len(parts)):
        part = parts[i]
        if i % 2 == 1:
            if current_chunk_content.strip():
                chunks_data.append({"source": current_chunk_content.strip(), **current_metadata})
            current_metadata = _parse_metadata_block(part)
            current_chunk_content = ""
        else:
            current_chunk_content += part

    if current_chunk_content.strip():
        chunks_data.append({"source": current_chunk_content.strip(), **current_metadata})

    return chunks_data
