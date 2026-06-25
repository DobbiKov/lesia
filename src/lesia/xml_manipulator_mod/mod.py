from lesia.enums import ChunkType
from lesia.xml_manipulator_mod.code import CodeParser
from lesia.xml_manipulator_mod.latex import parse_latex
from lesia.xml_manipulator_mod.myst import parse_myst
from lesia.xml_manipulator_mod.typst import typst_to_xml
from lesia.xml_manipulator_mod.xml import create_translation_xml

def chunk_to_xml_bis(source: str, chunk_type: ChunkType) -> tuple[str, dict, bool]:
    """
    Takes a chunk and the document type and returns the XML tagged version of the chunk
    """
    match chunk_type:
        case ChunkType.LaTeX:
            res = latex_to_xml(source)
            return res[0], res[1], res[2]
        case ChunkType.Myst:
            res = myst_to_xml(source)
            return res[0], res[1], res[2]
        case ChunkType.Typst:
            res = typst_to_xml(source)
            return res[0], res[1], res[2]
        case _:
            raise RuntimeError("Not implemented yet")

def chunk_to_xml(source: str, chunk_type: ChunkType) -> str:
    return chunk_to_xml_bis(source, chunk_type)[0]

def chunk_to_xml_with_placeholders(source: str, chunk_type: ChunkType) -> tuple[str, dict]:
    xml, placeholders, _ = chunk_to_xml_bis(source, chunk_type)
    return xml, placeholders

def chunk_contains_ph_only(source: str, chunk_type: ChunkType) -> bool:
    if chunk_type == ChunkType.Code: # temp while code not implemented yet
        return True
    return chunk_to_xml_bis(source, chunk_type)[2]

def latex_to_xml(source: str) -> tuple[str, dict, bool]:
    return create_translation_xml(parse_latex(source))

def code_to_xml(source: str, language: str) -> tuple[str, dict, bool]:
    """
    Main function that takes a code and the language it is written in and returns an XML for translating.
    """
    segments = []
    try:
        parser = CodeParser(language=language)
        segments = parser.parse(source)
    except Exception: # if a language is not supported
        segments = [
                ('placeholder', source)
                ]
    
    return create_translation_xml(segments)

def myst_to_xml(source: str) -> tuple[str, dict, bool]:
    segments = parse_myst(source)
    def handle_segment(segment: tuple[str, str]) -> tuple[str, str]:
        if segment[0] == "math":
            return ('placeholder', segment[1]) # temporary | TODO: handle math
        return segment
    segments = [handle_segment(segment) for segment in segments]
    return create_translation_xml(segments)


def typst_to_xml_mod(source: str) -> tuple[str, dict, bool]:
    return typst_to_xml(source)
