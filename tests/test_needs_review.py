"""Tests verifying needs_review tag is set only when LLM is called,
not on cache hits, and is preserved from an existing translated file."""

import asyncio

from lesia.enums import Language, ChunkType, DocumentType
from lesia.helpers import calculate_checksum
from lesia.translator_retrieval import ChunkTranslator, Meta
from lesia.doc_translator_mod import (
    myst_file_translator,
    latex_file_translator,
    typst_file_translator,
    notebook_file_translator,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeTranslator:
    """Fake ChunkTranslator that returns a fixed (text, from_cache) pair."""

    def __init__(self, result: str, from_cache: bool):
        self._result = result
        self._from_cache = from_cache

    async def translate_or_fetch(self, meta):
        return self._result, self._from_cache


SRC = Language.ENGLISH
TGT = Language.FRENCH
REL = "docs/example.md"
TRANSLATED = "Texte traduit."
SOURCE_TEXT = "Some text."
CHECKSUM = calculate_checksum(SOURCE_TEXT)


# ---------------------------------------------------------------------------
# MyST
# ---------------------------------------------------------------------------

class TestMystNeedsReview:
    def _run(self, from_cache: bool, existing_meta=None):
        cell = {"metadata": {}, "source": SOURCE_TEXT}
        return asyncio.run(
            myst_file_translator.translate_chunk_async(
                cell, SRC, TGT, REL, None,
                FakeTranslator(TRANSLATED, from_cache),
                existing_meta=existing_meta,
            )
        )

    def test_llm_call_adds_needs_review(self):
        cell = self._run(from_cache=False)
        assert cell["metadata"].get("needs_review") == "True"

    def test_cache_hit_does_not_add_needs_review(self):
        cell = self._run(from_cache=True, existing_meta={})
        assert "needs_review" not in cell["metadata"]

    def test_cache_hit_preserves_needs_review_from_existing_target(self):
        existing_meta = {CHECKSUM: {"needs_review": "True", "src_checksum": CHECKSUM}}
        cell = self._run(from_cache=True, existing_meta=existing_meta)
        assert cell["metadata"].get("needs_review") == "True"


# ---------------------------------------------------------------------------
# LaTeX
# ---------------------------------------------------------------------------

class TestLatexNeedsReview:
    def _run(self, from_cache: bool, existing_meta=None):
        cell = {"metadata": {}, "source": SOURCE_TEXT}
        return asyncio.run(
            latex_file_translator.translate_chunk_async(
                cell, SRC, TGT, REL, None,
                FakeTranslator(TRANSLATED, from_cache),
                existing_meta=existing_meta,
            )
        )

    def test_llm_call_adds_needs_review(self):
        cell = self._run(from_cache=False)
        assert cell["metadata"].get("needs_review") == "True"

    def test_cache_hit_does_not_add_needs_review(self):
        cell = self._run(from_cache=True, existing_meta={})
        assert "needs_review" not in cell["metadata"]

    def test_cache_hit_preserves_needs_review_from_existing_target(self):
        existing_meta = {CHECKSUM: {"needs_review": "True", "src_checksum": CHECKSUM}}
        cell = self._run(from_cache=True, existing_meta=existing_meta)
        assert cell["metadata"].get("needs_review") == "True"


# ---------------------------------------------------------------------------
# Typst
# ---------------------------------------------------------------------------

class TestTypstNeedsReview:
    def _run(self, from_cache: bool, existing_meta=None):
        cell = {"metadata": {}, "source": SOURCE_TEXT}
        return asyncio.run(
            typst_file_translator.translate_chunk_async(
                cell, SRC, TGT, REL, None,
                FakeTranslator(TRANSLATED, from_cache),
                existing_meta=existing_meta,
            )
        )

    def test_llm_call_adds_needs_review(self):
        cell = self._run(from_cache=False)
        assert cell["metadata"].get("needs_review") == "True"

    def test_cache_hit_does_not_add_needs_review(self):
        cell = self._run(from_cache=True, existing_meta={})
        assert "needs_review" not in cell["metadata"]

    def test_cache_hit_preserves_needs_review_from_existing_target(self):
        existing_meta = {CHECKSUM: {"needs_review": "True", "src_checksum": CHECKSUM}}
        cell = self._run(from_cache=True, existing_meta=existing_meta)
        assert cell["metadata"].get("needs_review") == "True"


# ---------------------------------------------------------------------------
# Notebook  (needs_review lives in cell["metadata"]["tags"])
# ---------------------------------------------------------------------------

class TestNotebookNeedsReview:
    def _run(self, from_cache: bool, existing_meta=None):
        cell = {"cell_type": "markdown", "source": SOURCE_TEXT, "metadata": {"tags": []}}
        return asyncio.run(
            notebook_file_translator.translate_jupyter_cell_async(
                cell, SRC, TGT, None,
                FakeTranslator(TRANSLATED, from_cache),
                REL,
                existing_meta=existing_meta,
            )
        )

    def test_llm_call_adds_needs_review(self):
        cell = self._run(from_cache=False)
        assert "needs_review" in cell["metadata"]["tags"]

    def test_cache_hit_does_not_add_needs_review(self):
        cell = self._run(from_cache=True, existing_meta={})
        assert "needs_review" not in cell["metadata"]["tags"]

    def test_cache_hit_preserves_needs_review_from_existing_target(self):
        existing_meta = {CHECKSUM: {"tags": ["needs_review"], "src_checksum": CHECKSUM}}
        cell = self._run(from_cache=True, existing_meta=existing_meta)
        assert "needs_review" in cell["metadata"]["tags"]


# ---------------------------------------------------------------------------
# Edge cases: session_checksums behaviour in ChunkTranslator
# ---------------------------------------------------------------------------

class PersistingStore:
    """In-memory store that actually stores and looks up translation pairs."""

    def __init__(self, prepopulated: dict[str, str] | None = None):
        # Maps src_checksum -> tgt_text
        self._store: dict[str, str] = prepopulated or {}
        self.llm_calls = 0

    def lookup(self, src_checksum, src_lang, tgt_lang, relative_path):
        return self._store.get(src_checksum)

    def persist_pair(self, src_checksum, tgt_checksum, src_lang, tgt_lang, src_text, tgt_text, relative_path):
        self._store[src_checksum] = tgt_text

    def get_best_pair_example_from_cache(self, *args, **kwargs):
        return None

    def get_contents_by_checksum(self, *args, **kwargs):
        return None


class CountingCaller:
    """Caller that counts invocations and returns a fixed translated string."""

    def __init__(self):
        self.calls = 0

    def call(self, prompt: str) -> str:
        self.calls += 1
        return "<translated>Translated.</translated>"

    def wait_cooldown(self) -> None:
        pass


def _meta(chunk: str) -> Meta:
    # Use Other/Other so the plain strategy is selected — no XML post-processing needed.
    return Meta(chunk, Language.ENGLISH, Language.FRENCH, DocumentType.Other, ChunkType.Other, None, "doc.md")


class TestSessionChecksums:
    def test_duplicate_chunk_in_same_pass_both_get_from_cache_false(self, monkeypatch):
        """Second occurrence of a chunk in the same file should still return
        from_cache=False because it was LLM-translated in this same pass."""
        monkeypatch.setattr(
            "lesia.translator_retrieval.chunk_contains_ph_only",
            lambda *a, **kw: False,
        )
        caller = CountingCaller()
        store = PersistingStore()
        tr = ChunkTranslator(store, caller)

        chunk = "Hello world."
        _, from_cache_1 = asyncio.run(tr.translate_or_fetch(_meta(chunk)))
        _, from_cache_2 = asyncio.run(tr.translate_or_fetch(_meta(chunk)))

        assert from_cache_1 is False
        assert from_cache_2 is False   # not True — same pass, LLM was called
        assert caller.calls == 1       # LLM only called once; second hit uses cache value

    def test_new_translator_instance_treats_old_cache_as_true(self, monkeypatch):
        """A fresh ChunkTranslator on a new file has an empty session set, so a
        lookup that hits a pre-existing cache entry is correctly from_cache=True."""
        monkeypatch.setattr(
            "lesia.translator_retrieval.chunk_contains_ph_only",
            lambda *a, **kw: False,
        )
        chunk = "Hello world."
        checksum = calculate_checksum(chunk)

        # Simulate a pre-existing cache entry from a previous run
        store = PersistingStore(prepopulated={checksum: "Bonjour monde."})
        tr = ChunkTranslator(store, CountingCaller())

        _, from_cache = asyncio.run(tr.translate_or_fetch(_meta(chunk)))

        assert from_cache is True   # genuinely from persistent cache, not this session

    def test_session_does_not_bleed_across_translator_instances(self, monkeypatch):
        """Session checksums are per-instance. Two files translated with separate
        translators don't share session state."""
        monkeypatch.setattr(
            "lesia.translator_retrieval.chunk_contains_ph_only",
            lambda *a, **kw: False,
        )
        # Shared persistent store (simulates the on-disk cache)
        shared_store = PersistingStore()
        caller = CountingCaller()

        chunk = "Hello world."

        # First file: tr1 calls LLM, writes to cache
        tr1 = ChunkTranslator(shared_store, caller)
        _, from_cache_1 = asyncio.run(tr1.translate_or_fetch(_meta(chunk)))

        # Second file: tr2 is a fresh instance — lookup hits persistent cache → from_cache=True
        tr2 = ChunkTranslator(shared_store, caller)
        _, from_cache_2 = asyncio.run(tr2.translate_or_fetch(_meta(chunk)))

        assert from_cache_1 is False  # LLM called in file 1
        assert from_cache_2 is True   # genuinely cached for file 2
        assert caller.calls == 1      # LLM not called again


# ---------------------------------------------------------------------------
# Placeholder-only chunks: needs_review must NOT be added
# ---------------------------------------------------------------------------

class RaisingCaller:
    """Caller that must never be invoked — raises if called."""

    def call(self, prompt: str) -> str:
        raise AssertionError("LLM must not be called for placeholder-only chunks")

    def wait_cooldown(self) -> None:
        pass


class TestPlaceholderOnlyNeedsReview:
    """Placeholder-only chunks bypass the LLM and must not get needs_review."""

    # --- MyST ---

    def test_myst_ph_only_chunk_no_needs_review(self):
        # A bare toctree directive contains only a placeholder — ph_only=True
        chunk = "```{toctree}\npage1\npage2\n```\n"
        cell = {"metadata": {}, "source": chunk}
        tr = ChunkTranslator(PersistingStore(), RaisingCaller())
        result = asyncio.run(
            myst_file_translator.translate_chunk_async(
                cell, SRC, TGT, REL, None, tr
            )
        )
        assert "needs_review" not in result["metadata"]
        assert result["source"] == chunk  # passed through unchanged

    def test_myst_ph_only_does_not_add_needs_review_even_with_existing_meta(self):
        chunk = "```{toctree}\npage1\npage2\n```\n"
        cell = {"metadata": {}, "source": chunk}
        tr = ChunkTranslator(PersistingStore(), RaisingCaller())
        # even when existing_meta contains no prior needs_review, none should appear
        result = asyncio.run(
            myst_file_translator.translate_chunk_async(
                cell, SRC, TGT, REL, None, tr, existing_meta={}
            )
        )
        assert "needs_review" not in result["metadata"]

    # --- LaTeX ---

    def test_latex_ph_only_chunk_no_needs_review(self):
        # \begin{document}\end{document} is placeholder-only for LaTeX
        chunk = r"\begin{document}\end{document}"
        cell = {"metadata": {}, "source": chunk}
        tr = ChunkTranslator(PersistingStore(), RaisingCaller())
        result = asyncio.run(
            latex_file_translator.translate_chunk_async(
                cell, SRC, TGT, REL, None, tr
            )
        )
        assert "needs_review" not in result["metadata"]
        assert result["source"] == chunk

    def test_latex_ph_only_does_not_add_needs_review_even_with_existing_meta(self):
        chunk = r"\begin{document}\end{document}"
        cell = {"metadata": {}, "source": chunk}
        tr = ChunkTranslator(PersistingStore(), RaisingCaller())
        result = asyncio.run(
            latex_file_translator.translate_chunk_async(
                cell, SRC, TGT, REL, None, tr, existing_meta={}
            )
        )
        assert "needs_review" not in result["metadata"]

    # --- Notebook (code cell — ChunkType.Code is always ph_only) ---

    def test_notebook_code_cell_no_needs_review(self):
        cell = {
            "cell_type": "code",
            "metadata": {"tags": []},
            "source": "import numpy as np\nprint('hello')",
        }
        tr = ChunkTranslator(PersistingStore(), RaisingCaller())
        result = asyncio.run(
            notebook_file_translator.translate_jupyter_cell_async(
                cell, SRC, TGT, None, tr, REL
            )
        )
        assert "needs_review" not in result["metadata"].get("tags", [])

    def test_notebook_code_cell_no_needs_review_with_existing_meta(self):
        cell = {
            "cell_type": "code",
            "metadata": {"tags": []},
            "source": "x = 1",
        }
        tr = ChunkTranslator(PersistingStore(), RaisingCaller())
        result = asyncio.run(
            notebook_file_translator.translate_jupyter_cell_async(
                cell, SRC, TGT, None, tr, REL, existing_meta={}
            )
        )
        assert "needs_review" not in result["metadata"].get("tags", [])
