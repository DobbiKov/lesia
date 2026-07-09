"""Tests for the .env file feature.

Covers:
- _parse_env_file         — file parsing logic
- resolve_api_keys        — shell-vs-file precedence
- ProjectConfig           — set/get/unset env_file, path relativization, JSON round-trip
- translate_file_to_file_async — env_file threaded to resolve_api_keys
- project_runtime         — env_file kwarg forwarded to translate_file_to_file_async
- CLI                     — set-env-file / unset-env-file commands
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from typer.testing import CliRunner

from cli import app
from lesia.constants import CONF_DIR, CONFIG_FILENAME
from lesia.enums import Language
from lesia.project_config_io import write_project_config
from lesia.project_config_models import ProjectConfig
from lesia.project_manager import Project, init_project, load_project
from lesia.translator import _parse_env_file, resolve_api_keys
import lesia.doc_translator as doc_translator
import lesia.project_runtime as project_runtime

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_env_file(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def _make_project(tmp_path: Path) -> tuple[Project, Path]:
    """Minimal project with one translatable .md file."""
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
    config.set_llm_service_with_model("google", "gemini-2.0-flash")

    return Project(project_root, config), source_file


# ---------------------------------------------------------------------------
# _parse_env_file
# ---------------------------------------------------------------------------

class TestParseEnvFile:

    def test_simple_key_value(self, tmp_path):
        f = _write_env_file(tmp_path / ".env", "LLM_API_KEY=abc123\n")
        assert _parse_env_file(f) == {"LLM_API_KEY": "abc123"}

    def test_multiple_keys(self, tmp_path):
        f = _write_env_file(tmp_path / ".env",
                            "LLM_API_KEY=key1\nLLM_REASONING_API_KEY=key2\n")
        result = _parse_env_file(f)
        assert result["LLM_API_KEY"] == "key1"
        assert result["LLM_REASONING_API_KEY"] == "key2"

    def test_comments_ignored(self, tmp_path):
        f = _write_env_file(tmp_path / ".env",
                            "# this is a comment\nLLM_API_KEY=abc\n")
        assert _parse_env_file(f) == {"LLM_API_KEY": "abc"}

    def test_blank_lines_ignored(self, tmp_path):
        f = _write_env_file(tmp_path / ".env", "\n\nLLM_API_KEY=abc\n\n")
        assert _parse_env_file(f) == {"LLM_API_KEY": "abc"}

    def test_double_quoted_value(self, tmp_path):
        f = _write_env_file(tmp_path / ".env", 'LLM_API_KEY="my key"\n')
        assert _parse_env_file(f)["LLM_API_KEY"] == "my key"

    def test_single_quoted_value(self, tmp_path):
        f = _write_env_file(tmp_path / ".env", "LLM_API_KEY='my key'\n")
        assert _parse_env_file(f)["LLM_API_KEY"] == "my key"

    def test_value_with_equals_sign(self, tmp_path):
        # Only the first '=' is used as the separator; the rest is part of the value.
        f = _write_env_file(tmp_path / ".env", "LLM_API_KEY=abc=def\n")
        assert _parse_env_file(f)["LLM_API_KEY"] == "abc=def"

    def test_line_without_equals_ignored(self, tmp_path):
        f = _write_env_file(tmp_path / ".env", "NOEQUALS\nLLM_API_KEY=abc\n")
        assert _parse_env_file(f) == {"LLM_API_KEY": "abc"}

    def test_missing_file_returns_empty_dict(self, tmp_path):
        result = _parse_env_file(tmp_path / "nonexistent.env")
        assert result == {}

    def test_whitespace_around_key_and_value_stripped(self, tmp_path):
        f = _write_env_file(tmp_path / ".env", "  LLM_API_KEY  =  abc  \n")
        assert _parse_env_file(f)["LLM_API_KEY"] == "abc"


# ---------------------------------------------------------------------------
# resolve_api_keys
# ---------------------------------------------------------------------------

class TestResolveApiKeys:

    @pytest.fixture(autouse=True)
    def clear_shell_keys(self, monkeypatch):
        """Ensure shell env vars don't bleed in from the test runner's environment."""
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.delenv("LLM_REASONING_API_KEY", raising=False)

    def test_no_shell_no_file_returns_none_none(self):
        main, reasoning = resolve_api_keys(None)
        assert main is None
        assert reasoning is None

    def test_shell_only(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "shell_main")
        monkeypatch.setenv("LLM_REASONING_API_KEY", "shell_reasoning")
        main, reasoning = resolve_api_keys(None)
        assert main == "shell_main"
        assert reasoning == "shell_reasoning"

    def test_file_only(self, tmp_path):
        f = _write_env_file(tmp_path / ".env",
                            "LLM_API_KEY=file_main\nLLM_REASONING_API_KEY=file_reasoning\n")
        main, reasoning = resolve_api_keys(f)
        assert main == "file_main"
        assert reasoning == "file_reasoning"

    def test_shell_wins_over_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "shell_main")
        monkeypatch.setenv("LLM_REASONING_API_KEY", "shell_reasoning")
        f = _write_env_file(tmp_path / ".env",
                            "LLM_API_KEY=file_main\nLLM_REASONING_API_KEY=file_reasoning\n")
        main, reasoning = resolve_api_keys(f)
        assert main == "shell_main"
        assert reasoning == "shell_reasoning"

    def test_shell_main_overrides_file_main_but_file_reasoning_used(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "shell_main")
        f = _write_env_file(tmp_path / ".env", "LLM_REASONING_API_KEY=file_reasoning\n")
        main, reasoning = resolve_api_keys(f)
        assert main == "shell_main"
        assert reasoning == "file_reasoning"

    def test_shell_reasoning_overrides_file_reasoning(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LLM_REASONING_API_KEY", "shell_reasoning")
        f = _write_env_file(tmp_path / ".env",
                            "LLM_API_KEY=file_main\nLLM_REASONING_API_KEY=file_reasoning\n")
        _, reasoning = resolve_api_keys(f)
        assert reasoning == "shell_reasoning"

    def test_reasoning_key_falls_back_to_main_key(self, tmp_path):
        f = _write_env_file(tmp_path / ".env", "LLM_API_KEY=only_main\n")
        main, reasoning = resolve_api_keys(f)
        assert main == "only_main"
        assert reasoning == "only_main"

    def test_missing_env_file_returns_none_none(self, tmp_path):
        main, reasoning = resolve_api_keys(tmp_path / "nonexistent.env")
        assert main is None
        assert reasoning is None


# ---------------------------------------------------------------------------
# ProjectConfig env_file methods
# ---------------------------------------------------------------------------

class TestProjectConfigEnvFile:

    def test_default_is_none(self, tmp_path):
        config = ProjectConfig.new("proj")
        config.set_runtime_root_path(tmp_path)
        assert config.env_file is None
        assert config.get_env_file_path() is None

    def test_set_env_file_inside_project_stored_as_relative(self, tmp_path):
        config = ProjectConfig.new("proj")
        config.set_runtime_root_path(tmp_path)
        env_path = tmp_path / ".env"
        config.set_env_file(env_path)
        assert config.env_file == Path(".env")

    def test_set_env_file_nested_path_stored_as_relative(self, tmp_path):
        config = ProjectConfig.new("proj")
        config.set_runtime_root_path(tmp_path)
        env_path = tmp_path / "secrets" / "keys.env"
        config.set_env_file(env_path)
        assert config.env_file == Path("secrets/keys.env")

    def test_set_env_file_outside_project_stored_as_absolute(self, tmp_path):
        project_root = tmp_path / "project"
        project_root.mkdir()
        outside_env = tmp_path / "outside.env"
        config = ProjectConfig.new("proj")
        config.set_runtime_root_path(project_root)
        config.set_env_file(outside_env)
        assert config.env_file == outside_env.resolve()

    def test_get_env_file_path_resolves_relative(self, tmp_path):
        config = ProjectConfig.new("proj")
        config.set_runtime_root_path(tmp_path)
        config.set_env_file(tmp_path / ".env")
        assert config.get_env_file_path() == (tmp_path / ".env").resolve()

    def test_unset_env_file_clears_to_none(self, tmp_path):
        config = ProjectConfig.new("proj")
        config.set_runtime_root_path(tmp_path)
        config.set_env_file(tmp_path / ".env")
        config.unset_env_file()
        assert config.env_file is None
        assert config.get_env_file_path() is None

    def test_set_env_file_none_clears_field(self, tmp_path):
        config = ProjectConfig.new("proj")
        config.set_runtime_root_path(tmp_path)
        config.set_env_file(tmp_path / ".env")
        config.set_env_file(None)
        assert config.env_file is None

    def test_env_file_survives_json_round_trip(self, tmp_path):
        config = ProjectConfig.new("proj")
        config.set_runtime_root_path(tmp_path)
        config.set_env_file(tmp_path / ".env")

        config_file = tmp_path / CONF_DIR / CONFIG_FILENAME
        config_file.parent.mkdir(parents=True)
        write_project_config(config_file, config)

        reloaded = load_project(str(tmp_path))
        reloaded_path = reloaded.config.get_env_file_path()
        assert reloaded_path == (tmp_path / ".env").resolve()

    def test_env_file_none_survives_json_round_trip(self, tmp_path):
        config = ProjectConfig.new("proj")
        config.set_runtime_root_path(tmp_path)
        # env_file left as None

        config_file = tmp_path / CONF_DIR / CONFIG_FILENAME
        config_file.parent.mkdir(parents=True)
        write_project_config(config_file, config)

        reloaded = load_project(str(tmp_path))
        assert reloaded.config.get_env_file_path() is None


# ---------------------------------------------------------------------------
# translate_file_to_file_async — env_file threaded to resolve_api_keys
# ---------------------------------------------------------------------------

class TestDocTranslatorEnvFileThreading:
    """Verify env_file is forwarded from translate_file_to_file_async to resolve_api_keys."""

    def _run(self, tmp_path, env_file, monkeypatch):
        src = tmp_path / "doc.md"
        src.write_text("Hello.", encoding="utf-8")
        tgt = tmp_path / "tgt" / "doc.md"
        tgt.parent.mkdir(parents=True)

        captured = {}

        def fake_resolve(env_file=None):
            captured["env_file"] = env_file
            return ("key", "key")

        monkeypatch.setattr(doc_translator, "resolve_api_keys", fake_resolve)
        monkeypatch.setattr(doc_translator, "LLMCaller", _make_noop_caller())
        monkeypatch.setattr(
            doc_translator.myst_file_translator, "translate_file_async", AsyncMock()
        )

        asyncio.run(doc_translator.translate_file_to_file_async(
            tmp_path, src, Language.ENGLISH, tgt, Language.FRENCH, "doc.md",
            None, "google", "gemini-2.0-flash", env_file=env_file,
        ))
        return captured

    def test_no_env_file_passes_none(self, tmp_path, monkeypatch):
        captured = self._run(tmp_path, env_file=None, monkeypatch=monkeypatch)
        assert captured["env_file"] is None

    def test_env_file_path_forwarded(self, tmp_path, monkeypatch):
        env_path = tmp_path / ".env"
        captured = self._run(tmp_path, env_file=env_path, monkeypatch=monkeypatch)
        assert captured["env_file"] == env_path


def _make_noop_caller():
    class NoopCaller:
        def __init__(self, service, model, api_key):
            pass
        def requires_token(self):
            return False
    return NoopCaller


# ---------------------------------------------------------------------------
# project_runtime — env_file kwarg forwarded to translate_file_to_file_async
# ---------------------------------------------------------------------------

class TestProjectRuntimeEnvFileForwarding:
    """Verify project_runtime passes project.config.get_env_file_path() as env_file."""

    def _call_args(self, tmp_path, env_file_path=None):
        from lesia.translator_retrieval import TranslationStats
        project, source_file = _make_project(tmp_path)

        if env_file_path is not None:
            project.config.set_env_file(env_file_path)

        mock_fn = AsyncMock(return_value=TranslationStats())

        with pytest.MonkeyPatch().context() as mp:
            mp.setattr(doc_translator, "translate_file_to_file_async", mock_fn)
            asyncio.run(
                project_runtime.translate_single_file(
                    project, str(source_file), Language.FRENCH, None,
                )
            )

        return mock_fn.call_args

    def test_no_env_file_passes_none(self, tmp_path):
        _, kwargs = self._call_args(tmp_path, env_file_path=None)
        assert kwargs.get("env_file") is None

    def test_configured_env_file_forwarded(self, tmp_path):
        env_path = tmp_path / "proj" / ".env"
        _, kwargs = self._call_args(tmp_path, env_file_path=env_path)
        assert kwargs.get("env_file") == env_path.resolve()


# ---------------------------------------------------------------------------
# CLI — set-env-file / unset-env-file
# ---------------------------------------------------------------------------

@pytest.fixture
def cli_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return init_project("proj", str(tmp_path))


class TestCliSetEnvFile:

    def test_set_env_file_existing_file(self, cli_project, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("LLM_API_KEY=abc\n")
        result = runner.invoke(app, ["set-env-file", str(env_file)])
        assert result.exit_code == 0
        reloaded = load_project(str(tmp_path))
        assert reloaded.config.get_env_file_path() == env_file.resolve()

    def test_set_env_file_nonexistent_file_warns_but_succeeds(self, cli_project, tmp_path):
        env_file = tmp_path / "missing.env"
        result = runner.invoke(app, ["set-env-file", str(env_file)])
        assert result.exit_code == 0
        assert "Warning" in result.output or "warning" in result.output.lower()
        reloaded = load_project(str(tmp_path))
        assert reloaded.config.get_env_file_path() == env_file.resolve()

    def test_set_env_file_persisted_in_config(self, cli_project, tmp_path):
        import tomllib
        env_file = tmp_path / ".env"
        env_file.write_text("LLM_API_KEY=abc\n")
        runner.invoke(app, ["set-env-file", str(env_file)])

        config_file = tmp_path / CONF_DIR / CONFIG_FILENAME
        with config_file.open("rb") as f:
            raw = tomllib.load(f)
        assert raw.get("env_file") is not None


class TestCliUnsetEnvFile:

    def test_unset_env_file_clears_config(self, cli_project, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("LLM_API_KEY=abc\n")
        runner.invoke(app, ["set-env-file", str(env_file)])

        result = runner.invoke(app, ["unset-env-file"])
        assert result.exit_code == 0

        reloaded = load_project(str(tmp_path))
        assert reloaded.config.get_env_file_path() is None

    def test_unset_env_file_when_not_set_succeeds(self, cli_project):
        result = runner.invoke(app, ["unset-env-file"])
        assert result.exit_code == 0


class TestCliInfoShowsEnvFile:

    def test_info_shows_not_set_when_no_env_file(self, cli_project, tmp_path):
        src = tmp_path / "src_en"
        src.mkdir()
        runner.invoke(app, ["set-source", "src_en", "English"])

        result = runner.invoke(app, ["info"])
        assert result.exit_code == 0
        assert "Env file" in result.output
        assert "Not set" in result.output

    def test_info_shows_env_file_path_when_set(self, cli_project, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("LLM_API_KEY=abc\n")
        # Need a source dir set for info to print env file details
        src = tmp_path / "src_en"
        src.mkdir()
        runner.invoke(app, ["set-source", "src_en", "English"])
        runner.invoke(app, ["set-env-file", str(env_file)])

        result = runner.invoke(app, ["info"])
        assert result.exit_code == 0
        assert str(env_file.resolve()) in result.output
