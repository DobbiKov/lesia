"""Tests for `translate` without --to: translates to all configured target languages."""

from unittest.mock import AsyncMock

import pytest
from typer.testing import CliRunner

from cli import app
from lesia.project_manager import Project, init_project
from lesia.translator_retrieval import TranslationStats

runner = CliRunner()


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return init_project("proj", str(tmp_path))


def _setup_two_targets(tmp_path):
    """Project with English source, French + Spanish targets, one translatable file."""
    (tmp_path / "src_en").mkdir()
    (tmp_path / "tgt_fr").mkdir()
    (tmp_path / "tgt_es").mkdir()
    (tmp_path / "src_en" / "doc.txt").write_text("Hello world", encoding="utf-8")

    runner.invoke(app, ["source", "add", "src_en", "English"])
    runner.invoke(app, ["target", "add", "tgt_fr", "French"])
    runner.invoke(app, ["target", "add", "tgt_es", "Spanish"])
    runner.invoke(app, ["file", "add", "src_en/doc.txt"])


def test_translate_all_without_to_translates_every_target(project, tmp_path, monkeypatch):
    _setup_two_targets(tmp_path)
    mock = AsyncMock(return_value=TranslationStats())
    monkeypatch.setattr(Project, "translate_all_for_language", mock)

    result = runner.invoke(app, ["translate", "--all"])

    assert result.exit_code == 0
    langs = [str(c.args[0]) for c in mock.await_args_list]
    assert langs == ["French", "Spanish"]
    assert "=== Translating to French ===" in result.output
    assert "=== Translating to Spanish ===" in result.output


def test_translate_file_without_to_translates_every_target(project, tmp_path, monkeypatch):
    _setup_two_targets(tmp_path)
    mock = AsyncMock(return_value=TranslationStats())
    monkeypatch.setattr(Project, "translate_single_file", mock)

    result = runner.invoke(app, ["translate", "src_en/doc.txt"])

    assert result.exit_code == 0
    langs = [str(c.args[1]) for c in mock.await_args_list]
    assert langs == ["French", "Spanish"]


def test_translate_without_to_and_no_targets_errors(project, tmp_path):
    result = runner.invoke(app, ["translate", "--all"])
    assert result.exit_code == 1
    assert "No target languages configured" in result.output


def test_translate_with_to_translates_only_that_language(project, tmp_path, monkeypatch):
    _setup_two_targets(tmp_path)
    mock = AsyncMock(return_value=TranslationStats())
    monkeypatch.setattr(Project, "translate_all_for_language", mock)

    result = runner.invoke(app, ["translate", "--to", "French", "--all"])

    assert result.exit_code == 0
    langs = [str(c.args[0]) for c in mock.await_args_list]
    assert langs == ["French"]
    assert "=== Translating to" not in result.output
