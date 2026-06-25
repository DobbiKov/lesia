import pytest
from pathlib import Path
from typer.testing import CliRunner

from cli import app
from lesia.project_manager import init_project, load_project
from lesia.enums import Language

runner = CliRunner()


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return init_project("proj", str(tmp_path))


# --- add-lang ---

def test_cli_add_lang_success(project, tmp_path):
    result = runner.invoke(app, ["add-lang", "Catalan", "_ca"])
    assert result.exit_code == 0
    assert "Catalan" in result.output

    from lesia.project_manager import load_project
    reloaded = load_project(str(tmp_path))
    assert "Catalan" in reloaded.config.custom_languages


def test_cli_add_lang_duplicate_errors(project):
    runner.invoke(app, ["add-lang", "Catalan", "_ca"])
    result = runner.invoke(app, ["add-lang", "Catalan", "_ca"])
    assert result.exit_code == 1
    assert "already exists" in result.output


def test_cli_add_lang_predefined_errors(project):
    result = runner.invoke(app, ["add-lang", "French", "_fr"])
    assert result.exit_code == 1
    assert "predefined" in result.output


# --- remove-lang ---

def test_cli_remove_lang_success(project, tmp_path):
    runner.invoke(app, ["add-lang", "Catalan", "_ca"])
    result = runner.invoke(app, ["remove-lang", "Catalan"])
    assert result.exit_code == 0
    assert "Catalan" in result.output

    from lesia.project_manager import load_project
    reloaded = load_project(str(tmp_path))
    assert "Catalan" not in reloaded.config.custom_languages


def test_cli_remove_lang_not_in_config_errors(project):
    result = runner.invoke(app, ["remove-lang", "Klingon"])
    assert result.exit_code == 1
    assert "not in the config" in result.output


def test_cli_remove_lang_predefined_errors(project):
    result = runner.invoke(app, ["remove-lang", "French"])
    assert result.exit_code == 1
    assert "predefined" in result.output


# --- set-source with custom languages ---

def test_cli_set_source_with_predefined_language(project, tmp_path):
    src_dir = tmp_path / "src_en"
    src_dir.mkdir()

    result = runner.invoke(app, ["set-source", "src_en", "English"])
    assert result.exit_code == 0
    assert "English" in result.output

    reloaded = load_project(str(tmp_path))
    assert reloaded.config.src_dir is not None
    assert reloaded.config.src_dir.language == "English"


def test_cli_set_source_with_custom_language(project, tmp_path):
    src_dir = tmp_path / "src_ca"
    src_dir.mkdir()
    runner.invoke(app, ["add-lang", "Catalan", "_ca"])

    result = runner.invoke(app, ["set-source", "src_ca", "Catalan"])
    assert result.exit_code == 0
    assert "Catalan" in result.output

    reloaded = load_project(str(tmp_path))
    assert reloaded.config.src_dir is not None
    assert reloaded.config.src_dir.language == "Catalan"


def test_cli_set_source_unknown_language_errors(project, tmp_path):
    src_dir = tmp_path / "src_kl"
    src_dir.mkdir()

    result = runner.invoke(app, ["set-source", "src_kl", "Klingon"])
    assert result.exit_code == 1
    assert "Unknown language" in result.output


# --- set-target with custom languages ---

def test_cli_set_target_with_predefined_language(project, tmp_path):
    src_dir = tmp_path / "src_en"
    tgt_dir = tmp_path / "tgt_fr"
    src_dir.mkdir()
    tgt_dir.mkdir()
    runner.invoke(app, ["set-source", "src_en", "English"])

    result = runner.invoke(app, ["set-target", "tgt_fr", "French"])
    assert result.exit_code == 0
    assert "French" in result.output

    reloaded = load_project(str(tmp_path))
    assert reloaded.config.get_target_dir_path_by_lang(Language.FRENCH) == tgt_dir.resolve()


def test_cli_set_target_with_custom_language(project, tmp_path):
    src_dir = tmp_path / "src_en"
    tgt_dir = tmp_path / "tgt_ca"
    src_dir.mkdir()
    tgt_dir.mkdir()
    runner.invoke(app, ["set-source", "src_en", "English"])
    runner.invoke(app, ["add-lang", "Catalan", "_ca"])

    result = runner.invoke(app, ["set-target", "tgt_ca", "Catalan"])
    assert result.exit_code == 0
    assert "Catalan" in result.output

    reloaded = load_project(str(tmp_path))
    catalan = reloaded.config.resolve_language("Catalan")
    assert reloaded.config.get_target_dir_path_by_lang(catalan) == tgt_dir.resolve()


def test_cli_set_target_rejects_source_directory(project, tmp_path):
    shared_dir = tmp_path / "doc"
    shared_dir.mkdir()
    runner.invoke(app, ["set-source", "doc", "French"])

    result = runner.invoke(app, ["set-target", "doc", "English"])

    assert result.exit_code == 1
    assert "same as the source directory" in result.output


def test_cli_set_target_unknown_language_errors(project, tmp_path):
    src_dir = tmp_path / "src_en"
    tgt_dir = tmp_path / "tgt_kl"
    src_dir.mkdir()
    tgt_dir.mkdir()
    runner.invoke(app, ["set-source", "src_en", "English"])

    result = runner.invoke(app, ["set-target", "tgt_kl", "Klingon"])
    assert result.exit_code == 1
    assert "Unknown language" in result.output


# --- remove-target with custom languages ---

def test_cli_remove_target_with_custom_language(project, tmp_path):
    src_dir = tmp_path / "src_en"
    tgt_dir = tmp_path / "tgt_ca"
    src_dir.mkdir()
    tgt_dir.mkdir()
    runner.invoke(app, ["add-lang", "Catalan", "_ca"])
    runner.invoke(app, ["set-source", "src_en", "English"])
    runner.invoke(app, ["set-target", "tgt_ca", "Catalan"])

    result = runner.invoke(app, ["remove-target", "Catalan"])
    assert result.exit_code == 0
    assert "Catalan" in result.output

    reloaded = load_project(str(tmp_path))
    catalan = reloaded.config.resolve_language("Catalan")
    assert reloaded.config.get_target_dir_path_by_lang(catalan) is None


def test_cli_remove_target_unknown_language_errors(project, tmp_path):
    result = runner.invoke(app, ["remove-target", "Klingon"])
    assert result.exit_code == 1
    assert "Unknown language" in result.output


# --- translate file / translate all with custom languages ---

def _setup_project_with_custom_target(tmp_path):
    """Helper: project with English source, Catalan target, one translatable file."""
    src_dir = tmp_path / "src_en"
    tgt_dir = tmp_path / "tgt_ca"
    src_dir.mkdir()
    tgt_dir.mkdir()
    trans_file = src_dir / "doc.txt"
    trans_file.write_text("Hello world", encoding="utf-8")

    runner.invoke(app, ["add-lang", "Catalan", "_ca"])
    runner.invoke(app, ["set-source", "src_en", "English"])
    runner.invoke(app, ["set-target", "tgt_ca", "Catalan"])
    runner.invoke(app, ["add", "src_en/doc.txt"])
    return trans_file


def test_cli_translate_file_unknown_language_errors(project, tmp_path):
    _setup_project_with_custom_target(tmp_path)
    result = runner.invoke(app, ["translate", "file", "src_en/doc.txt", "Klingon"])
    assert result.exit_code == 1
    assert "Unknown language" in result.output


def test_cli_translate_all_unknown_language_errors(project, tmp_path):
    _setup_project_with_custom_target(tmp_path)
    result = runner.invoke(app, ["translate", "all", "Klingon"])
    assert result.exit_code == 1
    assert "Unknown language" in result.output


def test_cli_translate_file_custom_language_resolves(project, tmp_path):
    """Language resolution succeeds — failure is at the LLM call, not 'Unknown language'."""
    _setup_project_with_custom_target(tmp_path)
    result = runner.invoke(app, ["translate", "file", "src_en/doc.txt", "Catalan"])
    assert "Unknown language" not in (result.output or "")


def test_cli_translate_all_custom_language_resolves(project, tmp_path):
    """Language resolution succeeds — failure is at the LLM call, not 'Unknown language'."""
    _setup_project_with_custom_target(tmp_path)
    result = runner.invoke(app, ["translate", "all", "Catalan"])
    assert "Unknown language" not in (result.output or "")


# --- cache clear --lang with custom languages ---

def test_cli_cache_clear_unknown_language_errors(project, tmp_path):
    result = runner.invoke(app, ["cache", "clear", "--all", "--lang", "Klingon"])
    assert result.exit_code == 1
    assert "Unknown language" in result.output


def test_cli_cache_clear_custom_language_resolves(project, tmp_path):
    """Language resolution succeeds — clears nothing if cache is empty, no error."""
    runner.invoke(app, ["add-lang", "Catalan", "_ca"])
    result = runner.invoke(app, ["cache", "clear", "--all", "--lang", "Catalan"])
    assert "Unknown language" not in (result.output or "")


def test_cli_remove_lang_with_associated_source_dir_errors(project, tmp_path):
    from lesia.project_manager import load_project

    runner.invoke(app, ["add-lang", "Catalan", "_ca"])

    src_dir = tmp_path / "src_ca"
    src_dir.mkdir()

    reloaded = load_project(str(tmp_path))
    catalan = reloaded.config.resolve_language("Catalan")
    reloaded.config.set_src_dir_config(src_dir, catalan)
    reloaded.save_config()

    result = runner.invoke(app, ["remove-lang", "Catalan"])
    assert result.exit_code == 1
    assert "source directory" in result.output


def test_cli_remove_lang_with_associated_target_dir_errors(project, tmp_path):
    from lesia.project_manager import load_project

    runner.invoke(app, ["add-lang", "Catalan", "_ca"])

    src_dir = tmp_path / "src_en"
    tgt_dir = tmp_path / "tgt_ca"
    src_dir.mkdir()
    tgt_dir.mkdir()

    # Set up source and target dirs via the reloaded project (so custom_languages is populated)
    reloaded = load_project(str(tmp_path))
    catalan = reloaded.config.resolve_language("Catalan")
    reloaded.config.set_src_dir_config(src_dir, Language.ENGLISH)
    reloaded.config.add_lang_dir_config(tgt_dir, catalan)
    reloaded.save_config()

    result = runner.invoke(app, ["remove-lang", "Catalan"])
    assert result.exit_code == 1
    assert "associated target directory" in result.output


# --- short name (--short flag) ---

def test_cli_add_lang_with_short(project, tmp_path):
    result = runner.invoke(app, ["add-lang", "American English", "_ae", "--short", "AmEng"])
    assert result.exit_code == 0
    assert "American English" in result.output
    assert "AmEng" in result.output

    reloaded = load_project(str(tmp_path))
    assert "American English" in reloaded.config.custom_languages
    assert reloaded.config.custom_language_shorts.get("AmEng") == "American English"


def test_cli_add_lang_duplicate_short_errors(project):
    runner.invoke(app, ["add-lang", "American English", "_ae", "--short", "AmEng"])
    result = runner.invoke(app, ["add-lang", "Australian English", "_au", "--short", "AmEng"])
    assert result.exit_code == 1
    assert "already used" in result.output


def test_cli_set_source_with_short(project, tmp_path):
    src_dir = tmp_path / "src_ae"
    src_dir.mkdir()
    runner.invoke(app, ["add-lang", "American English", "_ae", "--short", "AmEng"])

    result = runner.invoke(app, ["set-source", "src_ae", "AmEng"])
    assert result.exit_code == 0

    reloaded = load_project(str(tmp_path))
    assert reloaded.config.src_dir is not None
    assert reloaded.config.src_dir.language == "American English"


def test_cli_set_target_with_short(project, tmp_path):
    src_dir = tmp_path / "src_en"
    tgt_dir = tmp_path / "tgt_ae"
    src_dir.mkdir()
    tgt_dir.mkdir()
    runner.invoke(app, ["set-source", "src_en", "English"])
    runner.invoke(app, ["add-lang", "American English", "_ae", "--short", "AmEng"])

    result = runner.invoke(app, ["set-target", "tgt_ae", "AmEng"])
    assert result.exit_code == 0

    reloaded = load_project(str(tmp_path))
    lang = reloaded.config.resolve_language("American English")
    assert reloaded.config.get_target_dir_path_by_lang(lang) == tgt_dir.resolve()


def test_cli_remove_target_with_short(project, tmp_path):
    src_dir = tmp_path / "src_en"
    tgt_dir = tmp_path / "tgt_ae"
    src_dir.mkdir()
    tgt_dir.mkdir()
    runner.invoke(app, ["add-lang", "American English", "_ae", "--short", "AmEng"])
    runner.invoke(app, ["set-source", "src_en", "English"])
    runner.invoke(app, ["set-target", "tgt_ae", "AmEng"])

    result = runner.invoke(app, ["remove-target", "AmEng"])
    assert result.exit_code == 0

    reloaded = load_project(str(tmp_path))
    lang = reloaded.config.resolve_language("American English")
    assert reloaded.config.get_target_dir_path_by_lang(lang) is None


def test_cli_remove_lang_with_short(project, tmp_path):
    runner.invoke(app, ["add-lang", "American English", "_ae", "--short", "AmEng"])

    result = runner.invoke(app, ["remove-lang", "AmEng"])
    assert result.exit_code == 0

    reloaded = load_project(str(tmp_path))
    assert "American English" not in reloaded.config.custom_languages
    assert "AmEng" not in reloaded.config.custom_language_shorts


def test_cli_remove_lang_clears_short(project, tmp_path):
    runner.invoke(app, ["add-lang", "American English", "_ae", "--short", "AmEng"])
    runner.invoke(app, ["remove-lang", "American English"])

    reloaded = load_project(str(tmp_path))
    assert "AmEng" not in reloaded.config.custom_language_shorts


def test_cli_translate_file_with_short_resolves(project, tmp_path):
    _setup_project_with_custom_target(tmp_path)
    runner.invoke(app, ["add-lang", "American English", "_ae", "--short", "AmEng"])

    result = runner.invoke(app, ["translate", "file", "src_en/doc.txt", "AmEng"])
    assert "Unknown language" not in (result.output or "")


def test_cli_translate_all_with_short_resolves(project, tmp_path):
    _setup_project_with_custom_target(tmp_path)
    runner.invoke(app, ["add-lang", "American English", "_ae", "--short", "AmEng"])

    result = runner.invoke(app, ["translate", "all", "AmEng"])
    assert "Unknown language" not in (result.output or "")


def test_cli_cache_clear_with_short_resolves(project, tmp_path):
    runner.invoke(app, ["add-lang", "American English", "_ae", "--short", "AmEng"])
    result = runner.invoke(app, ["cache", "clear", "--all", "--lang", "AmEng"])
    assert "Unknown language" not in (result.output or "")
