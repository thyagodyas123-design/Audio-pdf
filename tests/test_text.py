from audiopdf.chapters import split_chapters
from audiopdf.clean import clean_pages, merge_broken_paragraphs
from audiopdf.extract import Outline
from audiopdf.translate.argos import ArgosTranslator, _blocks


def test_merge_broken_paragraphs_joins_lowercase_continuation():
    assert merge_broken_paragraphs("Manutenção: se ele for verdadeiro antes\n\niteração.") == \
        "Manutenção: se ele for verdadeiro antes iteração."


def test_merge_keeps_real_paragraphs_and_headings():
    text = "Primeiro parágrafo.\n\nSegundo parágrafo.\n\nCapítulo Novo\n\nTexto."
    assert merge_broken_paragraphs(text) == text


def test_merge_joins_hyphen_break_across_blocks():
    assert merge_broken_paragraphs("a conver-\n\nsão final.") == "a conversão final."


def test_clean_pages_keeps_paragraph_breaks():
    pages = [f"CABEÇALHO\n\nPrimeira frase da página {i}.\n\nSegunda frase única {i * 7}.\n\n{i}" for i in range(1, 7)]
    out = clean_pages(pages)
    assert "CABEÇALHO" not in out[0]
    assert out[0].count("\n\n") == 1


def _outline():
    return [
        Outline(1, "Copyright", 0), Outline(1, "Prefácio", 1),
        Outline(1, "Parte I", 2), Outline(2, "1 | Um", 2), Outline(2, "2 | Dois", 4),
        Outline(1, "Parte II", 6), Outline(2, "3 | Três", 6),
        Outline(1, "Índice", 8),
    ]


def test_chapters_use_level2_under_parts_and_skip_matter():
    pages = [f"texto {i}" for i in range(9)]
    ch = split_chapters(pages, _outline())
    assert [c.title for c in ch] == ["Prefácio", "1 | Um", "2 | Dois", "3 | Três"]
    assert ch[0].text == "texto 1"
    assert ch[1].text == "texto 2 texto 3"  # quebra de página sem pontuação é reunida


def test_chapters_keep_matter_when_asked():
    pages = [f"texto {i}" for i in range(9)]
    titles = [c.title for c in split_chapters(pages, _outline(), skip_matter=False)]
    assert "Copyright" in titles and "Índice" in titles


def test_chapters_fallback_whole_book():
    ch = split_chapters(["a", "b"], [], title="Livro")
    assert len(ch) == 1 and ch[0].title == "Livro"


def test_translate_blocks_never_split_paragraphs():
    paras = ["a" * 700, "b" * 700, "c" * 700]
    blocks = _blocks("\n\n".join(paras), limit=1500)
    assert len(blocks) == 2 and all(p in "\n\n".join(blocks) for p in paras)


def test_translate_same_language_is_noop():
    assert ArgosTranslator().translate("olá", "pt", "pt") == "olá"
