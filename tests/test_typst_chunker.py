from lesia.doc_translator_mod.typst_chunker import split_typst_document_into_chunks


def test_inline_math_stays_in_single_context_chunk() -> None:
    source = "Before $x + y$ after.\n"

    chunks = split_typst_document_into_chunks(source)

    assert len(chunks) == 1
    assert chunks[0]["content"] == source


def test_inline_hash_func_call_stays_with_surrounding_text() -> None:
    source = "Read #link(\"https://example.com\")[this] now.\n"

    chunks = split_typst_document_into_chunks(source)

    assert len(chunks) == 1
    assert chunks[0]["content"] == source


def test_long_section_is_split_by_paragraph_groups_not_tiny_parser_fragments() -> None:
    para1 = ("alpha " * 120) + "before $x+y$ after.\n\n"
    para2 = ("beta " * 120) + "middle sentence.\n\n"
    para3 = ("gamma " * 120) + "ending sentence.\n"
    source = para1 + para2 + para3

    chunks = split_typst_document_into_chunks(source)

    assert len(chunks) == 2
    assert chunks[0]["content"] == para1 + para2
    assert chunks[1]["content"] == para3


def test_long_section_does_not_emit_standalone_inline_math_chunk() -> None:
    source = ("word " * 380) + "before $x+y$ after " + ("word " * 80) + "\n"

    chunks = split_typst_document_into_chunks(source)

    assert not any(chunk["content"] == "$x+y$" for chunk in chunks)


def test_long_section_does_not_split_hash_function_command_with_body() -> None:
    command = '#figure(caption: [A caption])[Body text]'
    source = ("w " * 990) + command + "\n" + ("tail " * 80)

    chunks = split_typst_document_into_chunks(source)

    assert len(chunks) >= 2
    assert any(command in chunk["content"] for chunk in chunks)


def test_long_section_does_not_split_show_rule_command() -> None:
    command = "#show heading: set text(fill: red)"
    source = ("w " * 990) + command + "\nHello world\n" + ("tail " * 80)

    chunks = split_typst_document_into_chunks(source)

    assert len(chunks) >= 2
    assert any(command in chunk["content"] for chunk in chunks)
