from audiopdf.chunk import chunk_text
from audiopdf.clean import clean_pages, join_hyphenation, rebuild_paragraphs


def test_hyphenation():
    assert join_hyphenation("conver-\nsão") == "conversão"


def test_paragraphs():
    assert rebuild_paragraphs("a\nb\n\nc") == "a b\n\nc"


def test_header_footer_and_page_number_removed():
    pages = [f"MEU LIVRO\ntexto {i}\n{i}" for i in range(1, 8)]
    out = clean_pages(pages)
    assert all("MEU LIVRO" not in p for p in out)
    assert out[2] == "texto 3"


def test_chunk_never_splits_sentence():
    text = " ".join(f"Frase número {i}." for i in range(200))
    for c in chunk_text(text, 100):
        assert len(c) <= 100 and c.endswith(".")
