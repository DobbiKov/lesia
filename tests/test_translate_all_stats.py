"""Tests for per-file callback and stats aggregation in translate_all_for_language."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, call

import pytest

from lesia.constants import CONF_DIR
from lesia.enums import Language
from lesia.errors import TranslateFileError, FileDoesNotExistError
from lesia.project_config_models import ProjectConfig
from lesia.project_manager import Project
from lesia.translator_retrieval import TranslationStats
import lesia.project_runtime as project_runtime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_project_with_files(tmp_path: Path, n_files: int) -> tuple[Project, list[Path]]:
    """Create a project with n_files translatable .md files."""
    project_root = tmp_path / "proj"
    src_dir = project_root / "src_en"
    tgt_dir = project_root / "tgt_fr"
    src_dir.mkdir(parents=True)
    tgt_dir.mkdir(parents=True)
    (project_root / CONF_DIR).mkdir(parents=True)

    config = ProjectConfig.new(project_name="proj")
    config.set_runtime_root_path(project_root)
    config.set_src_dir_config(src_dir, Language.ENGLISH)
    config.add_lang_dir_config(tgt_dir, Language.FRENCH)
    config.set_llm_service_with_model("google", "gemini-2.0-flash")

    source_files = []
    for i in range(n_files):
        f = src_dir / f"doc{i}.md"
        f.write_text(f"Hello {i}.", encoding="utf-8")
        config.make_file_translatable(f, True)
        source_files.append(f)

    return Project(project_root, config), source_files


def _make_stats(**kwargs) -> TranslationStats:
    return TranslationStats(**kwargs)


# ---------------------------------------------------------------------------
# on_file_translated callback
# ---------------------------------------------------------------------------

class TestOnFileTranslatedCallback:

    def test_callback_called_once_per_successful_file(self, tmp_path, monkeypatch):
        project, files = _make_project_with_files(tmp_path, n_files=3)
        monkeypatch.setattr(
            project_runtime, "translate_single_file",
            AsyncMock(return_value=_make_stats(chunks_translated=1)),
        )

        calls = []
        asyncio.run(project_runtime.translate_all_for_language(
            project, Language.FRENCH, None,
            on_file_translated=lambda fp, st: calls.append((fp, st)),
        ))

        assert len(calls) == 3

    def test_callback_receives_correct_file_path(self, tmp_path, monkeypatch):
        project, files = _make_project_with_files(tmp_path, n_files=2)
        monkeypatch.setattr(
            project_runtime, "translate_single_file",
            AsyncMock(return_value=_make_stats()),
        )

        received_paths = []
        asyncio.run(project_runtime.translate_all_for_language(
            project, Language.FRENCH, None,
            on_file_translated=lambda fp, st: received_paths.append(fp),
        ))

        # paths passed to callback match the translatable files
        assert set(received_paths) == set(files)

    def test_callback_receives_correct_stats_per_file(self, tmp_path, monkeypatch):
        project, files = _make_project_with_files(tmp_path, n_files=2)
        stats_a = _make_stats(chunks_translated=3)
        stats_b = _make_stats(chunks_from_cache=5)
        monkeypatch.setattr(
            project_runtime, "translate_single_file",
            AsyncMock(side_effect=[stats_a, stats_b]),
        )

        received_stats = []
        asyncio.run(project_runtime.translate_all_for_language(
            project, Language.FRENCH, None,
            on_file_translated=lambda fp, st: received_stats.append(st),
        ))

        assert received_stats == [stats_a, stats_b]

    def test_callback_not_called_for_failed_file(self, tmp_path, monkeypatch):
        project, files = _make_project_with_files(tmp_path, n_files=2)
        ok_stats = _make_stats(chunks_translated=2)
        monkeypatch.setattr(
            project_runtime, "translate_single_file",
            AsyncMock(side_effect=[
                TranslateFileError(FileDoesNotExistError("boom")),
                ok_stats,
            ]),
        )

        calls = []
        asyncio.run(project_runtime.translate_all_for_language(
            project, Language.FRENCH, None,
            on_file_translated=lambda fp, st: calls.append(st),
        ))

        # only the successful file triggers the callback
        assert calls == [ok_stats]

    def test_callback_not_called_when_no_translatable_files(self, tmp_path):
        project, _ = _make_project_with_files(tmp_path, n_files=0)

        calls = []
        asyncio.run(project_runtime.translate_all_for_language(
            project, Language.FRENCH, None,
            on_file_translated=lambda fp, st: calls.append(st),
        ))

        assert calls == []

    def test_no_callback_does_not_raise(self, tmp_path, monkeypatch):
        project, _ = _make_project_with_files(tmp_path, n_files=1)
        monkeypatch.setattr(
            project_runtime, "translate_single_file",
            AsyncMock(return_value=_make_stats(chunks_translated=1)),
        )

        # on_file_translated defaults to None — must not raise
        asyncio.run(project_runtime.translate_all_for_language(
            project, Language.FRENCH, None,
        ))


# ---------------------------------------------------------------------------
# Stats aggregation
# ---------------------------------------------------------------------------

class TestTranslateAllStatsAggregation:

    def test_total_stats_sum_of_per_file_stats(self, tmp_path, monkeypatch):
        project, _ = _make_project_with_files(tmp_path, n_files=3)
        monkeypatch.setattr(
            project_runtime, "translate_single_file",
            AsyncMock(side_effect=[
                _make_stats(chunks_from_cache=2, chunks_translated=3),
                _make_stats(chunks_from_cache=1, chunks_translated=5, chunks_failed=1),
                _make_stats(chunks_translated=2, chunks_passed_to_reasoning=1),
            ]),
        )

        total = asyncio.run(project_runtime.translate_all_for_language(
            project, Language.FRENCH, None,
        ))

        assert total.chunks_from_cache == 3
        assert total.chunks_translated == 10
        assert total.chunks_failed == 1
        assert total.chunks_passed_to_reasoning == 1

    def test_failed_files_excluded_from_total_stats(self, tmp_path, monkeypatch):
        project, _ = _make_project_with_files(tmp_path, n_files=2)
        monkeypatch.setattr(
            project_runtime, "translate_single_file",
            AsyncMock(side_effect=[
                TranslateFileError(FileDoesNotExistError("boom")),
                _make_stats(chunks_translated=4),
            ]),
        )

        total = asyncio.run(project_runtime.translate_all_for_language(
            project, Language.FRENCH, None,
        ))

        assert total.chunks_translated == 4
        assert total.total == 4

    def test_returns_empty_stats_when_no_translatable_files(self, tmp_path):
        project, _ = _make_project_with_files(tmp_path, n_files=0)

        total = asyncio.run(project_runtime.translate_all_for_language(
            project, Language.FRENCH, None,
        ))

        assert total == TranslationStats()

    def test_returns_empty_stats_when_all_files_fail(self, tmp_path, monkeypatch):
        project, _ = _make_project_with_files(tmp_path, n_files=2)
        monkeypatch.setattr(
            project_runtime, "translate_single_file",
            AsyncMock(side_effect=TranslateFileError(FileDoesNotExistError("boom"))),
        )

        total = asyncio.run(project_runtime.translate_all_for_language(
            project, Language.FRENCH, None,
        ))

        assert total == TranslationStats()


# ---------------------------------------------------------------------------
# Project.translate_all_for_language passes callback through
# ---------------------------------------------------------------------------

class TestProjectTranslateAllPassesCallback:

    def test_callback_forwarded_from_project_method(self, tmp_path, monkeypatch):
        project, _ = _make_project_with_files(tmp_path, n_files=2)
        monkeypatch.setattr(
            project_runtime, "translate_single_file",
            AsyncMock(return_value=_make_stats(chunks_translated=1)),
        )

        calls = []
        asyncio.run(project.translate_all_for_language(
            Language.FRENCH, None,
            on_file_translated=lambda fp, st: calls.append(st),
        ))

        assert len(calls) == 2
