from pathlib import Path

from lesia.constants import CACHE_DIR_NAME, CONF_DIR
from lesia.enums import Language
from lesia.helpers import calculate_checksum, calculate_path_checksum
from lesia.project_config_models import ProjectConfig
from lesia.project_manager import Project
from lesia.translation_cache.cache_backend import (
    PATH_CHECKSUM_COLUMN,
    read_correspondence_cache,
    write_correspondence_cache,
)
from lesia.translation_cache.translation_cache import TranslationCacheCsv


def _write_chunk(cache_dir: Path, lang: Language, path_hash: str, checksum: str, contents: str) -> None:
    chunk_dir = cache_dir / str(lang) / path_hash
    chunk_dir.mkdir(parents=True, exist_ok=True)
    (chunk_dir / checksum).write_text(contents, encoding="utf-8")


def _make_project(tmp_path: Path) -> Project:
    project_root = tmp_path / "proj"
    src_dir = project_root / "src_en"
    src_dir.mkdir(parents=True)
    (project_root / CONF_DIR).mkdir(parents=True)

    config = ProjectConfig.new(project_name="proj")
    config.set_runtime_root_path(project_root)
    config.set_src_dir_config(src_dir, Language.ENGLISH)
    return Project(project_root, config)


def test_clear_missing_chunks_no_cache_dir(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    stats = project.clear_translation_cache_missing_chunks()
    assert stats.removed_rows == 0
    assert stats.cleared_fields == 0
    assert stats.removed_source_chunks == 0


def test_clear_missing_chunks_no_csv_deletes_source_chunks(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    cache_dir = project.root_path / CONF_DIR / CACHE_DIR_NAME
    path_hash = calculate_path_checksum("doc.md")

    src_text = "Hello"
    fr_text = "Bonjour"
    src_checksum = calculate_checksum(src_text)
    fr_checksum = calculate_checksum(fr_text)
    _write_chunk(cache_dir, Language.ENGLISH, path_hash, src_checksum, src_text)
    _write_chunk(cache_dir, Language.FRENCH, path_hash, fr_checksum, fr_text)

    stats = project.clear_translation_cache_missing_chunks()
    assert stats.removed_source_chunks == 1
    assert stats.removed_target_chunks == 1
    assert not (cache_dir / "English" / path_hash / src_checksum).exists()
    assert not (cache_dir / "French" / path_hash / fr_checksum).exists()


def test_clear_missing_chunks_empty_source_checksum_row(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    write_correspondence_cache(
        project.root_path,
        [{PATH_CHECKSUM_COLUMN: "", "English": "", "French": "abc"}],
        [PATH_CHECKSUM_COLUMN, "English", "French"],
    )

    stats = project.clear_translation_cache_missing_chunks()
    assert stats.removed_rows == 1


def test_clear_missing_chunks_row_without_targets(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    cache_dir = project.root_path / CONF_DIR / CACHE_DIR_NAME
    path_hash = calculate_path_checksum("doc.md")

    src_text = "Hello"
    src_checksum = calculate_checksum(src_text)
    _write_chunk(cache_dir, Language.ENGLISH, path_hash, src_checksum, src_text)

    write_correspondence_cache(
        project.root_path,
        [{PATH_CHECKSUM_COLUMN: path_hash, "English": src_checksum}],
        [PATH_CHECKSUM_COLUMN, "English"],
    )

    stats = project.clear_translation_cache_missing_chunks()
    assert stats.removed_rows == 1
    assert stats.removed_source_chunks == 1


def test_clear_missing_chunks_preserves_row_with_targets(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    cache_dir = project.root_path / CONF_DIR / CACHE_DIR_NAME
    path_hash = calculate_path_checksum("doc.md")

    src_text = "Hello"
    fr_text = "Bonjour"
    src_checksum = calculate_checksum(src_text)
    fr_checksum = calculate_checksum(fr_text)

    _write_chunk(cache_dir, Language.ENGLISH, path_hash, src_checksum, src_text)
    _write_chunk(cache_dir, Language.FRENCH, path_hash, fr_checksum, fr_text)

    write_correspondence_cache(
        project.root_path,
        [{PATH_CHECKSUM_COLUMN: path_hash, "English": src_checksum, "French": fr_checksum}],
        [PATH_CHECKSUM_COLUMN, "English", "French"],
    )

    stats = project.clear_translation_cache_missing_chunks()
    assert stats.removed_rows == 0
    assert stats.cleared_fields == 0
    assert stats.removed_source_chunks == 0


def test_clear_missing_chunks_handles_top_level_lang_files(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    cache_dir = project.root_path / CONF_DIR / CACHE_DIR_NAME
    lang_dir = cache_dir / "English"
    lang_dir.mkdir(parents=True, exist_ok=True)

    src_text = "Hello"
    src_checksum = calculate_checksum(src_text)
    (lang_dir / src_checksum).write_text(src_text, encoding="utf-8")

    stats = project.clear_translation_cache_missing_chunks()
    assert stats.removed_source_chunks == 1
    assert not (lang_dir / src_checksum).exists()


def test_clear_missing_chunks_removes_row_and_source(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    cache_dir = project.root_path / CONF_DIR / CACHE_DIR_NAME
    path_hash = calculate_path_checksum("doc.md")

    src_text = "Hello"
    tgt_text = "Bonjour"
    src_checksum = calculate_checksum(src_text)
    tgt_checksum = calculate_checksum(tgt_text)

    _write_chunk(cache_dir, Language.ENGLISH, path_hash, src_checksum, src_text)
    write_correspondence_cache(
        project.root_path,
        [{PATH_CHECKSUM_COLUMN: path_hash, "English": src_checksum, "French": tgt_checksum}],
        [PATH_CHECKSUM_COLUMN, "English", "French"],
    )

    stats = project.clear_translation_cache_missing_chunks()
    assert stats.removed_rows == 1
    assert not (cache_dir / "English" / path_hash / src_checksum).exists()

    cache_data = read_correspondence_cache(project.root_path)
    assert cache_data is not None
    _, data_list = cache_data
    assert data_list == []


def test_clear_missing_chunks_clears_missing_target_fields(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    cache_dir = project.root_path / CONF_DIR / CACHE_DIR_NAME
    path_hash = calculate_path_checksum("doc.md")

    src_text = "Hello"
    fr_text = "Bonjour"
    de_text = "Hallo"
    src_checksum = calculate_checksum(src_text)
    fr_checksum = calculate_checksum(fr_text)
    de_checksum = calculate_checksum(de_text)

    _write_chunk(cache_dir, Language.ENGLISH, path_hash, src_checksum, src_text)
    _write_chunk(cache_dir, Language.FRENCH, path_hash, fr_checksum, fr_text)
    write_correspondence_cache(
        project.root_path,
        [{
            PATH_CHECKSUM_COLUMN: path_hash,
            "English": src_checksum,
            "French": fr_checksum,
            "German": de_checksum,
        }],
        [PATH_CHECKSUM_COLUMN, "English", "French", "German"],
    )

    stats = project.clear_translation_cache_missing_chunks()
    assert stats.removed_rows == 0
    assert stats.cleared_fields == 1

    cache_data = read_correspondence_cache(project.root_path)
    assert cache_data is not None
    _, data_list = cache_data
    assert len(data_list) == 1
    assert data_list[0]["German"] == ""
    assert data_list[0]["French"] == fr_checksum


def test_clear_missing_chunks_removes_row_when_source_missing(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    cache_dir = project.root_path / CONF_DIR / CACHE_DIR_NAME
    path_hash = calculate_path_checksum("doc.md")

    src_checksum = calculate_checksum("Hello")
    fr_text = "Bonjour"
    fr_checksum = calculate_checksum(fr_text)

    _write_chunk(cache_dir, Language.FRENCH, path_hash, fr_checksum, fr_text)
    write_correspondence_cache(
        project.root_path,
        [{PATH_CHECKSUM_COLUMN: path_hash, "English": src_checksum, "French": fr_checksum}],
        [PATH_CHECKSUM_COLUMN, "English", "French"],
    )

    stats = project.clear_translation_cache_missing_chunks()
    assert stats.removed_rows == 1
    assert stats.removed_target_chunks == 1
    assert not (cache_dir / "French" / path_hash / fr_checksum).exists()


def test_clear_missing_chunks_removes_orphan_source_chunks(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    cache_dir = project.root_path / CONF_DIR / CACHE_DIR_NAME
    path_hash = calculate_path_checksum("doc.md")

    src_text = "Hello"
    src_checksum = calculate_checksum(src_text)
    _write_chunk(cache_dir, Language.ENGLISH, path_hash, src_checksum, src_text)

    stats = project.clear_translation_cache_missing_chunks()
    assert stats.removed_source_chunks == 1
    assert not (cache_dir / "English" / path_hash / src_checksum).exists()


def test_clear_missing_chunks_multi_row_mixed_states(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    cache_dir = project.root_path / CONF_DIR / CACHE_DIR_NAME
    path_a = calculate_path_checksum("a.md")
    path_b = calculate_path_checksum("b.md")

    src_a = "Alpha"
    tgt_a = "Alfa"
    src_b = "Beta"
    tgt_b = "Bete"

    src_a_checksum = calculate_checksum(src_a)
    tgt_a_checksum = calculate_checksum(tgt_a)
    src_b_checksum = calculate_checksum(src_b)
    tgt_b_checksum = calculate_checksum(tgt_b)

    _write_chunk(cache_dir, Language.ENGLISH, path_a, src_a_checksum, src_a)
    _write_chunk(cache_dir, Language.FRENCH, path_a, tgt_a_checksum, tgt_a)
    _write_chunk(cache_dir, Language.ENGLISH, path_b, src_b_checksum, src_b)

    write_correspondence_cache(
        project.root_path,
        [
            {PATH_CHECKSUM_COLUMN: path_a, "English": src_a_checksum, "French": tgt_a_checksum},
            {PATH_CHECKSUM_COLUMN: path_b, "English": src_b_checksum, "French": tgt_b_checksum},
        ],
        [PATH_CHECKSUM_COLUMN, "English", "French"],
    )

    stats = project.clear_translation_cache_missing_chunks()
    assert stats.removed_rows == 1
    assert stats.cleared_fields == 0

    cache_data = read_correspondence_cache(project.root_path)
    assert cache_data is not None
    _, data_list = cache_data
    assert len(data_list) == 1
    assert data_list[0][PATH_CHECKSUM_COLUMN] == path_a


def test_clear_all_lang_deletes_lang_chunks(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    cache_dir = project.root_path / CONF_DIR / CACHE_DIR_NAME
    path_hash = calculate_path_checksum("doc.md")

    src_text = "Hello"
    fr_text = "Bonjour"
    src_checksum = calculate_checksum(src_text)
    fr_checksum = calculate_checksum(fr_text)

    _write_chunk(cache_dir, Language.ENGLISH, path_hash, src_checksum, src_text)
    _write_chunk(cache_dir, Language.FRENCH, path_hash, fr_checksum, fr_text)

    write_correspondence_cache(
        project.root_path,
        [{PATH_CHECKSUM_COLUMN: path_hash, "English": src_checksum, "French": fr_checksum}],
        [PATH_CHECKSUM_COLUMN, "English", "French"],
    )

    stats = project.clear_translation_cache_all(Language.FRENCH, None, None)
    assert stats.removed_chunk_files == 1
    assert not (cache_dir / "French" / path_hash / fr_checksum).exists()
    assert (cache_dir / "English" / path_hash / src_checksum).exists()

    cache_data = read_correspondence_cache(project.root_path)
    assert cache_data is not None
    _, data_list = cache_data
    assert data_list[0]["French"] == ""
    assert data_list[0]["English"] == src_checksum


def test_clear_all_file_removes_rows_and_chunks(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    cache_dir = project.root_path / CONF_DIR / CACHE_DIR_NAME
    src_dir = project.config.get_src_dir_path()
    assert src_dir is not None
    file_path = src_dir / "doc.md"
    file_path.write_text("Hello", encoding="utf-8")
    path_hash = calculate_path_checksum("doc.md")

    src_checksum = calculate_checksum("Hello")
    fr_checksum = calculate_checksum("Bonjour")
    _write_chunk(cache_dir, Language.ENGLISH, path_hash, src_checksum, "Hello")
    _write_chunk(cache_dir, Language.FRENCH, path_hash, fr_checksum, "Bonjour")

    write_correspondence_cache(
        project.root_path,
        [{PATH_CHECKSUM_COLUMN: path_hash, "English": src_checksum, "French": fr_checksum}],
        [PATH_CHECKSUM_COLUMN, "English", "French"],
    )

    stats = project.clear_translation_cache_all(None, str(file_path), None)
    assert stats.removed_rows == 1
    assert stats.removed_chunk_files == 2
    assert not (cache_dir / "English" / path_hash / src_checksum).exists()
    assert not (cache_dir / "French" / path_hash / fr_checksum).exists()

    cache_data = read_correspondence_cache(project.root_path)
    assert cache_data is not None
    _, data_list = cache_data
    assert data_list == []


def test_clear_all_file_accepts_target_path(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    cache_dir = project.root_path / CONF_DIR / CACHE_DIR_NAME
    tgt_dir = project.root_path / "tgt_fr"
    tgt_dir.mkdir(parents=True, exist_ok=True)
    project.config.add_lang_dir_config(tgt_dir, Language.FRENCH)

    file_path = tgt_dir / "doc.md"
    file_path.write_text("Bonjour", encoding="utf-8")
    path_hash = calculate_path_checksum("doc.md")

    src_checksum = calculate_checksum("Hello")
    fr_checksum = calculate_checksum("Bonjour")
    _write_chunk(cache_dir, Language.ENGLISH, path_hash, src_checksum, "Hello")
    _write_chunk(cache_dir, Language.FRENCH, path_hash, fr_checksum, "Bonjour")

    write_correspondence_cache(
        project.root_path,
        [{PATH_CHECKSUM_COLUMN: path_hash, "English": src_checksum, "French": fr_checksum}],
        [PATH_CHECKSUM_COLUMN, "English", "French"],
    )

    stats = project.clear_translation_cache_all(None, str(file_path), None)
    assert stats.removed_rows == 1
    assert stats.removed_chunk_files == 2
    assert not (cache_dir / "English" / path_hash / src_checksum).exists()
    assert not (cache_dir / "French" / path_hash / fr_checksum).exists()

def test_clear_all_lang_and_file_clears_intersection(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    cache_dir = project.root_path / CONF_DIR / CACHE_DIR_NAME
    src_dir = project.config.get_src_dir_path()
    assert src_dir is not None
    file_a = src_dir / "a.md"
    file_b = src_dir / "b.md"
    file_a.write_text("Alpha", encoding="utf-8")
    file_b.write_text("Beta", encoding="utf-8")

    path_a = calculate_path_checksum("a.md")
    path_b = calculate_path_checksum("b.md")

    src_a_checksum = calculate_checksum("Alpha")
    src_b_checksum = calculate_checksum("Beta")
    fr_a_checksum = calculate_checksum("Alfa")
    fr_b_checksum = calculate_checksum("Bete")

    _write_chunk(cache_dir, Language.ENGLISH, path_a, src_a_checksum, "Alpha")
    _write_chunk(cache_dir, Language.FRENCH, path_a, fr_a_checksum, "Alfa")
    _write_chunk(cache_dir, Language.ENGLISH, path_b, src_b_checksum, "Beta")
    _write_chunk(cache_dir, Language.FRENCH, path_b, fr_b_checksum, "Bete")

    write_correspondence_cache(
        project.root_path,
        [
            {PATH_CHECKSUM_COLUMN: path_a, "English": src_a_checksum, "French": fr_a_checksum},
            {PATH_CHECKSUM_COLUMN: path_b, "English": src_b_checksum, "French": fr_b_checksum},
        ],
        [PATH_CHECKSUM_COLUMN, "English", "French"],
    )

    stats = project.clear_translation_cache_all(Language.FRENCH, str(file_a), None)
    assert stats.removed_chunk_files == 1
    assert not (cache_dir / "French" / path_a / fr_a_checksum).exists()
    assert (cache_dir / "French" / path_b / fr_b_checksum).exists()

    cache_data = read_correspondence_cache(project.root_path)
    assert cache_data is not None
    _, data_list = cache_data
    assert data_list[0]["French"] == ""
    assert data_list[1]["French"] == fr_b_checksum


def test_clear_all_without_scopes_removes_everything(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    cache_dir = project.root_path / CONF_DIR / CACHE_DIR_NAME
    path_hash = calculate_path_checksum("doc.md")

    src_checksum = calculate_checksum("Hello")
    fr_checksum = calculate_checksum("Bonjour")
    _write_chunk(cache_dir, Language.ENGLISH, path_hash, src_checksum, "Hello")
    _write_chunk(cache_dir, Language.FRENCH, path_hash, fr_checksum, "Bonjour")

    write_correspondence_cache(
        project.root_path,
        [{PATH_CHECKSUM_COLUMN: path_hash, "English": src_checksum, "French": fr_checksum}],
        [PATH_CHECKSUM_COLUMN, "English", "French"],
    )

    stats = project.clear_translation_cache_all(None, None, None)
    assert stats.removed_rows == 1
    assert stats.removed_chunk_files == 2
    assert not (cache_dir / "English" / path_hash / src_checksum).exists()
    assert not (cache_dir / "French" / path_hash / fr_checksum).exists()

    cache_data = read_correspondence_cache(project.root_path)
    assert cache_data is not None
    _, data_list = cache_data
    assert data_list == []


def test_clear_all_keyword_clears_matching_chunks(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    cache_dir = project.root_path / CONF_DIR / CACHE_DIR_NAME
    path_hash = calculate_path_checksum("doc.md")

    src_text = "Hello keyword"
    fr_text = "Bonjour"
    src_checksum = calculate_checksum(src_text)
    fr_checksum = calculate_checksum(fr_text)

    _write_chunk(cache_dir, Language.ENGLISH, path_hash, src_checksum, src_text)
    _write_chunk(cache_dir, Language.FRENCH, path_hash, fr_checksum, fr_text)

    write_correspondence_cache(
        project.root_path,
        [{PATH_CHECKSUM_COLUMN: path_hash, "English": src_checksum, "French": fr_checksum}],
        [PATH_CHECKSUM_COLUMN, "English", "French"],
    )

    stats = project.clear_translation_cache_all(None, None, "keyword")
    assert stats.removed_chunk_files == 1
    assert stats.cleared_fields == 1
    assert stats.removed_rows == 0
    assert not (cache_dir / "English" / path_hash / src_checksum).exists()
    assert (cache_dir / "French" / path_hash / fr_checksum).exists()

    cache_data = read_correspondence_cache(project.root_path)
    assert cache_data is not None
    _, data_list = cache_data
    assert data_list[0]["English"] == ""
    assert data_list[0]["French"] == fr_checksum


def test_clear_all_keyword_with_lang_scopes_deletion(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    cache_dir = project.root_path / CONF_DIR / CACHE_DIR_NAME
    path_hash = calculate_path_checksum("doc.md")

    src_text = "Hello keyword"
    fr_text = "Bonjour keyword"
    src_checksum = calculate_checksum(src_text)
    fr_checksum = calculate_checksum(fr_text)

    _write_chunk(cache_dir, Language.ENGLISH, path_hash, src_checksum, src_text)
    _write_chunk(cache_dir, Language.FRENCH, path_hash, fr_checksum, fr_text)

    write_correspondence_cache(
        project.root_path,
        [{PATH_CHECKSUM_COLUMN: path_hash, "English": src_checksum, "French": fr_checksum}],
        [PATH_CHECKSUM_COLUMN, "English", "French"],
    )

    stats = project.clear_translation_cache_all(Language.ENGLISH, None, "keyword")
    assert stats.removed_chunk_files == 1
    assert stats.cleared_fields == 1
    assert stats.removed_rows == 0
    assert not (cache_dir / "English" / path_hash / src_checksum).exists()
    assert (cache_dir / "French" / path_hash / fr_checksum).exists()


def test_clear_all_keyword_with_file_scopes_deletion(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    cache_dir = project.root_path / CONF_DIR / CACHE_DIR_NAME
    src_dir = project.config.get_src_dir_path()
    assert src_dir is not None

    file_a = src_dir / "a.md"
    file_b = src_dir / "b.md"
    file_a.write_text("Alpha", encoding="utf-8")
    file_b.write_text("Beta", encoding="utf-8")

    path_a = calculate_path_checksum("a.md")
    path_b = calculate_path_checksum("b.md")

    src_a_checksum = calculate_checksum("Alpha keyword")
    src_b_checksum = calculate_checksum("Beta keyword")

    _write_chunk(cache_dir, Language.ENGLISH, path_a, src_a_checksum, "Alpha keyword")
    _write_chunk(cache_dir, Language.ENGLISH, path_b, src_b_checksum, "Beta keyword")

    write_correspondence_cache(
        project.root_path,
        [
            {PATH_CHECKSUM_COLUMN: path_a, "English": src_a_checksum},
            {PATH_CHECKSUM_COLUMN: path_b, "English": src_b_checksum},
        ],
        [PATH_CHECKSUM_COLUMN, "English"],
    )

    stats = project.clear_translation_cache_all(None, str(file_a), "keyword")
    assert stats.removed_chunk_files == 1
    assert stats.cleared_fields == 1
    assert stats.removed_rows == 1
    assert not (cache_dir / "English" / path_a / src_a_checksum).exists()
    assert (cache_dir / "English" / path_b / src_b_checksum).exists()

    cache_data = read_correspondence_cache(project.root_path)
    assert cache_data is not None
    _, data_list = cache_data
    assert len(data_list) == 1
    assert data_list[0][PATH_CHECKSUM_COLUMN] == path_b


# --- custom language tests ---

def _make_project_with_custom_lang(tmp_path: Path):
    """Returns (project, catalan_custom_language) with English source and Catalan target."""
    project = _make_project(tmp_path)
    tgt_dir = project.root_path / "tgt_ca"
    tgt_dir.mkdir(parents=True, exist_ok=True)
    project.add_custom_language("Catalan", "_ca")
    catalan = project.config.resolve_language("Catalan")
    project.config.add_lang_dir_config(tgt_dir, catalan)
    return project, catalan


def test_clear_all_custom_lang_deletes_chunks(tmp_path: Path) -> None:
    project, catalan = _make_project_with_custom_lang(tmp_path)
    cache_dir = project.root_path / CONF_DIR / CACHE_DIR_NAME
    path_hash = calculate_path_checksum("doc.md")

    src_text = "Hello"
    ca_text = "Hola"
    src_checksum = calculate_checksum(src_text)
    ca_checksum = calculate_checksum(ca_text)

    _write_chunk(cache_dir, Language.ENGLISH, path_hash, src_checksum, src_text)
    _write_chunk(cache_dir, catalan, path_hash, ca_checksum, ca_text)

    write_correspondence_cache(
        project.root_path,
        [{PATH_CHECKSUM_COLUMN: path_hash, "English": src_checksum, "Catalan": ca_checksum}],
        [PATH_CHECKSUM_COLUMN, "English", "Catalan"],
    )

    stats = project.clear_translation_cache_all(catalan, None, None)
    assert stats.removed_chunk_files == 1
    assert not (cache_dir / "Catalan" / path_hash / ca_checksum).exists()
    assert (cache_dir / "English" / path_hash / src_checksum).exists()

    cache_data = read_correspondence_cache(project.root_path)
    assert cache_data is not None
    _, data_list = cache_data
    assert data_list[0]["Catalan"] == ""
    assert data_list[0]["English"] == src_checksum


def test_clear_all_custom_lang_and_file_clears_intersection(tmp_path: Path) -> None:
    project, catalan = _make_project_with_custom_lang(tmp_path)
    cache_dir = project.root_path / CONF_DIR / CACHE_DIR_NAME
    src_dir = project.config.get_src_dir_path()
    assert src_dir is not None
    file_a = src_dir / "a.md"
    file_b = src_dir / "b.md"
    file_a.write_text("Alpha", encoding="utf-8")
    file_b.write_text("Beta", encoding="utf-8")

    path_a = calculate_path_checksum("a.md")
    path_b = calculate_path_checksum("b.md")

    ca_a_checksum = calculate_checksum("Alfa")
    ca_b_checksum = calculate_checksum("Bete")

    _write_chunk(cache_dir, catalan, path_a, ca_a_checksum, "Alfa")
    _write_chunk(cache_dir, catalan, path_b, ca_b_checksum, "Bete")

    write_correspondence_cache(
        project.root_path,
        [
            {PATH_CHECKSUM_COLUMN: path_a, "Catalan": ca_a_checksum},
            {PATH_CHECKSUM_COLUMN: path_b, "Catalan": ca_b_checksum},
        ],
        [PATH_CHECKSUM_COLUMN, "Catalan"],
    )

    stats = project.clear_translation_cache_all(catalan, str(file_a), None)
    assert stats.removed_chunk_files == 1
    assert not (cache_dir / "Catalan" / path_a / ca_a_checksum).exists()
    assert (cache_dir / "Catalan" / path_b / ca_b_checksum).exists()

    # row for file_a is removed entirely (no other lang columns to preserve it)
    cache_data = read_correspondence_cache(project.root_path)
    assert cache_data is not None
    _, data_list = cache_data
    assert len(data_list) == 1
    assert data_list[0][PATH_CHECKSUM_COLUMN] == path_b
    assert data_list[0]["Catalan"] == ca_b_checksum


def test_clear_all_custom_lang_keyword_scopes_deletion(tmp_path: Path) -> None:
    project, catalan = _make_project_with_custom_lang(tmp_path)
    cache_dir = project.root_path / CONF_DIR / CACHE_DIR_NAME
    path_hash = calculate_path_checksum("doc.md")

    ca_text = "Hola keyword"
    ca_checksum = calculate_checksum(ca_text)
    _write_chunk(cache_dir, catalan, path_hash, ca_checksum, ca_text)

    write_correspondence_cache(
        project.root_path,
        [{PATH_CHECKSUM_COLUMN: path_hash, "Catalan": ca_checksum}],
        [PATH_CHECKSUM_COLUMN, "Catalan"],
    )

    stats = project.clear_translation_cache_all(catalan, None, "keyword")
    assert stats.removed_chunk_files == 1
    assert stats.cleared_fields == 1
    assert not (cache_dir / "Catalan" / path_hash / ca_checksum).exists()

    # row is removed entirely — Catalan was the only language column
    cache_data = read_correspondence_cache(project.root_path)
    assert cache_data is not None
    _, data_list = cache_data
    assert data_list == []


def test_diff_custom_language(tmp_path: Path) -> None:
    """diff searches the given language's cache dir — exact match yields score 1.0."""
    project, catalan = _make_project_with_custom_lang(tmp_path)
    store = TranslationCacheCsv(project.root_path)

    src_text = "Hello world"
    ca_text = "Hola món"
    src_checksum = calculate_checksum(src_text)
    ca_checksum = calculate_checksum(ca_text)
    store.persist_pair(src_checksum, ca_checksum, Language.ENGLISH, catalan, src_text, ca_text, "doc.md")

    result_txt, score = project.diff(ca_text, catalan)
    assert score == 1.0
    assert result_txt == ca_text


def test_diff_custom_language_partial_match(tmp_path: Path) -> None:
    """diff returns a sub-1.0 score for a near-miss query against the cached Catalan chunk."""
    project, catalan = _make_project_with_custom_lang(tmp_path)
    store = TranslationCacheCsv(project.root_path)

    src_text = "Hello world"
    ca_text = "Hola món"
    src_checksum = calculate_checksum(src_text)
    ca_checksum = calculate_checksum(ca_text)
    store.persist_pair(src_checksum, ca_checksum, Language.ENGLISH, catalan, src_text, ca_text, "doc.md")

    result_txt, score = project.diff("Hola", catalan)
    assert 0.0 < score < 1.0
    assert result_txt == ca_text
