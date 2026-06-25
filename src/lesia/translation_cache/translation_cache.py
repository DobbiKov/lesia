from abc import ABC, abstractmethod
from pathlib import Path

from lesia.diff import get_best_match_in_dir, get_checksum_for_best_match_in_dir
from lesia.enums import Language
from lesia.translation_cache.cache_backend import (
    PATH_CHECKSUM_COLUMN,
    add_contents_to_cache,
    do_translation_correspond_to_source,
    ensure_cache_dir,
    ensure_lang_cache_dirs,
    get_lang_cache_path_dir,
    read_cached_contents_by_lang,
    read_correspondence_cache,
    register_path_hash,
    set_checksum_pair_in_correspondence_cache,
)


class TranslationCache(ABC):
    def __init__(self, root_path: Path, cache_path: Path) -> None:
        self.cache_path = cache_path
        self.root_path = root_path
    @abstractmethod
    def lookup(self, src_checksum: str, src_lang: Language, tgt_lang: Language, relative_path: str) -> str | None:
        pass

    @abstractmethod
    def persist_pair(
        self,
        src_checksum: str,
        tgt_checksum: str,
        src_lang: Language,
        tgt_lang: Language,
        src_text: str,
        tgt_text: str,
        relative_path: str,
    ) -> None:
        """Return the cached *target text* if the pair exists, else *None*."""
        pass

    @abstractmethod
    def get_contents_by_checksum(self, checksum: str, lang: Language, relative_path: str) -> str | None:
        pass

    @abstractmethod
    def get_best_pair_example_from_cache(
        self,
        lang: Language,
        tgt_lang: Language,
        txt: str,
        relative_path: str,
    ) -> tuple[str, str, float] | None:
        """
        Returns the triplet (src, tgt, score) of the best match between the provided text and the found source text in the cache.
        """
        pass

    @abstractmethod
    def get_best_match_from_cache(self, lang: Language, txt: str) -> tuple[str, float]:
        """
        Returns the best match and the score between the provided chunk and all the chunks of the provided language.
        """
        pass

    @abstractmethod
    def do_translation_correspond_to_source(self, src_checksum: str, src_lang: Language, tgt_contents: str, tgt_lang: Language, relative_path: str) -> bool:
        pass

class TranslationCacheCsv(TranslationCache):
    def __init__(self, root_path: Path) -> None:
        cache_path = ensure_cache_dir(root_path)
        super().__init__(root_path, cache_path)
        self._index: dict[tuple[str, str, str, str], str] = {}
        self._load_index()

    def _load_index(self) -> None:
        cache_data = read_correspondence_cache(self.root_path)
        if cache_data is None:
            return
        fields, data_list = cache_data
        lang_fields = [f for f in fields if f != PATH_CHECKSUM_COLUMN]
        for row in data_list:
            path_hash = row.get(PATH_CHECKSUM_COLUMN, "")
            for src_lang in lang_fields:
                src_checksum = row.get(src_lang, "")
                if not src_checksum:
                    continue
                for tgt_lang in lang_fields:
                    if src_lang == tgt_lang:
                        continue
                    tgt_checksum = row.get(tgt_lang, "")
                    if tgt_checksum:
                        self._index[(path_hash, src_lang, tgt_lang, src_checksum)] = tgt_checksum

    def lookup(self, src_checksum: str, src_lang: Language, tgt_lang: Language, relative_path: str) -> str | None:
        """Return the cached *target text* if the pair exists, else *None*."""
        path_hash = register_path_hash(self.root_path, relative_path)
        tgt_checksum = self._index.get((path_hash, str(src_lang), str(tgt_lang), src_checksum))
        if tgt_checksum is None:
            return None
        return read_cached_contents_by_lang(self.root_path, tgt_checksum, tgt_lang, path_hash)

    def persist_pair(
        self,
        src_checksum: str,
        tgt_checksum: str,
        src_lang: Language,
        tgt_lang: Language,
        src_text: str,
        tgt_text: str,
        relative_path: str,
    ) -> None:
        """
        Adds translation pair to the on-disk cache.
        """
        path_hash = register_path_hash(self.root_path, relative_path)
        src_checksum = add_contents_to_cache(self.root_path, src_text, src_lang, path_hash)
        tgt_checksum = add_contents_to_cache(self.root_path, tgt_text, tgt_lang, path_hash)
        set_checksum_pair_in_correspondence_cache(
            self.root_path,
            src_checksum,
            src_lang,
            tgt_checksum,
            tgt_lang,
            path_hash,
        )
        self._index[(path_hash, str(src_lang), str(tgt_lang), src_checksum)] = tgt_checksum
        self._index[(path_hash, str(tgt_lang), str(src_lang), tgt_checksum)] = src_checksum

    def get_best_pair_example_from_cache(self, lang: Language, tgt_lang: Language, txt: str, relative_path: str) -> tuple[str, str, float] | None:
        """
        Returns the triplet (src, tgt, score) of the best match between the provided text and the found source text in the cache.
        """
        path_hash = register_path_hash(self.root_path, relative_path)
        dir = get_lang_cache_path_dir(self.root_path, lang, path_hash)
        if not dir.exists():
            return None
        src_checksum, score = get_checksum_for_best_match_in_dir(dir, txt)
        if not src_checksum:
            return None
        src = self.get_contents_by_checksum(src_checksum, lang, relative_path)
        tgt = self.lookup(src_checksum, lang, tgt_lang, relative_path)
        if tgt is None or src is None:
            return None
        return src, tgt, score

    def get_best_match_from_cache(self, lang: Language, txt: str) -> tuple[str, float]:
        """
        Returns the best match and the score between the provided chunk and all the chunks of the provided language.
        """
        lang_dir = ensure_lang_cache_dirs(self.root_path, [lang])[0]
        best_txt, best_score = "", 0.0
        for path_dir in lang_dir.iterdir():
            if not path_dir.is_dir():
                continue
            candidate_txt, score = get_best_match_in_dir(path_dir, txt)
            if score > best_score:
                best_txt, best_score = candidate_txt, score
        return best_txt, best_score

    def do_translation_correspond_to_source(self, src_checksum: str, src_lang: Language, tgt_contents: str, tgt_lang: Language, relative_path: str) -> bool:
        path_hash = register_path_hash(self.root_path, relative_path)
        return do_translation_correspond_to_source(self.root_path, src_checksum, src_lang, tgt_contents, tgt_lang, path_hash)

    def get_contents_by_checksum(self, checksum: str, lang: Language, relative_path: str) -> str | None:
        path_hash = register_path_hash(self.root_path, relative_path)
        return read_cached_contents_by_lang(self.root_path, checksum, lang, path_hash)
