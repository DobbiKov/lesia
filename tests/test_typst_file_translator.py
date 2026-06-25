from lesia.doc_translator_mod.typst_chunker import read_chunks_with_metadata_from_typst
from lesia.doc_translator_mod.typst_file_translator import compile_typst_cells


def test_compile_typst_cells_forces_metadata_to_start_on_new_line_between_chunks(tmp_path) -> None:
    cells = [
        {"metadata": {"src_checksum": "aaa"}, "source": "First chunk without trailing newline"},
        {"metadata": {"src_checksum": "bbb"}, "source": "Second chunk"},
    ]

    compiled = compile_typst_cells(cells)
    first_block = compiled.find("// --- CHUNK_METADATA_START ---")
    second_block = compiled.find("// --- CHUNK_METADATA_START ---", first_block + 1)

    assert first_block != -1
    assert second_block != -1
    assert compiled[second_block - 1] == "\n"
    assert "First chunk without trailing newline\n// --- CHUNK_METADATA_START ---" in compiled

    out = tmp_path / "target.typ"
    out.write_text(compiled, encoding="utf-8")
    recovered = read_chunks_with_metadata_from_typst(out)

    assert len(recovered) == 2
    assert recovered[0]["source"] == "First chunk without trailing newline"
    assert recovered[1]["source"] == "Second chunk"
