from pathlib import Path

from trans_lib.enums import Language, CustomLanguage


def test_custom_language(tmp_path: Path) -> None:
    l = Language.from_str('Ukrainian')
    assert l == Language.UKRAINIAN
    assert l.get_dir_suffix() == "_ua"
    cl = CustomLanguage.from_language(l)
    assert cl.get_lang() == "Ukrainian"
    assert cl.get_dir_suffix() == "_ua"


