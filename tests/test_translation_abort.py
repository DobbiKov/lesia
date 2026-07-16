"""Tests for fatal-vs-chunk-level error classification: service-level failures
(bad key, unknown model, unreachable service) abort the whole run with a clear
message instead of failing chunk by chunk."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from unified_model_caller.errors import (
    ApiCallError,
    ApiConnectionError,
    AuthenticationError,
    BadRequestError,
    InvalidResponseError,
    NotFoundError,
    RateLimitError,
)

from lesia import project_runtime
from lesia.enums import ChunkType, DocumentType, Language
from lesia.errors import ChunkTranslationFailed, TranslationAbortedError
from lesia.translator_retrieval import ChunkTranslator, Meta, TranslationStats


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _no_ph_only(monkeypatch):
    """ChunkType.Other has no placeholder syntax; skip the ph-only check."""
    monkeypatch.setattr(
        "lesia.translator_retrieval.chunk_contains_ph_only",
        lambda *args, **kwargs: False,
    )


class InMemoryStore:
    def lookup(self, src_checksum, src_lang, tgt_lang, relative_path):
        return None

    def persist_pair(self, *args, **kwargs):
        pass

    def get_best_pair_example_from_cache(self, lang, tgt_lang, txt, relative_path):
        return None


class RaisingCaller:
    service_name = "ilaas"
    model = "gpt-oss-120b"

    def __init__(self, error: Exception):
        self.error = error
        self.calls = 0

    def call(self, prompt: str) -> str:
        self.calls += 1
        raise self.error

    def wait_cooldown(self) -> None:
        pass


class FailThenSucceedCaller:
    service_name = "ilaas"
    model = "gpt-oss-120b"

    def __init__(self, error: Exception, fail_times: int):
        self.error = error
        self.fail_times = fail_times
        self.calls = 0

    def call(self, prompt: str) -> str:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise self.error
        return "<output>Translated chunk</output>"

    def wait_cooldown(self) -> None:
        pass


def _meta() -> Meta:
    return Meta(
        chunk="Some plain text to translate.",
        src_lang=Language.FRENCH,
        tgt_lang=Language.ENGLISH,
        doc_type=DocumentType.Other,
        chunk_type=ChunkType.Other,
        vocab=None,
        rel_path="docs/example.md",
    )


def _translate(caller) -> tuple[str, bool]:
    translator = ChunkTranslator(
        InMemoryStore(),
        caller,
        overload_retry_attempts=2,
        overload_retry_initial_delay=0.0,
        overload_retry_max_delay=0.0,
    )
    return asyncio.run(translator.translate_or_fetch(_meta()))


# ---------------------------------------------------------------------------
# Fatal errors abort with a helpful message
# ---------------------------------------------------------------------------

class TestFatalErrorsAbort:
    def test_authentication_error_aborts_with_key_hint(self):
        error = AuthenticationError(
            "The ilaas API returned HTTP 401: invalid key", service="ilaas", status_code=401
        )
        with pytest.raises(TranslationAbortedError) as excinfo:
            _translate(RaisingCaller(error))
        message = str(excinfo.value)
        assert "Authentication with service 'ilaas' failed" in message
        assert "API key" in message
        assert "HTTP 401" in message
        assert excinfo.value.original_exception is error

    def test_not_found_error_aborts_with_model_hint(self):
        error = NotFoundError(
            "The ilaas API returned HTTP 404: model not found", service="ilaas", status_code=404
        )
        with pytest.raises(TranslationAbortedError) as excinfo:
            _translate(RaisingCaller(error))
        message = str(excinfo.value)
        assert "Model 'gpt-oss-120b' was not found on service 'ilaas'" in message

    def test_connection_error_aborts_after_retries(self):
        caller = RaisingCaller(ApiConnectionError("Could not reach the ilaas API", service="ilaas"))
        with pytest.raises(TranslationAbortedError) as excinfo:
            _translate(caller)
        assert "Could not reach service 'ilaas'" in str(excinfo.value)
        assert caller.calls == 2  # exhausted the transient retries first

    def test_rate_limit_aborts_after_retries(self):
        caller = RaisingCaller(RateLimitError("HTTP 429", service="ilaas", status_code=429))
        with pytest.raises(TranslationAbortedError) as excinfo:
            _translate(caller)
        assert "kept failing after retries" in str(excinfo.value)
        assert caller.calls == 2

    def test_auth_error_does_not_burn_transient_retries(self):
        caller = RaisingCaller(AuthenticationError("HTTP 401", service="ilaas", status_code=401))
        with pytest.raises(TranslationAbortedError):
            _translate(caller)
        assert caller.calls == 1  # not retried: it can never succeed


# ---------------------------------------------------------------------------
# Transient errors still recover
# ---------------------------------------------------------------------------

class TestTransientErrorsRetry:
    def test_rate_limit_then_success_is_not_fatal(self):
        caller = FailThenSucceedCaller(
            RateLimitError("HTTP 429", service="ilaas", status_code=429), fail_times=1
        )
        translated, from_cache = _translate(caller)
        assert translated == "Translated chunk"
        assert from_cache is False
        assert caller.calls == 2

    def test_connection_blip_then_success_is_not_fatal(self):
        caller = FailThenSucceedCaller(
            ApiConnectionError("timeout", service="ilaas"), fail_times=1
        )
        translated, _ = _translate(caller)
        assert translated == "Translated chunk"


# ---------------------------------------------------------------------------
# Chunk-level errors keep the old behavior
# ---------------------------------------------------------------------------

class TestChunkLevelErrorsStayChunkLevel:
    @pytest.mark.parametrize("error", [
        ApiCallError("generic api failure", service="ilaas"),
        BadRequestError("HTTP 400: prompt too long", service="ilaas", status_code=400),
        InvalidResponseError("no text content", service="ilaas"),
    ])
    def test_raises_chunk_translation_failed(self, error):
        with pytest.raises(ChunkTranslationFailed) as excinfo:
            _translate(RaisingCaller(error))
        assert excinfo.value.original_exception is error


# ---------------------------------------------------------------------------
# translate_all_for_language stops the run on abort
# ---------------------------------------------------------------------------

class TestTranslateAllAborts:
    def test_abort_stops_remaining_files(self, tmp_path, monkeypatch):
        from tests.test_translate_all_stats import _make_project_with_files

        project, _ = _make_project_with_files(tmp_path, n_files=3)
        mock = AsyncMock(side_effect=TranslationAbortedError("Authentication failed"))
        monkeypatch.setattr(project_runtime, "translate_single_file", mock)

        with pytest.raises(TranslationAbortedError):
            asyncio.run(project_runtime.translate_all_for_language(project, Language.FRENCH, None))

        assert mock.await_count == 1  # aborted after the first file, others untouched
