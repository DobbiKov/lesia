import xml.etree.ElementTree as ET

from lesia.enums import ChunkType
from lesia.xml_manipulator_mod.mod import chunk_to_xml_with_placeholders, typst_to_xml_mod
from lesia.xml_manipulator_mod.typst import (
    configure_typst_translatable_string_args_by_function,
    reset_typst_translatable_string_args_by_function,
)
from lesia.xml_manipulator_mod.xml import reconstruct_from_xml


TYPST_SAMPLE = """= Heading
== Subheading

Plain text paragraph with *bold* and _italic_.

Inline math: $E = m c^2$.

$ a + b = c $

```python
print("hi")
```

<intro> reference @intro.
#let x = 1
Inline code: `val`
// line comment
"""


def _get_text_content(root: ET.Element) -> str:
    return "".join(root.itertext())


def _get_non_placeholder_text(root: ET.Element) -> str:
    text_container = root.find("TEXT")
    if text_container is None:
        return ""

    parts: list[str] = []
    if text_container.text:
        parts.append(text_container.text)
    for element in text_container:
        if element.tail:
            parts.append(element.tail)
    return "".join(parts)


def test_typst_chunk_to_xml_produces_valid_xml():
    xml_output, placeholders = chunk_to_xml_with_placeholders(TYPST_SAMPLE, ChunkType.Typst)
    root = ET.fromstring(xml_output)

    assert root.tag == "document"
    assert root.findall(".//PH"), "Expected placeholder tags in Typst XML output"

    reconstructed = reconstruct_from_xml(xml_output, placeholders)
    assert "Plain text paragraph" in reconstructed


def test_typst_to_xml_preserves_text_segments():
    xml_output, placeholders, ph_only = typst_to_xml_mod(TYPST_SAMPLE)
    root = ET.fromstring(xml_output)
    text_content = _get_text_content(root)

    assert "Heading" in text_content
    assert "Subheading" in text_content
    assert "Plain text paragraph" in text_content
    assert placeholders
    assert ph_only is False


def test_typst_to_xml_placeholders_not_in_text():
    xml_output, _, _ = typst_to_xml_mod(TYPST_SAMPLE)
    root = ET.fromstring(xml_output)
    text_content = _get_non_placeholder_text(root)

    assert "$E = m c^2$" not in text_content
    assert "```python" not in text_content
    assert "@intro" not in text_content
    assert "<intro>" not in text_content
    assert "`val`" not in text_content


def test_typst_round_trip_plain_text():
    source = "Plain text paragraph.\n"
    xml_output, placeholders, _ = typst_to_xml_mod(source)
    reconstructed = reconstruct_from_xml(xml_output, placeholders)
    assert reconstructed == source


def test_typst_round_trip_bold_italic():
    source = "This is *bold* and _italic_.\n"
    xml_output, placeholders, _ = typst_to_xml_mod(source)
    reconstructed = reconstruct_from_xml(xml_output, placeholders)
    assert reconstructed == source


def test_typst_round_trip_heading():
    source = "= Heading\n"
    xml_output, placeholders, _ = typst_to_xml_mod(source)
    reconstructed = reconstruct_from_xml(xml_output, placeholders)
    assert reconstructed == source


def test_typst_round_trip_math():
    source = "$E = m c^2$\n"
    xml_output, placeholders, _ = typst_to_xml_mod(source)
    reconstructed = reconstruct_from_xml(xml_output, placeholders)
    assert reconstructed == source


def test_typst_round_trip_raw_block():
    source = "```python\nprint(\"hi\")\n```\n"
    xml_output, placeholders, _ = typst_to_xml_mod(source)
    reconstructed = reconstruct_from_xml(xml_output, placeholders)
    assert reconstructed == source


def test_typst_round_trip_label_ref():
    source = "<intro> @intro\n"
    xml_output, placeholders, _ = typst_to_xml_mod(source)
    reconstructed = reconstruct_from_xml(xml_output, placeholders)
    assert reconstructed == source


def test_typst_round_trip_full_sample():
    xml_output, placeholders, _ = typst_to_xml_mod(TYPST_SAMPLE)
    reconstructed = reconstruct_from_xml(xml_output, placeholders)
    assert reconstructed == TYPST_SAMPLE


def test_typst_ph_only_code_chunk():
    source = "#let x = 1\n"
    _, _, ph_only = typst_to_xml_mod(source)
    assert ph_only is True


def test_typst_ph_only_math_chunk():
    source = "$ a + b = c $\n"
    _, _, ph_only = typst_to_xml_mod(source)
    assert ph_only is True


def test_typst_command_with_content_block_translates_inner_text():
    source = '#figure(caption: [A small caption])[Body text]\n'
    xml_output, placeholders, ph_only = typst_to_xml_mod(source)
    root = ET.fromstring(xml_output)
    text_content = _get_non_placeholder_text(root)
    reconstructed = reconstruct_from_xml(xml_output, placeholders)

    assert "A small caption" in text_content
    assert "Body text" in text_content
    assert ph_only is False
    assert reconstructed == source


def test_typst_show_rule_with_content_block_translates_inner_text():
    source = "#show heading: it => [Section #it.body]\n"
    xml_output, placeholders, ph_only = typst_to_xml_mod(source)
    root = ET.fromstring(xml_output)
    text_content = _get_non_placeholder_text(root)
    reconstructed = reconstruct_from_xml(xml_output, placeholders)

    assert "Section" in text_content
    assert ph_only is False
    assert reconstructed == source


def test_typst_command_named_string_info_is_translatable():
    source = '#ex(info: "Familles de lois")[Body text]\n'
    xml_output, placeholders, ph_only = typst_to_xml_mod(source)
    root = ET.fromstring(xml_output)
    text_content = _get_non_placeholder_text(root)
    reconstructed = reconstruct_from_xml(xml_output, placeholders)

    assert "Familles de lois" in text_content
    assert "Body text" in text_content
    assert ph_only is False
    assert reconstructed == source


def test_typst_command_named_string_lang_stays_placeholder():
    source = '#set text(lang: "en")[Body text]\n'
    xml_output, placeholders, ph_only = typst_to_xml_mod(source)
    root = ET.fromstring(xml_output)
    text_content = _get_non_placeholder_text(root)
    reconstructed = reconstruct_from_xml(xml_output, placeholders)

    assert "Body text" in text_content
    assert "en" not in text_content
    assert ph_only is False
    assert reconstructed == source


def test_typst_configurable_function_string_args():
    source = '#custom(note: "Visible text")[Body]\n'
    try:
        configure_typst_translatable_string_args_by_function({"custom": ["note"]})
        xml_output, placeholders, ph_only = typst_to_xml_mod(source)
        root = ET.fromstring(xml_output)
        text_content = _get_non_placeholder_text(root)
        reconstructed = reconstruct_from_xml(xml_output, placeholders)

        assert "Visible text" in text_content
        assert "Body" in text_content
        assert ph_only is False
        assert reconstructed == source
    finally:
        reset_typst_translatable_string_args_by_function()


def test_typst_apostrophe_is_translatable_text():
    source = "l'estimateur\n"
    xml_output, placeholders, ph_only = typst_to_xml_mod(source)
    root = ET.fromstring(xml_output)
    text_content = _get_non_placeholder_text(root)
    reconstructed = reconstruct_from_xml(xml_output, placeholders)

    assert "l'estimateur" in text_content
    assert "'" not in "".join(placeholders.values())
    assert ph_only is False
    assert reconstructed == source


def test_typst_math_quoted_text_is_translatable():
    source = '$Ax = b " où " A " est une matrice "$\n'
    xml_output, placeholders, ph_only = typst_to_xml_mod(source)
    root = ET.fromstring(xml_output)
    text_content = _get_non_placeholder_text(root)
    reconstructed = reconstruct_from_xml(xml_output, placeholders)

    assert " où " in text_content
    assert " est une matrice " in text_content
    assert ph_only is False
    assert reconstructed == source


def test_typst_inline_math_keeps_surrounding_sentence_spacing_as_text():
    source = "Before $x + y$ after.\n"
    xml_output, placeholders, ph_only = typst_to_xml_mod(source)
    root = ET.fromstring(xml_output)
    text_content = _get_non_placeholder_text(root)
    reconstructed = reconstruct_from_xml(xml_output, placeholders)

    assert "Before " in text_content
    assert " after." in text_content
    assert "$x + y$" not in text_content
    assert "$x + y$" in "".join(placeholders.values())
    assert ph_only is False
    assert reconstructed == source
