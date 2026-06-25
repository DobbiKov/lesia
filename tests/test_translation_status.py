from pathlib import Path

from lesia.constants import CONF_DIR
from lesia.doc_translator_mod.myst_file_translator import get_myst_cells
from lesia.enums import Language
from lesia.helpers import calculate_checksum, calculate_path_checksum
from lesia.project_config_models import ProjectConfig
from lesia.project_manager import Project
from lesia.translation_cache.cache_backend import (
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
    from lesia.translation_cache.cache_backend import read_correspondence_cache

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


# ---------------------------------------------------------------------------
# Helpers for needs_review / proofread tests
# ---------------------------------------------------------------------------

def _write_target_md_with_metadata(
    directory: Path,
    name: str,
    chunks: list[dict],
) -> Path:
    """Write a translated MyST file with per-chunk metadata blocks.

    Each entry in *chunks* should have:
      - "src_checksum": str  – checksum of the original source chunk
      - "source": str        – translated text
      - "needs_review": bool (optional, defaults to False)
    """
    from lesia.doc_translator_mod.myst_file_translator import compile_myst_cells

    cells = []
    for chunk in chunks:
        metadata: dict[str, str] = {"src_checksum": chunk["src_checksum"]}
        if chunk.get("needs_review"):
            metadata["needs_review"] = "True"
        cells.append({"metadata": metadata, "source": chunk["source"]})

    path = directory / name
    path.write_text(compile_myst_cells(cells), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Unit tests for proofread_chunks / needs_review_chunks properties
# ---------------------------------------------------------------------------

def test_lang_status_proofread_chunks_property() -> None:
    from lesia.project_runtime import LangTranslationStatus

    lang = LangTranslationStatus(
        lang="French",
        total_chunks=10,
        translated_chunks=8,
        needs_review_chunks=3,
    )
    assert lang.proofread_chunks == 5
    assert lang.untranslated_chunks == 2


def test_file_status_proofread_chunks_property() -> None:
    from lesia.project_runtime import FileTranslationStatus

    f = FileTranslationStatus(
        relative_path="doc.md",
        total_chunks=6,
        translated_chunks=4,
        needs_review_chunks=1,
    )
    assert f.proofread_chunks == 3
    assert f.untranslated_chunks == 2


def test_lang_status_all_proofread_when_no_needs_review() -> None:
    from lesia.project_runtime import LangTranslationStatus

    lang = LangTranslationStatus(lang="French", total_chunks=5, translated_chunks=5)
    assert lang.needs_review_chunks == 0
    assert lang.proofread_chunks == 5


# ---------------------------------------------------------------------------
# Integration tests: needs_review counting in get_translation_status
# ---------------------------------------------------------------------------

def test_status_needs_review_zero_when_no_target_file(tmp_path: Path) -> None:
    """When the target file does not exist, needs_review_chunks must be 0."""
    project = _make_project(tmp_path)
    _add_french_target(project)
    src_dir = project.config.get_src_dir_path()
    assert src_dir is not None

    src_file = _write_md(src_dir, "doc.md", "# Hello\n\nWorld.\n")
    project.config.make_file_translatable(src_file, True)

    path_hash = calculate_path_checksum("doc.md")
    checksums = _chunk_checksums(src_file)
    for cs in checksums:
        _seed_row(project, path_hash, cs, {"French": calculate_checksum(f"fr_{cs}")})

    # No target file written — metadata cannot be read
    status = project.get_translation_status(include_files=False)

    lang = status.target_langs[0]
    assert lang.translated_chunks == len(checksums)
    assert lang.needs_review_chunks == 0
    assert lang.proofread_chunks == len(checksums)


def test_status_all_proofread_when_target_has_no_needs_review_flag(tmp_path: Path) -> None:
    """Translated chunks without the needs_review flag are counted as proofread."""
    project = _make_project(tmp_path)
    tgt_dir = _add_french_target(project)
    src_dir = project.config.get_src_dir_path()
    assert src_dir is not None

    src_file = _write_md(src_dir, "doc.md", "# Hello\n\nWorld.\n")
    project.config.make_file_translatable(src_file, True)

    path_hash = calculate_path_checksum("doc.md")
    checksums = _chunk_checksums(src_file)
    for cs in checksums:
        _seed_row(project, path_hash, cs, {"French": calculate_checksum(f"fr_{cs}")})

    # Write target file without needs_review metadata
    _write_target_md_with_metadata(
        tgt_dir,
        "doc.md",
        [{"src_checksum": cs, "source": f"fr_{cs}", "needs_review": False} for cs in checksums],
    )

    status = project.get_translation_status(include_files=False)

    lang = status.target_langs[0]
    assert lang.translated_chunks == len(checksums)
    assert lang.needs_review_chunks == 0
    assert lang.proofread_chunks == len(checksums)


def test_status_some_chunks_need_review(tmp_path: Path) -> None:
    """Only chunks with needs_review=True in the target file are counted."""
    project = _make_project(tmp_path)
    tgt_dir = _add_french_target(project)
    src_dir = project.config.get_src_dir_path()
    assert src_dir is not None

    src_file = _write_md(src_dir, "doc.md", "# Title\n\n## Section\n\nParagraph.\n")
    project.config.make_file_translatable(src_file, True)

    path_hash = calculate_path_checksum("doc.md")
    checksums = _chunk_checksums(src_file)
    assert len(checksums) >= 2

    for cs in checksums:
        _seed_row(project, path_hash, cs, {"French": calculate_checksum(f"fr_{cs}")})

    # Mark only the first chunk as needing review
    _write_target_md_with_metadata(
        tgt_dir,
        "doc.md",
        [
            {"src_checksum": checksums[0], "source": f"fr_{checksums[0]}", "needs_review": True},
            *[
                {"src_checksum": cs, "source": f"fr_{cs}", "needs_review": False}
                for cs in checksums[1:]
            ],
        ],
    )

    status = project.get_translation_status(include_files=False)

    lang = status.target_langs[0]
    assert lang.translated_chunks == len(checksums)
    assert lang.needs_review_chunks == 1
    assert lang.proofread_chunks == len(checksums) - 1


def test_status_all_chunks_need_review(tmp_path: Path) -> None:
    """When every translated chunk needs review, proofread_chunks is 0."""
    project = _make_project(tmp_path)
    tgt_dir = _add_french_target(project)
    src_dir = project.config.get_src_dir_path()
    assert src_dir is not None

    src_file = _write_md(src_dir, "doc.md", "# Hello\n\nWorld.\n")
    project.config.make_file_translatable(src_file, True)

    path_hash = calculate_path_checksum("doc.md")
    checksums = _chunk_checksums(src_file)
    for cs in checksums:
        _seed_row(project, path_hash, cs, {"French": calculate_checksum(f"fr_{cs}")})

    _write_target_md_with_metadata(
        tgt_dir,
        "doc.md",
        [{"src_checksum": cs, "source": f"fr_{cs}", "needs_review": True} for cs in checksums],
    )

    status = project.get_translation_status(include_files=False)

    lang = status.target_langs[0]
    assert lang.translated_chunks == len(checksums)
    assert lang.needs_review_chunks == len(checksums)
    assert lang.proofread_chunks == 0


def test_status_needs_review_independent_per_language(tmp_path: Path) -> None:
    """needs_review counts are tracked independently for each target language."""
    project = _make_project(tmp_path)
    fr_dir = _add_french_target(project)
    de_dir = _add_german_target(project)
    src_dir = project.config.get_src_dir_path()
    assert src_dir is not None

    src_file = _write_md(src_dir, "doc.md", "# Hello\n\nWorld.\n")
    project.config.make_file_translatable(src_file, True)

    path_hash = calculate_path_checksum("doc.md")
    checksums = _chunk_checksums(src_file)
    for cs in checksums:
        _seed_row(project, path_hash, cs, {
            "French": calculate_checksum(f"fr_{cs}"),
            "German": calculate_checksum(f"de_{cs}"),
        })

    # French: all proofread; German: all need review
    _write_target_md_with_metadata(
        fr_dir,
        "doc.md",
        [{"src_checksum": cs, "source": f"fr_{cs}", "needs_review": False} for cs in checksums],
    )
    _write_target_md_with_metadata(
        de_dir,
        "doc.md",
        [{"src_checksum": cs, "source": f"de_{cs}", "needs_review": True} for cs in checksums],
    )

    status = project.get_translation_status(include_files=False)
    by_lang = {s.lang: s for s in status.target_langs}

    assert by_lang["French"].needs_review_chunks == 0
    assert by_lang["French"].proofread_chunks == len(checksums)

    assert by_lang["German"].needs_review_chunks == len(checksums)
    assert by_lang["German"].proofread_chunks == 0


def test_status_needs_review_per_file_with_include_files(tmp_path: Path) -> None:
    """With include_files=True, needs_review and proofread counts appear per file."""
    project = _make_project(tmp_path)
    tgt_dir = _add_french_target(project)
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

    for cs in checksums_a:
        _seed_row(project, path_a, cs, {"French": calculate_checksum(f"fr_a_{cs}")})
    for cs in checksums_b:
        _seed_row(project, path_b, cs, {"French": calculate_checksum(f"fr_b_{cs}")})

    # file_a: proofread; file_b: needs review
    _write_target_md_with_metadata(
        tgt_dir,
        "a.md",
        [{"src_checksum": cs, "source": f"fr_a_{cs}", "needs_review": False} for cs in checksums_a],
    )
    _write_target_md_with_metadata(
        tgt_dir,
        "b.md",
        [{"src_checksum": cs, "source": f"fr_b_{cs}", "needs_review": True} for cs in checksums_b],
    )

    status = project.get_translation_status(include_files=True)

    lang = status.target_langs[0]
    by_file = {f.relative_path: f for f in lang.files}

    assert by_file["a.md"].needs_review_chunks == 0
    assert by_file["a.md"].proofread_chunks == len(checksums_a)

    assert by_file["b.md"].needs_review_chunks == len(checksums_b)
    assert by_file["b.md"].proofread_chunks == 0


def test_status_untranslated_chunks_not_counted_in_needs_review(tmp_path: Path) -> None:
    """Untranslated chunks must never contribute to needs_review_chunks."""
    project = _make_project(tmp_path)
    tgt_dir = _add_french_target(project)
    src_dir = project.config.get_src_dir_path()
    assert src_dir is not None

    src_file = _write_md(src_dir, "doc.md", "# Title\n\n## Section\n\nParagraph.\n")
    project.config.make_file_translatable(src_file, True)

    path_hash = calculate_path_checksum("doc.md")
    checksums = _chunk_checksums(src_file)
    assert len(checksums) >= 2

    # Only seed the first chunk in the cache (second chunk is untranslated)
    _seed_row(project, path_hash, checksums[0], {"French": calculate_checksum(f"fr_{checksums[0]}")})

    # Target file contains only the translated chunk, marked needs_review
    _write_target_md_with_metadata(
        tgt_dir,
        "doc.md",
        [{"src_checksum": checksums[0], "source": f"fr_{checksums[0]}", "needs_review": True}],
    )

    status = project.get_translation_status(include_files=False)

    lang = status.target_langs[0]
    assert lang.translated_chunks == 1
    assert lang.untranslated_chunks == len(checksums) - 1
    assert lang.needs_review_chunks == 1
    assert lang.proofread_chunks == 0
