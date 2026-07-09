"""Tests for the default vocabulary file feature.

Covers:
- ProjectConfig  — set/get/unset vocab_file, path relativization, JSON round-trip
- project_runtime — config vocab used when no explicit vocab_list passed;
                    explicit vocab_list takes precedence over config vocab
- CLI            — set-vocab-file / unset-vocab-file commands and info output
"""

import asyncio
import csv
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from cli import app
from lesia.constants import CONF_DIR, CONFIG_FILENAME
from lesia.enums import Language
from lesia.project_config_io import write_project_config
from lesia.project_config_models import ProjectConfig
from lesia.project_manager import Project, init_project, load_project
from lesia.vocab_list import VocabList
import lesia.doc_translator as doc_translator
import lesia.project_runtime as project_runtime

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_vocab_csv(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path


_VOCAB_ROWS = [
    {"French": "pomme", "English": "apple"},
    {"French": "ordinateur", "English": "computer"},
]


def _make_project(tmp_path: Path) -> tuple[Project, Path]:
    project_root = tmp_path / "proj"
    src_dir = project_root / "src_fr"
    tgt_dir = project_root / "tgt_en"
    src_dir.mkdir(parents=True)
    tgt_dir.mkdir(parents=True)
    (project_root / CONF_DIR).mkdir(parents=True)

    source_file = src_dir / "doc.md"
    source_file.write_text("Bonjour.", encoding="utf-8")

    config = ProjectConfig.new(project_name="proj")
    config.set_runtime_root_path(project_root)
    config.set_src_dir_config(src_dir, Language.FRENCH)
    config.add_lang_dir_config(tgt_dir, Language.ENGLISH)
    config.make_file_translatable(source_file, True)
    config.set_llm_service_with_model("google", "gemini-2.0-flash")

    return Project(project_root, config), source_file


# ---------------------------------------------------------------------------
# ProjectConfig vocab_file methods
# ---------------------------------------------------------------------------

class TestProjectConfigVocabFile:

    def test_default_is_none(self, tmp_path):
        config = ProjectConfig.new("proj")
        config.set_runtime_root_path(tmp_path)
        assert config.vocab_file is None
        assert config.get_vocab_file_path() is None

    def test_set_inside_project_stored_as_relative(self, tmp_path):
        config = ProjectConfig.new("proj")
        config.set_runtime_root_path(tmp_path)
        config.set_vocab_file(tmp_path / "vocab.csv")
        assert config.vocab_file == Path("vocab.csv")

    def test_set_nested_path_stored_as_relative(self, tmp_path):
        config = ProjectConfig.new("proj")
        config.set_runtime_root_path(tmp_path)
        config.set_vocab_file(tmp_path / "data" / "vocab.csv")
        assert config.vocab_file == Path("data/vocab.csv")

    def test_set_outside_project_stored_as_absolute(self, tmp_path):
        project_root = tmp_path / "project"
        project_root.mkdir()
        outside = tmp_path / "vocab.csv"
        config = ProjectConfig.new("proj")
        config.set_runtime_root_path(project_root)
        config.set_vocab_file(outside)
        assert config.vocab_file == outside.resolve()

    def test_get_vocab_file_path_resolves_to_absolute(self, tmp_path):
        config = ProjectConfig.new("proj")
        config.set_runtime_root_path(tmp_path)
        config.set_vocab_file(tmp_path / "vocab.csv")
        assert config.get_vocab_file_path() == (tmp_path / "vocab.csv").resolve()

    def test_unset_clears_to_none(self, tmp_path):
        config = ProjectConfig.new("proj")
        config.set_runtime_root_path(tmp_path)
        config.set_vocab_file(tmp_path / "vocab.csv")
        config.unset_vocab_file()
        assert config.vocab_file is None
        assert config.get_vocab_file_path() is None

    def test_set_none_clears_field(self, tmp_path):
        config = ProjectConfig.new("proj")
        config.set_runtime_root_path(tmp_path)
        config.set_vocab_file(tmp_path / "vocab.csv")
        config.set_vocab_file(None)
        assert config.vocab_file is None

    def test_vocab_file_survives_json_round_trip(self, tmp_path):
        config = ProjectConfig.new("proj")
        config.set_runtime_root_path(tmp_path)
        config.set_vocab_file(tmp_path / "vocab.csv")

        config_file = tmp_path / CONF_DIR / CONFIG_FILENAME
        config_file.parent.mkdir(parents=True)
        write_project_config(config_file, config)

        reloaded = load_project(str(tmp_path))
        assert reloaded.config.get_vocab_file_path() == (tmp_path / "vocab.csv").resolve()

    def test_vocab_file_none_survives_json_round_trip(self, tmp_path):
        config = ProjectConfig.new("proj")
        config.set_runtime_root_path(tmp_path)

        config_file = tmp_path / CONF_DIR / CONFIG_FILENAME
        config_file.parent.mkdir(parents=True)
        write_project_config(config_file, config)

        reloaded = load_project(str(tmp_path))
        assert reloaded.config.get_vocab_file_path() is None


# ---------------------------------------------------------------------------
# project_runtime — vocab precedence
# ---------------------------------------------------------------------------

class TestProjectRuntimeVocabPrecedence:
    """Verify the config vocab is used when no explicit vocab is given,
    and that an explicit vocab_list always takes precedence."""

    def _run(self, tmp_path, vocab_list_arg, set_config_vocab):
        """Run translate_single_file with mocked translate_file_to_file_async.
        Returns the vocab_list positional argument received by the mock."""
        from lesia.translator_retrieval import TranslationStats

        project, source_file = _make_project(tmp_path)

        if set_config_vocab:
            vocab_csv = tmp_path / "proj" / "vocab.csv"
            _write_vocab_csv(vocab_csv, _VOCAB_ROWS)
            project.config.set_vocab_file(vocab_csv)

        mock_fn = AsyncMock(return_value=TranslationStats())

        with pytest.MonkeyPatch().context() as mp:
            mp.setattr(doc_translator, "translate_file_to_file_async", mock_fn)
            asyncio.run(
                project_runtime.translate_single_file(
                    project, str(source_file), Language.ENGLISH, vocab_list_arg,
                )
            )

        # vocab_list is the 7th positional arg (index 6)
        return mock_fn.call_args[0][6]

    def test_no_flag_no_config_vocab_is_none(self, tmp_path):
        received = self._run(tmp_path, vocab_list_arg=None, set_config_vocab=False)
        assert received is None

    def test_no_flag_config_vocab_is_loaded(self, tmp_path):
        received = self._run(tmp_path, vocab_list_arg=None, set_config_vocab=True)
        assert isinstance(received, VocabList)
        assert "pomme" in received.source_lang_terms
        assert "apple" in received.target_lang_terms

    def test_explicit_flag_overrides_config_vocab(self, tmp_path):
        explicit_vocab = VocabList(["chat"], ["cat"])
        received = self._run(tmp_path, vocab_list_arg=explicit_vocab, set_config_vocab=True)
        assert received is explicit_vocab

    def test_explicit_flag_used_when_no_config_vocab(self, tmp_path):
        explicit_vocab = VocabList(["chat"], ["cat"])
        received = self._run(tmp_path, vocab_list_arg=explicit_vocab, set_config_vocab=False)
        assert received is explicit_vocab

    def test_missing_config_vocab_file_is_skipped(self, tmp_path):
        """If the configured vocab file doesn't exist, vocab_list stays None."""
        project, source_file = _make_project(tmp_path)
        project.config.set_vocab_file(tmp_path / "proj" / "nonexistent.csv")

        from lesia.translator_retrieval import TranslationStats
        mock_fn = AsyncMock(return_value=TranslationStats())

        with pytest.MonkeyPatch().context() as mp:
            mp.setattr(doc_translator, "translate_file_to_file_async", mock_fn)
            asyncio.run(
                project_runtime.translate_single_file(
                    project, str(source_file), Language.ENGLISH, None,
                )
            )

        received = mock_fn.call_args[0][6]
        assert received is None


# ---------------------------------------------------------------------------
# CLI — set-vocab-file / unset-vocab-file
# ---------------------------------------------------------------------------

@pytest.fixture
def cli_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return init_project("proj", str(tmp_path))


class TestCliSetVocabFile:

    def test_set_existing_file_succeeds(self, cli_project, tmp_path):
        vocab = tmp_path / "vocab.csv"
        _write_vocab_csv(vocab, _VOCAB_ROWS)
        result = runner.invoke(app, ["set-vocab-file", str(vocab)])
        assert result.exit_code == 0
        reloaded = load_project(str(tmp_path))
        assert reloaded.config.get_vocab_file_path() == vocab.resolve()

    def test_set_nonexistent_file_warns_but_stores(self, cli_project, tmp_path):
        vocab = tmp_path / "missing.csv"
        result = runner.invoke(app, ["set-vocab-file", str(vocab)])
        assert result.exit_code == 0
        assert "Warning" in result.output or "warning" in result.output.lower()
        reloaded = load_project(str(tmp_path))
        assert reloaded.config.get_vocab_file_path() == vocab.resolve()

    def test_set_persisted_in_config_json(self, cli_project, tmp_path):
        vocab = tmp_path / "vocab.csv"
        _write_vocab_csv(vocab, _VOCAB_ROWS)
        runner.invoke(app, ["set-vocab-file", str(vocab)])
        raw = json.loads((tmp_path / CONF_DIR / CONFIG_FILENAME).read_text())
        assert raw.get("vocab_file") is not None


class TestCliUnsetVocabFile:

    def test_unset_clears_config(self, cli_project, tmp_path):
        vocab = tmp_path / "vocab.csv"
        _write_vocab_csv(vocab, _VOCAB_ROWS)
        runner.invoke(app, ["set-vocab-file", str(vocab)])

        result = runner.invoke(app, ["unset-vocab-file"])
        assert result.exit_code == 0

        reloaded = load_project(str(tmp_path))
        assert reloaded.config.get_vocab_file_path() is None

    def test_unset_when_not_set_succeeds(self, cli_project):
        result = runner.invoke(app, ["unset-vocab-file"])
        assert result.exit_code == 0


class TestCliInfoShowsVocabFile:

    def _setup_with_source(self, tmp_path):
        src = tmp_path / "src_fr"
        src.mkdir()
        runner.invoke(app, ["set-source", "src_fr", "French"])

    def test_info_shows_not_set_when_no_vocab_file(self, cli_project, tmp_path):
        self._setup_with_source(tmp_path)
        result = runner.invoke(app, ["info"])
        assert result.exit_code == 0
        assert "Default vocab file" in result.output
        assert "Not set" in result.output

    def test_info_shows_vocab_file_path_when_set(self, cli_project, tmp_path):
        self._setup_with_source(tmp_path)
        vocab = tmp_path / "vocab.csv"
        _write_vocab_csv(vocab, _VOCAB_ROWS)
        runner.invoke(app, ["set-vocab-file", str(vocab)])

        result = runner.invoke(app, ["info"])
        assert result.exit_code == 0
        assert str(vocab.resolve()) in result.output
