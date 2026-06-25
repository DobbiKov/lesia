import os
import csv
from pathlib import Path
from typing import Iterable

from lesia.enums import Language
from lesia.helpers import (
    calculate_checksum,
    calculate_path_checksum,
    ensure_dir_exists,
    get_config_dir_from_root,
    normalize_relative_path,
    read_string_from_file,
)
from lesia.constants import CACHE_DIR_NAME, CORRESPONDENCE_CACHE_FILENAME, PATH_MAP_FILENAME

PATH_CHECKSUM_COLUMN = "path_checksum"
PATH_MAP_COLUMNS = [PATH_CHECKSUM_COLUMN, "relative_path"]

def _ensure_path_field(fields: list[str]) -> list[str]:
    if PATH_CHECKSUM_COLUMN not in fields:
        fields.insert(0, PATH_CHECKSUM_COLUMN)
    return fields


def ensure_cache_dir(root_path: Path) -> Path:
    cache_full_dir_path = get_config_dir_from_root(root_path).joinpath(CACHE_DIR_NAME)
    ensure_dir_exists(cache_full_dir_path)
    return cache_full_dir_path

def ensure_lang_cache_dir(root_path: Path, lang: Language) -> Path:
    cache_full_dir_path = ensure_cache_dir(root_path)
    lang_full_path = cache_full_dir_path.joinpath(str(lang))
    ensure_dir_exists(lang_full_path)
    return lang_full_path

def ensure_lang_cache_dirs(root_path: Path, langs: Iterable[Language]) -> list[Path]:
    return [ensure_lang_cache_dir(root_path, lang) for lang in langs]

def ensure_lang_cache_path_dir(root_path: Path, lang: Language, path_hash: str) -> Path:
    lang_full_path = ensure_lang_cache_dir(root_path, lang)
    path_dir = lang_full_path.joinpath(path_hash)
    ensure_dir_exists(path_dir)
    return path_dir

def get_lang_cache_path_dir(root_path: Path, lang: Language, path_hash: str) -> Path:
    lang_full_path = ensure_lang_cache_dir(root_path, lang)
    return lang_full_path.joinpath(path_hash)

def get_path_map_path(root_path: Path) -> Path:
    return ensure_cache_dir(root_path).joinpath(PATH_MAP_FILENAME)

def ensure_path_map(root_path: Path) -> Path:
    path = get_path_map_path(root_path)
    ensure_cache_dir(root_path)
    if not os.path.exists(path):
        with open(path, "w", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=PATH_MAP_COLUMNS)
            writer.writeheader()
    return path

def register_path_hash(root_path: Path, relative_path: str | Path) -> str:
    normalized = normalize_relative_path(relative_path)
    path_hash = calculate_path_checksum(normalized)
    path_map = ensure_path_map(root_path)

    with open(path_map, "r", newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            if row.get(PATH_CHECKSUM_COLUMN) == path_hash:
                existing = row.get("relative_path", "")
                if existing and existing != normalized:
                    raise ValueError(
                        f"Path hash collision: {path_hash} already mapped to {existing}, got {normalized}",
                    )
                return path_hash

    with open(path_map, "a", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=PATH_MAP_COLUMNS)
        writer.writerow({PATH_CHECKSUM_COLUMN: path_hash, "relative_path": normalized})

    return path_hash

def add_contents_to_cache(root_path: Path, contents: str, lang: Language, path_hash: str) -> str:
    """
    Adds the given contents to the translation cache for the appropriate language/path and returns the contents checksum.
    """
    ensure_cache_dir(root_path)
    lang_dir_full_path = ensure_lang_cache_path_dir(root_path, lang, path_hash)
    checksum = calculate_checksum(contents)
    file_path = lang_dir_full_path.joinpath(checksum)
    if os.path.exists(file_path): # if the checksum file already exists, then no need to write it
        return checksum

    with open(file_path, "w") as f:
        f.write(contents)
    return checksum

def read_cached_contents_by_lang(root_path: Path, checksum: str, lang: Language, path_hash: str) -> str | None:
    """
    Looks for a file with the given checksum in the directory of the given language and returns its contents if it finds such file and None if it doesn't

    Note: better performance than a full cache scan via read_contents_from_cache_by_checksum.
    """
    lang_dir_full_path = get_lang_cache_path_dir(root_path, lang, path_hash)
    if not lang_dir_full_path.exists():
        return None
    return _read_contents_from_cache_by_checksum_in_dir(checksum, lang_dir_full_path)

def _read_contents_from_cache_by_checksum_in_dir(checksum: str, dir: Path) -> str | None:
    if not os.path.exists(dir) or not dir.is_dir():
        return None
    for file in dir.iterdir():
        if not file.is_file():
            continue
        file_name = file.name
        if file_name == checksum:
            return read_string_from_file(file.absolute())
    return None

def read_contents_from_cache_by_checksum(root_path: Path, checksum: str) -> str | None:
    """
    Iterates through all the files in all the lang directories and searches for the checksum and returns the contents if it finds such file and None if it doesn't
    """
    cache_dir_path = ensure_cache_dir(root_path)
    if not os.path.exists(cache_dir_path):
        return None

    for lang_dir in cache_dir_path.iterdir():
        if not lang_dir.is_dir():
            continue

        for path_dir in lang_dir.iterdir():
            if not path_dir.is_dir():
                continue

            res = _read_contents_from_cache_by_checksum_in_dir(checksum, path_dir.absolute())
            if res is not None:
                return res

    return None

# correspondence cache
def get_correspondence_cache_path(root_path: Path) -> Path:
    """
    Returns a full path to the correspondence cache file.
    """
    cache_dir_path = ensure_cache_dir(root_path)
    file_path = cache_dir_path.joinpath(CORRESPONDENCE_CACHE_FILENAME)
    return file_path

def ensure_correspondence_cache(root_path: Path) -> None:
    file_path = get_correspondence_cache_path(root_path)
    ensure_cache_dir(root_path)
    if os.path.exists(file_path):
        return
    with open(file_path, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=[PATH_CHECKSUM_COLUMN])
        writer.writeheader()

def add_lang_to_cache_data(fields: list[str], data_list: list[dict], lang: Language) -> tuple[list[str], list[dict]]:
    """
    Helper function to add a language column to cached correspondence rows.
    """
    fields = _ensure_path_field(fields)
    if str(lang) in fields:
        return (fields, data_list)

    fields.append(str(lang)) 

    for i in range(len(data_list)):
        data_list[i][str(lang)] = ""

    return (fields, data_list)

def remove_lang_from_cache_data(fields: list[str], data_list: list[dict], lang: Language) -> tuple[list[str], list[dict]]:
    """
    Helper function to drop a language column from cached correspondence rows.
    """
    fields = _ensure_path_field(fields)
    if str(lang) not in fields:
        return (fields, data_list)

    fields.remove(str(lang))
    for i in range(len(data_list)):
        data_list[i].pop(str(lang))

    return (fields, data_list)

def add_language_to_correspondence_cache(root_path: Path, lang: Language) -> None:
    cache_data = read_correspondence_cache(root_path)
    if cache_data is None: # if the cache doesn't exist, then we create it and add our lang as a field
        write_correspondence_cache(root_path, [], [str(lang)])
        return

    (fields, data_list) = cache_data

    (fields, data_list) = add_lang_to_cache_data(fields, data_list, lang)

    write_correspondence_cache(root_path, data_list, fields)


def remove_language_from_correspondence_cache(root_path: Path, lang: Language) -> None:
    cache_data = read_correspondence_cache(root_path)
    if cache_data is None: # if the cache doesn't exist, then do nothing
        ensure_correspondence_cache(root_path)
        return

    (fields, data_list) = cache_data

    (fields, data_list) = remove_lang_from_cache_data(fields, data_list, lang)

    write_correspondence_cache(root_path, data_list, fields)

def find_correspondent_checksum(
    root_path: Path,
    src_checksum: str,
    src_lang: Language,
    tgt_lang: Language,
    path_hash: str,
) -> str | None:
    """
    Looks for the correspondent checksum of a particular language to the given checksum (of the given language) returns the checksum if finds it, None otherwise

    Example:
        eng_checksum | fr_checksum
        aaa          | aca
        baa          | aba

    ```py
    find_correspondent_checksum(., "aaa", English, French) # returns "aca"
    find_correspondent_checksum(., "aba", French, English) # returns "baa"
    find_correspondent_checksum(., "ccc", French, English) # returns None
    ```
    """
    if src_lang == tgt_lang:
        return None
    cache_data = read_correspondence_cache(root_path)
    if cache_data is None: # if the db doesn't exist, then do nothing
        ensure_correspondence_cache(root_path)
        return None

    (fields, data_list) = cache_data
    fields = _ensure_path_field(fields)
    if str(src_lang) not in fields or str(tgt_lang) not in fields:
        return None

    for data in data_list:
        row_path_hash = data.get(PATH_CHECKSUM_COLUMN, "")
        if row_path_hash and row_path_hash != path_hash:
            continue
        if data[str(src_lang)] == src_checksum:
            tgt_checksum = data[str(tgt_lang)]
            if tgt_checksum == "": # if target checksum is an empty string, it means that for such source checksum and these languages there's no correspondence pair, return None
                return None 
            return tgt_checksum

    return None

def do_translation_checksum_correspond_to_source(
    root_path: Path,
    src_checksum: str,
    src_lang: Language,
    tgt_checksum: str,
    tgt_lang: Language,
    path_hash: str,
) -> bool:
    """
    Returns true if two given checksums of two different languages correspond (i.e the one is a translation of the other) and False otherwise
    """
    if tgt_lang == src_lang:
        return False
    true_tgt_checksum = find_correspondent_checksum(root_path, src_checksum, src_lang, tgt_lang, path_hash)
    if true_tgt_checksum is None:
        return False

    return true_tgt_checksum == tgt_checksum

def do_translation_correspond_to_source(
    root_path: Path,
    src_checksum: str,
    src_lang: Language,
    tgt_contents: str,
    tgt_lang: Language,
    path_hash: str,
) -> bool:
    """
    Returns true if the given translation corresponds to the given source checksum and false otherwise
    """
    tgt_checksum = calculate_checksum(tgt_contents)
    return do_translation_checksum_correspond_to_source(root_path, src_checksum, src_lang, tgt_checksum, tgt_lang, path_hash)

def set_checksum_pair_in_correspondence_cache(
    root_path: Path,
    src_checksum: str,
    src_lang: Language,
    tgt_checksum: str,
    tgt_lang: Language,
    path_hash: str,
) -> None:
    if src_lang == tgt_lang:
        return None

    cache_data = read_correspondence_cache(root_path)
    if cache_data is None: # if the db doesn't exist, then create it
        ensure_correspondence_cache(root_path)

    (fields, data_list) = ([], [])
    if cache_data is not None:
        (fields, data_list) = cache_data

    fields = _ensure_path_field(fields)

    if str(src_lang) not in fields:
        (fields, data_list) = add_lang_to_cache_data(fields, data_list, src_lang)
    if str(tgt_lang) not in fields:
        (fields, data_list) = add_lang_to_cache_data(fields, data_list, tgt_lang)

    for i in range(len(data_list)):
        row = data_list[i]
        row_path_hash = row.get(PATH_CHECKSUM_COLUMN, "")
        if row_path_hash and row_path_hash != path_hash:
            continue
        if row[str(src_lang)] == src_checksum:
            row[PATH_CHECKSUM_COLUMN] = path_hash
            data_list[i][str(tgt_lang)] = tgt_checksum
            write_correspondence_cache(root_path, data_list, fields)
            return

    # if the source checksum isn't present in the db, then we create a new row with the pair
    new_row = {}
    for field in fields:
        new_row[field] = ""
    new_row[PATH_CHECKSUM_COLUMN] = path_hash
    new_row[str(src_lang)] = src_checksum
    new_row[str(tgt_lang)] = tgt_checksum
    data_list.append(new_row)
    write_correspondence_cache(root_path, data_list, fields)


    

def read_correspondence_cache(root_path: Path) -> tuple[list[str], list[dict]] | None:
    """
    Returns (list of fields, data in dictionary format) or None if the cache file doesn't exist
    """

    file_path = get_correspondence_cache_path(root_path)

    if not os.path.exists(file_path):
        return None

    data_list = []
    field_names = []
    
    with open(file_path, mode='r', newline='') as file:
        csv_reader = csv.DictReader(file)
        raw_fields = list(csv_reader.fieldnames or [])
        field_names = _ensure_path_field(raw_fields)

        for row in csv_reader:
            row.setdefault(PATH_CHECKSUM_COLUMN, "")
            data_list.append(row)

    return (field_names, data_list)

def write_correspondence_cache(root_path: Path, data_list: list[dict], fields: list[str] = []) -> None:
    """
    Writes the correspondence cache to disk; if no data is provided we only write the headers.
    """
    ensure_cache_dir(root_path)
    file_path = get_correspondence_cache_path(root_path)
    fields = _ensure_path_field(list(fields))

    if len(data_list) == 0:
        with open(file_path, 'w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fields)
            writer.writeheader()
        return

    for row in data_list:
        row.setdefault(PATH_CHECKSUM_COLUMN, "")
        for field in fields:
            row.setdefault(field, "")

    with open(file_path, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fields)
        writer.writeheader()
        writer.writerows(data_list)
