from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from .errors import (
    CorrectTranslationError,
    CorrectingTranslationError,
    FileDoesNotExistError,
    GetTranslatableFilesError,
    NoSourceFileError,
    NoSourceLanguageError,
    TargetLanguageNotInProjectError,
    TranslateFileError,
    TranslationCacheSyncError,
    TranslationCacheClearError,
    TranslationProcessError,
    UntranslatableFileError,
)
from .enums import DocumentType, Language, CustomLanguage
from .translator_retrieval import TranslationStats


@dataclass
class FileTranslationStatus:
    relative_path: str
    total_chunks: int
    translated_chunks: int
    needs_review_chunks: int = 0

    @property
    def untranslated_chunks(self) -> int:
        return self.total_chunks - self.translated_chunks

    @property
    def proofread_chunks(self) -> int:
        return self.translated_chunks - self.needs_review_chunks


@dataclass
class LangTranslationStatus:
    lang: str
    total_chunks: int
    translated_chunks: int
    needs_review_chunks: int = 0
    files: list[FileTranslationStatus] = field(default_factory=list)

    @property
    def untranslated_chunks(self) -> int:
        return self.total_chunks - self.translated_chunks

    @property
    def proofread_chunks(self) -> int:
        return self.translated_chunks - self.needs_review_chunks


@dataclass
class TranslationStatus:
    source_lang: str
    target_langs: list[LangTranslationStatus]
    never_processed_files: list[str]

if TYPE_CHECKING:
    from .project_manager import Project
    from lesia.vocab_list import VocabList


def _require_source_language(project: Project) -> CustomLanguage:
    source_language = project._get_source_language()
    if source_language is None:
        raise NoSourceLanguageError("No source language set")
    return project.config.resolve_language(source_language)


def _apply_typst_translation_settings(project: Project) -> None:
    from .xml_manipulator_mod.typst import configure_typst_translatable_string_args_by_function

    configure_typst_translatable_string_args_by_function(
        project.get_typst_translatable_string_args_by_function()
    )


def _apply_latex_translation_settings(project: Project) -> None:
    from .xml_manipulator_mod.latex import configure_latex_settings

    settings = project.get_latex_settings()
    configure_latex_settings(
        extra_placeholder_envs=settings["extra_placeholder_envs"],
        extra_math_envs=settings["extra_math_envs"],
        extra_placeholder_commands=settings["extra_placeholder_commands"],
        command_translatable_args=settings["command_translatable_args"],
        custom_command_specs=settings["custom_command_specs"],
    )


def _get_target_dir_config(project: Project, target_lang: Language | CustomLanguage):
    for lang_dir in project.config.lang_dirs:
        if lang_dir.language == target_lang:
            return lang_dir
    return None


def _correct_translation_file(project: Project, target_path: Path, target_lang: Language | CustomLanguage) -> None:
    print(f"Verifying {target_path.name} for the corrected translations ...")
    source_language = _require_source_language(project)

    target_lang_dir_config = _get_target_dir_config(project, target_lang)
    if not target_lang_dir_config:
        raise CorrectTranslationError(
            TargetLanguageNotInProjectError(f"Cannot correct translation: Target language {target_lang} not in project."))

    target_root = target_lang_dir_config.get_path()
    try:
        relative_path = target_path.relative_to(target_root).as_posix()
    except ValueError as exc:
        raise CorrectTranslationError(
            UntranslatableFileError(f"File {target_path} is not inside the target directory {target_root}")) from exc

    try:
        from .doc_corrector import correct_file_translation
        if correct_file_translation(project.root_path, target_path, target_lang, source_language, relative_path):
            print(f"Successfully corrected the translation in {target_path.name}")
        else:
            print("The file doesn't need any corrections to be saved")
    except CorrectingTranslationError as e:
        raise CorrectTranslationError(f"Correcting process failed for {target_path.name}: {e}", e)
    except IOError as e:
        raise CorrectTranslationError(f"IO error during correction of {target_path.name}: {e}", e)


def correct_translation_for_lang(project: Project, target_lang: Language | CustomLanguage) -> None:
    if target_lang not in project._get_target_languages():
        raise CorrectTranslationError(
            TargetLanguageNotInProjectError(f"Cannot correct translation: Target language {target_lang} not in project."))
    source_language = project._get_source_language()
    src_dir = project.config.src_dir
    if source_language is None or src_dir is None:
        raise CorrectTranslationError(
            NoSourceLanguageError("Cannot find the source file: No source language set."))
    src_path = src_dir.get_path()
    translatable_files = project.get_translatable_files()
    target_lang_dir_config = _get_target_dir_config(project, target_lang)

    if not target_lang_dir_config:
        raise CorrectTranslationError(
            TargetLanguageNotInProjectError("Critical: Target language config vanished."))
    tgt_lang_dir = target_lang_dir_config.get_path()
    translated_paths = [tgt_lang_dir.joinpath(path.relative_to(src_path)) for path in translatable_files]
    for tr_path in translated_paths:
        _correct_translation_file(project, tr_path, target_lang)


def correct_translation_single_file(project: Project, file_path_str: str) -> None:
    try:
        file_path = Path(file_path_str).resolve(strict=True)
    except FileNotFoundError:
        raise CorrectTranslationError(FileDoesNotExistError(f"File {file_path_str} not found."))

    _require_source_language(project)
    target_lang_dirs = project._get_target_language_dirs()

    src_lang_dir = project.config.src_dir
    if src_lang_dir is None:
        raise CorrectTranslationError(NoSourceLanguageError("Cannot find the source file: No source language set."))
    root_path = project.root_path
    if not file_path.is_relative_to(root_path):
        raise CorrectTranslationError(
            UntranslatableFileError("The file doesn't have any correspondent source translatable file"))

    target_lang = None
    for tgt_lang_dir in target_lang_dirs:
        if file_path.is_relative_to(tgt_lang_dir.get_path()):
            target_lang = tgt_lang_dir.language
            break

    if target_lang is None:
        raise CorrectTranslationError(
            UntranslatableFileError("The file doesn't have any correspondent source translatable file"))

    if target_lang not in project._get_target_languages():
        raise CorrectTranslationError(
            TargetLanguageNotInProjectError(f"Cannot correct translation: Target language {target_lang} not in project."))

    src_file = project._find_correspondent_translatable_file(file_path)
    if src_file is None:
        raise CorrectTranslationError(
            NoSourceFileError(f"There's no source file for the given {file_path_str}"))

    if not project.config.src_dir:
        raise CorrectTranslationError(NoSourceLanguageError("Critical: Source directory vanished"))

    if not _get_target_dir_config(project, target_lang):
        raise CorrectTranslationError(
            TargetLanguageNotInProjectError("Critical: Target language config vanished."))

    _correct_translation_file(project, file_path, target_lang)


def sync_translation_cache(project: Project, target_lang: Language | CustomLanguage | None = None) -> None:
    source_language = project._get_source_language()
    if source_language is None:
        raise TranslationCacheSyncError("Cannot sync translation cache: Source language is not set.")

    src_dir = project.config.src_dir
    if src_dir is None:
        raise TranslationCacheSyncError("Cannot sync translation cache: Source directory is not configured.")
    src_root = src_dir.get_path()

    target_lang_dirs = project._get_target_language_dirs()
    if target_lang is not None:
        target_lang_dirs = [ld for ld in target_lang_dirs if ld.language == target_lang]
        if not target_lang_dirs:
            raise TranslationCacheSyncError(
                f"Language {target_lang} is not configured as a target language.")

    if not target_lang_dirs:
        raise TranslationCacheSyncError("Cannot sync translation cache: No target languages configured.")

    try:
        translatable_files = project.get_translatable_files()
    except GetTranslatableFilesError as exc:
        raise TranslationCacheSyncError(f"Cannot sync translation cache: {exc}") from exc

    if not translatable_files:
        raise TranslationCacheSyncError(
            "Cannot sync translation cache: No translatable files configured.")

    from loguru import logger
    from .translation_cache.translation_cache import TranslationCacheCsv
    from .translation_cache.cache_rebuilder import collect_translation_pairs
    from .helpers import analyze_document_type, calculate_checksum

    store = TranslationCacheCsv(project.root_path)
    synced_pairs = 0
    processed_files = 0

    for target_dir in target_lang_dirs:
        target_root = target_dir.get_path()
        if not target_root.exists():
            raise TranslationCacheSyncError(
                f"Target directory {target_root} does not exist.")

        for src_file in translatable_files:
            try:
                relative_path = src_file.relative_to(src_root)
            except ValueError as exc:
                raise TranslationCacheSyncError(
                    f"Translatable file {src_file} is not inside the configured source directory {src_root}.",
                ) from exc

            target_file = target_root / relative_path
            if not target_file.exists():
                logger.warning(
                    "Skipping cache sync for {} → {}: target file is missing.",
                    src_file,
                    target_file,
                )
                continue

            doc_type = analyze_document_type(src_file)
            try:
                recovered_pairs = collect_translation_pairs(src_file, target_file, doc_type)
            except Exception as exc:
                raise TranslationCacheSyncError(
                    f"Failed to collect translation chunks for {target_file}: {exc}",
                ) from exc

            if not recovered_pairs:
                continue

            processed_files += 1
            relative_path_str = relative_path.as_posix()

            for pair in recovered_pairs:
                tgt_checksum = calculate_checksum(pair.tgt_text)
                store.persist_pair(
                    pair.src_checksum,
                    tgt_checksum,
                    source_language,
                    target_dir.language,
                    pair.src_text,
                    pair.tgt_text,
                    relative_path_str,
                )
                synced_pairs += 1

    logger.info(
        "Synced {} translation chunk pairs from {} files for {} target language(s).",
        synced_pairs,
        processed_files,
        len(target_lang_dirs),
    )


def clear_translation_cache_missing_chunks(project: Project) -> CacheClearStats:
    source_language = project._get_source_language()
    if source_language is None:
        raise TranslationCacheClearError("Cannot clear translation cache: Source language is not set.")

    from .translation_cache.cache_cleaner import clear_missing_chunks
    try:
        return clear_missing_chunks(project.root_path, source_language)
    except Exception as exc:
        raise TranslationCacheClearError(f"Cannot clear translation cache: {exc}") from exc


def _resolve_relative_cache_path(project: Project, file_path_str: str) -> str:
    src_dir_path = project.config.get_src_dir_path()
    if src_dir_path is None:
        raise TranslationCacheClearError(
            "Cannot clear translation cache by file: Source directory is not set.",
        )

    src_dir_path = src_dir_path.resolve()
    input_path = Path(file_path_str)
    candidates = []
    if input_path.is_absolute():
        candidates.append(input_path)
    else:
        candidates.append(input_path.resolve())
        candidates.append(project.root_path / input_path)
        candidates.append(src_dir_path / input_path)

    target_dir_paths = []
    for lang in project._get_target_languages():
        target_dir = project.config.get_target_dir_path_by_lang(lang)
        if target_dir is not None:
            target_dir_paths.append(target_dir.resolve())

    base_dirs = [src_dir_path, *target_dir_paths]

    for candidate in candidates:
        resolved = candidate.resolve()
        if not resolved.exists():
            continue
        for base_dir in base_dirs:
            if resolved.is_relative_to(base_dir):
                return resolved.relative_to(base_dir).as_posix()

    raise TranslationCacheClearError(
        "Cannot clear translation cache: File path must be inside the source or target directories.",
    )


def clear_translation_cache_by_checksum(
    project: Project,
    checksum: str,
    lang: Language | CustomLanguage | None,
) -> CacheDeleteStats:
    source_language = project._get_source_language()
    if source_language is None:
        raise TranslationCacheClearError("Cannot clear translation cache: Source language is not set.")

    from .translation_cache.cache_cleaner import clear_by_checksum
    try:
        return clear_by_checksum(project.root_path, checksum, source_language, lang)
    except Exception as exc:
        raise TranslationCacheClearError(f"Cannot clear translation cache: {exc}") from exc


def clear_translation_cache_all(
    project: Project,
    lang: Language | CustomLanguage | None,
    file_path_str: str | None,
    keyword: str | None,
) -> CacheDeleteStats:
    relative_path = None
    if file_path_str is not None:
        relative_path = _resolve_relative_cache_path(project, file_path_str)

    from .translation_cache.cache_cleaner import clear_all
    try:
        return clear_all(project.root_path, lang, relative_path, keyword)
    except Exception as exc:
        raise TranslationCacheClearError(f"Cannot clear translation cache: {exc}") from exc


async def translate_single_file(
    project: Project,
    file_path_str: str,
    target_lang: Language | CustomLanguage,
    vocab_list: VocabList | None,
    use_reasoning_model: bool = False,
) -> TranslationStats:
    _apply_typst_translation_settings(project)
    _apply_latex_translation_settings(project)

    try:
        file_path = Path(file_path_str).resolve(strict=True)
    except FileNotFoundError:
        raise TranslateFileError(FileDoesNotExistError(f"File {file_path_str} not found."))

    source_language = project._get_source_language()
    if source_language is None:
        raise TranslateFileError(NoSourceLanguageError("Cannot translate: No source language set."))

    if vocab_list is None:
        vocab_file = project.config.get_vocab_file_path()
        if vocab_file is not None:
            if vocab_file.is_file():
                import csv
                from .vocab_list import vocab_list_from_vocab_db
                with open(vocab_file, "r", encoding="utf-8") as _f:
                    _db = list(csv.DictReader(_f))
                src_lang = project.get_source_langugage()
                vocab_list = vocab_list_from_vocab_db(_db, src_lang, target_lang)
                print(f"  [vocab] Using config vocab file: {vocab_file.name}")
            else:
                from loguru import logger
                logger.warning("Config vocab file '{}' does not exist, skipping.", vocab_file)

    if target_lang not in project._get_target_languages():
        raise TranslateFileError(
            TargetLanguageNotInProjectError(
                f"Cannot translate: Target language {target_lang} not in project."))

    translatable_files = project.get_translatable_files()
    if file_path not in translatable_files:
        raise TranslateFileError(
            UntranslatableFileError(f"File {file_path} is not marked as translatable."))

    if not project.config.src_dir:
        raise TranslateFileError(
            NoSourceLanguageError("Critical: Source directory vanished"))

    src_dir_root_path = project.config.src_dir.get_path()
    target_lang_dir_config = _get_target_dir_config(project, target_lang)

    if not target_lang_dir_config:
        raise TranslateFileError(
            TargetLanguageNotInProjectError("Critical: Target language config vanished."))

    target_dir_root_path = target_lang_dir_config.get_path()

    try:
        relative_path = file_path.relative_to(src_dir_root_path)
    except ValueError:
        raise TranslateFileError(
            FileDoesNotExistError(
                f"File {file_path} is translatable but not in source root {src_dir_root_path}."))

    target_file_path = target_dir_root_path / relative_path
    relative_path_str = relative_path.as_posix()

    from .translator_retrieval import display_path
    src_display = display_path(file_path, project.root_path)
    tgt_display = display_path(target_file_path, project.root_path)
    print(f"Translating {src_display} ({source_language}) -> {tgt_display} ({target_lang})...")
    if use_reasoning_model:
        llm_service = project.get_llm_reasoning_service() or project.get_llm_service()
        llm_model = project.get_llm_reasoning_model() or project.get_llm_model()
        llm_reasoning_service = None
        llm_reasoning_model = None
        print(f"  [model] Using reasoning model only: {llm_service}/{llm_model}")
    else:
        llm_service = project.get_llm_service()
        llm_model = project.get_llm_model()
        llm_reasoning_service = project.get_llm_reasoning_service()
        llm_reasoning_model = project.get_llm_reasoning_model()
        print(f"  [model] Casual: {llm_service}/{llm_model}", end="")
        if llm_reasoning_service and llm_reasoning_model:
            print(f"  |  Reasoning: {llm_reasoning_service}/{llm_reasoning_model}")
        else:
            print()
    from .doc_translator import translate_file_to_file_async
    try:
        stats = await translate_file_to_file_async(
            project.root_path,
            file_path,
            source_language,
            target_file_path,
            target_lang,
            relative_path_str,
            vocab_list,
            llm_service,
            llm_model,
            llm_reasoning_service,
            llm_reasoning_model,
            use_reasoning_model=use_reasoning_model,
            xml_retries_before_reasoning=project.get_xml_retries_before_reasoning(),
            env_file=project.config.get_env_file_path(),
        )
    except TranslationProcessError as e:
        raise TranslateFileError(f"Translation process failed for {file_path.name}: {e}", e)
    except IOError as e:
        raise TranslateFileError(f"IO error during translation of {file_path.name}: {e}", e)
    return stats


async def translate_all_for_language(
    project: Project,
    target_lang: Language | CustomLanguage,
    vocab_list: VocabList | None,
    use_reasoning_model: bool = False,
    on_file_translated: Callable[[Path, TranslationStats], None] | None = None,
) -> TranslationStats:
    translatable_files = project.get_translatable_files()
    if not translatable_files:
        print(f"No translatable files found for language {target_lang}.")
        return TranslationStats()

    print(f"Starting translation of {len(translatable_files)} files to {target_lang}...")
    total_stats = TranslationStats()
    for i, file_path in enumerate(translatable_files):
        print(f"--- File {i+1}/{len(translatable_files)} ---")
        try:
            file_stats = await translate_single_file(project, str(file_path), target_lang, vocab_list, use_reasoning_model=use_reasoning_model)
            total_stats = total_stats + file_stats
            if on_file_translated is not None:
                on_file_translated(file_path, file_stats)
        except TranslateFileError as e:
            print(f"ERROR translating {file_path.name}: {e}. Skipping this file.")
    print(f"Finished translation to {target_lang}.")
    return total_stats


def diff(project: Project, txt: str, lang: Language | CustomLanguage) -> tuple[str, float]:
    from .translation_cache.translation_cache import TranslationCacheCsv
    return TranslationCacheCsv(project.root_path).get_best_match_from_cache(lang, txt)


def _get_source_chunk_texts(file_path: Path, doc_type: DocumentType) -> list[str]:
    """Returns the text of each translatable chunk in a source file."""
    from loguru import logger
    try:
        if doc_type == DocumentType.LaTeX:
            from .doc_translator_mod.latex_file_translator import get_latex_cells
            return [c["source"] for c in get_latex_cells(file_path)]
        elif doc_type == DocumentType.Markdown:
            from .doc_translator_mod.myst_file_translator import get_myst_cells
            return [c["source"] for c in get_myst_cells(file_path)]
        elif doc_type == DocumentType.Typst:
            from .doc_translator_mod.typst_file_translator import get_typst_cells
            return [c["source"] for c in get_typst_cells(file_path)]
        elif doc_type == DocumentType.JupyterNotebook:
            import jupytext
            nb = jupytext.read(file_path)
            return [cell["source"] for cell in nb.cells]
        else:
            return [file_path.read_text(encoding="utf-8")]
    except Exception as e:
        logger.warning("Could not chunk {}: {}", file_path, e)
        return []


def get_translation_status(project: Project, include_files: bool) -> TranslationStatus:
    from .translation_cache.cache_backend import read_correspondence_cache, PATH_CHECKSUM_COLUMN
    from .translation_cache.cache_rebuilder import read_existing_target_metadata
    from .helpers import analyze_document_type, calculate_checksum, calculate_path_checksum

    source_language = project._get_source_language()
    if source_language is None:
        raise NoSourceLanguageError("No source language set")

    source_lang_name = str(project.config.resolve_language(source_language))
    target_lang_objs = project._get_target_languages()
    target_langs = [str(project.config.resolve_language(l)) for l in target_lang_objs]

    # Build lookup: (src_checksum, path_hash) → {lang_name: tgt_checksum}
    # This lets us check, for each live source chunk, whether a translation exists.
    cache_lookup: dict[tuple[str, str], dict[str, str]] = {}
    cache_data = read_correspondence_cache(project.root_path)
    if cache_data is not None:
        fields, data_list = cache_data
        for row in data_list:
            path_hash = row.get(PATH_CHECKSUM_COLUMN, "")
            src_checksum = row.get(source_lang_name, "")
            if not src_checksum:
                continue
            cache_lookup[(src_checksum, path_hash)] = {
                lang: row.get(lang, "")
                for lang in target_langs
                if lang in fields
            }

    # Build target directory lookup: lang_name → target_dir Path
    lang_target_dirs: dict[str, Path | None] = {}
    for l, lang_name in zip(target_lang_objs, target_langs):
        lang_target_dirs[lang_name] = project.config.get_target_dir_path_by_lang(
            project.config.resolve_language(l)
        )

    src_dir_path = project.config.get_src_dir_path()
    if src_dir_path is None:
        raise NoSourceLanguageError("Source directory is not set")

    try:
        translatable_files = project.get_translatable_files()
    except GetTranslatableFilesError:
        translatable_files = []

    # Accumulators
    lang_total: dict[str, int] = {lang: 0 for lang in target_langs}
    lang_translated: dict[str, int] = {lang: 0 for lang in target_langs}
    lang_needs_review: dict[str, int] = {lang: 0 for lang in target_langs}
    # lang → {rel_path → [total, translated, needs_review]}
    lang_file_stats: dict[str, dict[str, list[int]]] = {lang: {} for lang in target_langs}
    never_processed_files: list[str] = []

    for src_file in translatable_files:
        try:
            rel_path = src_file.relative_to(src_dir_path).as_posix()
        except ValueError:
            continue

        path_hash = calculate_path_checksum(rel_path)
        doc_type = analyze_document_type(src_file)
        chunk_texts = _get_source_chunk_texts(src_file, doc_type)

        # Load needs_review metadata from each translated target file (once per lang per file)
        lang_file_metadata: dict[str, dict[str, dict]] = {}
        for lang_name in target_langs:
            target_dir = lang_target_dirs.get(lang_name)
            if target_dir is not None:
                lang_file_metadata[lang_name] = read_existing_target_metadata(
                    target_dir / rel_path, doc_type
                )
            else:
                lang_file_metadata[lang_name] = {}

        file_any_cached = False

        for chunk_text in chunk_texts:
            src_checksum = calculate_checksum(chunk_text)
            translations = cache_lookup.get((src_checksum, path_hash))

            if translations is not None:
                file_any_cached = True

            for lang_name in target_langs:
                lang_total[lang_name] += 1
                is_translated = bool(translations and translations.get(lang_name, ""))
                if is_translated:
                    lang_translated[lang_name] += 1
                    chunk_meta = lang_file_metadata[lang_name].get(src_checksum, {})
                    if chunk_meta.get("needs_review") == "True":
                        lang_needs_review[lang_name] += 1

                if include_files:
                    if rel_path not in lang_file_stats[lang_name]:
                        lang_file_stats[lang_name][rel_path] = [0, 0, 0]
                    lang_file_stats[lang_name][rel_path][0] += 1
                    if is_translated:
                        lang_file_stats[lang_name][rel_path][1] += 1
                        chunk_meta = lang_file_metadata[lang_name].get(src_checksum, {})
                        if chunk_meta.get("needs_review") == "True":
                            lang_file_stats[lang_name][rel_path][2] += 1

        if not file_any_cached:
            never_processed_files.append(rel_path)

    # Build result objects
    target_lang_statuses: list[LangTranslationStatus] = []
    for lang_name in target_langs:
        file_statuses: list[FileTranslationStatus] = []
        if include_files:
            for rel_path, (total, translated, needs_review) in lang_file_stats[lang_name].items():
                file_statuses.append(FileTranslationStatus(
                    relative_path=rel_path,
                    total_chunks=total,
                    translated_chunks=translated,
                    needs_review_chunks=needs_review,
                ))
            file_statuses.sort(key=lambda s: s.relative_path)
        target_lang_statuses.append(LangTranslationStatus(
            lang=lang_name,
            total_chunks=lang_total[lang_name],
            translated_chunks=lang_translated[lang_name],
            needs_review_chunks=lang_needs_review[lang_name],
            files=file_statuses,
        ))
    target_lang_statuses.sort(key=lambda s: s.lang)

    return TranslationStatus(
        source_lang=source_lang_name,
        target_langs=target_lang_statuses,
        never_processed_files=sorted(never_processed_files),
    )
