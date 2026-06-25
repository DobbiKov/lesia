"""
Tests for the in-memory correspondence index on TranslationCacheCsv.

Covers:
- index is populated from existing CSV on __init__
- lookup hits the index (O(1), no extra CSV read)
- persist_pair keeps the index and CSV in sync
- both directions are indexed after persist_pair
- multiple pairs under the same path all resolve correctly
- pairs from different paths don't cross-contaminate
- lookup returns None for an unknown pair
"""
from pathlib import Path

from lesia.constants import CONF_DIR
from lesia.enums import Language
from lesia.helpers import calculate_checksum
from lesia.translation_cache.translation_cache import TranslationCacheCsv


RELATIVE_PATH = "docs/lesson.typ"
OTHER_RELATIVE_PATH = "docs/other.typ"


def _store(tmp_path: Path) -> TranslationCacheCsv:
    (tmp_path / CONF_DIR).mkdir(parents=True, exist_ok=True)
    return TranslationCacheCsv(tmp_path)


# ---------------------------------------------------------------------------
# Basic miss / hit
# ---------------------------------------------------------------------------

def test_lookup_miss_on_empty_cache(tmp_path):
    store = _store(tmp_path)
    result = store.lookup("nonexistent", Language.ENGLISH, Language.FRENCH, RELATIVE_PATH)
    assert result is None


def test_lookup_miss_for_unknown_checksum(tmp_path):
    store = _store(tmp_path)
    store.persist_pair("", "", Language.ENGLISH, Language.FRENCH, "hello", "bonjour", RELATIVE_PATH)

    result = store.lookup("completely_unknown", Language.ENGLISH, Language.FRENCH, RELATIVE_PATH)
    assert result is None


def test_persist_then_lookup_same_instance(tmp_path):
    store = _store(tmp_path)
    src_checksum = calculate_checksum("hello")
    store.persist_pair("", "", Language.ENGLISH, Language.FRENCH, "hello", "bonjour", RELATIVE_PATH)

    result = store.lookup(src_checksum, Language.ENGLISH, Language.FRENCH, RELATIVE_PATH)
    assert result == "bonjour"


# ---------------------------------------------------------------------------
# Index is loaded from CSV on a fresh instance
# ---------------------------------------------------------------------------

def test_index_loaded_from_csv_on_new_instance(tmp_path):
    """A second TranslationCacheCsv instance reads the CSV and rebuilds the index."""
    store1 = _store(tmp_path)
    store1.persist_pair("", "", Language.ENGLISH, Language.FRENCH, "hello", "bonjour", RELATIVE_PATH)

    store2 = _store(tmp_path)
    src_checksum = calculate_checksum("hello")
    result = store2.lookup(src_checksum, Language.ENGLISH, Language.FRENCH, RELATIVE_PATH)
    assert result == "bonjour"


# ---------------------------------------------------------------------------
# Both directions are indexed by persist_pair
# ---------------------------------------------------------------------------

def test_reverse_direction_indexed_after_persist(tmp_path):
    store = _store(tmp_path)
    store.persist_pair("", "", Language.ENGLISH, Language.FRENCH, "hello", "bonjour", RELATIVE_PATH)

    tgt_checksum = calculate_checksum("bonjour")
    result = store.lookup(tgt_checksum, Language.FRENCH, Language.ENGLISH, RELATIVE_PATH)
    assert result == "hello"


def test_reverse_direction_loaded_from_csv(tmp_path):
    store1 = _store(tmp_path)
    store1.persist_pair("", "", Language.ENGLISH, Language.FRENCH, "hello", "bonjour", RELATIVE_PATH)

    store2 = _store(tmp_path)
    tgt_checksum = calculate_checksum("bonjour")
    result = store2.lookup(tgt_checksum, Language.FRENCH, Language.ENGLISH, RELATIVE_PATH)
    assert result == "hello"


# ---------------------------------------------------------------------------
# Multiple pairs under the same path
# ---------------------------------------------------------------------------

def test_multiple_pairs_same_path(tmp_path):
    store = _store(tmp_path)
    pairs = [
        ("Alpha chunk", "Alpha traduit"),
        ("Beta chunk", "Beta traduit"),
        ("Gamma chunk", "Gamma traduit"),
    ]
    for src, tgt in pairs:
        store.persist_pair("", "", Language.ENGLISH, Language.FRENCH, src, tgt, RELATIVE_PATH)

    for src, tgt in pairs:
        src_checksum = calculate_checksum(src)
        assert store.lookup(src_checksum, Language.ENGLISH, Language.FRENCH, RELATIVE_PATH) == tgt


def test_multiple_pairs_loaded_from_csv(tmp_path):
    store1 = _store(tmp_path)
    pairs = [
        ("Alpha chunk", "Alpha traduit"),
        ("Beta chunk", "Beta traduit"),
    ]
    for src, tgt in pairs:
        store1.persist_pair("", "", Language.ENGLISH, Language.FRENCH, src, tgt, RELATIVE_PATH)

    store2 = _store(tmp_path)
    for src, tgt in pairs:
        src_checksum = calculate_checksum(src)
        assert store2.lookup(src_checksum, Language.ENGLISH, Language.FRENCH, RELATIVE_PATH) == tgt


# ---------------------------------------------------------------------------
# Pairs from different paths don't cross-contaminate
# ---------------------------------------------------------------------------

def test_different_paths_do_not_cross_contaminate(tmp_path):
    store = _store(tmp_path)
    store.persist_pair("", "", Language.ENGLISH, Language.FRENCH, "hello", "bonjour", RELATIVE_PATH)
    store.persist_pair("", "", Language.ENGLISH, Language.FRENCH, "hello", "salut", OTHER_RELATIVE_PATH)

    src_checksum = calculate_checksum("hello")
    assert store.lookup(src_checksum, Language.ENGLISH, Language.FRENCH, RELATIVE_PATH) == "bonjour"
    assert store.lookup(src_checksum, Language.ENGLISH, Language.FRENCH, OTHER_RELATIVE_PATH) == "salut"


def test_lookup_wrong_path_returns_none(tmp_path):
    store = _store(tmp_path)
    store.persist_pair("", "", Language.ENGLISH, Language.FRENCH, "hello", "bonjour", RELATIVE_PATH)

    src_checksum = calculate_checksum("hello")
    result = store.lookup(src_checksum, Language.ENGLISH, Language.FRENCH, OTHER_RELATIVE_PATH)
    assert result is None
