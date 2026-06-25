from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from typst_syntax import SyntaxKind, parse_source

MAX_INLINE_CHUNK_LENGTH = 600

_BLOCK_LEVEL_KINDS = {
    SyntaxKind.HEADING,
    SyntaxKind.RAW,
    SyntaxKind.CODE_BLOCK,
    SyntaxKind.SHOW_RULE,
    SyntaxKind.SET_RULE,
    SyntaxKind.LET_BINDING,
    SyntaxKind.MODULE_IMPORT,
    SyntaxKind.MODULE_INCLUDE,
}

_INLINE_ACCUMULATION_KINDS = {
    SyntaxKind.TEXT,
    SyntaxKind.STRONG,
    SyntaxKind.EMPH,
    SyntaxKind.SPACE,
    SyntaxKind.EQUATION,
    SyntaxKind.MATH,
    SyntaxKind.MATH_DELIMITED,
}

_HASH_PREFIXABLE_KINDS = {
    SyntaxKind.SHOW_RULE,
    SyntaxKind.SET_RULE,
    SyntaxKind.LET_BINDING,
    SyntaxKind.MODULE_IMPORT,
    SyntaxKind.MODULE_INCLUDE,
    SyntaxKind.CODE_BLOCK,
}


def _slice_bytes(source_text: str, start_byte: int, end_byte: int) -> str:
    """Return a UTF-8 slice from byte offsets produced by typst_syntax spans."""
    raw = source_text.encode("utf-8")[start_byte:end_byte]
    return raw.decode("utf-8")


def _node_range(source: Any, node: Any) -> tuple[int, int]:
    """Resolve `(start_byte, end_byte)` for a syntax node.

    typst_syntax may return `None` for invalid spans; in that case we fall back
    to `(0, 0)` and let downstream code skip empty content naturally.
    """
    result = source.range(node.span)
    if result is None:
        return 0, 0
    return result


def _simple_chunk(
    chunk_type: str,
    start_byte: int,
    end_byte: int,
    source_text: str,
) -> dict[str, Any]:
    """Build a lightweight chunk record from byte range and source text."""
    return {
        "type": chunk_type,
        "byte_range": (start_byte, end_byte),
        "content": _slice_bytes(source_text, start_byte, end_byte),
    }


def _typst_to_simple_chunks(source_text: str) -> list[dict[str, Any]]:
    """Convert Typst root children into syntax-aware atomic units.

    The output is intentionally low-level ("simple chunks"):
    - inline text-like nodes are accumulated into `INLINE` units,
    - block-level / hash-prefixed command constructs are emitted as standalone
      atomic units,
    - paragraph breaks flush the inline accumulator.

    These units are later repacked into final translation chunks while
    preserving syntax boundaries.
    """
    parsed = parse_source(source_text)
    root = parsed.root()
    root_children = list(root.children())

    chunks: list[dict[str, Any]] = []
    inline_start_byte: int | None = None
    inline_end_byte: int | None = None
    inline_content = ""

    def flush_inline_buffer() -> None:
        nonlocal inline_start_byte, inline_end_byte, inline_content
        if inline_start_byte is None or inline_end_byte is None:
            return
        if inline_content:
            chunks.append(
                {
                    "type": "INLINE",
                    "byte_range": (inline_start_byte, inline_end_byte),
                    "content": inline_content,
                }
            )
        inline_start_byte = None
        inline_end_byte = None
        inline_content = ""

    def append_inline(node: Any) -> None:
        nonlocal inline_start_byte, inline_end_byte, inline_content
        start_byte, end_byte = _node_range(parsed, node)
        piece = _slice_bytes(source_text, start_byte, end_byte)

        if inline_start_byte is None:
            inline_start_byte = start_byte
            inline_end_byte = end_byte
        else:
            inline_end_byte = end_byte

        inline_content += piece
        if len(inline_content) >= MAX_INLINE_CHUNK_LENGTH:
            flush_inline_buffer()

    idx = 0
    while idx < len(root_children):
        node = root_children[idx]
        kind = node.kind()

        if (
            kind == SyntaxKind.HASH
            and idx + 1 < len(root_children)
            and root_children[idx + 1].kind() == SyntaxKind.FUNC_CALL
        ):
            append_inline(node)
            append_inline(root_children[idx + 1])
            idx += 2
            continue

        if (
            kind == SyntaxKind.HASH
            and idx + 1 < len(root_children)
            and root_children[idx + 1].kind() in _HASH_PREFIXABLE_KINDS
        ):
            flush_inline_buffer()
            next_node = root_children[idx + 1]
            start_byte, _ = _node_range(parsed, node)
            _, end_byte = _node_range(parsed, next_node)
            chunks.append(
                _simple_chunk(
                    next_node.kind().name.upper().replace(" ", "_"),
                    start_byte,
                    end_byte,
                    source_text,
                )
            )
            idx += 2
            continue

        if kind in _BLOCK_LEVEL_KINDS:
            flush_inline_buffer()
            start_byte, end_byte = _node_range(parsed, node)
            chunks.append(
                _simple_chunk(
                    kind.name.upper().replace(" ", "_"),
                    start_byte,
                    end_byte,
                    source_text,
                )
            )
            idx += 1
            continue

        if kind in _INLINE_ACCUMULATION_KINDS:
            append_inline(node)
            idx += 1
            continue

        if kind == SyntaxKind.PARBREAK:
            append_inline(node)
            flush_inline_buffer()
            idx += 1
            continue

        flush_inline_buffer()
        start_byte, end_byte = _node_range(parsed, node)
        chunks.append(
            _simple_chunk(
                kind.name.upper().replace(" ", "_"),
                start_byte,
                end_byte,
                source_text,
            )
        )
        idx += 1

    flush_inline_buffer()
    return chunks


def _simple_chunks_to_section_chunks(simple_chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group simple chunks into section-like containers.

    A heading starts a new section. Each section stores:
    - `elems`: original simple chunk units,
    - `content`: concatenated text,
    - `byte_range`: span from first to last element.
    """
    current = {"elems": [], "content": "", "byte_range": None}
    chunks: list[dict[str, Any]] = []

    for simple_chunk in simple_chunks:
        if simple_chunk["type"] == "HEADING" and current["elems"]:
            chunks.append(current)
            current = {"elems": [], "content": "", "byte_range": None}

        current["elems"].append(simple_chunk)
        current["content"] += simple_chunk["content"]

        if current["byte_range"] is None:
            current["byte_range"] = simple_chunk["byte_range"]
        else:
            start_byte = current["byte_range"][0]
            end_byte = simple_chunk["byte_range"][1]
            current["byte_range"] = (start_byte, end_byte)

    if current["elems"]:
        chunks.append(current)

    return chunks


def _complete_section_chunks(
    section_chunks: list[dict[str, Any]],
    max_chars_num: int = 2000,
) -> list[dict[str, Any]]:
    """Pack sections into size-bounded chunks without breaking syntax units.

    `max_chars_num` is a soft limit:
    - chunks are packed by section `elems` boundaries,
    - each elem is atomic and never split in the middle,
    - if one elem exceeds the limit, it is emitted as an oversized chunk.

    This behavior prevents splitting command wrappers/bodies across chunks.
    """
    result: list[dict[str, Any]] = []

    def _chunk_from_elems(elems: list[dict[str, Any]]) -> dict[str, Any]:
        content = "".join(elem["content"] for elem in elems if elem.get("content"))
        if not elems:
            return {"type": "SECTION", "byte_range": (0, 0), "content": content}

        start_byte = elems[0]["byte_range"][0]
        end_byte = elems[-1]["byte_range"][1]
        first_type = elems[0]["type"]
        return {
            "type": first_type,
            "byte_range": (start_byte, end_byte),
            "content": content,
        }

    def _split_long_text(long_text: str) -> list[str]:
        if not long_text:
            return []
        if len(long_text) <= max_chars_num:
            return [long_text]

        # Prefer splitting near the size limit at natural boundaries.
        min_split = max(1, int(max_chars_num * 0.6))
        boundary = re.compile(r"\n\s*\n+|\n|(?<=\.)\s+|\s+")

        pieces: list[str] = []
        rest = long_text
        while len(rest) > max_chars_num:
            candidate = 0
            for match in boundary.finditer(rest[: max_chars_num + 1]):
                split_idx = match.end()
                if split_idx >= min_split:
                    candidate = split_idx
            if candidate == 0:
                candidate = max_chars_num
            pieces.append(rest[:candidate])
            rest = rest[candidate:]

        if rest:
            pieces.append(rest)

        return [piece for piece in pieces if piece]

    for section in section_chunks:
        section_content = section.get("content", "")
        section_elems = section.get("elems") or []

        if len(section_content) > max_chars_num and section_elems:
            current_elems: list[dict[str, Any]] = []
            current_len = 0

            for elem in section_elems:
                elem_content = elem.get("content", "")
                if not elem_content:
                    continue

                elem_len = len(elem_content)

                # Keep AST-derived units atomic even when they exceed the soft size limit.
                if elem_len > max_chars_num:
                    if current_elems:
                        result.append(_chunk_from_elems(current_elems))
                        current_elems = []
                        current_len = 0
                    result.append(_chunk_from_elems([elem]))
                    continue

                if current_elems and current_len + elem_len > max_chars_num:
                    result.append(_chunk_from_elems(current_elems))
                    current_elems = [elem]
                    current_len = elem_len
                    continue

                current_elems.append(elem)
                current_len += elem_len

            if current_elems:
                result.append(_chunk_from_elems(current_elems))
            continue

        if len(section_content) > max_chars_num:
            for piece in _split_long_text(section_content):
                result.append(
                    {
                        "type": section_elems[0]["type"] if section_elems else "SECTION",
                        "byte_range": section.get("byte_range"),
                        "content": piece,
                    }
                )
            continue

        first_type = section_elems[0]["type"] if section_elems else "SECTION"
        result.append(
            {
                "type": first_type,
                "byte_range": section.get("byte_range"),
                "content": section_content,
            }
        )

    return result


def split_typst_document_into_chunks(source: str) -> list[dict[str, Any]]:
    """Split a Typst document into translation chunks.

    Pipeline:
    1. parse Typst and build simple syntax-aware units,
    2. group units into sections (heading-aware),
    3. repack sections with a soft size limit while keeping AST units atomic.
    """
    simple_chunks = _typst_to_simple_chunks(source)
    section_chunks = _simple_chunks_to_section_chunks(simple_chunks)
    complete_chunks = _complete_section_chunks(section_chunks)

    return [
        {
            "id": f"auto_chunk_{index + 1}",
            "content": chunk["content"],
            "chunk_type": "content",
        }
        for index, chunk in enumerate(complete_chunks)
        if chunk["content"]
    ]


def _parse_metadata_block(block_str: str) -> dict[str, str]:
    """Parse `// key: value` metadata lines between Typst metadata sentinels."""
    metadata: dict[str, str] = {}
    for line in block_str.splitlines():
        stripped = line.strip()
        if not stripped.startswith("//"):
            continue
        stripped = stripped[2:].strip()
        if stripped.startswith("--- CHUNK_METADATA_START ---") or stripped.startswith(
            "--- CHUNK_METADATA_END ---"
        ):
            continue
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        metadata[key.strip()] = value.strip()
    return metadata


def read_chunks_with_metadata_from_typst(filepath: Path) -> list[dict]:
    """Read translated Typst file and recover chunk sources with metadata.

    The file format is:
    - metadata comment block,
    - chunk source,
    - metadata block,
    - next chunk source, ...

    Returns a list of dictionaries with `source` plus parsed metadata fields.
    """
    with open(filepath, "r", encoding="utf-8") as file:
        full_content = file.read()

    chunks_data: list[dict] = []
    metadata_pattern = re.compile(
        r"(?s)(// --- CHUNK_METADATA_START ---\n.*?\n// --- CHUNK_METADATA_END ---\n)"
    )

    parts = metadata_pattern.split(full_content)
    current_chunk_content = ""
    current_metadata: dict[str, str] = {}

    start_index = 0
    if not parts[0].strip() and len(parts) > 1:
        current_metadata = _parse_metadata_block(parts[1])
        start_index = 2

    for index in range(start_index, len(parts)):
        part = parts[index]
        if index % 2 == 1:
            if current_chunk_content.strip():
                chunks_data.append({"source": current_chunk_content.strip(), **current_metadata})
            current_metadata = _parse_metadata_block(part)
            current_chunk_content = ""
        else:
            current_chunk_content += part

    if current_chunk_content.strip():
        chunks_data.append({"source": current_chunk_content.strip(), **current_metadata})

    return chunks_data
