import xml.etree.ElementTree as ET

import pytest

from lesia.enums import ChunkType
from lesia.errors import PlaceholderVerificationError
from lesia.translator_retrieval import PromptContext, _xml_postprocess
from lesia.xml_manipulator_mod.mod import chunk_to_xml_with_placeholders, latex_to_xml, myst_to_xml
from lesia.xml_manipulator_mod.xml import reconstruct_from_xml, verify_placeholders


LATEX_SAMPLE = r"""\section*{Introduction}
Here is an inline equation $E=mc^2$ and a labeled reference \ref{eq:energy}.

\begin{align}
  a &= b + c \\
  d &= e + f \text{Hello there}
\end{align}

We also include a verbatim example: \verb|printf(\"hi\")|.

\begin{equation}\label{eq:energy}
  \int_0^\infty e^{-x} dx = 1
\end{equation}
"""


MYST_SAMPLE = """
# Sample MyST Document

:::{admonition} Note
Stay hydrated.
:::

```{code-cell} python3
print(\"Hello world\")
```

Some inline math: $E = mc^2$.

```{math}
a^2 + b^2 = c^2
```

A definition using MyST roles: {term}`energy`.


Wait:
- [Jupyter: mode édition versus mode commande <status>](jupyter/mode-edition-vs-commande.md)
- [Valeurs et types <status>](premiers-calculs/01-valeurs-types.md)
- [Fonctions mathématiques <status>](premiers-calculs/02-fonctions-maths.md)
- [Variables <status>](premiers-calculs/03-variables.md)
- [Premières fonctions <status>](fonctions/00-initiation-fonctions.md)
"""


def _get_text_content(root: ET.Element) -> str:
    """Return the concatenated textual content of the XML tree."""
    return "".join(root.itertext())


def test_latex_chunk_to_xml_produces_valid_xml():
    xml_output, placeholders = chunk_to_xml_with_placeholders(LATEX_SAMPLE, ChunkType.LaTeX)
    print(xml_output)
    root = ET.fromstring(xml_output)

    assert root.tag == "document"
    assert root.findall(".//PH"), "Expected placeholder tags in LaTeX XML output"

    reconstructed = reconstruct_from_xml(xml_output, placeholders)
    print("====][]")
    print(reconstructed)
    assert "Introduction" in reconstructed


def test_latex_to_xml_preserves_text_segments_and_placeholders():
    xml_output, placeholders, ph_only = latex_to_xml(LATEX_SAMPLE)
    root = ET.fromstring(xml_output)

    text_content = _get_text_content(root)

    assert "Introduction" in text_content
    assert placeholders, "Expected placeholder mapping for LaTeX XML"
    assert ph_only is False

    reconstructed = reconstruct_from_xml(xml_output, placeholders)
    assert "\\begin{align}" in reconstructed


def test_myst_chunk_to_xml_produces_valid_xml():
    xml_output, placeholders = chunk_to_xml_with_placeholders(MYST_SAMPLE, ChunkType.Myst)
    print("---myst")
    print(xml_output)
    root = ET.fromstring(xml_output)

    assert root.tag == "document"
    assert root.findall(".//PH"), "Expected placeholder tags in MyST XML output"

    reconstructed = reconstruct_from_xml(xml_output, placeholders)
    print("===[]")
    print(reconstructed)
    assert "Stay hydrated." in reconstructed


def test_myst_to_xml_preserves_text_segments_and_placeholders():
    xml_output, placeholders, ph_only = myst_to_xml(MYST_SAMPLE)
    root = ET.fromstring(xml_output)

    text_content = _get_text_content(root)

    assert "Sample MyST Document" in text_content
    assert placeholders, "Expected placeholder mapping for MyST XML"
    assert ph_only is False

    reconstructed = reconstruct_from_xml(xml_output, placeholders)
    assert "print(\"Hello world\")" in reconstructed


def test_myst_list_item_preserves_continuation_lines():
    source = "- hey\n  hey\n  hey\n"
    xml_output, placeholders, _ = myst_to_xml(source)
    reconstructed = reconstruct_from_xml(xml_output, placeholders)

    assert "- hey\n  hey\n  hey" in reconstructed
    assert reconstructed.count("\n  hey") == 2


def test_myst_inline_link_round_trip_preserves_markup():
    source = "Paragraph with [example](https://example.com) link.\n\nSecond paragraph.\n"
    xml_output, placeholders, _ = myst_to_xml(source)
    reconstructed = reconstruct_from_xml(xml_output, placeholders).rstrip()

    lines = reconstructed.splitlines()

    assert lines[0] == "Paragraph with [example](https://example.com) link."
    assert lines[1] == ""
    assert lines[2] == "Second paragraph."


def test_myst_admonition_with_list_round_trip():
    source = ":::{admonition} Tip\n- item\n  detail\n:::\n"
    xml_output, placeholders, _ = myst_to_xml(source)
    reconstructed = reconstruct_from_xml(xml_output, placeholders).rstrip()

    lines = reconstructed.splitlines()

    assert lines[0] == ":::{admonition} Tip"
    assert "- item" in lines[1]
    assert lines[2] == "  detail"
    assert lines[-1] == ":::"


@pytest.mark.parametrize(
    "fields",
    [
        [(':class:', 'very important'), (':name:', 'tip-field'), (':width:', '60%')],
        [(':caption:', 'Danger zone'), (':height:', '120px')],
    ],
)
def test_myst_admonition_field_list_preserves_space_between_name_and_value(fields):
    field_lines = "\n".join(f"{name} {value}" for name, value in fields)
    source = ":::{admonition} Tip\n" + field_lines + "\nBody\n:::\n"

    xml_output, placeholders, _ = myst_to_xml(source)
    field_placeholder = next(value for value in placeholders.values() if fields[0][0] in value)

    for name, value in fields:
        expected_line = f"{name} {value}"
        assert expected_line in field_placeholder

    reconstructed_lines = reconstruct_from_xml(xml_output, placeholders).splitlines()
    for name, value in fields:
        assert f"{name} {value}" in reconstructed_lines


def test_myst_nested_lists_preserve_indentation():
    source = "- outer\n  1. inner\n     - detail\n       line\n"
    xml_output, placeholders, _ = myst_to_xml(source)
    reconstructed = reconstruct_from_xml(xml_output, placeholders).rstrip()

    lines = reconstructed.splitlines()

    assert lines[0] == "- outer"
    assert lines[1] == "  1. inner"
    assert lines[2] == "     - detail"
    assert lines[3] == "       line"


def test_myst_course_outline_round_trip_preserves_structure():
    source = """1. Chaque feuille ci-dessous correspond à un défi. Ouvrez-les tour à tour dans l'ordre et\n   suivez les instructions incluses. Vous pouvez cocher les cases ci-dessous au fur et à\n   mesure que vous finissez les feuilles. Si vous bloquez sur l'un des défis, n'hésitez\n   pas à passer à la suite et y revenir ultérieurement.\n\n   % Déposez votre travail après chaque fiche.\n\n   - [Prise en main de Laby <status>](premiers-pas/01-prise-en-main-laby.md)\n   - [À vous de jouer <status>](premiers-pas/10-premier-exo.md)\n   - [Un caillou dans la chaussure <status>](premiers-pas/11-un-caillou.md)\n   - [Encore un caillou! <status>](premiers-pas/12-encore-un-caillou.md)\n   - [Le débogueur <status>](premiers-pas/13-pas-%C3%A0-pas.md)\n\n   Répéter :\n\n   % boucles while\n\n   - [Que c'est loin! <status>](premiers-pas/20-on-regarde-devant-soi.md)\n   - [Le couloir des cailloux <status>](premiers-pas/21-beaucoup-de-cailloux.md)\n\n   % et petites fonctions\n\n   - [En zigzag <status>](premiers-pas/22-en-zigzag.md)\n   - [La spirale infernale <status>](premiers-pas/23-la-spirale.md)\n\n   %- ♣ [Encore un zigzag <status>](premiers-pas/24-encore-un-zigzag.md)\n\n   S'adapter :\n\n   % conditionnelles\n\n   - [Ahhh des toiles! <status>](premiers-pas/30-si-si-si.md)\n\n   %- [Le caillou et la toile <status>](premiers-pas/31-le-caillou-et-la-toile.md)\n\n   Compter :\n\n   % boucles for et variables\n\n   - [Tu répéteras trois fois <status>](boucles/02-boucles-for-introduction-laby.md)\n   - [Variables <status>](premiers-pas/41-variables.md)\n   - [Compter les cailloux <status>](premiers-pas/42-compter.md)\n"""
    xml_output, placeholders, _ = myst_to_xml(source)
    reconstructed = reconstruct_from_xml(xml_output, placeholders).rstrip()
    normalized = (reconstructed
                  .replace('\u00a0', ' ')
                  .replace('’', "'")
                  )

    lines = normalized.splitlines()

    assert lines[0].startswith("1. Chaque feuille ci-dessous correspond à un défi")
    assert any("Déposez votre travail" in line for line in lines)

    bullet_lines = [line for line in lines if line.startswith("   - [")]
    assert len(bullet_lines) == 13, "Expected all nested bullet links to survive"

    assert "% boucles while" in normalized
    assert "% boucles for et variables" in normalized
    assert "%- ♣ [Encore un zigzag <status>](premiers-pas/24-encore-un-zigzag.md)" in normalized
    assert "%- [Le caillou et la toile <status>](premiers-pas/31-le-caillou-et-la-toile.md)" in normalized
    assert "S'adapter :" in normalized
    assert "Compter :" in normalized


def test_myst_numbered_item_with_continuation_lines():
    source = "2. just test\n  haha\n"
    xml_output, placeholders, _ = myst_to_xml(source)
    reconstructed = reconstruct_from_xml(xml_output, placeholders).rstrip()

    assert reconstructed.splitlines() == ["2. just test", "   haha"]


def test_myst_renater_admonition_round_trip():
    """
    Full round-trip for the Renater admonition block.

    Known encoding differences vs. the original source:
    - A plain code fence inside a nested directive body loses the outer 2-space
      directive indent (markdown-it strips the body before we see the token), so
      5-space becomes 3-space.
    Everything else — structure, blank lines, text, HTML inline, links, fields,
    ordered/bullet list indentation — is preserved verbatim.
    """
    source = (
        ":::::{admonition} Hors Fédération Renater Éducation Recherche\n"
        ":class: dropdown\n"
        "\n"
        "- Vous pouvez travailler sur le matériel pédagogique <a\n"
        '  href="https://nicolas.thiery.name/Enseignement/intro-prog-en/lite/lab/?path=index.ipynb"\n'
        '  target="_blank">en ligne avec JupyterLite</a>.\\\n'
        "  Limitation: votre travail sera sauvegardé dans votre navigateur web. Si vous changez\n"
        "  d'ordinateur ou de navigateur web, vous ne le retrouverez pas. L'adresse du site\n"
        "  ci-dessus est temporaire.\n"
        "\n"
        "- Alternativement, vous pouvez télécharger la version 2026-01 du matériel pédagogique depuis\n"
        "  [ici](https://gitlab.dsi.universite-paris-saclay.fr/IntroductionProgrammationPython/2026-01)\n"
        "  (Code -> Télécharger le code source -> zip). Vous aurez aussi besoin d'installer un\n"
        "  certain nombre de logiciels (jupyterlab, jupylates, Laby).\n"
        "\n"
        "  ::::{admonition} Instructions d'installation avec `uv`\n"
        "  :class: dropdown tip\n"
        "\n"
        "  1. Si vous ne l'avez pas déjà, installez le gestionnaire d'environnements\n"
        "     [uv](https://docs.astral.sh/uv/getting-started/installation/).\n"
        "\n"
        "  2. Allez dans le dossier contenant le matériel pédagogique et lancez JupyterLab. Les\n"
        "     logiciels requis seront automatiquement installés dans ce dossier.\n"
        "\n"
        "     ```\n"
        "     uv run jupyter lab index.md\n"
        "     ```\n"
        "  ::::\n"
        ":::::\n"
    )
    # Expected output after round-trip (with known encoding differences documented above).
    expected = (
        ":::::{admonition} Hors Fédération Renater Éducation Recherche\n"
        ":class: dropdown\n"
        "\n"
        "- Vous pouvez travailler sur le matériel pédagogique <a\n"
        '  href="https://nicolas.thiery.name/Enseignement/intro-prog-en/lite/lab/?path=index.ipynb"\n'
        '  target="_blank">en ligne avec JupyterLite</a>.\\\n'
        "  Limitation: votre travail sera sauvegardé dans votre navigateur web. Si vous changez\n"
        "  d'ordinateur ou de navigateur web, vous ne le retrouverez pas. L'adresse du site\n"
        "  ci-dessus est temporaire.\n"
        "\n"
        "- Alternativement, vous pouvez télécharger la version 2026-01 du matériel pédagogique depuis\n"
        "  [ici](https://gitlab.dsi.universite-paris-saclay.fr/IntroductionProgrammationPython/2026-01)\n"
        "  (Code -> Télécharger le code source -> zip). Vous aurez aussi besoin d'installer un\n"
        "  certain nombre de logiciels (jupyterlab, jupylates, Laby).\n"
        "\n"
        "  ::::{admonition} Instructions d'installation avec `uv`\n"
        "  :class: dropdown tip\n"
        "\n"
        # ordered list items: 2-space indent preserved from source
        "  1. Si vous ne l'avez pas déjà, installez le gestionnaire d'environnements\n"
        "     [uv](https://docs.astral.sh/uv/getting-started/installation/).\n"
        "\n"
        "  2. Allez dans le dossier contenant le matériel pédagogique et lancez JupyterLab. Les\n"
        "     logiciels requis seront automatiquement installés dans ce dossier.\n"
        "\n"
        # code fence: 5-space (2 directive + 3 list continuation) → 3-space (directive prefix stripped)
        "   ```\n"
        "   uv run jupyter lab index.md\n"
        "   ```\n"
        "  ::::\n"
        ":::::\n"
    )

    xml_output, placeholders, _ = myst_to_xml(source)
    reconstructed = reconstruct_from_xml(xml_output, placeholders)
    assert reconstructed == expected


def test_myst_nested_admonition_inside_list_item_preserves_indentation():
    source = (
        ":::::{admonition} Hors Fédération Renater Éducation Recherche\n"
        ":class: dropdown\n"
        "\n"
        "- Vous pouvez travailler sur le matériel pédagogique <a\n"
        '  href="https://nicolas.thiery.name/Enseignement/intro-prog-en/lite/lab/?path=index.ipynb"\n'
        '  target="_blank">en ligne avec JupyterLite</a>.\\\n'
        "  Limitation: votre travail sera sauvegardé dans votre navigateur web. Si vous changez\n"
        "  d'ordinateur ou de navigateur web, vous ne le retrouverez pas. L'adresse du site\n"
        "  ci-dessus est temporaire.\n"
        "\n"
        "- Alternativement, vous pouvez télécharger la version 2026-01 du matériel pédagogique depuis\n"
        "  [ici](https://gitlab.dsi.universite-paris-saclay.fr/IntroductionProgrammationPython/2026-01)\n"
        "  (Code -> Télécharger le code source -> zip). Vous aurez aussi besoin d'installer un\n"
        "  certain nombre de logiciels (jupyterlab, jupylates, Laby).\n"
        "\n"
        "  ::::{admonition} Instructions d'installation avec `uv`\n"
        "  :class: dropdown tip\n"
        "\n"
        "  1. Si vous ne l'avez pas déjà, installez le gestionnaire d'environnements\n"
        "     [uv](https://docs.astral.sh/uv/getting-started/installation/).\n"
        "\n"
        "  2. Allez dans le dossier contenant le matériel pédagogique et lancez JupyterLab. Les\n"
        "     logiciels requis seront automatiquement installés dans ce dossier.\n"
        "\n"
        "     ```\n"
        "     uv run jupyter lab index.md\n"
        "     ```\n"
        "  ::::\n"
        ":::::\n"
    )
    xml_output, placeholders, _ = myst_to_xml(source)
    reconstructed = reconstruct_from_xml(xml_output, placeholders)
    lines = reconstructed.splitlines()

    # Outer admonition structure
    assert lines[0] == ":::::{admonition} Hors Fédération Renater Éducation Recherche"
    assert lines[-1] == ":::::"

    # Outer bullet list items (level 0 — no tab)
    bullet_lines = [line for line in lines if line.startswith("- ")]
    assert len(bullet_lines) == 2

    # Inner admonition is indented (inside bullet item)
    assert any("::::{admonition}" in line for line in lines)
    assert any(line.startswith("  ::::") for line in lines)

    # Ordered list items inside the nested admonition preserve source 2-space indent
    assert any(line.startswith("  1.") for line in lines)
    assert any(line.startswith("  2.") for line in lines)

    # Code fence content is preserved
    assert "uv run jupyter lab index.md" in reconstructed

    # Text content survives the round-trip
    assert "Hors Fédération Renater Éducation Recherche" in reconstructed
    assert "Instructions d'installation" in reconstructed


def test_header_with_inline_code():
    src = r'''# Les boucles `while`
'''
    xml_output, placeholders, _ = myst_to_xml(src)
    reconstructed = reconstruct_from_xml(xml_output, placeholders)

    assert src == reconstructed

@pytest.mark.parametrize(
  "source",
  [
      "```{math}\na^2 + b^2 = c^2\n```\n",
      "```{amsmath}\n\\begin{align}\nE &= mc^2 \\\\\nF &= ma\n\\end{align}\n```\n",
      "```{eval-rst}\n.. note:: Hello\n\n   Body text that must survive.\n```\n",
  ],
)
def test_myst_directive_fence_bodies_round_trip(source):
  xml_output, placeholders, _ = myst_to_xml(source)
  reconstructed = reconstruct_from_xml(xml_output, placeholders)

  assert reconstructed == source


@pytest.mark.parametrize("source", [
    # versionadded — version number and description must not be translated
    pytest.param(
        "```{versionadded} 2.0\nAdded support for foo.\n```\n",
        id="versionadded",
    ),
    # versionchanged
    pytest.param(
        "```{versionchanged} 1.5\nChanged the behaviour of bar.\n```\n",
        id="versionchanged",
    ),
    # deprecated
    pytest.param(
        "```{deprecated} 3.0\nUse baz() instead.\n```\n",
        id="deprecated",
    ),
    # toctree — file paths must not be translated
    pytest.param(
        "```{toctree}\n:maxdepth: 2\n\nchapter1\nchapter2\n```\n",
        id="toctree",
    ),
    # toctree with titled entries
    pytest.param(
        "```{toctree}\nMy Chapter <chapter1>\nOther <chapter2>\n```\n",
        id="toctree_titled_entries",
    ),
    # tab-set — body is structural, not plain MyST prose
    pytest.param(
        "```{tab-set}\nsome content\n```\n",
        id="tab_set",
    ),
    # table directive
    pytest.param(
        "```{table} My Table\n| A | B |\n|---|---|\n| 1 | 2 |\n```\n",
        id="table",
    ),
    # todo / TODO
    pytest.param(
        "```{todo}\nFix this later.\n```\n",
        id="todo",
    ),
    pytest.param(
        "```{TODO}\nFix this later.\n```\n",
        id="TODO",
    ),
])
def test_myst_opaque_directive_round_trip(source):
    """Opaque directives must be preserved verbatim — nothing dropped, nothing translated."""
    xml_output, placeholders, _ = myst_to_xml(source)
    reconstructed = reconstruct_from_xml(xml_output, placeholders)
    assert reconstructed == source


@pytest.mark.parametrize("source,hidden_texts", [
    # versionadded body text must not reach the translator
    pytest.param(
        "```{versionadded} 2.0\nAdded support for foo.\n```\n",
        ["Added support for foo", "2.0"],
        id="versionadded_body_is_placeholder",
    ),
    # toctree file paths must not reach the translator
    pytest.param(
        "```{toctree}\nchapter1\nchapter2\n```\n",
        ["chapter1", "chapter2"],
        id="toctree_paths_are_placeholder",
    ),
    # toctree titled entries: neither title nor path should reach translator
    pytest.param(
        "```{toctree}\nMy Chapter <chapter1>\n```\n",
        ["My Chapter", "chapter1"],
        id="toctree_titled_entry_is_placeholder",
    ),
])
def test_myst_opaque_directive_body_not_translated(source, hidden_texts):
    """Body content of opaque directives must not appear as translator-visible text."""
    xml_output, placeholders, _ = myst_to_xml(source)
    root = ET.fromstring(xml_output)
    text_el = root.find("TEXT")
    # Collect only what the translator sees: TEXT.text and each PH's tail
    translator_text = (text_el.text or "") + "".join(
        (ph.tail or "") for ph in text_el
    )
    for text in hidden_texts:
        assert text not in translator_text


@pytest.mark.parametrize(
    "source",
    [
        # no title
        "```{list-table}\n- * A\n  * B\n- * 1\n  * 2\n```\n",
        # with title
        "```{list-table} My Table\n- * Col A\n  * Col B\n- * val1\n  * val2\n```\n",
        # with options
        "```{list-table} Caption\n:header-rows: 1\n:widths: 20 80\n\n- * Header A\n  * Header B\n- * data1\n  * data2\n```\n",
    ],
)
def test_myst_list_table_round_trip(source):
    """Body is opaque (placeholder); title is the only translatable part."""
    xml_output, placeholders, _ = myst_to_xml(source)
    reconstructed = reconstruct_from_xml(xml_output, placeholders)
    assert reconstructed == source


def test_myst_list_table_title_is_translatable():
    source = "```{list-table} Important Data\n- * A\n  * B\n```\n"
    xml_output, placeholders, _ = myst_to_xml(source)
    root = ET.fromstring(xml_output)
    text_content = "".join(root.itertext())
    assert "Important Data" in text_content


def test_myst_list_table_body_is_placeholder():
    source = "```{list-table} Title\n- * Col A\n  * Col B\n- * val1\n  * val2\n```\n"
    xml_output, placeholders, _ = myst_to_xml(source)
    root = ET.fromstring(xml_output)
    text_el = root.find("TEXT")
    # Collect only what the translator sees: TEXT.text + each PH's tail
    translator_text = (text_el.text or "") + "".join(
        (ph.tail or "") for ph in text_el
    )
    # Cell content must NOT reach the translator
    assert "Col A" not in translator_text
    assert "val1" not in translator_text


@pytest.mark.parametrize("source,expected_lines", [
    # 2-space nested bullet inside bullet
    pytest.param(
        "- outer\n  - inner\n",
        ["- outer", "  - inner"],
        id="2space_nested_bullet",
    ),
    # 3-space nested bullet inside ordered (marker "1. " = 3 chars)
    pytest.param(
        "1. outer\n   - inner\n",
        ["1. outer", "   - inner"],
        id="3space_nested_bullet_inside_ordered",
    ),
    # 3-space nested ordered inside bullet (marker "- " = 2 chars + 1 indent)
    pytest.param(
        "- outer\n   1. inner\n",
        ["- outer", "   1. inner"],
        id="3space_nested_ordered_inside_bullet",
    ),
    # 3-level deep nesting preserves each indent exactly
    pytest.param(
        "- a\n  - b\n    - c\n",
        ["- a", "  - b", "    - c"],
        id="3level_deep_nesting",
    ),
    # continuation line indented to marker end
    pytest.param(
        "- outer\n  - inner item\n    continuation\n",
        ["- outer", "  - inner item", "    continuation"],
        id="nested_item_continuation_line",
    ),
    # star marker preserved with its source indentation
    pytest.param(
        "* top\n  * nested\n",
        ["* top", "  * nested"],
        id="star_marker_nested",
    ),
    # tab-indented nested bullet inside bullet
    pytest.param(
        "- outer\n\t- inner\n",
        ["- outer", "\t- inner"],
        id="tab_nested_bullet",
    ),
    # tab-indented nested bullet inside ordered
    pytest.param(
        "1. outer\n\t- inner\n",
        ["1. outer", "\t- inner"],
        id="tab_nested_bullet_inside_ordered",
    ),
    # tab-based 3-level deep nesting
    pytest.param(
        "- a\n\t- b\n\t\t- c\n",
        ["- a", "\t- b", "\t\t- c"],
        id="tab_3level_deep_nesting",
    ),
    # tab-indented continuation line
    pytest.param(
        "- outer\n\t- inner item\n\t  continuation\n",
        ["- outer", "\t- inner item", "\t  continuation"],
        id="tab_nested_item_continuation_line",
    ),
    # tab-indented star marker
    pytest.param(
        "* top\n\t* nested\n",
        ["* top", "\t* nested"],
        id="tab_star_marker_nested",
    ),
])
def test_myst_nested_list_preserves_source_indentation(source, expected_lines):
    """Round-trip must reproduce the exact source indentation (spaces or tabs)."""
    xml_output, placeholders, _ = myst_to_xml(source)
    reconstructed = reconstruct_from_xml(xml_output, placeholders).rstrip()
    assert reconstructed.splitlines() == expected_lines


@pytest.mark.parametrize("source,expected_lines", [
    # bullet list inside admonition body uses 2-space indent
    pytest.param(
        ":::{note}\n- item one\n  - nested\n:::\n",
        [":::{note}", "- item one", "  - nested", ":::"],
        id="nested_bullet_inside_admonition",
    ),
    # ordered list inside admonition body
    pytest.param(
        ":::{note}\n1. first\n   - sub\n:::\n",
        [":::{note}", "1. first", "   - sub", ":::"],
        id="nested_ordered_inside_admonition",
    ),
    # tab-indented nested bullet inside admonition body
    pytest.param(
        ":::{note}\n- item one\n\t- nested\n:::\n",
        [":::{note}", "- item one", "\t- nested", ":::"],
        id="tab_nested_bullet_inside_admonition",
    ),
    # tab-indented nested bullet inside ordered list in admonition body
    pytest.param(
        ":::{note}\n1. first\n\t- sub\n:::\n",
        [":::{note}", "1. first", "\t- sub", ":::"],
        id="tab_nested_ordered_inside_admonition",
    ),
])
def test_myst_list_inside_directive_preserves_source_indentation(source, expected_lines):
    """Lists inside directive bodies must keep exact source indentation (spaces or tabs)."""
    xml_output, placeholders, _ = myst_to_xml(source)
    reconstructed = reconstruct_from_xml(xml_output, placeholders).rstrip()
    assert reconstructed.splitlines() == expected_lines


def test_myst_mixed_directive_fences_round_trip():
  source = (
      "# Example\n\n"
      "```{eval-rst}\n"
      ".. note::\n"
      "   This warning is important and must not disappear.\n"
      "```\n\n"
      "```{amsmath}\n"
      "\\begin{align}\n"
      "E &= mc^2 \\\\\n"
      "F &= ma\n"
      "\\end{align}\n"
      "```\n"
  )

  xml_output, placeholders, _ = myst_to_xml(source)
  reconstructed = reconstruct_from_xml(xml_output, placeholders)

  assert reconstructed == source


def test_myst_definiendum_role_content_is_translatable():
    source = "The word {definiendum}`cat` is defined here.\n"
    xml_output, placeholders, _ = myst_to_xml(source)
    root = ET.fromstring(xml_output)
    text_el = root.find("TEXT")
    translator_text = (text_el.text or "") + "".join(
        (ph.tail or "") for ph in text_el
    )
    assert "cat" in translator_text


def test_myst_definiendum_role_syntax_is_placeholder():
    source = "The word {definiendum}`cat` is defined here.\n"
    xml_output, placeholders, _ = myst_to_xml(source)
    root = ET.fromstring(xml_output)
    text_el = root.find("TEXT")
    ph_texts = [ph.text or "" for ph in text_el]
    assert any("{definiendum}`" in ph for ph in ph_texts)
    assert any(ph == "`" for ph in ph_texts)


def test_myst_definiendum_role_round_trip():
    source = "The word {definiendum}`cat` is defined here.\n"
    xml_output, placeholders, _ = myst_to_xml(source)
    reconstructed = reconstruct_from_xml(xml_output, placeholders)
    assert reconstructed == source


def test_myst_non_translatable_role_content_is_placeholder():
    source = "See {term}`energy` for details.\n"
    xml_output, placeholders, _ = myst_to_xml(source)
    root = ET.fromstring(xml_output)
    text_el = root.find("TEXT")
    translator_text = (text_el.text or "") + "".join(
        (ph.tail or "") for ph in text_el
    )
    assert "energy" not in translator_text


def test_myst_definiendum_role_with_target_both_texts_are_translatable():
    source = "The word {definiendum}`cat <feline>` is defined here.\n"
    xml_output, placeholders, _ = myst_to_xml(source)
    root = ET.fromstring(xml_output)
    text_el = root.find("TEXT")
    translator_text = (text_el.text or "") + "".join(
        (ph.tail or "") for ph in text_el
    )
    assert "cat" in translator_text
    assert "feline" in translator_text


def test_myst_definiendum_role_with_target_syntax_is_placeholder():
    source = "The word {definiendum}`cat <feline>` is defined here.\n"
    xml_output, placeholders, _ = myst_to_xml(source)
    root = ET.fromstring(xml_output)
    text_el = root.find("TEXT")
    ph_texts = [ph.text or "" for ph in text_el]
    assert any("{definiendum}`" in ph for ph in ph_texts)
    assert any(ph == " <" for ph in ph_texts)
    assert any(ph == ">`" for ph in ph_texts)


def test_myst_definiendum_role_with_target_round_trip():
    source = "The word {definiendum}`cat <feline>` is defined here.\n"
    xml_output, placeholders, _ = myst_to_xml(source)
    reconstructed = reconstruct_from_xml(xml_output, placeholders)
    assert reconstructed == source


def test_myst_tight_list_followed_by_paragraph_preserves_blank_line():
    source = (
        "- `expression` est l'opération à appliquer.\n"
        "- `name` est une variable temporaire.\n"
        "- `iterable` est la liste ou l'objet itérable.\n"
        "\n"
        "Supposons que nous ayons une liste de nombres.\n"
    )
    xml_output, placeholders, _ = myst_to_xml(source)
    reconstructed = reconstruct_from_xml(xml_output, placeholders)
    assert reconstructed == source

def test_myst_admonition_option_without_blank_line_body_is_translatable():
    """Directive body paragraph directly after an option (no blank line) must be translatable."""
    source = (
        ":::{admonition} Indication : Quelques éléments de Python\n"
        ":class: hint\n"
        "Tant que la condition est vraie, répéter les instructions :\n"
        "\n"
        "Bonjour à tous.\n"
        ":::\n"
    )
    xml_output, placeholders, _ = myst_to_xml(source)
    root = ET.fromstring(xml_output)
    text_el = root.find("TEXT")
    translator_text = (text_el.text or "") + "".join((ph.tail or "") for ph in text_el)

    assert "Tant que la condition est vraie" in translator_text
    assert "Bonjour à tous" in translator_text

    reconstructed = reconstruct_from_xml(xml_output, placeholders)
    assert reconstructed == source


def test_myst_admonition_option_without_blank_line_option_is_placeholder():
    """The ':class: hint' option line must be a placeholder, not translator-visible text."""
    source = (
        ":::{admonition} Note\n"
        ":class: hint\n"
        "Body text.\n"
        ":::\n"
    )
    xml_output, placeholders, _ = myst_to_xml(source)
    root = ET.fromstring(xml_output)
    text_el = root.find("TEXT")
    translator_text = (text_el.text or "") + "".join((ph.tail or "") for ph in text_el)

    assert ":class: hint" not in translator_text
    assert "hint" not in translator_text


def test_myst_blockquote_inside_list_item_preserves_indent_and_continuation():
    source = (
        ":::{admonition} Exemple: expertiser un code\n"
        "1. Sélectionnez du code\n"
        "\n"
        "2. Saisissez la question:\n"
        "\n"
        "   > Je suis débutant en programmation Python. Commente le code suivant en proposant des\n"
        "   > améliorations:\n"
        "\n"
        "3. Cliquez sur «envoyer la sélection» avec la question.\n"
        ":::\n"
    )
    xml_output, placeholders, _ = myst_to_xml(source)
    reconstructed = reconstruct_from_xml(xml_output, placeholders)
    assert reconstructed == source


def test_myst_blockquote_at_top_level_continuation_line():
    source = (
        "> Line one of the blockquote that is quite long and wraps\n"
        "> onto a second line.\n"
    )
    xml_output, placeholders, _ = myst_to_xml(source)
    reconstructed = reconstruct_from_xml(xml_output, placeholders)
    assert reconstructed == source

def test_myst_nested_admonition_multiline_options_stay_indented():
    source = (
        "- Parent item\n"
        "\n"
        "  :::{admonition} Inner note\n"
        "  :class: dropdown tip\n"
        "  :name: nested-note\n"
        "\n"
        "  Body text.\n"
        "  :::\n"
    )
    xml_output, placeholders, _ = myst_to_xml(source)
    reconstructed = reconstruct_from_xml(xml_output, placeholders)
    lines = reconstructed.splitlines()

    assert "  :class: dropdown tip" in lines
    assert "  :name: nested-note" in lines
    assert ":name: nested-note" not in [line for line in lines if line.startswith(":name:")]
    assert reconstructed == source


# ---------------------------------------------------------------------------
# Helpers for media directive tests
# ---------------------------------------------------------------------------

def _translator_visible_text(xml_output: str) -> str:
    """Return only the text that the translator will see (TEXT node text + PH tails)."""
    root = ET.fromstring(xml_output)
    text_el = root.find("TEXT")
    return (text_el.text or "") + "".join((ph.tail or "") for ph in text_el)


# ---------------------------------------------------------------------------
# {image} directive — :alt: translatability
# ---------------------------------------------------------------------------

def test_myst_image_alt_is_translatable():
    """:alt: value in {image} must reach the translator."""
    source = ":::{image} path/to/image.png\n:alt: A beautiful sunset over the mountains\n:::\n"
    xml_output, placeholders, _ = myst_to_xml(source)
    translator_text = _translator_visible_text(xml_output)
    assert "A beautiful sunset over the mountains" in translator_text


def test_myst_image_path_and_non_alt_options_are_placeholders():
    """:width:, :height: and the image path must NOT reach the translator."""
    source = ":::{image} path/to/image.png\n:alt: Some alt text\n:width: 80%\n:height: 200px\n:::\n"
    xml_output, placeholders, _ = myst_to_xml(source)
    translator_text = _translator_visible_text(xml_output)
    assert "path/to/image.png" not in translator_text
    assert ":width: 80%" not in translator_text
    assert ":height: 200px" not in translator_text


@pytest.mark.parametrize("options_before,options_after", [
    # alt first
    ([], [":width: 80%", ":align: center"]),
    # alt last
    ([":width: 80%", ":align: center"], []),
    # alt in the middle
    ([":width: 80%"], [":align: center", ":height: 100px"]),
])
def test_myst_image_alt_is_translatable_regardless_of_field_order(options_before, options_after):
    """The :alt: value must be translatable no matter where it appears in the option block."""
    lines = [":::{image} path/to/image.png"]
    lines += options_before
    lines += [":alt: Descriptive alt text"]
    lines += options_after
    lines += [":::"]
    source = "\n".join(lines) + "\n"

    xml_output, placeholders, _ = myst_to_xml(source)
    translator_text = _translator_visible_text(xml_output)

    assert "Descriptive alt text" in translator_text
    for opt in options_before + options_after:
        # Strip leading ':' to get just the value or key part
        _, _, value = opt.partition(": ")
        assert value not in translator_text


def test_myst_image_with_only_alt_round_trip():
    source = ":::{image} path/to/image.png\n:alt: A beautiful sunset\n:::\n"
    xml_output, placeholders, _ = myst_to_xml(source)
    reconstructed = reconstruct_from_xml(xml_output, placeholders)
    assert reconstructed == source


def test_myst_image_with_alt_and_other_options_round_trip():
    source = ":::{image} path/to/image.png\n:alt: A beautiful sunset\n:width: 80%\n:align: center\n:::\n"
    xml_output, placeholders, _ = myst_to_xml(source)
    reconstructed = reconstruct_from_xml(xml_output, placeholders)
    assert reconstructed == source


def test_myst_image_alt_last_round_trip():
    source = ":::{image} path/to/image.png\n:width: 80%\n:align: center\n:alt: A beautiful sunset\n:::\n"
    xml_output, placeholders, _ = myst_to_xml(source)
    reconstructed = reconstruct_from_xml(xml_output, placeholders)
    assert reconstructed == source


# ---------------------------------------------------------------------------
# {figure} directive — :alt: and caption body translatability
# ---------------------------------------------------------------------------

def test_myst_figure_alt_is_translatable():
    """:alt: value in {figure} must reach the translator."""
    source = (
        ":::{figure} path/to/image.png\n"
        ":alt: A diagram showing the architecture\n"
        "\n"
        "Figure caption text.\n"
        ":::\n"
    )
    xml_output, placeholders, _ = myst_to_xml(source)
    translator_text = _translator_visible_text(xml_output)
    assert "A diagram showing the architecture" in translator_text


def test_myst_figure_caption_body_is_translatable():
    """Figure caption (body after options) must reach the translator."""
    source = (
        ":::{figure} path/to/image.png\n"
        ":alt: Alt text\n"
        "\n"
        "This caption explains the figure in detail.\n"
        ":::\n"
    )
    xml_output, placeholders, _ = myst_to_xml(source)
    translator_text = _translator_visible_text(xml_output)
    assert "This caption explains the figure in detail." in translator_text


def test_myst_figure_path_and_non_alt_options_are_placeholders():
    """Image path and non-alt options in {figure} must NOT reach the translator."""
    source = (
        ":::{figure} path/to/image.png\n"
        ":alt: Alt text\n"
        ":width: 80%\n"
        ":align: center\n"
        "\n"
        "Caption.\n"
        ":::\n"
    )
    xml_output, placeholders, _ = myst_to_xml(source)
    translator_text = _translator_visible_text(xml_output)
    assert "path/to/image.png" not in translator_text
    assert ":width: 80%" not in translator_text
    assert ":align: center" not in translator_text


def test_myst_figure_caption_only_no_alt_is_translatable():
    """A figure without :alt: still has a translatable caption."""
    source = (
        ":::{figure} path/to/image.png\n"
        ":width: 60%\n"
        "\n"
        "Caption without an alt field.\n"
        ":::\n"
    )
    xml_output, placeholders, _ = myst_to_xml(source)
    translator_text = _translator_visible_text(xml_output)
    assert "Caption without an alt field." in translator_text


@pytest.mark.parametrize("options_before,options_after", [
    # alt first
    ([], [":width: 80%"]),
    # alt last
    ([":width: 80%"], []),
    # alt in the middle
    ([":width: 80%"], [":align: center"]),
])
def test_myst_figure_alt_is_translatable_regardless_of_field_order(options_before, options_after):
    """The :alt: value in {figure} must be translatable regardless of its position."""
    lines = [":::{figure} path/to/image.png"]
    lines += options_before
    lines += [":alt: Architecture overview"]
    lines += options_after
    lines += ["", "Caption text.", ":::"]
    source = "\n".join(lines) + "\n"

    xml_output, placeholders, _ = myst_to_xml(source)
    translator_text = _translator_visible_text(xml_output)

    assert "Architecture overview" in translator_text
    assert "Caption text." in translator_text
    for opt in options_before + options_after:
        _, _, value = opt.partition(": ")
        assert value not in translator_text


def test_myst_figure_full_round_trip():
    source = (
        ":::{figure} path/to/image.png\n"
        ":alt: A diagram showing the architecture\n"
        ":width: 80%\n"
        ":align: center\n"
        "\n"
        "This caption explains the figure in detail.\n"
        ":::\n"
    )
    xml_output, placeholders, _ = myst_to_xml(source)
    reconstructed = reconstruct_from_xml(xml_output, placeholders)
    assert reconstructed == source


def test_myst_figure_alt_last_round_trip():
    source = (
        ":::{figure} path/to/image.png\n"
        ":width: 80%\n"
        ":align: center\n"
        ":alt: A diagram showing the architecture\n"
        "\n"
        "Caption text.\n"
        ":::\n"
    )
    xml_output, placeholders, _ = myst_to_xml(source)
    reconstructed = reconstruct_from_xml(xml_output, placeholders)
    assert reconstructed == source


def test_myst_figure_no_alt_round_trip():
    source = (
        ":::{figure} path/to/image.png\n"
        ":width: 60%\n"
        "\n"
        "Caption without an alt field.\n"
        ":::\n"
    )
    xml_output, placeholders, _ = myst_to_xml(source)
    reconstructed = reconstruct_from_xml(xml_output, placeholders)
    assert reconstructed == source


# ---------------------------------------------------------------------------
# {video} directive — :alt: translatability
# ---------------------------------------------------------------------------

def test_myst_video_alt_is_translatable():
    """:alt: value in {video} must reach the translator."""
    source = ":::{video} path/to/video.mp4\n:alt: A video demonstrating the workflow\n:width: 100%\n:::\n"
    xml_output, placeholders, _ = myst_to_xml(source)
    translator_text = _translator_visible_text(xml_output)
    assert "A video demonstrating the workflow" in translator_text


def test_myst_video_path_and_non_alt_options_are_placeholders():
    """Video path and non-alt options must NOT reach the translator."""
    source = ":::{video} path/to/video.mp4\n:alt: A video\n:width: 100%\n:::\n"
    xml_output, placeholders, _ = myst_to_xml(source)
    translator_text = _translator_visible_text(xml_output)
    assert "path/to/video.mp4" not in translator_text
    assert ":width: 100%" not in translator_text


def test_myst_video_round_trip():
    source = ":::{video} path/to/video.mp4\n:alt: A video demonstrating the workflow\n:width: 100%\n:::\n"
    xml_output, placeholders, _ = myst_to_xml(source)
    reconstructed = reconstruct_from_xml(xml_output, placeholders)
    assert reconstructed == source


# ---------------------------------------------------------------------------
# verify_placeholders — unit tests
# ---------------------------------------------------------------------------

def _make_xml(ph_ids: list[str]) -> str:
    """Build a minimal translated XML containing the given PH IDs."""
    phs = "".join(f'<PH id="{pid}">content</PH>' for pid in ph_ids)
    return f"<document><TEXT>text {phs}</TEXT></document>"


def test_verify_placeholders_all_present_returns_empty():
    expected = {"1": "\\ref{eq}", "2": "$E=mc^2$", "3": "\\label{x}"}
    xml = _make_xml(["1", "2", "3"])
    missing, extra = verify_placeholders(xml, expected)
    assert missing == []
    assert extra == []


def test_verify_placeholders_detects_missing_id():
    expected = {"1": "\\ref{eq}", "2": "$E=mc^2$"}
    xml = _make_xml(["1"])  # PH 2 was dropped by the LLM
    missing, extra = verify_placeholders(xml, expected)
    assert missing == ["2"]
    assert extra == []


def test_verify_placeholders_detects_extra_id():
    expected = {"1": "\\ref{eq}"}
    xml = _make_xml(["1", "2"])  # LLM hallucinated PH 2
    missing, extra = verify_placeholders(xml, expected)
    assert missing == []
    assert extra == ["2"]


def test_verify_placeholders_detects_both_missing_and_extra():
    expected = {"1": "\\ref{eq}", "2": "$x^2$"}
    xml = _make_xml(["1", "3"])  # PH 2 dropped, PH 3 hallucinated
    missing, extra = verify_placeholders(xml, expected)
    assert missing == ["2"]
    assert extra == ["3"]


def test_verify_placeholders_empty_expected_always_ok():
    xml = "<document><TEXT>Translated text.</TEXT></document>"
    missing, extra = verify_placeholders(xml, {})
    assert missing == []
    assert extra == []


def test_verify_placeholders_invalid_xml_returns_empty():
    """ParseError must not propagate — it is handled separately in the retry logic."""
    missing, extra = verify_placeholders("this is not xml", {"1": "content"})
    assert missing == []
    assert extra == []


def test_verify_placeholders_ids_sorted_numerically():
    expected = {"1": "a", "3": "b", "5": "c"}
    xml = _make_xml(["1"])  # 3 and 5 are missing
    missing, _ = verify_placeholders(xml, expected)
    assert missing == ["3", "5"]


# ---------------------------------------------------------------------------
# _xml_postprocess integration — raises PlaceholderVerificationError
# ---------------------------------------------------------------------------

def _wrap_in_response(xml: str) -> str:
    """Wrap XML in the fenced block that extract_translated_from_response expects."""
    return f"```xml\n{xml}\n```"


def test_xml_postprocess_raises_on_missing_structural_placeholder():
    source = "Some text with $E=mc^2$ and more text.\n"
    xml_output, placeholders, _ = myst_to_xml(source)

    # Ensure there is at least one structural (non-whitespace) PH to drop
    structural_ids = [k for k, v in placeholders.items() if v.strip()]
    assert structural_ids, "test requires at least one structural PH"

    # Simulate an LLM response that drops a structural PH tag
    root = ET.fromstring(xml_output)
    text_el = root.find("TEXT")
    for ph in list(text_el):
        if ph.get("id") == structural_ids[0]:
            # Absorb tail into preceding text / container text before removing
            tail = ph.tail or ""
            prev = list(text_el)
            idx = list(text_el).index(ph)
            if idx == 0:
                text_el.text = (text_el.text or "") + tail
            else:
                prev[idx - 1].tail = (prev[idx - 1].tail or "") + tail
            text_el.remove(ph)
            break
    corrupted_xml = ET.tostring(root, encoding="unicode")

    ctx = PromptContext(is_xml=True, placeholders=placeholders)
    with pytest.raises(PlaceholderVerificationError) as exc_info:
        _xml_postprocess(_wrap_in_response(corrupted_xml), ctx)

    assert exc_info.value.missing


def test_xml_postprocess_does_not_raise_on_missing_whitespace_placeholder():
    """Dropping a bare '\\n' PH must not trigger a retry — it's an acceptable loss."""
    # Build a minimal placeholder map that contains only a whitespace PH
    whitespace_phs = {"1": "\n", "2": "\n\n"}
    xml = "<document><TEXT>Translated paragraph without newline PHs.</TEXT></document>"

    ctx = PromptContext(is_xml=True, placeholders=whitespace_phs)
    # Should not raise even though both PHs are absent
    result = _xml_postprocess(_wrap_in_response(xml), ctx)
    assert "Translated paragraph" in result


def test_xml_postprocess_succeeds_when_all_placeholders_present():
    source = "Hello $E=mc^2$ world.\n"
    xml_output, placeholders, _ = myst_to_xml(source)

    ctx = PromptContext(is_xml=True, placeholders=placeholders)
    result = _xml_postprocess(_wrap_in_response(xml_output), ctx)
    assert "Hello" in result
    assert "$E=mc^2$" in result


def test_xml_postprocess_skips_verification_when_no_placeholders():
    """Plain-text chunks have no placeholders — postprocess must not raise."""
    xml = "<document><TEXT>Translated text with no syntax.</TEXT></document>"
    ctx = PromptContext(is_xml=True, placeholders={})
    result = _xml_postprocess(_wrap_in_response(xml), ctx)
    assert "Translated text" in result
