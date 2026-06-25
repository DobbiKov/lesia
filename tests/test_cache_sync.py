from pathlib import Path

import nbformat

from lesia.doc_translator_mod.typst_file_translator import compile_typst_cells, get_typst_cells
from lesia.enums import Language
from lesia.helpers import calculate_checksum
from lesia.project_config_models import ProjectConfig
from lesia.project_manager import Project
from lesia.translation_cache.translation_cache import TranslationCacheCsv
from lesia.constants import CONF_DIR


def _write_notebook(path: Path, cells: list[nbformat.NotebookNode]) -> None:
    nb = nbformat.v4.new_notebook()
    nb.cells = cells
    nbformat.write(nb, path)


def test_sync_translation_cache_from_notebook(tmp_path):
    project_root = tmp_path / "proj"
    src_dir = project_root / "src_en"
    tgt_dir = project_root / "proj_fr"
    src_dir.mkdir(parents=True)
    tgt_dir.mkdir(parents=True)
    (project_root / CONF_DIR).mkdir(parents=True)

    source_file = src_dir / "notebook.ipynb"
    target_file = tgt_dir / "notebook.ipynb"

    source_cells = [
        nbformat.v4.new_markdown_cell("Alpha chunk"),
        nbformat.v4.new_markdown_cell("Beta chunk"),
    ]
    _write_notebook(source_file, source_cells)

    translated_texts = ["Alpha traduit", "Beta traduit"]
    target_cells = []
    for cell, translated in zip(source_cells, translated_texts):
        checksum = calculate_checksum(cell["source"])
        new_cell = nbformat.v4.new_markdown_cell(translated)
        new_cell.metadata = {"src_checksum": checksum}
        target_cells.append(new_cell)
    _write_notebook(target_file, target_cells)

    config = ProjectConfig.new(project_name="proj")
    config.set_runtime_root_path(project_root)
    config.set_src_dir_config(src_dir, Language.ENGLISH)
    config.add_lang_dir_config(tgt_dir, Language.FRENCH)
    config.make_file_translatable(source_file, True)

    project = Project(project_root, config)
    project.sync_translation_cache()

    store = TranslationCacheCsv(project_root)
    relative_path = source_file.relative_to(src_dir).as_posix()

    for original_cell, translated in zip(source_cells, translated_texts):
        checksum = calculate_checksum(original_cell["source"])
        cached = store.lookup(checksum, Language.ENGLISH, Language.FRENCH, relative_path)
        assert cached == translated


def test_sync_translation_cache_from_typst(tmp_path):
    project_root = tmp_path / "proj"
    src_dir = project_root / "src_en"
    tgt_dir = project_root / "proj_fr"
    src_dir.mkdir(parents=True)
    tgt_dir.mkdir(parents=True)
    (project_root / CONF_DIR).mkdir(parents=True)

    source_file = src_dir / "lesson.typ"
    target_file = tgt_dir / "lesson.typ"

    source_text = """= Heading

Plain paragraph one.

#ex(info: "Label")[Body text]
"""
    source_file.write_text(source_text, encoding="utf-8")

    source_cells = get_typst_cells(source_file)
    translated_cells: list[dict] = []
    for index, cell in enumerate(source_cells):
        src_chunk = cell["source"]
        checksum = calculate_checksum(src_chunk)
        translated_cells.append(
            {
                "metadata": {"src_checksum": checksum, "needs_review": "True"},
                "source": f"translated-{index}",
            }
        )
    target_file.write_text(compile_typst_cells(translated_cells), encoding="utf-8")

    config = ProjectConfig.new(project_name="proj")
    config.set_runtime_root_path(project_root)
    config.set_src_dir_config(src_dir, Language.ENGLISH)
    config.add_lang_dir_config(tgt_dir, Language.FRENCH)
    config.make_file_translatable(source_file, True)

    project = Project(project_root, config)
    project.sync_translation_cache()

    store = TranslationCacheCsv(project_root)
    relative_path = source_file.relative_to(src_dir).as_posix()

    for index, cell in enumerate(source_cells):
        checksum = calculate_checksum(cell["source"])
        cached = store.lookup(checksum, Language.ENGLISH, Language.FRENCH, relative_path)
        assert cached == f"translated-{index}"


def test_sync_translation_cache_custom_language(tmp_path):
    project_root = tmp_path / "proj"
    src_dir = project_root / "src_en"
    tgt_dir = project_root / "tgt_ca"
    src_dir.mkdir(parents=True)
    tgt_dir.mkdir(parents=True)
    (project_root / CONF_DIR).mkdir(parents=True)

    source_file = src_dir / "notebook.ipynb"
    target_file = tgt_dir / "notebook.ipynb"

    source_cells = [
        nbformat.v4.new_markdown_cell("Alpha chunk"),
        nbformat.v4.new_markdown_cell("Beta chunk"),
    ]
    _write_notebook(source_file, source_cells)

    translated_texts = ["Alpha traduït", "Beta traduït"]
    target_cells = []
    for cell, translated in zip(source_cells, translated_texts):
        checksum = calculate_checksum(cell["source"])
        new_cell = nbformat.v4.new_markdown_cell(translated)
        new_cell.metadata = {"src_checksum": checksum}
        target_cells.append(new_cell)
    _write_notebook(target_file, target_cells)

    config = ProjectConfig.new(project_name="proj")
    config.set_runtime_root_path(project_root)
    config.set_src_dir_config(src_dir, Language.ENGLISH)
    config.add_custom_language("Catalan", "_ca")
    catalan = config.resolve_language("Catalan")
    config.add_lang_dir_config(tgt_dir, catalan)
    config.make_file_translatable(source_file, True)

    project = Project(project_root, config)
    project.sync_translation_cache()

    store = TranslationCacheCsv(project_root)
    relative_path = source_file.relative_to(src_dir).as_posix()

    for original_cell, translated in zip(source_cells, translated_texts):
        checksum = calculate_checksum(original_cell["source"])
        cached = store.lookup(checksum, Language.ENGLISH, catalan, relative_path)
        assert cached == translated
