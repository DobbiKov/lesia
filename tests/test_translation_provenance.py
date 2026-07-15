"""Tests verifying that the LLM service and model used for a translation are
recorded on the ChunkTranslator and written into chunk metadata, and that they
are preserved from an existing translated file on cache hits."""

import asyncio

from lesia.enums import Language, ChunkType, DocumentType
from lesia.helpers import calculate_checksum
from lesia.translator_retrieval import ChunkTranslator, Meta, TranslationStats
from lesia.doc_translator_mod import (
    myst_file_translator,
    latex_file_translator,
    typst_file_translator,
    notebook_file_translator,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeCaller:
    """Caller that mimics an LLMCaller: has model and service_name attributes."""

    def __init__(self, service_name: str = "google", model: str = "gemini-2.0-flash"):
        self.model = model
        self.service_name = service_name

    def call(self, prompt: str) -> str:
        return "<translated>Translated.</translated>"

    def wait_cooldown(self) -> None:
        pass


class InMemoryStore:
    def __init__(self, prepopulated: dict[str, str] | None = None):
        self._store: dict[str, str] = prepopulated or {}

    def lookup(self, src_checksum, src_lang, tgt_lang, relative_path):
        return self._store.get(src_checksum)

    def persist_pair(self, src_checksum, tgt_checksum, src_lang, tgt_lang, src_text, tgt_text, relative_path):
        self._store[src_checksum] = tgt_text

    def get_best_pair_example_from_cache(self, *args, **kwargs):
        return None

    def get_contents_by_checksum(self, *args, **kwargs):
        return None


class FakeTranslator:
    """Fake ChunkTranslator returning a fixed (text, from_cache) pair with provenance."""

    def __init__(self, result: str, from_cache: bool, service: str | None = "google", model: str | None = "gemini-2.0-flash"):
        self._result = result
        self._from_cache = from_cache
        self.stats = TranslationStats()
        self.last_translation_service = service
        self.last_translation_model = model

    async def translate_or_fetch(self, meta):
        return self._result, self._from_cache


def _meta(chunk: str) -> Meta:
    # Other/Other selects the plain strategy — no XML post-processing needed.
    return Meta(chunk, Language.ENGLISH, Language.FRENCH, DocumentType.Other, ChunkType.Other, None, "doc.md")


SRC = Language.ENGLISH
TGT = Language.FRENCH
REL = "docs/example.md"
TRANSLATED = "Texte traduit."
SOURCE_TEXT = "Some text."
CHECKSUM = calculate_checksum(SOURCE_TEXT)


# ---------------------------------------------------------------------------
# ChunkTranslator provenance recording
# ---------------------------------------------------------------------------

class TestChunkTranslatorProvenance:
    def test_translation_records_service_and_model(self, monkeypatch):
        monkeypatch.setattr(
            "lesia.translator_retrieval.chunk_contains_ph_only",
            lambda *a, **kw: False,
        )
        translator = ChunkTranslator(InMemoryStore(), FakeCaller("google", "gemini-2.0-flash"))

        _, from_cache = asyncio.run(translator.translate_or_fetch(_meta("Hello world.")))

        assert from_cache is False
        assert translator.last_translation_service == "google"
        assert translator.last_translation_model == "gemini-2.0-flash"

    def test_reasoning_caller_provenance_recorded_when_used(self, monkeypatch):
        """With xml_retries_before_reasoning=0 the only attempt uses the reasoning caller."""
        monkeypatch.setattr(
            "lesia.translator_retrieval.chunk_contains_ph_only",
            lambda *a, **kw: False,
        )
        standard = FakeCaller("google", "gemini-2.0-flash")
        reasoning = FakeCaller("openai", "o3")
        translator = ChunkTranslator(
            InMemoryStore(), standard, reasoning, xml_retries_before_reasoning=0
        )

        asyncio.run(translator.translate_or_fetch(_meta("Hello world.")))

        assert translator.last_translation_service == "openai"
        assert translator.last_translation_model == "o3"

    def test_no_caller_leaves_provenance_unset(self, monkeypatch):
        monkeypatch.setattr(
            "lesia.translator_retrieval.chunk_contains_ph_only",
            lambda *a, **kw: False,
        )
        monkeypatch.setattr(
            "lesia.translator_retrieval.TranslateStrategy.run",
            lambda self, meta: _fake_run(),
        )
        translator = ChunkTranslator(InMemoryStore())

        asyncio.run(translator.translate_or_fetch(_meta("Hello world.")))

        assert translator.last_translation_service is None
        assert translator.last_translation_model is None

    def test_real_llmcaller_exposes_service_name(self):
        """unified_model_caller >= 0.2.7 exposes the service via .service_name."""
        from unified_model_caller import LLMCaller

        caller = LLMCaller("google", "gemini-2.0-flash", "dummy-key")
        assert caller.service_name == "google"
        assert caller.model == "gemini-2.0-flash"


async def _fake_run():
    return "<translated>Translated.</translated>"


# ---------------------------------------------------------------------------
# File translators: writing provenance into chunk metadata
# ---------------------------------------------------------------------------

class _MetadataChunkSuite:
    """Shared cases for the myst/latex/typst chunk translators."""

    translate_chunk_async = None  # set in subclasses

    def _run(self, from_cache: bool, existing_meta=None, **fake_kwargs):
        cell = {"metadata": {}, "source": SOURCE_TEXT}
        return asyncio.run(
            type(self).translate_chunk_async(
                cell, SRC, TGT, REL, None,
                FakeTranslator(TRANSLATED, from_cache, **fake_kwargs),
                existing_meta=existing_meta,
            )
        )

    def test_llm_call_writes_service_and_model(self):
        cell = self._run(from_cache=False)
        assert cell["metadata"].get("translation_service") == "google"
        assert cell["metadata"].get("translation_model") == "gemini-2.0-flash"

    def test_llm_call_without_provenance_writes_nothing(self):
        cell = self._run(from_cache=False, service=None, model=None)
        assert "translation_service" not in cell["metadata"]
        assert "translation_model" not in cell["metadata"]

    def test_cache_hit_does_not_write_provenance(self):
        cell = self._run(from_cache=True, existing_meta={})
        assert "translation_service" not in cell["metadata"]
        assert "translation_model" not in cell["metadata"]

    def test_cache_hit_preserves_provenance_from_existing_target(self):
        existing_meta = {
            CHECKSUM: {
                "src_checksum": CHECKSUM,
                "translation_service": "openai",
                "translation_model": "gpt-4o",
            }
        }
        cell = self._run(from_cache=True, existing_meta=existing_meta)
        assert cell["metadata"].get("translation_service") == "openai"
        assert cell["metadata"].get("translation_model") == "gpt-4o"

    def test_translator_without_provenance_attributes_is_tolerated(self):
        """Duck-typed translators without the new attributes must not break."""
        class MinimalTranslator:
            stats = TranslationStats()

            async def translate_or_fetch(self, meta):
                return TRANSLATED, False

        cell = {"metadata": {}, "source": SOURCE_TEXT}
        result = asyncio.run(
            type(self).translate_chunk_async(
                cell, SRC, TGT, REL, None, MinimalTranslator(), existing_meta=None
            )
        )
        assert "translation_service" not in result["metadata"]
        assert "translation_model" not in result["metadata"]


class TestMystProvenance(_MetadataChunkSuite):
    translate_chunk_async = staticmethod(myst_file_translator.translate_chunk_async)


class TestLatexProvenance(_MetadataChunkSuite):
    translate_chunk_async = staticmethod(latex_file_translator.translate_chunk_async)


class TestTypstProvenance(_MetadataChunkSuite):
    translate_chunk_async = staticmethod(typst_file_translator.translate_chunk_async)


class TestNotebookProvenance:
    def _run(self, from_cache: bool, existing_meta=None, **fake_kwargs):
        cell = {"cell_type": "markdown", "source": SOURCE_TEXT, "metadata": {"tags": []}}
        return asyncio.run(
            notebook_file_translator.translate_jupyter_cell_async(
                cell, SRC, TGT, None,
                FakeTranslator(TRANSLATED, from_cache, **fake_kwargs),
                REL,
                existing_meta=existing_meta,
            )
        )

    def test_llm_call_writes_service_and_model(self):
        cell = self._run(from_cache=False)
        assert cell["metadata"].get("translation_service") == "google"
        assert cell["metadata"].get("translation_model") == "gemini-2.0-flash"

    def test_cache_hit_does_not_write_provenance(self):
        cell = self._run(from_cache=True, existing_meta={})
        assert "translation_service" not in cell["metadata"]
        assert "translation_model" not in cell["metadata"]

    def test_cache_hit_preserves_provenance_from_existing_target(self):
        existing_meta = {
            CHECKSUM: {
                "src_checksum": CHECKSUM,
                "tags": [],
                "translation_service": "openai",
                "translation_model": "gpt-4o",
            }
        }
        cell = self._run(from_cache=True, existing_meta=existing_meta)
        assert cell["metadata"].get("translation_service") == "openai"
        assert cell["metadata"].get("translation_model") == "gpt-4o"


# ---------------------------------------------------------------------------
# Round-trip: provenance survives compile + re-read of a MyST file
# ---------------------------------------------------------------------------

class TestMystRoundTrip:
    def test_provenance_survives_compile_and_read(self, tmp_path):
        cells = [{
            "metadata": {
                "src_checksum": CHECKSUM,
                "needs_review": "True",
                "translation_service": "google",
                "translation_model": "gemini-2.0-flash",
            },
            "source": TRANSLATED + "\n",
        }]
        target = tmp_path / "out.md"
        target.write_text(myst_file_translator.compile_myst_cells(cells), encoding="utf-8")

        chunks = myst_file_translator.read_chunks_with_metadata_from_myst(target)

        assert len(chunks) == 1
        assert chunks[0]["translation_service"] == "google"
        assert chunks[0]["translation_model"] == "gemini-2.0-flash"
        assert chunks[0]["src_checksum"] == CHECKSUM
