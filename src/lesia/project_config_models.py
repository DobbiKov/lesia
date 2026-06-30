from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING

from pydantic import BaseModel, Field, ConfigDict

from .enums import Language, CustomLanguage

from .errors import AddTranslatableFileError, NoSourceLanguageError, FileDoesNotExistError

if TYPE_CHECKING:
    from typing import Callable


class FileModel(BaseModel):
    """A config for a file."""
    name: str
    path: Path
    translatable: bool = False

    class Config:
        arbitrary_types_allowed = True 

    def get_name(self) -> str:
        return self.name

    def get_path(self) -> Path:
        return self.path

    def is_translatable(self) -> bool:
        return self.translatable

class DirectoryModel(BaseModel):
    """A config representation of a directory."""
    name: str
    path: Path
    dirs: List[DirectoryModel] = Field(default_factory=list)
    files: List[FileModel] = Field(default_factory=list)

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def new_from_path(cls, path: Path) -> DirectoryModel:
        name = path.name
        return cls(name=name, path=path, dirs=[], files=[])

    def get_dir_name(self) -> str:
        return self.name

    def get_path(self) -> Path:
        return self.path

    def get_files(self) -> List[FileModel]: # Returns a copy
        return list(self.files)

    def get_dirs(self) -> List[DirectoryModel]: # Returns a copy
        return list(self.dirs)


def _lang_to_str(lang: Language | CustomLanguage) -> str:
    """Extracts the display name string from a Language enum or CustomLanguage."""
    if isinstance(lang, CustomLanguage):
        return lang.get_lang()
    return str(lang)


class LangDir(BaseModel):
    """A master directory for a language."""
    language: str  # language display name, e.g. "French" or a custom "Catalan"
    path: Path
    root_path: Path | None = Field(default=None, exclude=True)

    def get_lang(self) -> str:
        return self.language

    def attach_root_path(self, root_path: Path) -> None:
        """Stores the project root used to resolve the relative path."""
        self.root_path = root_path.resolve()

    def get_path(self) -> Path:
        if self.path.is_absolute() or not self.root_path:
            return self.path
        return (self.root_path / self.path).resolve()


class ProjectConfig(BaseModel):
    """A struct representing a particular project's config."""
    model_config = ConfigDict(extra="ignore")

    name: str
    lang_dirs: List[LangDir] = Field(default_factory=list)
    src_dir: Optional[LangDir] = None
    translatable_files: List[Path] = Field(default_factory=list)
    runtime_root_path: Path | None = Field(default=None, exclude=True)

    custom_languages: dict[str, str] = Field(default_factory=dict)
    custom_language_shorts: dict[str, str] = Field(default_factory=dict)  # short → full name

    llm_service: str = "google"
    llm_model: str = "gemini-2.0-flash"
    llm_reasoning_service: Optional[str] = None
    llm_reasoning_model: Optional[str] = None
    typst_translatable_string_args_by_function: dict[str, list[str]] = Field(
        default_factory=lambda: {"ex": ["info"]}
    )

    latex_extra_placeholder_envs: list[str] = Field(default_factory=list)
    latex_extra_math_envs: list[str] = Field(default_factory=list)
    latex_extra_placeholder_commands: list[str] = Field(default_factory=list)
    # command name → {"mandatory": [1, 2, ...], "optional": [1, ...]}  (1-based)
    latex_command_translatable_args: dict[str, dict[str, list[int]]] = Field(default_factory=dict)
    # command name → {"mandatory": N, "optional": M}  — arg counts for pylatexenc spec registration
    latex_custom_command_specs: dict[str, dict[str, int]] = Field(default_factory=dict)

    @classmethod
    def new(cls, project_name: str) -> ProjectConfig:
        return cls(
            name=project_name,
            lang_dirs=[],
            src_dir=None,
        )

    def get_name(self) -> str:
        return self.name

    def get_src_dir(self) -> Optional[LangDir]:
        return self.src_dir

    def get_lang_dirs(self) -> List[LangDir]: # Returns a copy
        return list(self.lang_dirs)

    def get_src_dir_path(self) -> Optional[Path]:
        if self.src_dir:
            self._attach_root_if_missing(self.src_dir)
            return self.src_dir.get_path()
        return None

    def get_llm_service(self) -> str:
        return self.llm_service

    def get_llm_model(self) -> str:
        return self.llm_model

    def get_llm_reasoning_service(self) -> Optional[str]:
        return self.llm_reasoning_service

    def get_llm_reasoning_model(self) -> Optional[str]:
        return self.llm_reasoning_model

    def get_typst_translatable_string_args_by_function(self) -> dict[str, list[str]]:
        return {
            function_name: list(arg_names)
            for function_name, arg_names in self.typst_translatable_string_args_by_function.items()
        }

    def get_target_dir_path_by_lang(self, lang: Language | CustomLanguage) -> Optional[Path]:
        lang_str = _lang_to_str(lang)
        for lang_dir_obj in self.lang_dirs:
            if lang_dir_obj.get_lang().lower() == lang_str.lower():
                self._attach_root_if_missing(lang_dir_obj)
                return lang_dir_obj.get_path()
        return None

    def set_src_dir_config(self, dir_path: Path, lang: Language | CustomLanguage) -> None:
        """
        Sets the source directory in the config.
        """
        rel_path = self._relativize_to_runtime_root(dir_path)
        self._ensure_not_target_dir(rel_path)
        lang_dir = LangDir(language=_lang_to_str(lang), path=rel_path)
        lang_dir.attach_root_path(self._get_runtime_root())
        self.src_dir = lang_dir

    def add_lang_dir_config(self, dir_path: Path, lang: Language | CustomLanguage) -> None:
        """
        Adds a target language directory to the config.
        """
        rel_path = self._relativize_to_runtime_root(dir_path)
        self._ensure_not_source_dir(rel_path)
        lang_dir = LangDir(language=_lang_to_str(lang), path=rel_path)
        lang_dir.attach_root_path(self._get_runtime_root())
        self.lang_dirs.append(lang_dir)

    def remove_lang_config(self, lang: Language | CustomLanguage) -> bool:
        """Removes a language directory from the config. Returns True if removed."""
        lang_str = _lang_to_str(lang).lower()
        original_len = len(self.lang_dirs)
        self.lang_dirs = [ld for ld in self.lang_dirs if ld.get_lang().lower() != lang_str]
        return len(self.lang_dirs) < original_len

    def add_custom_language(self, name: str, suffix: str, short: Optional[str] = None) -> None:
        """Registers a custom language in the config."""
        normalized_name = name.strip()
        normalized_suffix = suffix.strip()
        if not normalized_name:
            raise ValueError("Language name cannot be empty.")
        if not normalized_suffix:
            raise ValueError("Language suffix cannot be empty.")
        try:
            Language.from_str(normalized_name)
            raise ValueError(f"'{normalized_name}' is already a predefined language.")
        except ValueError as e:
            if "already a predefined" in str(e):
                raise
        if normalized_name in self.custom_languages:
            raise ValueError(f"Custom language '{normalized_name}' already exists.")
        normalized_short = short.strip() if short else None
        if normalized_short:
            if normalized_short in self.custom_language_shorts:
                existing = self.custom_language_shorts[normalized_short]
                raise ValueError(f"Short name '{normalized_short}' is already used by '{existing}'.")
            try:
                Language.from_str(normalized_short)
                raise ValueError(f"Short name '{normalized_short}' conflicts with a predefined language.")
            except ValueError as e:
                if "conflicts with a predefined" in str(e):
                    raise
            for existing_name in self.custom_languages:
                if existing_name.lower() == normalized_short.lower():
                    raise ValueError(f"Short name '{normalized_short}' conflicts with existing custom language '{existing_name}'.")
        self.custom_languages[normalized_name] = normalized_suffix
        if normalized_short:
            self.custom_language_shorts[normalized_short] = normalized_name

    def _resolve_custom_name(self, name: str) -> str:
        """Returns the canonical full name for a custom language, resolving short aliases."""
        stripped = name.strip()
        if stripped in self.custom_languages:
            return stripped
        for short, full_name in self.custom_language_shorts.items():
            if short.lower() == stripped.lower():
                return full_name
        return stripped  # Return as-is; caller handles the missing-language error

    def remove_custom_language(self, name: str) -> None:
        """Removes a custom language from the registry, with safety checks."""
        normalized = self._resolve_custom_name(name)

        try:
            Language.from_str(normalized)
            raise ValueError(f"'{normalized}' is a predefined language and cannot be removed.")
        except ValueError as e:
            if "predefined" in str(e):
                raise

        if normalized not in self.custom_languages:
            raise ValueError(f"Custom language '{name.strip()}' not found: it is not in the config.")

        if self.src_dir is not None and self.src_dir.language.lower() == normalized.lower():
            raise ValueError(
                f"Cannot remove '{normalized}': it is configured as the source directory language. "
                "Change or unset the source directory first."
            )

        for ld in self.lang_dirs:
            if ld.language.lower() == normalized.lower():
                raise ValueError(
                    f"Cannot remove '{normalized}': it has an associated target directory '{ld.get_path()}'. "
                    "Remove the target language first with 'remove-target'."
                )

        del self.custom_languages[normalized]
        # Remove any short name that points to this language
        shorts_to_remove = [s for s, full in self.custom_language_shorts.items() if full == normalized]
        for s in shorts_to_remove:
            del self.custom_language_shorts[s]

    def resolve_language(self, name: str) -> CustomLanguage:
        """Resolves a language name (or short name) to a CustomLanguage."""
        try:
            predefined = Language.from_str(name)
            return CustomLanguage.from_language(predefined)
        except ValueError:
            pass
        if name in self.custom_languages:
            return CustomLanguage(name, self.custom_languages[name])
        # Check short names (case-insensitive)
        for short, full_name in self.custom_language_shorts.items():
            if short.lower() == name.lower():
                return CustomLanguage(full_name, self.custom_languages[full_name])
        raise ValueError(f"Unknown language: '{name}'. Add it via add_custom_language() first.")
            
    def _find_file_and_apply(self, dir_model: DirectoryModel, path: Path, func: Callable[[FileModel], None]) -> bool:
        """
        Helper to find a file and apply a function.
        Note: This modifies the FileModel in-place.
        """
        for file_obj in dir_model.files:
            # Compare resolved paths for robustness
            if os.path.samefile(file_obj.path.resolve(), path.resolve()):
                func(file_obj)
                return True
        
        for sub_dir_model in dir_model.dirs:
            if not path.is_relative_to(sub_dir_model.path):
                continue
            if self._find_file_and_apply(sub_dir_model, path, func):
                return True
        return False

    def set_llm_service_with_model(self, service: str, model: str) -> None:
        """Set's LLM service and model"""
        # TODO: verify that service is availible but add custom services beforehand
        self.llm_service = service
        self.llm_model = model

    def set_llm_reasoning_service_with_model(self, service: str, model: str) -> None:
        """Sets the reasoning LLM service and model."""
        # TODO: verify that service is availible but add custom services beforehand
        self.llm_reasoning_service = service
        self.llm_reasoning_model = model

    def set_typst_translatable_string_args_for_function(
        self,
        function_name: str,
        arg_names: list[str],
    ) -> None:
        normalized_function = function_name.strip().lower()
        if not normalized_function:
            raise ValueError("Function name cannot be empty.")

        normalized_args = sorted(
            {
                arg_name.strip().lower()
                for arg_name in arg_names
                if arg_name and arg_name.strip()
            }
        )
        if not normalized_args:
            raise ValueError("At least one argument name is required.")

        self.typst_translatable_string_args_by_function[normalized_function] = normalized_args

    def remove_typst_translatable_string_args_for_function(self, function_name: str) -> None:
        normalized_function = function_name.strip().lower()
        if normalized_function in self.typst_translatable_string_args_by_function:
            del self.typst_translatable_string_args_by_function[normalized_function]

    # ------------------------------------------------------------------
    # LaTeX configuration
    # ------------------------------------------------------------------

    def add_latex_placeholder_env(self, env_name: str) -> None:
        name = env_name.strip()
        if not name:
            raise ValueError("Environment name cannot be empty.")
        if name not in self.latex_extra_placeholder_envs:
            self.latex_extra_placeholder_envs.append(name)

    def remove_latex_placeholder_env(self, env_name: str) -> None:
        name = env_name.strip()
        if name not in self.latex_extra_placeholder_envs:
            raise ValueError(f"Environment '{name}' is not in the placeholder list.")
        self.latex_extra_placeholder_envs.remove(name)

    def add_latex_math_env(self, env_name: str) -> None:
        name = env_name.strip()
        if not name:
            raise ValueError("Environment name cannot be empty.")
        if name not in self.latex_extra_math_envs:
            self.latex_extra_math_envs.append(name)

    def remove_latex_math_env(self, env_name: str) -> None:
        name = env_name.strip()
        if name not in self.latex_extra_math_envs:
            raise ValueError(f"Environment '{name}' is not in the math list.")
        self.latex_extra_math_envs.remove(name)

    def add_latex_placeholder_command(self, cmd_name: str) -> None:
        name = cmd_name.strip()
        if not name:
            raise ValueError("Command name cannot be empty.")
        if name not in self.latex_extra_placeholder_commands:
            self.latex_extra_placeholder_commands.append(name)

    def remove_latex_placeholder_command(self, cmd_name: str) -> None:
        name = cmd_name.strip()
        if name not in self.latex_extra_placeholder_commands:
            raise ValueError(f"Command '{name}' is not in the placeholder list.")
        self.latex_extra_placeholder_commands.remove(name)

    def set_latex_command_translatable_args(
        self,
        cmd_name: str,
        mandatory: list[int] | None = None,
        optional: list[int] | None = None,
    ) -> None:
        name = cmd_name.strip()
        if not name:
            raise ValueError("Command name cannot be empty.")
        entry: dict[str, list[int]] = {}
        if mandatory is not None:
            bad = [i for i in mandatory if not isinstance(i, int) or i < 1]
            if bad:
                raise ValueError(f"Mandatory arg indices must be integers >= 1, got: {bad}")
            entry["mandatory"] = sorted(set(mandatory))
        if optional is not None:
            bad = [i for i in optional if not isinstance(i, int) or i < 1]
            if bad:
                raise ValueError(f"Optional arg indices must be integers >= 1, got: {bad}")
            entry["optional"] = sorted(set(optional))
        if not entry:
            raise ValueError("At least one of 'mandatory' or 'optional' must be provided.")
        self.latex_command_translatable_args[name] = entry

    def remove_latex_command_translatable_args(self, cmd_name: str) -> None:
        name = cmd_name.strip()
        if name not in self.latex_command_translatable_args:
            raise ValueError(f"Command '{name}' has no translatable-args config.")
        del self.latex_command_translatable_args[name]

    def set_latex_custom_command_spec(
        self,
        cmd_name: str,
        mandatory: int,
        optional: int = 0,
    ) -> None:
        name = cmd_name.strip()
        if not name:
            raise ValueError("Command name cannot be empty.")
        if not isinstance(mandatory, int) or mandatory < 0:
            raise ValueError("mandatory must be a non-negative integer.")
        if not isinstance(optional, int) or optional < 0:
            raise ValueError("optional must be a non-negative integer.")
        if mandatory == 0 and optional == 0:
            raise ValueError("At least one of mandatory or optional must be > 0.")
        self.latex_custom_command_specs[name] = {"mandatory": mandatory, "optional": optional}

    def remove_latex_custom_command_spec(self, cmd_name: str) -> None:
        name = cmd_name.strip()
        if name not in self.latex_custom_command_specs:
            raise ValueError(f"Command '{name}' has no custom spec defined.")
        del self.latex_custom_command_specs[name]

    def get_latex_settings(self) -> dict:
        return {
            "extra_placeholder_envs": list(self.latex_extra_placeholder_envs),
            "extra_math_envs": list(self.latex_extra_math_envs),
            "extra_placeholder_commands": list(self.latex_extra_placeholder_commands),
            "command_translatable_args": {
                cmd: dict(spec)
                for cmd, spec in self.latex_command_translatable_args.items()
            },
            "custom_command_specs": {
                cmd: dict(spec)
                for cmd, spec in self.latex_custom_command_specs.items()
            },
        }

    def make_file_translatable(self, path: Path, translatable: bool) -> None:
        """Marks a file as translatable or untranslatable."""
        # Resolve path to ensure consistency
        resolved_path = path.resolve()

        src_dir = self.src_dir
        if src_dir is None:
            raise AddTranslatableFileError(NoSourceLanguageError())

        if not translatable:
            rel_path = self._relativize_to_runtime_root(resolved_path)
            if rel_path not in self.translatable_files:
                raise AddTranslatableFileError("This file is not marked as translatable!")
            self.translatable_files.remove(rel_path)
            return  # Exit early after removal - don't continue to add logic
        

        src_dir_path = src_dir.get_path().resolve()

        try:
            resolved_path.relative_to(src_dir_path)
        except ValueError:
            raise AddTranslatableFileError(f"The provided file {path} is not in the source directory!")
        if not resolved_path.exists() or not resolved_path.is_file():
            raise AddTranslatableFileError(FileDoesNotExistError("This file does not exist"))
        
        rel_path = self._relativize_to_runtime_root(resolved_path)
        if rel_path not in self.translatable_files:
            self.translatable_files.append(rel_path)

    def get_translatable_files(self) -> List[Path]:
        """Gets a list of all the translatable files in the source directory."""
        if not self.src_dir:
            return [] 
        root = self._get_runtime_root()
        resolved_files: List[Path] = []
        for stored_path in self.translatable_files:
            if stored_path.is_absolute():
                resolved_files.append(stored_path)
            else:
                resolved_files.append((root / stored_path).resolve())
        return resolved_files

    def set_runtime_root_path(self, root_path: Path) -> bool:
        """Sets the runtime root used to resolve stored relative paths."""
        resolved_root = root_path.resolve()
        self.runtime_root_path = resolved_root

        changed = False
        if self._normalize_lang_dir(self.src_dir, resolved_root):
            changed = True

        for lang_dir in self.lang_dirs:
            if self._normalize_lang_dir(lang_dir, resolved_root):
                changed = True

        normalized_files: List[Path] = []
        for path in self.translatable_files:
            normalized = self._ensure_relative_path(path, resolved_root)
            if normalized != path:
                changed = True
            normalized_files.append(normalized)
        self.translatable_files = normalized_files
        return changed

    def _normalize_lang_dir(self, lang_dir: Optional[LangDir], reference_root: Path) -> bool:
        if not lang_dir:
            return False
        normalized_path = self._ensure_relative_path(lang_dir.path, reference_root)
        changed = normalized_path != lang_dir.path
        lang_dir.path = normalized_path
        lang_dir.attach_root_path(self.runtime_root_path or reference_root)
        return changed

    def _get_runtime_root(self) -> Path:
        if self.runtime_root_path:
            return self.runtime_root_path
        raise ValueError("Project root path is not set, cannot resolve relative paths.")

    def _relativize_to_runtime_root(self, path: Path) -> Path:
        root = self._get_runtime_root()
        resolved_path = path.resolve()
        try:
            return resolved_path.relative_to(root)
        except ValueError:
            raise ValueError(f"Path {resolved_path} is not under the project root {root}")

    def _resolve_from_runtime_root(self, path: Path) -> Path:
        if path.is_absolute():
            return path.resolve()
        return (self._get_runtime_root() / path).resolve()

    def _ensure_not_source_dir(self, rel_path: Path) -> None:
        if not self.src_dir:
            return
        if self._resolve_from_runtime_root(rel_path) == self.src_dir.get_path().resolve():
            raise ValueError("Target directory cannot be the same as the source directory.")

    def _ensure_not_target_dir(self, rel_path: Path) -> None:
        resolved_path = self._resolve_from_runtime_root(rel_path)
        for lang_dir in self.lang_dirs:
            self._attach_root_if_missing(lang_dir)
            if resolved_path == lang_dir.get_path().resolve():
                raise ValueError("Source directory cannot be the same as a target directory.")

    def _ensure_relative_path(self, path: Path, reference_root: Path) -> Path:
        if not path.is_absolute():
            return path
        try:
            return path.relative_to(reference_root)
        except ValueError:
            from loguru import logger
            logger.warning(
                f"Path {path} is not within the project root {reference_root}. Keeping absolute path in config."
            )
            return path

    def _attach_root_if_missing(self, lang_dir: Optional[LangDir]) -> None:
        if lang_dir and not lang_dir.root_path:
            lang_dir.attach_root_path(self._get_runtime_root())
