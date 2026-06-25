import json
from pathlib import Path

import pytest

from lesia.enums import CustomLanguage, Language
from lesia.project_config_models import LangDir, ProjectConfig
from lesia.project_config_io import write_project_config
from lesia.project_manager import load_project
from lesia.constants import CONF_DIR, CONFIG_FILENAME


def test_config_stores_relative_paths(tmp_path):
    root = tmp_path
    src_dir = root / "src_en"
    tgt_dir = root / "proj_fr"
    src_dir.mkdir()
    tgt_dir.mkdir()
    file_path = src_dir / "doc.txt"
    file_path.write_text("hello", encoding="utf-8")

    config = ProjectConfig.new(project_name="proj")
    config.set_runtime_root_path(root)

    config.set_src_dir_config(src_dir, Language.ENGLISH)
    config.add_lang_dir_config(tgt_dir, Language.FRENCH)

    assert config.src_dir is not None
    assert config.src_dir.path == Path("src_en")
    assert config.lang_dirs[0].path == Path("proj_fr")

    assert config.get_src_dir_path() == src_dir.resolve()
    assert config.get_target_dir_path_by_lang(Language.FRENCH) == tgt_dir.resolve()

    config.make_file_translatable(file_path, True)
    assert config.translatable_files == [Path("src_en/doc.txt")]
    assert config.get_translatable_files() == [file_path.resolve()]


def test_config_handles_project_move(tmp_path):
    old_root = tmp_path / "old"
    new_root = tmp_path / "new"
    old_root.mkdir()
    new_root.mkdir()
    (old_root / "src").mkdir()
    (new_root / "src").mkdir()

    config = ProjectConfig.new(project_name="proj")
    config.set_runtime_root_path(old_root)
    config.set_src_dir_config(old_root / "src", Language.ENGLISH)

    # Simulate loading the project from a new location.
    config.set_runtime_root_path(new_root)
    assert config.get_src_dir_path() == (new_root / "src").resolve()

    # Model dump should not persist any runtime root information.
    dumped = config.model_dump()
    assert "root_path" not in dumped


def test_runtime_root_must_be_set_before_using_paths(tmp_path):
    config = ProjectConfig.new(project_name="proj")
    with pytest.raises(ValueError):
        config.set_src_dir_config(tmp_path, Language.ENGLISH)


def test_rejects_paths_outside_root(tmp_path):
    project_root = tmp_path / "proj"
    external = tmp_path / "elsewhere"
    project_root.mkdir()
    external.mkdir()

    config = ProjectConfig.new(project_name="proj")
    config.set_runtime_root_path(project_root)

    with pytest.raises(ValueError):
        config.set_src_dir_config(external, Language.ENGLISH)


def test_rejects_target_directory_matching_source(tmp_path):
    root = tmp_path
    shared_dir = root / "shared"
    shared_dir.mkdir()

    config = ProjectConfig.new(project_name="proj")
    config.set_runtime_root_path(root)
    config.set_src_dir_config(shared_dir, Language.FRENCH)

    with pytest.raises(ValueError, match="same as the source directory"):
        config.add_lang_dir_config(shared_dir, Language.ENGLISH)


def test_rejects_source_directory_matching_target(tmp_path):
    root = tmp_path
    shared_dir = root / "shared"
    shared_dir.mkdir()

    config = ProjectConfig.new(project_name="proj")
    config.set_runtime_root_path(root)
    config.add_lang_dir_config(shared_dir, Language.ENGLISH)

    with pytest.raises(ValueError, match="same as a target directory"):
        config.set_src_dir_config(shared_dir, Language.FRENCH)


def test_normalizes_existing_absolute_entries(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    src_dir = root / "src"
    src_dir.mkdir()
    tgt_dir = root / "target"
    tgt_dir.mkdir()
    trans_file = src_dir / "note.md"
    trans_file.write_text("doc", encoding="utf-8")

    config = ProjectConfig.new(project_name="proj")
    config.lang_dirs.append(LangDir(language=Language.FRENCH, path=tgt_dir.resolve()))
    config.src_dir = LangDir(language=Language.ENGLISH, path=src_dir.resolve())
    config.translatable_files = [trans_file.resolve()]

    config.set_runtime_root_path(root)

    assert config.src_dir is not None
    assert config.src_dir.path == Path("src")
    assert config.lang_dirs[0].path == Path("target")
    assert config.translatable_files == [Path("src/note.md")]
    assert config.get_src_dir_path() == src_dir.resolve()
    assert config.get_target_dir_path_by_lang(Language.FRENCH) == tgt_dir.resolve()
    assert config.get_translatable_files() == [trans_file.resolve()]


def test_translatable_file_round_trip(tmp_path):
    root = tmp_path
    src_dir = root / "src"
    src_dir.mkdir()
    file_path = src_dir / "doc.txt"
    file_path.write_text("text", encoding="utf-8")

    config = ProjectConfig.new(project_name="proj")
    config.set_runtime_root_path(root)
    config.set_src_dir_config(src_dir, Language.ENGLISH)

    config.make_file_translatable(file_path, True)
    assert config.translatable_files == [Path("src/doc.txt")]
    assert config.get_translatable_files() == [file_path.resolve()]

    config.make_file_translatable(file_path, False)
    assert config.translatable_files == []


def test_load_project_rewrites_config_file(tmp_path):
    root = tmp_path / "proj"
    src_dir = root / "src"
    conf_dir = root / CONF_DIR
    root.mkdir()
    src_dir.mkdir()
    conf_dir.mkdir()

    config = ProjectConfig.new(project_name="proj")
    config.src_dir = LangDir(language=Language.ENGLISH, path=src_dir.resolve())

    config_path = conf_dir / CONFIG_FILENAME
    write_project_config(config_path, config)

    load_project(str(root))

    contents = json.loads(config_path.read_text(encoding="utf-8"))
    assert contents["src_dir"]["path"] == "src"


def test_custom_language_equality():
    a = CustomLanguage("Catalan", "_ca")
    b = CustomLanguage("catalan", "_ca")
    assert a == b
    assert hash(a) == hash(b)
    assert a == "Catalan"
    assert a == "catalan"
    assert a != CustomLanguage("Spanish", "_es")


def test_add_and_resolve_custom_language():
    config = ProjectConfig.new(project_name="proj")
    config.add_custom_language("Catalan", "_ca")

    lang = config.resolve_language("Catalan")
    assert lang == CustomLanguage("Catalan", "_ca")
    assert lang.get_dir_suffix() == "_ca"


def test_resolve_predefined_language():
    config = ProjectConfig.new(project_name="proj")
    lang = config.resolve_language("French")
    assert lang == CustomLanguage("French", "_fr")
    assert lang.get_dir_suffix() == "_fr"


def test_resolve_unknown_language_raises():
    config = ProjectConfig.new(project_name="proj")
    with pytest.raises(ValueError, match="Unknown language"):
        config.resolve_language("Klingon")


def test_add_predefined_language_as_custom_raises():
    config = ProjectConfig.new(project_name="proj")
    with pytest.raises(ValueError, match="already a predefined"):
        config.add_custom_language("French", "_fr")


def test_remove_custom_language():
    config = ProjectConfig.new(project_name="proj")
    config.add_custom_language("Catalan", "_ca")
    config.remove_custom_language("Catalan")
    assert "Catalan" not in config.custom_languages
    with pytest.raises(ValueError, match="Unknown language"):
        config.resolve_language("Catalan")


def test_add_duplicate_custom_language_raises():
    config = ProjectConfig.new(project_name="proj")
    config.add_custom_language("Catalan", "_ca")
    with pytest.raises(ValueError, match="already exists"):
        config.add_custom_language("Catalan", "_ca")


def test_add_predefined_language_as_custom_via_project_manager(tmp_path):
    from lesia.project_manager import init_project
    from lesia.errors import AddCustomLanguageError

    project = init_project("proj", str(tmp_path))
    with pytest.raises(AddCustomLanguageError, match="already a predefined"):
        project.add_custom_language("French", "_fr")


def test_add_duplicate_custom_language_via_project_manager(tmp_path):
    from lesia.project_manager import init_project
    from lesia.errors import AddCustomLanguageError

    project = init_project("proj", str(tmp_path))
    project.add_custom_language("Catalan", "_ca")
    with pytest.raises(AddCustomLanguageError, match="already exists"):
        project.add_custom_language("Catalan", "_ca")


def test_remove_nonexistent_custom_language_raises():
    config = ProjectConfig.new(project_name="proj")
    with pytest.raises(ValueError, match="not found"):
        config.remove_custom_language("Klingon")


def test_remove_custom_language_success(tmp_path):
    from lesia.project_manager import init_project
    from lesia.errors import RemoveCustomLanguageError

    project = init_project("proj", str(tmp_path))
    project.add_custom_language("Catalan", "_ca")
    project.remove_custom_language("Catalan")
    assert "Catalan" not in project.config.custom_languages


def test_remove_predefined_language_raises(tmp_path):
    from lesia.project_manager import init_project
    from lesia.errors import RemoveCustomLanguageError

    project = init_project("proj", str(tmp_path))
    with pytest.raises(RemoveCustomLanguageError, match="predefined"):
        project.remove_custom_language("French")


def test_remove_nonexistent_custom_language_via_project_raises(tmp_path):
    from lesia.project_manager import init_project
    from lesia.errors import RemoveCustomLanguageError

    project = init_project("proj", str(tmp_path))
    with pytest.raises(RemoveCustomLanguageError, match="not in the config"):
        project.remove_custom_language("Klingon")


def test_remove_custom_language_with_target_dir_raises(tmp_path):
    from lesia.project_manager import init_project
    from lesia.errors import RemoveCustomLanguageError

    project = init_project("proj", str(tmp_path))
    project.add_custom_language("Catalan", "_ca")

    src_dir = tmp_path / "src_en"
    tgt_dir = tmp_path / "tgt_ca"
    src_dir.mkdir()
    tgt_dir.mkdir()

    catalan = project.config.resolve_language("Catalan")
    project.config.set_src_dir_config(src_dir, Language.ENGLISH)
    project.config.add_lang_dir_config(tgt_dir, catalan)

    with pytest.raises(RemoveCustomLanguageError, match="associated target directory"):
        project.remove_custom_language("Catalan")


def test_custom_language_as_source_and_target(tmp_path):
    root = tmp_path
    src_dir = root / "src_ca"
    tgt_dir = root / "tgt_en"
    src_dir.mkdir()
    tgt_dir.mkdir()

    config = ProjectConfig.new(project_name="proj")
    config.set_runtime_root_path(root)
    config.add_custom_language("Catalan", "_ca")

    catalan = config.resolve_language("Catalan")
    config.set_src_dir_config(src_dir, catalan)
    config.add_lang_dir_config(tgt_dir, Language.ENGLISH)

    assert config.src_dir is not None
    assert config.src_dir.language == "Catalan"
    assert config.get_src_dir_path() == src_dir.resolve()
    assert config.get_target_dir_path_by_lang(Language.ENGLISH) == tgt_dir.resolve()
    assert config.get_target_dir_path_by_lang(catalan) is None


def test_custom_language_config_round_trip(tmp_path):
    root = tmp_path / "proj"
    src_dir = root / "src_ca"
    tgt_dir = root / "tgt_en"
    conf_dir = root / CONF_DIR
    root.mkdir()
    src_dir.mkdir()
    tgt_dir.mkdir()
    conf_dir.mkdir()

    config = ProjectConfig.new(project_name="proj")
    config.set_runtime_root_path(root)
    config.add_custom_language("Catalan", "_ca")

    catalan = config.resolve_language("Catalan")
    config.set_src_dir_config(src_dir, catalan)
    config.add_lang_dir_config(tgt_dir, Language.ENGLISH)

    config_path = conf_dir / CONFIG_FILENAME
    write_project_config(config_path, config)

    # Verify JSON structure
    contents = json.loads(config_path.read_text(encoding="utf-8"))
    assert contents["custom_languages"] == {"Catalan": "_ca"}
    assert contents["src_dir"]["language"] == "Catalan"

    # Reload and verify
    loaded = load_project(str(root))
    assert loaded.config.custom_languages == {"Catalan": "_ca"}
    assert loaded.config.src_dir is not None
    assert loaded.config.src_dir.language == "Catalan"

    resolved = loaded.config.resolve_language("Catalan")
    assert resolved.get_dir_suffix() == "_ca"
    assert loaded.config.get_target_dir_path_by_lang(Language.ENGLISH) == tgt_dir.resolve()


def test_typst_translatable_string_args_config_round_trip(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()

    config = ProjectConfig.new(project_name="proj")
    config.set_runtime_root_path(root)
    config.set_typst_translatable_string_args_for_function("ex", ["info", "title"])
    config.set_typst_translatable_string_args_for_function("figure", ["caption"])

    assert config.get_typst_translatable_string_args_by_function() == {
        "ex": ["info", "title"],
        "figure": ["caption"],
    }

    config.remove_typst_translatable_string_args_for_function("figure")
    assert config.get_typst_translatable_string_args_by_function() == {
        "ex": ["info", "title"],
    }
