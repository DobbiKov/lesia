from loguru import logger
from lesia.enums import Language, CustomLanguage


class VocabList:
    def __init__(self, source_lang_terms: list[str], target_lang_terms: list[str]):
        assert len(source_lang_terms) == len(target_lang_terms)
        self.source_lang_terms = source_lang_terms
        self.target_lang_terms = target_lang_terms

    def compile_into_llm_vocab_list(self) -> str:
        """
        Returns the vocabulary list in the form convenient for the LLM input.
        """
        res = ""

        for i in range(len(self.source_lang_terms)):
            src = self.source_lang_terms[i]
            tgt = self.target_lang_terms[i]
            line = f"{src}={tgt}\n"
            res += line

        return res

def vocab_list_from_vocab_db(db: list[dict], source_lang: Language | CustomLanguage, target_lang: Language | CustomLanguage) -> VocabList:
    """
    Takes vocabulary list of several languages, extract only needed ones and returns VocabList.
    The db is taken in the next format:
        [
                {lang1: str, lang2: str, lang3: str},
                {lang1: str_2, lang2: str_2, lang3: str_2},
                {lang1: str_3, lang2: str_3, lang3: str_3},
                {lang1: str_4, lang2: str_4, lang3: str_4}
        ]
    """
    if len(db) == 0:
        return VocabList([], [])
    if str(source_lang) not in list(db[0].keys()) or str(target_lang) not in list(db[0].keys()):
        logger.warning("No source or target language provided in the vocabulary list.")
        return VocabList([], [])
    source_terms = []
    target_terms = []
    for elem in db:
        logger.trace(f"{elem}")
        source_terms.append(elem[str(source_lang)])
        target_terms.append(elem[str(target_lang)])

    return VocabList(source_terms, target_terms)
