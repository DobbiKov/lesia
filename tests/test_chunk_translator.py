import asyncio
import sys
import types

import pytest


# Provide lightweight shims for optional dependencies required by unified_model_caller imports.
if "xai_sdk" not in sys.modules:  # pragma: no cover - optional dependency stub
    xai_module = types.ModuleType("xai_sdk")

    class _DummyChat:
        def create(self, *, model, messages):
            return types.SimpleNamespace(sample=lambda: types.SimpleNamespace(content=""))

    xai_module.Client = lambda api_key: types.SimpleNamespace(chat=_DummyChat())

    chat_module = types.ModuleType("xai_sdk.chat")
    chat_module.user = lambda prompt: prompt

    sys.modules["xai_sdk"] = xai_module
    sys.modules["xai_sdk.chat"] = chat_module

if "google" not in sys.modules:  # pragma: no cover - optional dependency stub
    google_module = types.ModuleType("google")

    class _DummyModels:
        def generate_content(self, *, model, contents):
            return types.SimpleNamespace(text="")

    class _DummyClient:
        def __init__(self, api_key=None):
            self.models = _DummyModels()

    genai_module = types.ModuleType("google.genai")
    genai_module.Client = _DummyClient

    types_module = types.ModuleType("google.genai.types")

    class _DummyContent:
        def __init__(self, role, parts):
            self.role = role
            self.parts = parts

    class _DummyPart:
        @staticmethod
        def from_text(*, text):
            return text

    types_module.Content = _DummyContent
    types_module.Part = _DummyPart

    genai_module.types = types_module
    google_module.genai = genai_module

    sys.modules["google"] = google_module
    sys.modules["google.genai"] = genai_module
    sys.modules["google.genai.types"] = types_module


from lesia.doc_translator_mod import myst_file_translator, latex_file_translator, notebook_file_translator
from lesia.enums import ChunkType, DocumentType, Language
from lesia.errors import ChunkTranslationFailed
from lesia.helpers import calculate_checksum
from lesia.translator_retrieval import (
    ChunkTranslator,
    Meta,
    ModelOverloadedError,
    TranslationStats,
    _split_typst_chunk_for_internal_translation,
)
from lesia.xml_manipulator_mod.mod import typst_to_xml_mod
from unified_model_caller.errors import ApiCallError


class InMemoryStore:
    def __init__(self):
        self.persisted: list[tuple[str, str]] = []

    def lookup(self, src_checksum, src_lang, tgt_lang, relative_path):
        return None

    def persist_pair(
        self,
        src_checksum,
        tgt_checksum,
        src_lang,
        tgt_lang,
        src_text,
        tgt_text,
        relative_path,
    ):
        self.persisted.append((src_text, tgt_text))

    def get_best_pair_example_from_cache(self, lang, tgt_lang, txt, relative_path):
        return None

    def get_contents_by_checksum(self, checksum, lang, relative_path):
        return None

    def get_best_match_from_cache(self, lang, txt):
        raise NotImplementedError

    def do_translation_correspond_to_source(
        self,
        src_checksum,
        src_lang,
        tgt_contents,
        tgt_lang,
        relative_path,
    ):
        raise NotImplementedError


class InMemoryLookupStore(InMemoryStore):
    def __init__(self, cached_by_checksum: dict[str, str] | None = None):
        super().__init__()
        self.cached_by_checksum = cached_by_checksum or {}

    def lookup(self, src_checksum, src_lang, tgt_lang, relative_path):
        return self.cached_by_checksum.get(src_checksum)

    def persist_pair(
        self,
        src_checksum,
        tgt_checksum,
        src_lang,
        tgt_lang,
        src_text,
        tgt_text,
        relative_path,
    ):
        super().persist_pair(
            src_checksum,
            tgt_checksum,
            src_lang,
            tgt_lang,
            src_text,
            tgt_text,
            relative_path,
        )
        self.cached_by_checksum[src_checksum] = tgt_text


class RaisingCaller:
    def __init__(self):
        self.called = False
        self.waited = False

    def call(self, prompt: str) -> str:
        self.called = True
        raise ApiCallError("Gemini API call failed: missing api key")

    def wait_cooldown(self) -> None:
        self.waited = True


class OverloadedThenSucceedCaller:
    def __init__(self, fail_times: int):
        self.fail_times = fail_times
        self.calls = 0
        self.waits = 0

    def call(self, prompt: str) -> str:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise ModelOverloadedError("model overloaded")
        return "<output>Translated chunk</output>"

    def wait_cooldown(self) -> None:
        self.waits += 1


class AlwaysOverloadedCaller:
    def __init__(self):
        self.calls = 0

    def call(self, prompt: str) -> str:
        self.calls += 1
        raise ModelOverloadedError("still overloaded")

    def wait_cooldown(self) -> None:
        pass


class FailingTranslator:
    def __init__(self, error: Exception):
        self.error = error

    async def translate_or_fetch(self, meta: Meta) -> tuple[str, bool]:
        raise self.error


def test_placeholder_only_chunk_skips_model_call():
    store = InMemoryStore()
    caller = RaisingCaller()
    translator = ChunkTranslator(store, caller)

    chunk = "```{code-cell} python3\nprint('Hello')\n```\n"
    meta = Meta(
        chunk=chunk,
        src_lang=Language.ENGLISH,
        tgt_lang=Language.FRENCH,
        doc_type=DocumentType.JupyterNotebook,
        chunk_type=ChunkType.Myst,
        vocab=None,
        rel_path="docs/example.md",
    )

    translated, from_cache = asyncio.run(translator.translate_or_fetch(meta))

    assert translated == chunk
    assert from_cache is True   # ph_only: no LLM called, treated as passthrough
    assert caller.called is False
    assert store.persisted == [(chunk, chunk)]


def test_chunk_with_text_raises_chunk_translation_failed():
    store = InMemoryStore()
    caller = RaisingCaller()
    translator = ChunkTranslator(store, caller)

    chunk = "This sentence must be translated.\n"
    meta = Meta(
        chunk=chunk,
        src_lang=Language.ENGLISH,
        tgt_lang=Language.FRENCH,
        doc_type=DocumentType.JupyterNotebook,
        chunk_type=ChunkType.Myst,
        vocab=None,
        rel_path="docs/example.md",
    )

    with pytest.raises(ChunkTranslationFailed) as excinfo:
        asyncio.run(translator.translate_or_fetch(meta))

    assert caller.called is True
    assert excinfo.value.chunk == chunk
    assert isinstance(excinfo.value.original_exception, ApiCallError)
    assert store.persisted == []


def test_chunk_with_text_raises_chunk_translation_failed_latex():
    store = InMemoryStore()
    caller = RaisingCaller()
    translator = ChunkTranslator(store, caller)

    chunk = r"This sentence must be translated. \textbf{but we have some placeholders anyway}"
    meta = Meta(
        chunk=chunk,
        src_lang=Language.ENGLISH,
        tgt_lang=Language.FRENCH,
        doc_type=DocumentType.LaTeX,
        chunk_type=ChunkType.LaTeX,
        vocab=None,
        rel_path="docs/example.md",
    )

    with pytest.raises(ChunkTranslationFailed) as excinfo:
        asyncio.run(translator.translate_or_fetch(meta))

    assert caller.called is True
    assert excinfo.value.chunk == chunk
    assert store.persisted == []


def test_chunk_with_ph_only_doesnt_call_model_latex():
    store = InMemoryStore()
    caller = RaisingCaller()
    translator = ChunkTranslator(store, caller)

    chunk = r"\begin{document}\end{document}"
    meta = Meta(
        chunk=chunk,
        src_lang=Language.ENGLISH,
        tgt_lang=Language.FRENCH,
        doc_type=DocumentType.LaTeX,
        chunk_type=ChunkType.LaTeX,
        vocab=None,
        rel_path="docs/example.md",
    )

    translated, from_cache = asyncio.run(translator.translate_or_fetch(meta))

    assert translated == chunk
    assert from_cache is True   # ph_only: no LLM called, treated as passthrough
    assert caller.called is False
    assert store.persisted == [(chunk, chunk)]


def test_model_overloaded_retries_then_succeeds(monkeypatch):
    store = InMemoryStore()
    caller = OverloadedThenSucceedCaller(fail_times=2)
    translator = ChunkTranslator(
        store,
        caller,
        overload_retry_attempts=4,
        overload_retry_initial_delay=0.01,
        overload_retry_max_delay=0.02,
    )

    monkeypatch.setattr(
        "lesia.translator_retrieval.chunk_contains_ph_only",
        lambda *args, **kwargs: False,
    )

    observed_sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        observed_sleeps.append(delay)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    chunk = "Translate me please.\n"
    meta = Meta(
        chunk=chunk,
        src_lang=Language.ENGLISH,
        tgt_lang=Language.FRENCH,
        doc_type=DocumentType.Other,
        chunk_type=ChunkType.Other,
        vocab=None,
        rel_path="docs/example.md",
    )

    translated, from_cache = asyncio.run(translator.translate_or_fetch(meta))

    assert translated == "Translated chunk"
    assert from_cache is False
    assert caller.calls == 3  # two overloads then success
    assert observed_sleeps == [0.01, 0.02]
    assert store.persisted == [(chunk, translated)]


def test_model_overloaded_exhausts_retries(monkeypatch):
    store = InMemoryStore()
    caller = AlwaysOverloadedCaller()
    translator = ChunkTranslator(
        store,
        caller,
        overload_retry_attempts=2,
        overload_retry_initial_delay=0.01,
        overload_retry_max_delay=0.02,
    )

    monkeypatch.setattr(
        "lesia.translator_retrieval.chunk_contains_ph_only",
        lambda *args, **kwargs: False,
    )

    async def fake_sleep(_: float) -> None:
        pass

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    chunk = "Stuck chunk.\n"
    meta = Meta(
        chunk=chunk,
        src_lang=Language.ENGLISH,
        tgt_lang=Language.FRENCH,
        doc_type=DocumentType.Other,
        chunk_type=ChunkType.Other,
        vocab=None,
        rel_path="docs/example.md",
    )

    with pytest.raises(ChunkTranslationFailed) as excinfo:
        asyncio.run(translator.translate_or_fetch(meta))

    assert excinfo.value.chunk == chunk
    assert store.persisted == []
    assert caller.calls == 2


def test_myst_chunk_metadata_tagged_on_failure():
    chunk = "Paragraph needing translation.\n"
    cell = {"metadata": {}, "source": chunk}

    error = ChunkTranslationFailed(chunk, RuntimeError("boom"))

    result_cell = asyncio.run(
        myst_file_translator.translate_chunk_async(
            cell=cell,
            source_language=Language.ENGLISH,
            target_language=Language.FRENCH,
            relative_path="docs/example.md",
            vocab_list=None,
            tr=FailingTranslator(error),
        )
    )

    assert result_cell["source"] == chunk
    assert result_cell["metadata"].get("not-translated-due-to-exception") == "True"


def test_latex_chunk_metadata_tagged_on_failure():
    chunk = "\\section{Title}"
    cell = {"metadata": {}, "source": chunk}

    error = ChunkTranslationFailed(chunk, RuntimeError("boom"))

    result_cell = asyncio.run(
        latex_file_translator.translate_chunk_async(
            cell=cell,
            source_language=Language.ENGLISH,
            target_language=Language.FRENCH,
            relative_path="docs/example.md",
            vocab_list=None,
            tr=FailingTranslator(error),
        )
    )

    assert result_cell["source"] == chunk
    assert result_cell["metadata"].get("not-translated-due-to-exception") == "True"


def test_notebook_cell_metadata_tagged_on_failure():
    chunk = "Notebook cell text."
    cell = {
        "cell_type": "markdown",
        "metadata": {},
        "source": chunk,
    }

    error = ChunkTranslationFailed(chunk, RuntimeError("boom"))

    result_cell = asyncio.run(
        notebook_file_translator.translate_jupyter_cell_async(
            cell=cell,
            source_language=Language.ENGLISH,
            target_language=Language.FRENCH,
            vocab_list=None,
            tr=FailingTranslator(error),
            relative_path="docs/example.md",
        )
    )

    assert result_cell["source"] == chunk
    assert "not-translated-due-to-exception" in result_cell["metadata"].get("tags", [])


def test_oversized_typst_chunk_is_translated_via_internal_subchunks(monkeypatch):
    store = InMemoryStore()
    translator = ChunkTranslator(store, model_caller=None)

    calls: list[str] = []

    async def fake_run_with_caller(self, strategy, meta, caller):
        calls.append(meta.chunk)
        return f"[[{len(calls)}]]{meta.chunk}"

    monkeypatch.setattr(ChunkTranslator, "_run_with_caller", fake_run_with_caller)

    body = " ".join(["word"] * 1800)
    chunk = "#figure(caption: [A])[" + body + "]\n"
    meta = Meta(
        chunk=chunk,
        src_lang=Language.ENGLISH,
        tgt_lang=Language.FRENCH,
        doc_type=DocumentType.Typst,
        chunk_type=ChunkType.Typst,
        vocab=None,
        rel_path="docs/example.typ",
    )

    translated, from_cache = asyncio.run(translator.translate_or_fetch(meta))

    assert len(calls) > 1
    assert all(len(call) <= 2000 for call in calls)
    assert translated == "".join(f"[[{index + 1}]]{part}" for index, part in enumerate(calls))
    assert from_cache is False
    assert store.persisted[-1] == (chunk, translated)


def test_oversized_typst_chunk_from_cached_subchunks_skips_model(monkeypatch):
    body = " ".join(["word"] * 1800)
    chunk = "#figure(caption: [A])[" + body + "]\n"
    parts = _split_typst_chunk_for_internal_translation(chunk)
    assert len(parts) > 1

    cached_by_checksum = {
        calculate_checksum(part): f"<cached>{part}</cached>"
        for part in parts
    }
    store = InMemoryLookupStore(cached_by_checksum)
    translator = ChunkTranslator(store, model_caller=None)

    async def fail_if_called(self, strategy, meta, caller):
        raise AssertionError("model must not be called when all subchunks are cached")

    monkeypatch.setattr(ChunkTranslator, "_run_with_caller", fail_if_called)

    meta = Meta(
        chunk=chunk,
        src_lang=Language.ENGLISH,
        tgt_lang=Language.FRENCH,
        doc_type=DocumentType.Typst,
        chunk_type=ChunkType.Typst,
        vocab=None,
        rel_path="docs/example.typ",
    )

    translated, from_cache = asyncio.run(translator.translate_or_fetch(meta))

    assert translated == "".join(cached_by_checksum[calculate_checksum(part)] for part in parts)
    assert from_cache is True
    assert store.persisted[-1][0] == chunk
    assert store.persisted[-1][1] == translated


def test_typst_internal_subchunking_keeps_raw_block_atomic_in_command_body():
    raw = "```python\n" + "print('x')\n" * 220 + "```\n"
    chunk = "#figure(caption: [Cap])[" + raw + "]\n" + ("tail " * 350)

    parts = _split_typst_chunk_for_internal_translation(chunk)

    assert len(parts) >= 3
    assert "".join(parts) == chunk

    raw_parts = [part for part in parts if "```python\n" in part]
    assert len(raw_parts) == 1
    assert raw_parts[0].startswith("```python\n")
    assert raw_parts[0].endswith("```")
    assert raw_parts[0].count("print('x')\n") == 220

    _, _, ph_only = typst_to_xml_mod(raw_parts[0])
    assert ph_only is True


def test_typst_internal_subchunking_does_not_split_inline_math_placeholder():
    chunk = ("alpha " * 330) + "$x + y = z$" + (" beta" * 330)

    parts = _split_typst_chunk_for_internal_translation(chunk)

    assert len(parts) >= 2
    assert "".join(parts) == chunk
    assert any("$x + y = z$" in part for part in parts)
    assert not any("$x + y" in part and "$x + y = z$" not in part for part in parts)
    assert not any("y = z$" in part and "$x + y = z$" not in part for part in parts)


def test_oversized_typst_subchunking_skips_model_for_placeholder_only_subchunks(monkeypatch):
    store = InMemoryStore()
    translator = ChunkTranslator(store, model_caller=None)

    calls: list[str] = []

    async def fake_run_with_caller(self, strategy, meta, caller):
        calls.append(meta.chunk)
        return meta.chunk

    monkeypatch.setattr(ChunkTranslator, "_run_with_caller", fake_run_with_caller)

    raw = "```python\n" + "print('x')\n" * 220 + "```\n"
    chunk = "#figure(caption: [Cap])[" + raw + "]\n" + ("tail " * 350)
    meta = Meta(
        chunk=chunk,
        src_lang=Language.ENGLISH,
        tgt_lang=Language.FRENCH,
        doc_type=DocumentType.Typst,
        chunk_type=ChunkType.Typst,
        vocab=None,
        rel_path="docs/example.typ",
    )

    translated, from_cache = asyncio.run(translator.translate_or_fetch(meta))

    assert translated == chunk
    assert from_cache is False
    assert len(calls) == 2
    assert all("```python\n" not in call for call in calls)


# ---------------------------------------------------------------------------
# TranslationStats tracking
# ---------------------------------------------------------------------------

import xml.etree.ElementTree as ET


def _make_myst_meta(chunk: str = "Hello world.") -> Meta:
    return Meta(
        chunk=chunk,
        src_lang=Language.ENGLISH,
        tgt_lang=Language.FRENCH,
        doc_type=DocumentType.Markdown,
        chunk_type=ChunkType.Myst,
        vocab=None,
        rel_path="docs/test.md",
    )


def _make_typst_meta(chunk: str) -> Meta:
    return Meta(
        chunk=chunk,
        src_lang=Language.ENGLISH,
        tgt_lang=Language.FRENCH,
        doc_type=DocumentType.Typst,
        chunk_type=ChunkType.Typst,
        vocab=None,
        rel_path="docs/test.typ",
    )


class TestTranslationStats:
    """Tests for TranslationStats tracking in ChunkTranslator.translate_or_fetch."""

    # ------------------------------------------------------------------
    # TranslationStats dataclass itself
    # ------------------------------------------------------------------

    def test_stats_add(self):
        a = TranslationStats(chunks_from_cache=2, chunks_translated=3, chunks_passed_to_reasoning=1, chunks_failed=1)
        b = TranslationStats(chunks_from_cache=1, chunks_translated=0, chunks_passed_to_reasoning=2, chunks_failed=2)
        c = a + b
        assert c.chunks_from_cache == 3
        assert c.chunks_translated == 3
        assert c.chunks_passed_to_reasoning == 3
        assert c.chunks_failed == 3

    def test_stats_total_property(self):
        stats = TranslationStats(chunks_from_cache=2, chunks_translated=3, chunks_failed=1)
        assert stats.total == 6

    def test_stats_default_zeros(self):
        stats = TranslationStats()
        assert stats.chunks_from_cache == 0
        assert stats.chunks_translated == 0
        assert stats.chunks_passed_to_reasoning == 0
        assert stats.chunks_failed == 0
        assert stats.total == 0

    # ------------------------------------------------------------------
    # Passthrough cases — no stats change
    # ------------------------------------------------------------------

    def test_whitespace_chunk_does_not_affect_stats(self):
        translator = ChunkTranslator(InMemoryStore())
        asyncio.run(translator.translate_or_fetch(_make_myst_meta("   \n   ")))
        assert translator.stats.chunks_from_cache == 0
        assert translator.stats.chunks_translated == 0
        assert translator.stats.chunks_failed == 0

    def test_placeholder_only_chunk_does_not_affect_stats(self):
        translator = ChunkTranslator(InMemoryStore())
        # Code cell is ph_only for JupyterNotebook/Myst chunks
        chunk = "```{code-cell} python3\nprint('Hello')\n```\n"
        meta = Meta(
            chunk=chunk,
            src_lang=Language.ENGLISH,
            tgt_lang=Language.FRENCH,
            doc_type=DocumentType.JupyterNotebook,
            chunk_type=ChunkType.Myst,
            vocab=None,
            rel_path="docs/test.md",
        )
        asyncio.run(translator.translate_or_fetch(meta))
        assert translator.stats.chunks_from_cache == 0
        assert translator.stats.chunks_translated == 0
        assert translator.stats.chunks_failed == 0

    # ------------------------------------------------------------------
    # Cache hit
    # ------------------------------------------------------------------

    def test_cache_hit_increments_from_cache(self):
        chunk = "Hello world."
        store = InMemoryLookupStore({calculate_checksum(chunk): "Bonjour monde."})
        translator = ChunkTranslator(store)
        asyncio.run(translator.translate_or_fetch(_make_myst_meta(chunk)))
        assert translator.stats.chunks_from_cache == 1
        assert translator.stats.chunks_translated == 0
        assert translator.stats.chunks_failed == 0
        assert translator.stats.chunks_passed_to_reasoning == 0

    def test_multiple_cache_hits_accumulate(self):
        chunks = ["Hello.", "World.", "Goodbye."]
        store = InMemoryLookupStore({calculate_checksum(c): f"<{c}>" for c in chunks})
        translator = ChunkTranslator(store)
        for c in chunks:
            asyncio.run(translator.translate_or_fetch(_make_myst_meta(c)))
        assert translator.stats.chunks_from_cache == 3
        assert translator.stats.chunks_translated == 0

    # ------------------------------------------------------------------
    # Standard model success
    # ------------------------------------------------------------------

    def test_standard_model_success_increments_translated(self, monkeypatch):
        translator = ChunkTranslator(InMemoryStore())

        async def succeed(self, strategy, meta, caller):
            return "Bonjour monde."
        monkeypatch.setattr(ChunkTranslator, "_run_with_caller", succeed)

        asyncio.run(translator.translate_or_fetch(_make_myst_meta()))

        assert translator.stats.chunks_translated == 1
        assert translator.stats.chunks_from_cache == 0
        assert translator.stats.chunks_failed == 0
        assert translator.stats.chunks_passed_to_reasoning == 0

    def test_standard_model_succeeds_after_xml_retry_no_reasoning_counted(self, monkeypatch):
        """XML error on attempt 1, success on attempt 2 (still standard): no reasoning counted."""
        reasoning_caller = object()
        translator = ChunkTranslator(InMemoryStore(), reasoning_caller=reasoning_caller, xml_retries_before_reasoning=2)

        attempt = [0]
        async def xml_then_succeed(self, strategy, meta, caller):
            attempt[0] += 1
            if attempt[0] == 1:
                raise ET.ParseError("bad xml")
            return "Bonjour."
        monkeypatch.setattr(ChunkTranslator, "_run_with_caller", xml_then_succeed)

        asyncio.run(translator.translate_or_fetch(_make_myst_meta()))

        assert translator.stats.chunks_translated == 1
        assert translator.stats.chunks_passed_to_reasoning == 0
        assert translator.stats.chunks_failed == 0

    # ------------------------------------------------------------------
    # Reasoning model fallback
    # ------------------------------------------------------------------

    def test_reasoning_model_success_after_xml_failures(self, monkeypatch):
        """Standard model fails twice with XML error, reasoning model succeeds."""
        reasoning_caller = object()
        translator = ChunkTranslator(InMemoryStore(), reasoning_caller=reasoning_caller, xml_retries_before_reasoning=2)

        attempt = [0]
        async def xml_then_reasoning_success(self, strategy, meta, caller):
            attempt[0] += 1
            if attempt[0] < 3:
                raise ET.ParseError("bad xml")
            return "Bonjour."
        monkeypatch.setattr(ChunkTranslator, "_run_with_caller", xml_then_reasoning_success)

        asyncio.run(translator.translate_or_fetch(_make_myst_meta()))

        assert translator.stats.chunks_translated == 1
        assert translator.stats.chunks_passed_to_reasoning == 1
        assert translator.stats.chunks_failed == 0

    def test_reasoning_model_also_fails_after_xml_failures(self, monkeypatch):
        """All attempts fail with XML errors, including the reasoning model on the final attempt."""
        reasoning_caller = object()
        translator = ChunkTranslator(InMemoryStore(), reasoning_caller=reasoning_caller, xml_retries_before_reasoning=2)

        async def always_bad_xml(self, strategy, meta, caller):
            raise ET.ParseError("bad xml")
        monkeypatch.setattr(ChunkTranslator, "_run_with_caller", always_bad_xml)

        with pytest.raises(ChunkTranslationFailed):
            asyncio.run(translator.translate_or_fetch(_make_myst_meta()))

        assert translator.stats.chunks_failed == 1
        assert translator.stats.chunks_passed_to_reasoning == 1
        assert translator.stats.chunks_translated == 0

    def test_xml_retries_zero_always_uses_reasoning_on_success(self, monkeypatch):
        """With xml_retries_before_reasoning=0, the only attempt uses the reasoning model."""
        reasoning_caller = object()
        translator = ChunkTranslator(InMemoryStore(), reasoning_caller=reasoning_caller, xml_retries_before_reasoning=0)

        async def succeed(self, strategy, meta, caller):
            return "Bonjour."
        monkeypatch.setattr(ChunkTranslator, "_run_with_caller", succeed)

        asyncio.run(translator.translate_or_fetch(_make_myst_meta()))

        assert translator.stats.chunks_translated == 1
        assert translator.stats.chunks_passed_to_reasoning == 1
        assert translator.stats.chunks_failed == 0

    def test_xml_retries_zero_reasoning_fails(self, monkeypatch):
        """With xml_retries_before_reasoning=0, one attempt with reasoning, which fails."""
        reasoning_caller = object()
        translator = ChunkTranslator(InMemoryStore(), reasoning_caller=reasoning_caller, xml_retries_before_reasoning=0)

        async def bad_xml(self, strategy, meta, caller):
            raise ET.ParseError("bad xml")
        monkeypatch.setattr(ChunkTranslator, "_run_with_caller", bad_xml)

        with pytest.raises(ChunkTranslationFailed):
            asyncio.run(translator.translate_or_fetch(_make_myst_meta()))

        assert translator.stats.chunks_failed == 1
        assert translator.stats.chunks_passed_to_reasoning == 1

    # ------------------------------------------------------------------
    # Non-XML exceptions
    # ------------------------------------------------------------------

    def test_non_xml_exception_before_final_attempt_no_reasoning_counted(self, monkeypatch):
        """ApiCallError on attempt 1 (standard) immediately fails — reasoning never reached."""
        reasoning_caller = object()
        translator = ChunkTranslator(InMemoryStore(), reasoning_caller=reasoning_caller, xml_retries_before_reasoning=2)

        async def api_error(self, strategy, meta, caller):
            raise ApiCallError("api error")
        monkeypatch.setattr(ChunkTranslator, "_run_with_caller", api_error)

        with pytest.raises(ChunkTranslationFailed):
            asyncio.run(translator.translate_or_fetch(_make_myst_meta()))

        assert translator.stats.chunks_failed == 1
        assert translator.stats.chunks_passed_to_reasoning == 0

    def test_non_xml_exception_on_final_reasoning_attempt(self, monkeypatch):
        """XML errors exhaust standard retries, then reasoning model raises ApiCallError."""
        reasoning_caller = object()
        translator = ChunkTranslator(InMemoryStore(), reasoning_caller=reasoning_caller, xml_retries_before_reasoning=1)

        attempt = [0]
        async def xml_then_api_error(self, strategy, meta, caller):
            attempt[0] += 1
            if attempt[0] == 1:
                raise ET.ParseError("bad xml")
            raise ApiCallError("api error on reasoning")
        monkeypatch.setattr(ChunkTranslator, "_run_with_caller", xml_then_api_error)

        with pytest.raises(ChunkTranslationFailed):
            asyncio.run(translator.translate_or_fetch(_make_myst_meta()))

        assert translator.stats.chunks_failed == 1
        assert translator.stats.chunks_passed_to_reasoning == 1

    # ------------------------------------------------------------------
    # No reasoning caller configured
    # ------------------------------------------------------------------

    def test_no_reasoning_caller_xml_failure_no_reasoning_counted(self, monkeypatch):
        """When no reasoning caller is set, XML failures should not affect chunks_passed_to_reasoning."""
        # no reasoning caller — standard model used for all attempts
        translator = ChunkTranslator(InMemoryStore(), xml_retries_before_reasoning=1)

        async def always_bad_xml(self, strategy, meta, caller):
            raise ET.ParseError("bad xml")
        monkeypatch.setattr(ChunkTranslator, "_run_with_caller", always_bad_xml)

        with pytest.raises(ChunkTranslationFailed):
            asyncio.run(translator.translate_or_fetch(_make_myst_meta()))

        assert translator.stats.chunks_failed == 1
        assert translator.stats.chunks_passed_to_reasoning == 0

    def test_no_reasoning_caller_success_no_reasoning_counted(self, monkeypatch):
        """When no reasoning caller is set, a successful translation should not affect chunks_passed_to_reasoning."""
        translator = ChunkTranslator(InMemoryStore(), xml_retries_before_reasoning=0)

        async def succeed(self, strategy, meta, caller):
            return "Bonjour."
        monkeypatch.setattr(ChunkTranslator, "_run_with_caller", succeed)

        asyncio.run(translator.translate_or_fetch(_make_myst_meta()))

        assert translator.stats.chunks_translated == 1
        assert translator.stats.chunks_passed_to_reasoning == 0

    # ------------------------------------------------------------------
    # Multiple chunks accumulate correctly
    # ------------------------------------------------------------------

    def test_mixed_outcomes_across_chunks_accumulate(self, monkeypatch):
        """Cache hit + standard success + reasoning failure = correct totals."""
        chunk_cached = "I am cached."
        chunk_ok = "Translate me."
        chunk_fail = "I will fail."

        store = InMemoryLookupStore({calculate_checksum(chunk_cached): "Je suis en cache."})
        reasoning_caller = object()
        translator = ChunkTranslator(store, reasoning_caller=reasoning_caller, xml_retries_before_reasoning=2)

        async def by_chunk(self, strategy, meta, caller):
            if meta.chunk == chunk_ok:
                return "Traduit."
            raise ET.ParseError("bad xml")  # chunk_fail fails all 3 attempts
        monkeypatch.setattr(ChunkTranslator, "_run_with_caller", by_chunk)

        asyncio.run(translator.translate_or_fetch(_make_myst_meta(chunk_cached)))
        asyncio.run(translator.translate_or_fetch(_make_myst_meta(chunk_ok)))
        with pytest.raises(ChunkTranslationFailed):
            asyncio.run(translator.translate_or_fetch(_make_myst_meta(chunk_fail)))

        assert translator.stats.chunks_from_cache == 1
        assert translator.stats.chunks_translated == 1
        assert translator.stats.chunks_failed == 1
        assert translator.stats.chunks_passed_to_reasoning == 1  # only chunk_fail reached reasoning
        assert translator.stats.total == 3

    # ------------------------------------------------------------------
    # Oversized Typst: stats tracked at parent level, not per-subchunk
    # ------------------------------------------------------------------

    def _make_oversized_typst_chunk(self) -> str:
        body = " ".join(["word"] * 1800)
        return "#figure(caption: [A])[" + body + "]\n"

    def test_oversized_typst_translated_counted_once_not_per_subchunk(self, monkeypatch):
        """A translated oversized Typst chunk counts as 1 translated chunk, not N subchunks."""
        store = InMemoryStore()
        translator = ChunkTranslator(store)

        call_count = [0]
        async def succeed(self, strategy, meta, caller):
            call_count[0] += 1
            return f"[t{call_count[0]}]"
        monkeypatch.setattr(ChunkTranslator, "_run_with_caller", succeed)

        chunk = self._make_oversized_typst_chunk()
        asyncio.run(translator.translate_or_fetch(_make_typst_meta(chunk)))

        assert call_count[0] > 1, "must have split into subchunks"
        assert translator.stats.chunks_translated == 1
        assert translator.stats.chunks_from_cache == 0
        assert translator.stats.chunks_failed == 0

    def test_oversized_typst_cached_subchunks_counted_once(self, monkeypatch):
        """When all subchunks are cached, the parent counts as 1 cache hit, not N."""
        chunk = self._make_oversized_typst_chunk()
        parts = _split_typst_chunk_for_internal_translation(chunk)
        assert len(parts) > 1

        store = InMemoryLookupStore({calculate_checksum(p): f"<{i}>" for i, p in enumerate(parts)})
        translator = ChunkTranslator(store)

        async def fail_if_called(self, strategy, meta, caller):
            raise AssertionError("model must not be called when all subchunks are cached")
        monkeypatch.setattr(ChunkTranslator, "_run_with_caller", fail_if_called)

        asyncio.run(translator.translate_or_fetch(_make_typst_meta(chunk)))

        assert translator.stats.chunks_from_cache == 1
        assert translator.stats.chunks_translated == 0
        assert translator.stats.chunks_failed == 0

    def test_oversized_typst_failure_counted_once_not_double(self, monkeypatch):
        """A failing oversized Typst chunk counts as 1 failure, not 2 (subchunk + parent)."""
        translator = ChunkTranslator(InMemoryStore())

        async def api_error(self, strategy, meta, caller):
            raise ApiCallError("api error")
        monkeypatch.setattr(ChunkTranslator, "_run_with_caller", api_error)

        chunk = self._make_oversized_typst_chunk()
        with pytest.raises(ChunkTranslationFailed):
            asyncio.run(translator.translate_or_fetch(_make_typst_meta(chunk)))

        assert translator.stats.chunks_failed == 1
        assert translator.stats.chunks_translated == 0
