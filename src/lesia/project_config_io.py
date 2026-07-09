import json
import os
import tomllib
from pathlib import Path
import shutil

import tomli_w

from lesia.helpers import copy_tree_contents

from .project_config_models import DirectoryModel, FileModel, ProjectConfig
from .errors import LoadConfigError, WriteConfigError, CopyFileDirError, MigrateConfigError

def build_directory_tree(root_path: Path) -> DirectoryModel:
    """
    Builds a DirectoryModel tree rooted at `root_path`.
    Skips symlinks.
    """
    if not root_path.is_dir():
        # Or raise a more specific error
        raise ValueError(f"Path {root_path} is not a directory or does not exist.")

    dir_model = DirectoryModel.new_from_path(root_path)

    for entry in root_path.iterdir():
        try:
            if entry.is_symlink():
                continue

            if entry.is_dir():
                dir_model.dirs.append(build_directory_tree(entry))
            elif entry.is_file():
                file_model = FileModel(
                    name=entry.name,
                    path=entry.resolve(), 
                    translatable=False 
                )
                dir_model.files.append(file_model)
        except OSError: 
            # TODO: decide how to handle
            # print(f"Warning: Could not access {entry}, skipping.") 
            # continue
            raise
            
    return dir_model


def write_project_config(config_file_path: Path, config: ProjectConfig) -> None:
    """Writes the project configuration to a TOML file."""
    try:
        data = config.model_dump(mode="json", exclude_none=True)
        config_file_path.write_bytes(tomli_w.dumps(data).encode("utf-8"))
    except IOError as e:
        raise WriteConfigError(f"IO error writing config to {config_file_path}: {e}", original_exception=e)
    except Exception as e:
        raise WriteConfigError(f"Serialization error writing config: {e}", original_exception=e)


def load_project_config(config_file_path: Path) -> ProjectConfig:
    """Loads project configuration from a TOML file."""
    if not config_file_path.is_file():
        raise LoadConfigError(f"Config file not found: {config_file_path}")
    try:
        with config_file_path.open("rb") as f:
            data = tomllib.load(f)
        return ProjectConfig.model_validate(data)
    except FileNotFoundError:
        raise LoadConfigError(f"Config file not found: {config_file_path}")
    except tomllib.TOMLDecodeError as e:
        raise LoadConfigError(f"Incorrect config file format (TOML decode error): {config_file_path}", original_exception=e)
    except Exception as e:
        raise LoadConfigError(f"Incorrect config file format (validation error): {config_file_path} - {e}", original_exception=e)


def migrate_config_json_to_toml(json_config_path: Path, toml_config_path: Path) -> None:
    """Reads an existing config.json and rewrites it as config.toml, then removes the JSON file."""
    if not json_config_path.is_file():
        raise MigrateConfigError(f"No config.json found at: {json_config_path}")
    if toml_config_path.exists():
        raise MigrateConfigError(f"config.toml already exists at: {toml_config_path}")
    try:
        contents = json_config_path.read_text(encoding="utf-8")
        config = ProjectConfig.model_validate_json(contents)
    except json.JSONDecodeError as e:
        raise MigrateConfigError(f"Could not parse config.json: {e}", original_exception=e)
    except Exception as e:
        raise MigrateConfigError(f"Could not load config.json: {e}", original_exception=e)
    write_project_config(toml_config_path, config)
    json_config_path.unlink()

def copy_untranslatable_files_recursive(
    from_dir_root_path: Path, # Absolute path to the root of the source directory being copied (e.g. /path/to/project/src_en)
    to_dir_root_path: Path,   # Absolute path to the root of the target directory (e.g. /path/to/project/target_fr)
    translatable_files: list[Path] # The DirectoryModel of the from_dir (relative paths within this structure)
) -> None:
    """
    Recursively copies untranslatable files from a source structure to a target directory.
    - from_dir_root_path: The actual disk path of the source directory (e.g., project_root/src_dir_name).
    - to_dir_root_path: The actual disk path of the target directory (e.g., project_root/target_dir_name).
    - source_dir_structure: The DirectoryModel representing the 'from_dir_root_path'.
                            Paths within this model are absolute but need to be made relative
                            to from_dir_root_path to map to to_dir_root_path.
    """
    # Ensure target root exists
    to_dir_root_path.mkdir(parents=True, exist_ok=True)

    try:
        copy_tree_contents(from_dir_root_path, to_dir_root_path, ignore=translatable_files)
    except IOError as e:
        raise CopyFileDirError("Couldn't open all the files!", original_exception=e)

# WARNING: unused code
def remove_files_not_in_source_dir(
    from_dir_root_path: Path, # Absolute path to the root of the source directory being copied (e.g. /path/to/project/src_en) 
    to_dir_root_path: Path,   # Absolute path to the root of the target directory (e.g. /path/to/project/target_fr)
    source_dir_structure: DirectoryModel # The DirectoryModel of the from_dir (relative paths within this structure)
) -> None:
    """
    Verifies and removes all the files and directories in the target directory that are not in the source directory.
    - from_dir_root_path: The actual disk path of the source directory (e.g., project_root/src_dir_name).
    - to_dir_root_path: The actual disk path of the target directory (e.g., project_root/target_dir_name).
    - source_dir_structure: The DirectoryModel representing the 'from_dir_root_path'.
                            Paths within this model are absolute but need to be made relative
                            to from_dir_root_path to map to to_dir_root_path.
    """
    to_dir_root_path.mkdir(parents=True, exist_ok=True)

    # getting the files and the directories of the current directory of the source dir
    files = [file.get_name() for file in source_dir_structure.get_files()]
    dirs = [dir.get_dir_name() for dir in source_dir_structure.get_dirs()]

    # iterating over the files and dirs of the target directory
    for entry in to_dir_root_path.iterdir():
        try:
            entry_name = entry.name 
            if entry.is_dir() and entry_name not in dirs:
                if entry.is_symlink():
                    os.remove(entry)
                else:
                    shutil.rmtree(entry)
            elif entry.is_dir(): # so it is indeed in dirs list
                for sub_dir in source_dir_structure.get_dirs(): # now continue the process of removal in this sub directory
                    if sub_dir.get_dir_name() == entry_name:
                        remove_files_not_in_source_dir(from_dir_root_path.joinpath(entry), to_dir_root_path.joinpath(entry), sub_dir)
                        break
            elif entry.is_file() and entry_name not in files:
                os.remove(entry)
        except OSError: 
            # TODO: decide how to handle
            # print(f"Warning: Could not access {entry}, skipping.") 
            # continue
            raise
            
