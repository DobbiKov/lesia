from pathlib import Path

from trans_lib.constants import CONF_DIR
from trans_lib.doc_translator_mod.myst_file_translator import get_myst_cells
from trans_lib.enums import Language
from trans_lib.helpers import calculate_checksum, calculate_path_checksum
from trans_lib.project_config_models import ProjectConfig
from trans_lib.project_manager import Project
from trans_lib.translation_cache.cache_backend import (
    PATH_CHECKSUM_COLUMN,
    write_correspondence_cache,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_project(tmp_path: Path) -> Project:
    project_root = tmp_path / "proj"
    src_dir = project_root / "src_en"
    src_dir.mkdir(parents=True)
    (project_root / CONF_DIR).mkdir(parents=True)

    config = ProjectConfig.new(project_name="proj")
    config.set_runtime_root_path(project_root)
    config.set_src_dir_config(src_dir, Language.ENGLISH)
    return Project(project_root, config)


def _add_french_target(project: Project) -> Path:
    tgt_dir = project.root_path / "tgt_fr"
    tgt_dir.mkdir(parents=True, exist_ok=True)
    project.config.add_lang_dir_config(tgt_dir, Language.FRENCH)
    return tgt_dir


def _add_german_target(project: Project) -> Path:
    tgt_dir = project.root_path / "tgt_de"
    tgt_dir.mkdir(parents=True, exist_ok=True)
    project.config.add_lang_dir_config(tgt_dir, Language.GERMAN)
    return tgt_dir


def _write_md(directory: Path, name: str, content: str) -> Path:
    path = directory / name
    path.write_text(content, encoding="utf-8")
    return path


def _chunk_checksums(file_path: Path) -> list[str]:
    """Return the ordered checksums of all chunks in a .md source file."""
    return [calculate_checksum(c["source"]) for c in get_myst_cells(file_path)]


def _seed_row(
    project: Project,
    path_hash: str,
    src_checksum: str,
    translations: dict[str, str],  # lang_name → tgt_checksum (or "" for untranslated)
) -> None:
    """Insert one row into the correspondence cache."""
    from trans_lib.translation_cache.cache_backend import read_correspondence_cache

    cache_data = read_correspondence_cache(project.root_path)
    if cache_data is not None:
        fields, data_list = cache_data
    else:
        fields, data_list = [PATH_CHECKSUM_COLUMN, "English"], []

    for lang in translations:
        if lang not in fields:
            fields.append(lang)
    if "English" not in fields:
        fields.insert(1, "English")

    row: dict[str, str] = {PATH_CHECKSUM_COLUMN: path_hash, "English": src_checksum}
    for lang, tgt in translations.items():
        row[lang] = tgt
    data_list.append(row)
    write_correspondence_cache(project.root_path, data_list, fields)


# ---------------------------------------------------------------------------
# Basic structural tests
# ---------------------------------------------------------------------------

def test_status_no_target_languages(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    status = project.get_translation_status(include_files=False)

    assert status.source_lang == "English"
    assert status.target_langs == []
    assert status.never_processed_files == []


def test_status_no_translatable_files(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    _add_french_target(project)

    status = project.get_translation_status(include_files=False)

    assert len(status.target_langs) == 1
    lang = status.target_langs[0]
    assert lang.lang == "French"
    assert lang.total_chunks == 0
    assert lang.translated_chunks == 0
    assert lang.untranslated_chunks == 0
    assert status.never_processed_files == []


def test_status_no_cache_counts_all_as_untranslated(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    _add_french_target(project)
    src_dir = project.config.get_src_dir_path()
    assert src_dir is not None

    src_file = _write_md(src_dir, "doc.md", "# Hello\n\nWorld paragraph.\n")
    project.config.make_file_translatable(src_file, True)

    chunks = get_myst_cells(src_file)
    status = project.get_translation_status(include_files=False)

    lang = status.target_langs[0]
    assert lang.total_chunks == len(chunks)
    assert lang.translated_chunks == 0
    assert lang.untranslated_chunks == len(chunks)
    assert "doc.md" in status.never_processed_files


def test_status_all_chunks_translated(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    _add_french_target(project)
    src_dir = project.config.get_src_dir_path()
    assert src_dir is not None

    src_file = _write_md(src_dir, "doc.md", "# Hello\n\nWorld paragraph.\n")
    project.config.make_file_translatable(src_file, True)

    path_hash = calculate_path_checksum("doc.md")
    checksums = _chunk_checksums(src_file)
    for cs in checksums:
        _seed_row(project, path_hash, cs, {"French": calculate_checksum(f"fr_{cs}")})

    status = project.get_translation_status(include_files=False)

    lang = status.target_langs[0]
    assert lang.total_chunks == len(checksums)
    assert lang.translated_chunks == len(checksums)
    assert lang.untranslated_chunks == 0
    assert status.never_processed_files == []


def test_status_partial_translation(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    _add_french_target(project)
    src_dir = project.config.get_src_dir_path()
    assert src_dir is not None

    # Three-chunk document: top heading + two sections
    src_file = _write_md(src_dir, "doc.md", "# Title\n\n## Section 1\n\nFirst para.\n\n## Section 2\n\nSecond para.\n")
    project.config.make_file_translatable(src_file, True)

    path_hash = calculate_path_checksum("doc.md")
    checksums = _chunk_checksums(src_file)
    assert len(checksums) >= 2, "expected at least 2 chunks"

    # Translate only the first chunk
    _seed_row(project, path_hash, checksums[0], {"French": calculate_checksum("Titre")})
    # Second chunk: cached but not translated (empty target)
    _seed_row(project, path_hash, checksums[1], {"French": ""})

    status = project.get_translation_status(include_files=False)

    lang = status.target_langs[0]
    assert lang.total_chunks == len(checksums)
    assert lang.translated_chunks == 1
    assert lang.untranslated_chunks == len(checksums) - 1


# ---------------------------------------------------------------------------
# Modified-chunk detection (the key correctness test)
# ---------------------------------------------------------------------------

def test_status_modified_chunk_counted_as_untranslated(tmp_path: Path) -> None:
    """
    A chunk that existed in the cache under the old text should NOT count as
    translated after the source text changes.
    """
    project = _make_project(tmp_path)
    _add_french_target(project)
    src_dir = project.config.get_src_dir_path()
    assert src_dir is not None

    src_file = _write_md(src_dir, "doc.md", "# Original heading\n")
    project.config.make_file_translatable(src_file, True)

    old_checksums = _chunk_checksums(src_file)
    path_hash = calculate_path_checksum("doc.md")

    # Seed cache for the original content
    for cs in old_checksums:
        _seed_row(project, path_hash, cs, {"French": calculate_checksum(f"fr_{cs}")})

    # Mutate the source file — checksum changes, cache entry is now stale
    src_file.write_text("# Modified heading\n", encoding="utf-8")

    status = project.get_translation_status(include_files=False)

    lang = status.target_langs[0]
    new_chunks = get_myst_cells(src_file)
    assert lang.total_chunks == len(new_chunks)
    assert lang.translated_chunks == 0          # old cache entry no longer matches
    assert lang.untranslated_chunks == len(new_chunks)


# ---------------------------------------------------------------------------
# Multiple languages
# ---------------------------------------------------------------------------

def test_status_multiple_languages_independent_counts(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    _add_french_target(project)
    _add_german_target(project)
    src_dir = project.config.get_src_dir_path()
    assert src_dir is not None

    src_file = _write_md(src_dir, "doc.md", "# Hello\n\nWorld.\n")
    project.config.make_file_translatable(src_file, True)

    path_hash = calculate_path_checksum("doc.md")
    checksums = _chunk_checksums(src_file)

    # All chunks translated to French, none to German
    for cs in checksums:
        _seed_row(project, path_hash, cs, {
            "French": calculate_checksum(f"fr_{cs}"),
            "German": "",
        })

    status = project.get_translation_status(include_files=False)
    by_lang = {s.lang: s for s in status.target_langs}

    assert by_lang["French"].translated_chunks == len(checksums)
    assert by_lang["French"].untranslated_chunks == 0
    assert by_lang["German"].translated_chunks == 0
    assert by_lang["German"].untranslated_chunks == len(checksums)


# ---------------------------------------------------------------------------
# Multiple files
# ---------------------------------------------------------------------------

def test_status_multiple_files_aggregate_correctly(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    _add_french_target(project)
    src_dir = project.config.get_src_dir_path()
    assert src_dir is not None

    file_a = _write_md(src_dir, "a.md", "# A heading\n")
    file_b = _write_md(src_dir, "b.md", "# B heading\n")
    project.config.make_file_translatable(file_a, True)
    project.config.make_file_translatable(file_b, True)

    checksums_a = _chunk_checksums(file_a)
    checksums_b = _chunk_checksums(file_b)
    path_a = calculate_path_checksum("a.md")
    path_b = calculate_path_checksum("b.md")

    # Translate file_a fully, leave file_b untranslated
    for cs in checksums_a:
        _seed_row(project, path_a, cs, {"French": calculate_checksum(f"fr_{cs}")})

    status = project.get_translation_status(include_files=False)

    lang = status.target_langs[0]
    total_expected = len(checksums_a) + len(checksums_b)
    assert lang.total_chunks == total_expected
    assert lang.translated_chunks == len(checksums_a)
    assert lang.untranslated_chunks == len(checksums_b)
    assert "b.md" in status.never_processed_files
    assert "a.md" not in status.never_processed_files


# ---------------------------------------------------------------------------
# --files flag
# ---------------------------------------------------------------------------

def test_status_include_files_shows_per_file_breakdown(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    _add_french_target(project)
    src_dir = project.config.get_src_dir_path()
    assert src_dir is not None

    file_a = _write_md(src_dir, "a.md", "# A\n")
    file_b = _write_md(src_dir, "b.md", "# B\n")
    project.config.make_file_translatable(file_a, True)
    project.config.make_file_translatable(file_b, True)

    checksums_a = _chunk_checksums(file_a)
    checksums_b = _chunk_checksums(file_b)
    path_a = calculate_path_checksum("a.md")

    # Translate only file_a
    for cs in checksums_a:
        _seed_row(project, path_a, cs, {"French": calculate_checksum(f"fr_{cs}")})

    status = project.get_translation_status(include_files=True)

    lang = status.target_langs[0]
    by_file = {f.relative_path: f for f in lang.files}

    assert "a.md" in by_file
    assert by_file["a.md"].translated_chunks == len(checksums_a)
    assert by_file["a.md"].untranslated_chunks == 0

    assert "b.md" in by_file
    assert by_file["b.md"].translated_chunks == 0
    assert by_file["b.md"].untranslated_chunks == len(checksums_b)


def test_status_no_files_flag_returns_empty_file_list(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    _add_french_target(project)
    src_dir = project.config.get_src_dir_path()
    assert src_dir is not None

    src_file = _write_md(src_dir, "doc.md", "# Hello\n")
    project.config.make_file_translatable(src_file, True)

    status = project.get_translation_status(include_files=False)

    assert status.target_langs[0].files == []


# ---------------------------------------------------------------------------
# never_processed_files
# ---------------------------------------------------------------------------

def test_status_never_processed_file_listed(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    _add_french_target(project)
    src_dir = project.config.get_src_dir_path()
    assert src_dir is not None

    src_file = _write_md(src_dir, "untouched.md", "# Never translated\n")
    project.config.make_file_translatable(src_file, True)

    status = project.get_translation_status(include_files=False)

    assert "untouched.md" in status.never_processed_files


def test_status_fully_translated_file_not_in_never_processed(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    _add_french_target(project)
    src_dir = project.config.get_src_dir_path()
    assert src_dir is not None

    src_file = _write_md(src_dir, "done.md", "# Done\n")
    project.config.make_file_translatable(src_file, True)

    path_hash = calculate_path_checksum("done.md")
    for cs in _chunk_checksums(src_file):
        _seed_row(project, path_hash, cs, {"French": calculate_checksum(f"fr_{cs}")})

    status = project.get_translation_status(include_files=False)

    assert "done.md" not in status.never_processed_files


# ---------------------------------------------------------------------------
# Custom language
# ---------------------------------------------------------------------------

def test_status_custom_language(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    tgt_dir = project.root_path / "tgt_ca"
    tgt_dir.mkdir(parents=True, exist_ok=True)
    project.add_custom_language("Catalan", "_ca")
    catalan = project.config.resolve_language("Catalan")
    project.config.add_lang_dir_config(tgt_dir, catalan)

    src_dir = project.config.get_src_dir_path()
    assert src_dir is not None

    src_file = _write_md(src_dir, "doc.md", "# Hello\n\nWorld.\n")
    project.config.make_file_translatable(src_file, True)

    path_hash = calculate_path_checksum("doc.md")
    checksums = _chunk_checksums(src_file)
    for cs in checksums:
        _seed_row(project, path_hash, cs, {"Catalan": calculate_checksum(f"ca_{cs}")})

    status = project.get_translation_status(include_files=False)

    assert len(status.target_langs) == 1
    lang = status.target_langs[0]
    assert lang.lang == "Catalan"
    assert lang.translated_chunks == len(checksums)
    assert lang.untranslated_chunks == 0
