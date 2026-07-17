from typing import Any
from lesia.xml_manipulator_mod.myst import _parser

def _myst_to_simple_chunks(source_text: str) -> list[dict]:
    """
    Parses MyST/Markdown document into simple chunks
    """
    tokens = _parser.parse(source_text)
    chunks = []
    maps = []
    
    def token_in_maps(start_line: int, end_line: int) -> bool:
        for (m_s_l, m_n_l) in maps:
            if start_line >= m_s_l and end_line <= m_n_l:
                return True
        return False
    def complete_lines(lns: list[str]) -> str:
        res = ""
        for line in lns:
            res += line + "\n"
        return res
    
    for token in tokens:
        # Only look at block-level tokens
        if token.map:
            start_line, end_line = token.map
            if token_in_maps(start_line, end_line):
                continue

            
            chunks.append({
                "type": token.type,
                "lines": (start_line, end_line),
                "content": ""
            })
            maps.append(
                (start_line, end_line)
            )
    for i in range(len(chunks) - 1):
        chunk = chunks[i]
        next_chunk = chunks[i+1]
        (start_line, end_line) = chunk["lines"]
        (next_start_line, next_end_line) = next_chunk["lines"]
        if end_line >= next_start_line:
            source_chunk = complete_lines(source_text.splitlines()[start_line:end_line])
            chunks[i]["content"] = source_chunk
        else:
            offset = next_start_line - end_line
            source_chunk = complete_lines(source_text.splitlines()[start_line:end_line+offset])
            chunks[i]["content"] = source_chunk
    (start_line, end_line) = chunks[len(chunks)-1]["lines"]
    source_chunk = complete_lines(source_text.splitlines()[start_line:end_line])
    chunks[len(chunks)-1]["content"] = source_chunk
    
    return chunks

def _simple_chunks_to_section_chunks(simple_chunks: list[dict]):
    """
    Unifies simple chunks into chunks by sections

    A `myst_target` (e.g. `(label)=`) labels the section that follows it, so it
    is held back in `pending` until we know whether a heading comes next: if so
    it starts the new section instead of trailing the previous one.
    """
    curr = {"elems": [], "content": ""}
    chunks = []
    pending: list[dict] = []
    for s_chunk in simple_chunks:
        if s_chunk["type"] == "myst_target":
            pending.append(s_chunk)
            continue
        if s_chunk["type"] == "heading_open" and curr["elems"] != []:
            chunks.append(curr)
            curr = {"elems": [], "content": ""}
        for p_chunk in pending:
            curr["elems"].append(p_chunk)
            curr["content"] += p_chunk["content"]
        pending = []
        curr["elems"].append(s_chunk)
        curr["content"] += s_chunk["content"]
    for p_chunk in pending:
        curr["elems"].append(p_chunk)
        curr["content"] += p_chunk["content"]
    if curr["elems"] != []:
        chunks.append(curr)
    return chunks

def _complete_section_chunks(sec_chunks: list[dict], max_chars_num: int = 2000) -> list[dict[str, Any]]:
    """
    Analyzes section chunks and divides it into simple ones if the number of characters excees `max_chars_num`, and leave it as is if it doesn't exceed.
    """
    res = []
    for chunk in sec_chunks:
        if len(chunk["content"]) > max_chars_num:
            res = res + chunk["elems"]
        else:
            start_line = chunk["elems"][0]["lines"][0]
            end_line = chunk["elems"][len(chunk["elems"]) - 1]["lines"][1]
            res.append(
                {
                    "type": "section",
                    "lines": (start_line, end_line),
                    "content": chunk["content"]
                }
            )
    return res

def split_myst_document_into_chunks(source_text: str) -> list[dict[str, Any]]:
    """
    Splits given MyST/Markdown document text into chunks
    """
    return _complete_section_chunks(_simple_chunks_to_section_chunks(_myst_to_simple_chunks(source_text)))

