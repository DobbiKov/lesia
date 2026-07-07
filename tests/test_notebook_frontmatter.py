"""Tests verifying that notebook frontmatter — including unknown/custom fields —
is preserved after translation."""

import asyncio
import re
from pathlib import Path

import yaml

from lesia.enums import Language
from lesia.doc_translator_mod import notebook_file_translator


SRC = Language.ENGLISH
TGT = Language.FRENCH


class FakeTranslator:
    def __init__(self):
        from lesia.translator_retrieval import TranslationStats
        self.stats = TranslationStats()

    async def translate_or_fetch(self, meta):
        return "Texte traduit.", False


def _patch(monkeypatch):
    monkeypatch.setattr(
        notebook_file_translator,
        "build_translator_with_model",
        lambda *a, **kw: FakeTranslator(),
    )


def _extract_frontmatter(path: Path) -> dict:
    """Reads a MyST .md file and returns the parsed YAML frontmatter."""
    content = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?\n)---\n", content, re.DOTALL)
    assert m, "No frontmatter found in output file"
    return yaml.safe_load(m.group(1))


MYST_SOURCE_WITH_CUSTOM_FIELDS = """\
---
jupytext:
  text_representation:
    extension: .md
    format_name: myst
    format_version: 0.13
kernelspec:
  display_name: Python 3 (ipykernel)
  language: python
  name: python3
learning:
  objectives:
    understand: [variable, affectation]
    apply: [affectation, expression]
  prerequisites:
    apply: ["opération", expression]
---

# Hello

Some text.
"""


class TestNotebookFrontmatterPreservation:
    def _src(self, tmp_path: Path) -> Path:
        p = tmp_path / "source.md"
        p.write_text(MYST_SOURCE_WITH_CUSTOM_FIELDS, encoding="utf-8")
        return p

    def _translate(self, monkeypatch, src: Path, tgt: Path):
        _patch(monkeypatch)
        asyncio.run(notebook_file_translator.translate_notebook_async(
            src.parent, src, SRC, tgt, TGT, None, None, "source.md",
        ))

    def test_known_frontmatter_fields_are_preserved(self, monkeypatch, tmp_path):
        src = self._src(tmp_path)
        tgt = tmp_path / "target.md"
        self._translate(monkeypatch, src, tgt)

        fm = _extract_frontmatter(tgt)
        assert fm["kernelspec"]["name"] == "python3"
        assert fm["jupytext"]["text_representation"]["format_name"] == "myst"

    def test_unknown_frontmatter_fields_are_preserved(self, monkeypatch, tmp_path):
        src = self._src(tmp_path)
        tgt = tmp_path / "target.md"
        self._translate(monkeypatch, src, tgt)

        fm = _extract_frontmatter(tgt)
        assert "learning" in fm, "custom 'learning' key was dropped from frontmatter"

    def test_unknown_frontmatter_field_values_are_preserved(self, monkeypatch, tmp_path):
        src = self._src(tmp_path)
        tgt = tmp_path / "target.md"
        self._translate(monkeypatch, src, tgt)

        fm = _extract_frontmatter(tgt)
        learning = fm["learning"]
        assert learning["objectives"]["understand"] == ["variable", "affectation"]
        assert learning["objectives"]["apply"] == ["affectation", "expression"]
        assert learning["prerequisites"]["apply"] == ["opération", "expression"]
