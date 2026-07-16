"""Tests for detailed chunk-failure reporting: which chunk failed, why,
and where it lives in the source and target files."""

import asyncio
from pathlib import Path

import jupytext
import nbformat

from lesia.enums import Language
from lesia.errors import ChunkTranslationFailed
from lesia.translator_retrieval import (
    ChunkFailure,
    TranslationStats,
    locate_chunk_start_lines,
)
from lesia.doc_translator_mod import (
    myst_file_translator,
    latex_file_translator,
    typst_file_translator,
    notebook_file_translator,
)


SRC = Language.ENGLISH
TGT = Language.FRENCH
TRANSLATED = "Texte traduit."


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FailingTranslator:
    """Fake ChunkTranslator that fails chunks matching a predicate."""

    def __init__(self, fail_when=lambda chunk: True, result: str = TRANSLATED):
        self.stats = TranslationStats()
        self._fail_when = fail_when
        self._result = result
        self.failed_chunks: list[str] = []

    async def translate_or_fetch(self, meta):
        if self._fail_when(meta.chunk):
            self.stats.chunks_failed += 1
            self.failed_chunks.append(meta.chunk)
            raise ChunkTranslationFailed(meta.chunk, ValueError("boom"))
        self.stats.chunks_translated += 1
        return self._result, False


def _patch(monkeypatch, module, translator):
    monkeypatch.setattr(module, "build_translator_with_model", lambda *a, **kw: translator)


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

class TestLocateChunkStartLines:
    def test_locates_sequential_chunks(self):
        text = "alpha\nbeta\n\ngamma\ndelta\n"
        lines = locate_chunk_start_lines(text, ["alpha\nbeta\n", "gamma\ndelta\n"])
        assert lines == [1, 4]

    def test_unlocatable_chunk_gives_none(self):
        lines = locate_chunk_start_lines("alpha\n", ["missing"])
        assert lines == [None]

    def test_empty_chunk_gives_none(self):
        lines = locate_chunk_start_lines("alpha\n", [""])
        assert lines == [None]

    def test_repeated_chunks_advance(self):
        text = "same\nother\nsame\n"
        lines = locate_chunk_start_lines(text, ["same\n", "same\n"])
        assert lines == [1, 3]


class TestChunkFailureFormat:
    def test_format_includes_index_type_and_locations(self):
        failure = ChunkFailure(
            chunk_index=13,
            error_type="JSONDecodeError",
            error_message="Expecting value",
            source_path="fr/documentation.md",
            target_path="en/documentation.md",
            source_line=13,
            target_line=14,
        )
        lines = failure.format_lines()
        assert lines[0] == "Translation failure on chunk #13 (JSONDecodeError): Expecting value"
        assert lines[1] == "  source: fr/documentation.md:13"
        assert lines[2] == "  target: en/documentation.md:14"

    def test_format_without_line_numbers(self):
        failure = ChunkFailure(
            chunk_index=2,
            error_type="ValueError",
            error_message="boom",
            source_path="notebook.ipynb",
            target_path="fr/notebook.ipynb",
        )
        lines = failure.format_lines()
        assert lines[1] == "  source: notebook.ipynb"
        assert lines[2] == "  target: fr/notebook.ipynb"

    def test_long_message_is_truncated(self):
        failure = ChunkFailure(chunk_index=1, error_type="Error", error_message="x" * 500)
        assert len(failure.format_lines()[0]) < 300


class TestTranslationStatsFailures:
    def test_add_concatenates_failures(self):
        f1 = ChunkFailure(chunk_index=1, error_type="A", error_message="a")
        f2 = ChunkFailure(chunk_index=2, error_type="B", error_message="b")
        a = TranslationStats(chunks_failed=1, failures=[f1])
        b = TranslationStats(chunks_failed=1, failures=[f2])
        total = a + b
        assert total.chunks_failed == 2
        assert total.failures == [f1, f2]

    def test_default_stats_equality_still_holds(self):
        assert TranslationStats() == TranslationStats()


# ---------------------------------------------------------------------------
# MyST end-to-end
# ---------------------------------------------------------------------------

MYST_SOURCE = """# Title one

Alpha text.

# Title two

Beta text.
"""


class TestMystFailureReporting:
    def _translate(self, monkeypatch, tmp_path: Path, translator) -> TranslationStats:
        src = tmp_path / "source.md"
        src.write_text(MYST_SOURCE, encoding="utf-8")
        tgt = tmp_path / "target.md"
        _patch(monkeypatch, myst_file_translator, translator)
        return asyncio.run(myst_file_translator.translate_file_async(
            tmp_path, src, SRC, tgt, TGT, "source.md", None, None,
        ))

    def test_failure_records_location_and_error(self, monkeypatch, tmp_path):
        translator = FailingTranslator(fail_when=lambda chunk: "Beta" in chunk)
        stats = self._translate(monkeypatch, tmp_path, translator)

        assert len(stats.failures) == 1
        failure = stats.failures[0]
        assert failure.error_type == "ValueError"
        assert failure.error_message == "boom"
        assert failure.chunk_index >= 1
        assert failure.source_path == "source.md"
        assert failure.target_path == "target.md"

        # Source line must point at the start of the failed chunk.
        failed_chunk = translator.failed_chunks[0]
        expected_line = MYST_SOURCE[: MYST_SOURCE.find(failed_chunk)].count("\n") + 1
        assert failure.source_line == expected_line

        # Target line must point at the (untranslated) chunk in the output file.
        target_lines = (tmp_path / "target.md").read_text(encoding="utf-8").splitlines()
        assert target_lines[failure.target_line - 1] == failed_chunk.splitlines()[0]

    def test_no_failures_means_empty_list(self, monkeypatch, tmp_path):
        stats = self._translate(monkeypatch, tmp_path, FailingTranslator(fail_when=lambda c: False))
        assert stats.failures == []


# ---------------------------------------------------------------------------
# LaTeX end-to-end
# ---------------------------------------------------------------------------

LATEX_SOURCE = """\\section{One}
Alpha text.
\\section{Two}
Beta text.
"""


class TestLatexFailureReporting:
    def test_failure_records_location_and_error(self, monkeypatch, tmp_path):
        src = tmp_path / "source.tex"
        src.write_text(LATEX_SOURCE, encoding="utf-8")
        tgt = tmp_path / "target.tex"
        translator = FailingTranslator(fail_when=lambda chunk: "Beta" in chunk)
        _patch(monkeypatch, latex_file_translator, translator)

        stats = asyncio.run(latex_file_translator.translate_file_async(
            tmp_path, src, SRC, tgt, TGT, "source.tex", None, None,
        ))

        assert len(stats.failures) == 1
        failure = stats.failures[0]
        assert failure.error_type == "ValueError"
        assert failure.source_path == "source.tex"
        assert failure.target_path == "target.tex"

        failed_chunk = translator.failed_chunks[0]
        expected_line = LATEX_SOURCE[: LATEX_SOURCE.find(failed_chunk)].count("\n") + 1
        assert failure.source_line == expected_line

        target_lines = tgt.read_text(encoding="utf-8").splitlines()
        assert target_lines[failure.target_line - 1] == failed_chunk.splitlines()[0]


# ---------------------------------------------------------------------------
# Typst end-to-end
# ---------------------------------------------------------------------------

TYPST_SOURCE = """= One

Alpha text.

= Two

Beta text.
"""


class TestTypstFailureReporting:
    def test_failure_records_location_and_error(self, monkeypatch, tmp_path):
        src = tmp_path / "source.typ"
        src.write_text(TYPST_SOURCE, encoding="utf-8")
        tgt = tmp_path / "target.typ"
        translator = FailingTranslator(fail_when=lambda chunk: "Beta" in chunk)
        _patch(monkeypatch, typst_file_translator, translator)

        stats = asyncio.run(typst_file_translator.translate_file_async(
            tmp_path, src, SRC, tgt, TGT, "source.typ", None, None,
        ))

        assert len(stats.failures) == 1
        failure = stats.failures[0]
        assert failure.error_type == "ValueError"
        assert failure.source_path == "source.typ"
        assert failure.target_path == "target.typ"

        failed_chunk = translator.failed_chunks[0]
        expected_line = TYPST_SOURCE[: TYPST_SOURCE.find(failed_chunk)].count("\n") + 1
        assert failure.source_line == expected_line

        target_lines = tgt.read_text(encoding="utf-8").splitlines()
        assert target_lines[failure.target_line - 1] == failed_chunk.splitlines()[0]


# ---------------------------------------------------------------------------
# Notebook end-to-end
# ---------------------------------------------------------------------------

class TestNotebookFailureReporting:
    def test_failure_records_cell_index_and_paths(self, monkeypatch, tmp_path):
        nb = nbformat.v4.new_notebook()
        nb.cells = [
            nbformat.v4.new_markdown_cell("Alpha text."),
            nbformat.v4.new_markdown_cell("Beta text."),
        ]
        src = tmp_path / "source.ipynb"
        jupytext.write(nb, src)
        tgt = tmp_path / "target.ipynb"

        translator = FailingTranslator(fail_when=lambda chunk: "Beta" in chunk)
        _patch(monkeypatch, notebook_file_translator, translator)

        stats = asyncio.run(notebook_file_translator.translate_notebook_async(
            tmp_path, src, SRC, tgt, TGT, None, None, "source.ipynb",
        ))

        assert len(stats.failures) == 1
        failure = stats.failures[0]
        assert failure.chunk_index == 2  # 1-based cell number
        assert failure.error_type == "ValueError"
        assert failure.source_path == "source.ipynb"
        assert failure.target_path == "target.ipynb"
        assert failure.source_line is None
        assert failure.target_line is None
