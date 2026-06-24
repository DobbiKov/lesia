"""Tests verifying that --use-reasoning-model routes to the correct
LLM service/model and uses the correct API key."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from trans_lib.constants import CONF_DIR
from trans_lib.enums import Language
from trans_lib.project_config_models import ProjectConfig
from trans_lib.project_manager import Project
import trans_lib.project_runtime as project_runtime
import trans_lib.doc_translator as doc_translator


CASUAL_SERVICE = "google"
CASUAL_MODEL = "gemini-2.0-flash"
REASONING_SERVICE = "anthropic"
REASONING_MODEL = "claude-3-7-sonnet"
CASUAL_KEY = "casual-key-123"
REASONING_KEY = "reasoning-key-456"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_project(tmp_path: Path, with_reasoning: bool = True) -> tuple[Project, Path]:
    """Create a minimal project with one translatable .md file."""
    project_root = tmp_path / "proj"
    src_dir = project_root / "src_en"
    tgt_dir = project_root / "tgt_fr"
    src_dir.mkdir(parents=True)
    tgt_dir.mkdir(parents=True)
    (project_root / CONF_DIR).mkdir(parents=True)

    source_file = src_dir / "doc.md"
    source_file.write_text("Hello world.", encoding="utf-8")

    config = ProjectConfig.new(project_name="proj")
    config.set_runtime_root_path(project_root)
    config.set_src_dir_config(src_dir, Language.ENGLISH)
    config.add_lang_dir_config(tgt_dir, Language.FRENCH)
    config.make_file_translatable(source_file, True)
    config.set_llm_service_with_model(CASUAL_SERVICE, CASUAL_MODEL)
    if with_reasoning:
        config.set_llm_reasoning_service_with_model(REASONING_SERVICE, REASONING_MODEL)

    return Project(project_root, config), source_file


def _run_translate_single_file(
    tmp_path: Path,
    use_reasoning_model: bool,
    with_reasoning: bool = True,
) -> tuple:
    """Run translate_single_file with a mocked translate_file_to_file_async.
    Returns the call_args of the mock."""
    project, source_file = _make_project(tmp_path, with_reasoning=with_reasoning)
    mock_fn = AsyncMock()

    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(doc_translator, "translate_file_to_file_async", mock_fn)
        asyncio.run(
            project_runtime.translate_single_file(
                project, str(source_file), Language.FRENCH, None,
                use_reasoning_model=use_reasoning_model,
            )
        )

    return mock_fn.call_args


# ---------------------------------------------------------------------------
# project_runtime: service/model routing
# ---------------------------------------------------------------------------

class TestProjectRuntimeModelRouting:
    """Verify which service/model args are forwarded to translate_file_to_file_async."""

    def test_regular_mode_passes_casual_as_main(self, tmp_path):
        call_args = _run_translate_single_file(tmp_path, use_reasoning_model=False)
        args, kwargs = call_args
        # positional: root, src, src_lang, tgt, tgt_lang, rel_path, vocab, service, model, reasoning_service, reasoning_model
        assert args[7] == CASUAL_SERVICE
        assert args[8] == CASUAL_MODEL
        assert args[9] == REASONING_SERVICE
        assert args[10] == REASONING_MODEL

    def test_regular_mode_passes_use_reasoning_model_false(self, tmp_path):
        call_args = _run_translate_single_file(tmp_path, use_reasoning_model=False)
        _, kwargs = call_args
        assert kwargs.get("use_reasoning_model") is False

    def test_reasoning_mode_swaps_reasoning_as_main(self, tmp_path):
        call_args = _run_translate_single_file(tmp_path, use_reasoning_model=True)
        args, kwargs = call_args
        assert args[7] == REASONING_SERVICE
        assert args[8] == REASONING_MODEL

    def test_reasoning_mode_clears_reasoning_slot(self, tmp_path):
        call_args = _run_translate_single_file(tmp_path, use_reasoning_model=True)
        args, _ = call_args
        assert args[9] is None
        assert args[10] is None

    def test_reasoning_mode_passes_use_reasoning_model_true(self, tmp_path):
        call_args = _run_translate_single_file(tmp_path, use_reasoning_model=True)
        _, kwargs = call_args
        assert kwargs.get("use_reasoning_model") is True

    def test_reasoning_mode_falls_back_to_casual_when_no_reasoning_configured(self, tmp_path):
        call_args = _run_translate_single_file(
            tmp_path, use_reasoning_model=True, with_reasoning=False
        )
        args, _ = call_args
        assert args[7] == CASUAL_SERVICE
        assert args[8] == CASUAL_MODEL


# ---------------------------------------------------------------------------
# project_runtime: translate_all_for_language threads the flag
# ---------------------------------------------------------------------------

class TestProjectRuntimeTranslateAll:
    """Verify translate_all_for_language passes use_reasoning_model to each file."""

    def test_reasoning_flag_forwarded_to_each_file(self, tmp_path):
        project, _ = _make_project(tmp_path, with_reasoning=True)
        mock_fn = AsyncMock()

        with pytest.MonkeyPatch().context() as mp:
            mp.setattr(doc_translator, "translate_file_to_file_async", mock_fn)
            asyncio.run(
                project_runtime.translate_all_for_language(
                    project, Language.FRENCH, None, use_reasoning_model=True
                )
            )

        assert mock_fn.called
        for call in mock_fn.call_args_list:
            args, kwargs = call
            assert args[7] == REASONING_SERVICE
            assert args[8] == REASONING_MODEL
            assert kwargs.get("use_reasoning_model") is True

    def test_regular_flag_forwarded_to_each_file(self, tmp_path):
        project, _ = _make_project(tmp_path, with_reasoning=True)
        mock_fn = AsyncMock()

        with pytest.MonkeyPatch().context() as mp:
            mp.setattr(doc_translator, "translate_file_to_file_async", mock_fn)
            asyncio.run(
                project_runtime.translate_all_for_language(
                    project, Language.FRENCH, None, use_reasoning_model=False
                )
            )

        assert mock_fn.called
        for call in mock_fn.call_args_list:
            args, kwargs = call
            assert args[7] == CASUAL_SERVICE
            assert args[8] == CASUAL_MODEL
            assert kwargs.get("use_reasoning_model") is False


# ---------------------------------------------------------------------------
# doc_translator: API key selection
# ---------------------------------------------------------------------------

class _MockLLMCaller:
    """Captures constructor args and never requires a token."""
    instances: list

    def __init__(self, service, model, api_key):
        self.__class__.instances.append({"service": service, "model": model, "api_key": api_key})

    def requires_token(self):
        return False


def _run_doc_translator(
    tmp_path: Path,
    monkeypatch,
    use_reasoning_model: bool,
    casual_key: str | None,
    reasoning_key: str | None,
) -> list[dict]:
    """Run translate_file_to_file_async with mocked LLMCaller and translators.
    Returns list of dicts with {service, model, api_key} per LLMCaller created."""
    src = tmp_path / "doc.md"
    src.write_text("Hello world.", encoding="utf-8")
    tgt = tmp_path / "tgt" / "doc.md"
    tgt.parent.mkdir(parents=True)

    _MockLLMCaller.instances = []

    monkeypatch.setattr(doc_translator, "LLM_API_KEY", casual_key)
    monkeypatch.setattr(doc_translator, "LLM_REASONING_API_KEY", reasoning_key)
    monkeypatch.setattr(doc_translator, "LLMCaller", _MockLLMCaller)
    monkeypatch.setattr(
        doc_translator.myst_file_translator, "translate_file_async", AsyncMock()
    )

    asyncio.run(doc_translator.translate_file_to_file_async(
        tmp_path, src, Language.ENGLISH, tgt, Language.FRENCH, "doc.md", None,
        CASUAL_SERVICE, CASUAL_MODEL,
        use_reasoning_model=use_reasoning_model,
    ))

    return list(_MockLLMCaller.instances)


class TestDocTranslatorApiKey:
    """Verify the correct API key is used for the main LLMCaller."""

    def test_regular_mode_uses_casual_key(self, tmp_path, monkeypatch):
        callers = _run_doc_translator(
            tmp_path, monkeypatch,
            use_reasoning_model=False,
            casual_key=CASUAL_KEY,
            reasoning_key=REASONING_KEY,
        )
        main = callers[0]
        assert main["api_key"] == CASUAL_KEY

    def test_reasoning_mode_uses_reasoning_key(self, tmp_path, monkeypatch):
        callers = _run_doc_translator(
            tmp_path, monkeypatch,
            use_reasoning_model=True,
            casual_key=CASUAL_KEY,
            reasoning_key=REASONING_KEY,
        )
        main = callers[0]
        assert main["api_key"] == REASONING_KEY

    def test_reasoning_mode_falls_back_to_casual_key_when_reasoning_key_not_set(
        self, tmp_path, monkeypatch
    ):
        callers = _run_doc_translator(
            tmp_path, monkeypatch,
            use_reasoning_model=True,
            casual_key=CASUAL_KEY,
            reasoning_key=None,
        )
        main = callers[0]
        assert main["api_key"] == CASUAL_KEY

    def test_regular_mode_no_reasoning_caller_created(self, tmp_path, monkeypatch):
        callers = _run_doc_translator(
            tmp_path, monkeypatch,
            use_reasoning_model=False,
            casual_key=CASUAL_KEY,
            reasoning_key=REASONING_KEY,
        )
        # no llm_reasoning_service/model passed → only main caller
        assert len(callers) == 1


# ---------------------------------------------------------------------------
# doc_translator: missing API key raises with correct message
# ---------------------------------------------------------------------------

class TestDocTranslatorApiKeyErrors:
    """Verify error messages name the correct env var when a key is absent."""

    def _make_requiring_caller(self):
        class RequiringCaller:
            instances: list = []

            def __init__(self, service, model, api_key):
                self.__class__.instances.append(api_key)

            def requires_token(self):
                return True  # always needs a key

        return RequiringCaller

    def test_regular_mode_missing_key_names_llm_api_key(self, tmp_path, monkeypatch):
        src = tmp_path / "doc.md"
        src.write_text("Hello.", encoding="utf-8")
        tgt = tmp_path / "tgt" / "doc.md"
        tgt.parent.mkdir(parents=True)

        monkeypatch.setattr(doc_translator, "LLM_API_KEY", None)
        monkeypatch.setattr(doc_translator, "LLM_REASONING_API_KEY", None)
        monkeypatch.setattr(doc_translator, "LLMCaller", self._make_requiring_caller())

        from trans_lib.errors import TranslationProcessError
        with pytest.raises(TranslationProcessError) as exc_info:
            asyncio.run(doc_translator.translate_file_to_file_async(
                tmp_path, src, Language.ENGLISH, tgt, Language.FRENCH, "doc.md", None,
                CASUAL_SERVICE, CASUAL_MODEL,
                use_reasoning_model=False,
            ))
        assert "LLM_API_KEY" in str(exc_info.value)
        assert "LLM_REASONING_API_KEY" not in str(exc_info.value)

    def test_reasoning_mode_missing_key_names_reasoning_api_key(self, tmp_path, monkeypatch):
        src = tmp_path / "doc.md"
        src.write_text("Hello.", encoding="utf-8")
        tgt = tmp_path / "tgt" / "doc.md"
        tgt.parent.mkdir(parents=True)

        monkeypatch.setattr(doc_translator, "LLM_API_KEY", None)
        monkeypatch.setattr(doc_translator, "LLM_REASONING_API_KEY", None)
        monkeypatch.setattr(doc_translator, "LLMCaller", self._make_requiring_caller())

        from trans_lib.errors import TranslationProcessError
        with pytest.raises(TranslationProcessError) as exc_info:
            asyncio.run(doc_translator.translate_file_to_file_async(
                tmp_path, src, Language.ENGLISH, tgt, Language.FRENCH, "doc.md", None,
                CASUAL_SERVICE, CASUAL_MODEL,
                use_reasoning_model=True,
            ))
        assert "LLM_REASONING_API_KEY" in str(exc_info.value)
