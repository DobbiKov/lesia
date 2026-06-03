import enum
from typing import List

class Language(str, enum.Enum):
    """Enumeration for supported languages."""
    FRENCH = "French"
    ENGLISH = "English"
    GERMAN = "German"
    SPANISH = "Spanish"
    UKRAINIAN = "Ukrainian"
    ARMENIAN = "Armenian"

    def get_dir_suffix(self) -> str:
        """Returns the directory suffix for the language."""
        if self == Language.FRENCH:
            return "_fr"
        elif self == Language.ENGLISH:
            return "_en"
        elif self == Language.GERMAN:
            return "_de"
        elif self == Language.SPANISH:
            return "_es" 
        elif self == Language.UKRAINIAN:
            return "_ua"
        elif self == Language.ARMENIAN:
            return "_hy"
        # Should not happen with enum
        raise ValueError(f"Unknown language: {self}")

    @classmethod
    def from_str(cls, s: str) -> 'Language':
        for lang_member in cls:
            if lang_member.value.lower() == s.lower():
                return lang_member
        raise ValueError(f"'{s}' is not a valid Language")

    def __str__(self) -> str:
        return self.value


CLI_LANGUAGE_CHOICES: List[str] = [lang.value for lang in Language]

class DocumentType(str, enum.Enum):
    """
    Enumeration for the document types
    """
    JupyterNotebook = "jupyter"
    Markdown = "markdown"
    LaTeX = "latex"
    Typst = "typst"
    Other = "other"

class ChunkType(str, enum.Enum):
    """
    Enumeration for the chunk types
    """
    Code = "code"
    Myst = "myst"
    LaTeX = "latex"
    Typst = "typst"
    Other = "other"

class CustomLanguage:
    def __init__(self, lang: str, suffix: str):
        self.lang = lang
        self.suffix = suffix

    @classmethod
    def from_language(cls, l: Language) -> 'CustomLanguage':
       return cls(l.__str__(), l.get_dir_suffix()) 

    def get_dir_suffix(self) -> str:
        return self.suffix
    def get_lang(self) -> str:
        return self.lang

    def __str__(self) -> str:
        return self.lang 

    def __eq__(self, other: object) -> bool:
        if isinstance(other, CustomLanguage):
            return self.lang.lower() == other.lang.lower()
        if isinstance(other, str):
            return self.lang.lower() == other.lower()
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.lang.lower())
