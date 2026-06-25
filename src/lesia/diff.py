from difflib import SequenceMatcher
import os
from pathlib import Path

from lesia.helpers import read_string_from_file

def diff_score(a: str, b: str) -> float:
    # ratio() in [0..1], based on length of longest common subsequence
    return SequenceMatcher(None, a, b).ratio()


def get_best_match_in_dir(dir: Path, txt: str) -> tuple[str, float]:
    """
    Returns the best match between the provided chunk and all the chunks in the given directory.
    """
    _, _, files = list(os.walk(dir))[0]
    best_txt, best_score = "", 0.

    for file in files:
        contents = read_string_from_file(dir / file)
        score = diff_score(contents, txt)
        if score > best_score:
            best_txt, best_score = contents, score
    return best_txt, best_score

def get_checksum_for_best_match_in_dir(dir: Path, txt: str) -> tuple[str, float]:
    """
    Returns the best match between the provided chunk and all the chunks in the given directory.

    Returns:
        checksum, score
    """
    _, _, files = list(os.walk(dir))[0]
    checksum, best_score = "", 0.

    for file in files:
        contents = read_string_from_file(dir / file)
        score = diff_score(contents, txt)
        if score > best_score:
            checksum, best_score = file, score
    return checksum, best_score
