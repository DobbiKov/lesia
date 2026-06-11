from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING

from loguru import logger
from unified_model_caller import LLMCaller

from .enums import Language, CustomLanguage
from .project_config_models import ProjectConfig, LangDir
from .project_config_io import (
    load_project_config,
    write_project_config,
    copy_untranslatable_files_recursive
)
from .helpers import find_dir_upwards
from .constants import CONF_DIR, CONFIG_FILENAME, CUSTOM_SERVICES_DIR_NAME, CUSTOM_SERVICES_TEMPLATE_FILENAME
from .errors import (
    InitProjectError, InvalidPathError, ProjectAlreadyInitializedError, SetLLMServiceError, WriteConfigError as ConfigWriteError,
    LoadProjectError, NoConfigFoundError, LoadConfigError as ConfigLoadError,
    SetSourceDirError, DirectoryDoesNotExistError, NotADirectoryError as PathNotADirectoryError,
    AnalyzeDirError, LangAlreadyInProjectError,
    AddLanguageError, NoSourceLanguageError, LangDirExistsError,
    RemoveLanguageError, TargetLanguageNotInProjectError,
    SyncFilesError, NoTargetLanguagesError, CopyFileDirError, AddTranslatableFileError,
    FileDoesNotExistError, GetTranslatableFilesError,
    AddCustomLanguageError, RemoveCustomLanguageError
)

if TYPE_CHECKING:
    from trans_lib.vocab_list import VocabList


# TODO: add refine translation command

class Project:
    """Manages a translation project."""
    
    root_path: Path
    config: ProjectConfig

    # Private constructor, use load() or create_new_for_init()
    def __init__(self, root_path: Path, config: ProjectConfig):
        """
        Private constructor, use load() or create_new_for_init()
        """
        self.root_path = root_path.resolve()
        self.config = config
        self._normalized_paths_on_load = self.config.set_runtime_root_path(self.root_path)

    @property
    def config_file_path(self) -> Path:
        return self.root_path / CONF_DIR / CONFIG_FILENAME

    @property
    def config_dir_path(self) -> Path:
        return self.root_path / CONF_DIR

    @classmethod
    def _create_new_for_init(cls, project_name: str, project_root_path: Path) -> 'Project':
        """Creates a new Project instance with a new config, for internal use by init_project."""
        abs_path = project_root_path.resolve()
        config = ProjectConfig.new(project_name=project_name)
        return cls(abs_path, config)

    def save_config(self) -> None:
        """Saves the current project configuration (writes to the config file)."""
        try:
            os.makedirs(self.config_dir_path, exist_ok=True)
            write_project_config(self.config_file_path, self.config)
        except ConfigWriteError as e:
            # Wrap in a more specific error if needed, or re-raise
            raise e # Or ProjectSaveConfigError(e)

    @property
    def paths_normalized_on_load(self) -> bool:
        return self._normalized_paths_on_load

    def _get_source_language(self) -> Optional[str]:
        if self.config.src_dir:
            return self.config.src_dir.language
        return None

    def _get_target_language_dirs(self) -> List[LangDir]:
        return self.config.get_lang_dirs()

    def _get_target_languages(self) -> List[str]:
        return [ld.language for ld in self.config.lang_dirs]
    
    def get_source_langugage(self) -> CustomLanguage:
        """
        Returns a source language of the project if such is set, otherwise raises an exception.
        """
        res = self._get_source_language()
        if res is None:
            raise NoSourceLanguageError
        return self.config.resolve_language(res)

    def set_source_directory(self, dir_name: str, lang: Language | CustomLanguage) -> None:
        """Sets the source directory for translations."""
        source_dir_path = self.root_path / dir_name
        if not source_dir_path.exists():
            raise SetSourceDirError(DirectoryDoesNotExistError(f"Directory {source_dir_path} does not exist."))
        if not source_dir_path.is_dir():
            raise SetSourceDirError(PathNotADirectoryError(f"Path {source_dir_path} is not a directory."))

        resolved_source_dir_path = source_dir_path.resolve()

        # Check if lang is already in project (as src or tgt)
        if self._get_source_language() == lang:
            raise SetSourceDirError(LangAlreadyInProjectError(f"Language {lang} is already the source language."))
        if lang in self._get_target_languages():
            raise SetSourceDirError(LangAlreadyInProjectError(f"Language {lang} is already a target language."))

        try:
            self.config.set_src_dir_config(resolved_source_dir_path, lang)
            self.save_config()
        except IOError as e: # build_directory_tree or save_config can raise IOError
            raise SetSourceDirError(AnalyzeDirError(f"Error analyzing or saving config for source directory: {e}", e))
        except Exception as e: # Other errors from build_tree or Pydantic
             raise SetSourceDirError(AnalyzeDirError(f"Unexpected error setting source directory: {e}", e))


    def add_target_language(self, lang: Language | CustomLanguage, tgt_dir: Path | None = None) -> Path:
        """
        Adds a target language to the project.

        If a directory path is provided, it will be used as the target language's directory.
        If no directory is provided, a new one will be created automatically, and its full path will be returned.
        """
        src_lang = self._get_source_language()
        if not src_lang:
            raise AddLanguageError(NoSourceLanguageError("Cannot add target language: No source language set."))

        if lang == src_lang:
            raise AddLanguageError(LangAlreadyInProjectError("Cannot add language: It's already the source language."))

        if tgt_dir is not None:
            if not tgt_dir.exists():
                raise AddLanguageError(InvalidPathError(f"The provided directory {tgt_dir} does not exist!"))
            if not os.path.isdir(tgt_dir):
                raise AddLanguageError(InvalidPathError(f"The provided path {tgt_dir} must be a path to a directory!"))

            resolved_lang_dir_path = tgt_dir.resolve()

            if not resolved_lang_dir_path.is_relative_to(self.root_path):
                raise AddLanguageError(InvalidPathError(f"{tgt_dir} must be inside the project root"))

            try:
                self.config.remove_lang_config(lang)
                self.config.add_lang_dir_config(resolved_lang_dir_path, lang)
                self.save_config()
                return resolved_lang_dir_path
            except IOError as e:
                # Clean up created directory if subsequent steps fail?
                # For now, let it be and raise error.
                raise AddLanguageError(f"Error on saving config for language {lang}: {e}", e)
            except Exception as e:
                 raise AddLanguageError(f"Unexpected error adding language {lang} and setting directory {tgt_dir}: {e}", e)
        else:
            if lang in self._get_target_languages():
                raise AddLanguageError(LangAlreadyInProjectError("Cannot add language: It's already a target language."))

            lang_dir_name = f"{self.config.name}{lang.get_dir_suffix()}"
            lang_dir_path = self.root_path / lang_dir_name
            
            if lang_dir_path.exists():
                raise AddLanguageError(LangDirExistsError(f"Directory {lang_dir_path} for language {lang} already exists."))

            try:
                lang_dir_path.mkdir(parents=True) # Create the directory
                resolved_lang_dir_path = lang_dir_path.resolve()
                self.config.add_lang_dir_config(resolved_lang_dir_path, lang)
                self.save_config()
                return resolved_lang_dir_path
            except IOError as e:
                # Clean up created directory if subsequent steps fail?
                # For now, let it be and raise error.
                raise AddLanguageError(f"IO error creating directory or saving config for language {lang}: {e}", e)
            except Exception as e:
                 raise AddLanguageError(f"Unexpected error adding language {lang}: {e}", e)

    def remove_target_language(self, lang: Language | CustomLanguage) -> None:
        """Removes a target language and its directory."""
        target_dir_path = self.config.get_target_dir_path_by_lang(lang)
        if not target_dir_path:
            raise RemoveLanguageError(TargetLanguageNotInProjectError(f"Language {lang} is not a configured target language."))

        resolved_target_dir_path = target_dir_path.resolve()
        if not resolved_target_dir_path.exists() or not resolved_target_dir_path.is_dir():
            print(f"Warning: Language directory {resolved_target_dir_path} for {lang} not found or not a dir, removing from config only.")
            # raise RemoveLanguageError(LangDirDoesNotExistError(f"Directory {resolved_target_dir_path} for language {lang} does not exist."))

        try:
            removed_from_config = self.config.remove_lang_config(lang)
            if not removed_from_config:
                 # Should have been caught by get_target_dir_path_by_lang
                 raise RemoveLanguageError(TargetLanguageNotInProjectError(f"Language {lang} could not be removed from config (wasn't found)."))
            
            self.save_config()
            
            if resolved_target_dir_path.exists() and resolved_target_dir_path.is_dir():
                 shutil.rmtree(resolved_target_dir_path)
        except IOError as e:
            raise RemoveLanguageError(f"IO error removing directory or saving config for language {lang}: {e}", e)
        except ConfigWriteError as e:
            raise RemoveLanguageError(f"Failed to save config after removing language {lang}: {e}", e)


    def sync_untranslatable_files(self) -> None: # TODO: 
        """Copies untranslatable files from source to all target directories."""
        if not self.config.src_dir:
            raise SyncFilesError(NoSourceLanguageError("Cannot sync: No source directory configured."))
        if not self.config.lang_dirs:
            raise SyncFilesError(NoTargetLanguagesError("Cannot sync: No target languages configured."))

        # This path is already absolute from when it was set.
        source_root_disk_path = self.config.src_dir.get_path() 

        for target_lang_dir in self.config.lang_dirs:
            target_root_disk_path = target_lang_dir.get_path()
            print(f"Syncing untranslatable files from {source_root_disk_path.name} to {target_root_disk_path.name}...")
            try:
                copy_untranslatable_files_recursive(
                    from_dir_root_path=source_root_disk_path,
                    to_dir_root_path=target_root_disk_path,
                    translatable_files=self.get_translatable_files()
                )
            except CopyFileDirError as e:
                raise SyncFilesError(f"Error copying files to {target_root_disk_path.name}: {e}", e)
            except Exception as e: # Other unexpected errors
                raise SyncFilesError(f"Unexpected error syncing to {target_root_disk_path.name}: {e}", e)

    def set_file_translatability(self, file_path_str: str, translatable: bool) -> None:
        """Marks a file in the source directory as translatable or untranslatable."""
        try:
            # Ensure file_path is absolute and exists before passing to config
            file_path = Path(file_path_str).resolve(strict=True)
        except FileNotFoundError:
            raise AddTranslatableFileError(FileDoesNotExistError(f"File {file_path_str} not found."))
        
        if not self.config.src_dir:
             raise AddTranslatableFileError(NoSourceLanguageError("Cannot modify file: No source directory set."))

        # The logic to find and modify the file model is in ProjectConfig
        try:
            self.config.make_file_translatable(file_path, translatable)
            self.save_config()
        except AddTranslatableFileError as e: # Catches NoSourceLang, NoFile from Pydantic model
            raise e
        except ConfigWriteError as e:
            raise AddTranslatableFileError(f"Error saving config after changing file translatability: {e}", e)


    def get_translatable_files(self) -> List[Path]:
        """Returns a list of translatable files in the source directory."""
        if not self.config.src_dir:
            raise GetTranslatableFilesError(NoSourceLanguageError("No source language set, cannot get translatable files."))
        return self.config.get_translatable_files()

    def set_llm_service_and_model(self, service: str, model: str) -> None:
        """Sets the service and the model that will be used for translation."""
        try:
            self.config.set_llm_service_with_model(service, model)
            self.save_config()
        except Exception as e:
            raise SetLLMServiceError(f"Error while setting llm service: {e}")

    def set_llm_reasoning_service_and_model(self, service: str, model: str) -> None:
        """Sets the service and the model that will be used for reasoning translation."""
        try:
            self.config.set_llm_reasoning_service_with_model(service, model)
            self.save_config()
        except Exception as e:
            raise SetLLMServiceError(f"Error while setting reasoning llm service: {e}")

    def add_custom_language(self, name: str, suffix: str) -> None:
        """Registers a new custom language in the project config."""
        try:
            self.config.add_custom_language(name, suffix)
            self.save_config()
        except ValueError as e:
            raise AddCustomLanguageError(str(e))

    def remove_custom_language(self, name: str) -> None:
        """Removes a custom language from the project config."""
        normalized = name.strip()
        try:
            Language.from_str(normalized)
            raise RemoveCustomLanguageError(f"'{normalized}' is a predefined language and cannot be removed.")
        except ValueError as e:
            if "predefined" in str(e):
                raise RemoveCustomLanguageError(str(e))
        if normalized not in self.config.custom_languages:
            raise RemoveCustomLanguageError(f"Custom language '{normalized}' is not in the config.")
        if (
            self.config.src_dir is not None
            and self.config.src_dir.language.lower() == normalized.lower()
        ):
            raise RemoveCustomLanguageError(
                f"Cannot remove '{normalized}': it is configured as the source directory language. "
                "Change or unset the source directory first."
            )
        target_dir = self.config.get_target_dir_path_by_lang(normalized)
        if target_dir is not None:
            raise RemoveCustomLanguageError(
                f"Cannot remove '{normalized}': it has an associated target directory '{target_dir}'. "
                "Remove the target language first with 'remove-target'."
            )
        try:
            self.config.remove_custom_language(normalized)
            self.save_config()
        except ValueError as e:
            raise RemoveCustomLanguageError(str(e))

    def set_typst_translatable_string_args_for_function(
        self,
        function_name: str,
        arg_names: list[str],
    ) -> None:
        """Sets translatable Typst string arguments for a function."""
        try:
            self.config.set_typst_translatable_string_args_for_function(function_name, arg_names)
            self.save_config()
        except Exception as e:
            raise SetLLMServiceError(
                f"Error while setting Typst translatable string arguments for function '{function_name}': {e}"
            )

    def remove_typst_translatable_string_args_for_function(self, function_name: str) -> None:
        """Removes Typst string argument translation settings for a function."""
        try:
            self.config.remove_typst_translatable_string_args_for_function(function_name)
            self.save_config()
        except Exception as e:
            raise SetLLMServiceError(
                f"Error while removing Typst translatable string arguments for function '{function_name}': {e}"
            )

    def get_typst_translatable_string_args_by_function(self) -> dict[str, list[str]]:
        return self.config.get_typst_translatable_string_args_by_function()

    def _find_correspondent_translatable_file(self, target_path: Path) -> Path | None:
        """
        Returns a correspondent source language translatable file for the given translated one or None
        """
        trans_files = self.get_translatable_files()
        file_name = target_path.name
        for file in trans_files:
            if file.name == file_name:
                return file
        return None

    def correct_translation_for_lang(self, target_lang: Language | CustomLanguage) -> None:
        """
        Corrects translation (updates the translation cache) for the given language
        """
        from . import project_runtime as _project_runtime

        _project_runtime.correct_translation_for_lang(self, target_lang)

    def correct_translation_single_file(self, file_path_str: str) -> None:
        """
        Corrects translation (updates the translation cache) for a given file
        """
        from . import project_runtime as _project_runtime

        _project_runtime.correct_translation_single_file(self, file_path_str)

    def sync_translation_cache(self, target_lang: Language | CustomLanguage | None = None) -> None:
        """Synchronizes the translation cache by scanning on-disk source/target files."""
        from . import project_runtime as _project_runtime

        _project_runtime.sync_translation_cache(self, target_lang)

    def clear_translation_cache_missing_chunks(self):
        """Clears cache entries that reference missing chunks."""
        from . import project_runtime as _project_runtime

        return _project_runtime.clear_translation_cache_missing_chunks(self)

    def clear_translation_cache_all(
        self,
        lang: Language | CustomLanguage | None,
        file_path_str: str | None,
        keyword: str | None,
    ):
        """Clears translation cache for the selected language and/or file."""
        from . import project_runtime as _project_runtime

        return _project_runtime.clear_translation_cache_all(self, lang, file_path_str, keyword)

    def get_translation_status(self, include_files: bool = False):
        """Returns translation status statistics across all target languages."""
        from . import project_runtime as _project_runtime

        return _project_runtime.get_translation_status(self, include_files)

    def get_llm_service(self) -> str:
        return self.config.get_llm_service()

    def get_llm_model(self) -> str:
        return self.config.get_llm_model()

    def get_llm_reasoning_service(self) -> Optional[str]:
        return self.config.get_llm_reasoning_service()

    def get_llm_reasoning_model(self) -> Optional[str]:
        return self.config.get_llm_reasoning_model()

    async def translate_single_file(self, file_path_str: str, target_lang: Language | CustomLanguage, vocab_list: VocabList | None, use_reasoning_model: bool = False) -> None:
        """Translates a single specified file to the target language."""
        from . import project_runtime as _project_runtime

        await _project_runtime.translate_single_file(self, file_path_str, target_lang, vocab_list, use_reasoning_model=use_reasoning_model)


    async def translate_all_for_language(self, target_lang: Language | CustomLanguage, vocab_list: VocabList | None, use_reasoning_model: bool = False) -> None:
        """Translates all translatable files to the specified target language."""
        from . import project_runtime as _project_runtime

        await _project_runtime.translate_all_for_language(self, target_lang, vocab_list, use_reasoning_model=use_reasoning_model)

# TODO: remove this, as it is diff, it must be implemented in the translation, after XML tagging
# DEBUG!
    def diff(self, txt: str, lang: Language | CustomLanguage) -> tuple[str, float]:
        from . import project_runtime as _project_runtime

        return _project_runtime.diff(self, txt, lang)


# --- Module-level functions for project init and load ---
_CUSTOM_SERVICE_TEMPLATE = '''\
from unified_model_caller import BaseService


class CustomService(BaseService):
    def get_name(self) -> str:
        # The name used in `translate-dir set-llm` and `translate-dir set-reasoning-model`.
        return "my-service"

    def requires_token(self) -> bool:
        # Return True if the service needs an API key (read from the environment by the caller).
        return True

    def service_cooldown(self) -> int:
        # Milliseconds to wait between calls to respect rate limits. Use 0 for no delay.
        return 0

    def call(self, model: str, prompt: str) -> str:
        # Call the remote API and return the plain-text response.
        raise NotImplementedError
'''


def _write_custom_services_template(config_dir_path: Path) -> None:
    services_dir = config_dir_path / CUSTOM_SERVICES_DIR_NAME
    services_dir.mkdir(exist_ok=True)
    template_path = services_dir / CUSTOM_SERVICES_TEMPLATE_FILENAME
    template_path.write_text(_CUSTOM_SERVICE_TEMPLATE, encoding="utf-8")


def load_custom_services(config_dir_path: Path) -> None:
    """Loads all .py files from the services subdirectory of the project config dir."""
    services_dir = config_dir_path / CUSTOM_SERVICES_DIR_NAME
    if not services_dir.is_dir():
        return
    for service_file in sorted(services_dir.glob("*.py")):
        if service_file.name == CUSTOM_SERVICES_TEMPLATE_FILENAME:
            continue
        try:
            LLMCaller.add_service(str(service_file))
            logger.debug(f"Loaded custom service from {service_file}")
        except Exception as e:
            logger.warning(f"Failed to load custom service '{service_file.name}': {e}")


def init_project(project_name: str, root_dir_str: str) -> Project:
    """Initializes a new project configuration in the specified directory."""
    root_path = Path(root_dir_str)
    if not root_path.is_dir(): # Also checks existence
        raise InitProjectError(InvalidPathError(f"Invalid path: {root_dir_str} is not an existing directory."))
    
    abs_root_path = root_path.resolve()
    config_file = abs_root_path / CONF_DIR / CONFIG_FILENAME
    
    if config_file.exists():
        raise InitProjectError(ProjectAlreadyInitializedError(f"Project already initialized at {abs_root_path} ({CONFIG_FILENAME} exists)."))

    try:
        # Create a Project instance with an empty config, then save it.
        project = Project._create_new_for_init(project_name, abs_root_path)
        project.save_config() # This writes the initial trans_conf.json
        _write_custom_services_template(project.config_dir_path)
        print(f"{CONF_DIR} directory has been successfully created!")
        return project
    except ConfigWriteError as e:
        raise InitProjectError(f"Failed to write initial config file: {e}", e)
    except Exception as e:
        raise InitProjectError(f"An unexpected error occurred during project initialization: {e}", e)


def load_project(path_str: str) -> Project:
    """Loads an existing project from the given path (can be project root or any child path)."""
    start_path = Path(path_str).resolve()
    
    config_dir_path = find_dir_upwards(start_path, CONF_DIR)
    if not config_dir_path:
        raise NoConfigFoundError(f"No '{CONF_DIR}' found in or above {start_path}.")

    project_root = config_dir_path.parent

    config_file_path = config_dir_path / CONFIG_FILENAME
    
    try:
        config_model = load_project_config(config_file_path)
        project = Project(project_root, config_model)
        if project.paths_normalized_on_load:
            project.save_config()
        load_custom_services(config_dir_path)
        logger.debug(f"Project '{project.config.name}' loaded from {project_root}")
        return project
    except ConfigLoadError as e:
        raise LoadProjectError(f"Failed to load project configuration: {e}", e)
    except Exception as e:
        raise LoadProjectError(f"An unexpected error occurred during project loading: {e}", e)
