import pymupdf

from audiopdf.align import estimate_timeline, locate_paragraphs
from audiopdf.chunk import chunk_indexed, split_paragraphs

P1 = "A programação dinâmica resolve problemas de otimização dividindo-os em subproblemas menores e independentes."
P2 = "Cada subproblema é resolvido uma única vez e a solução fica guardada para reutilização posterior no algoritmo."
P3 = "No capítulo seguinte vemos a conversão de recorrências em tabelas, com várias aplicações práticas."


def _pdf():
    doc = pymupdf.open()
    a = doc.new_page()
    a.insert_textbox((50, 60, 540, 160), P1, fontsize=11)
    a.insert_textbox((50, 200, 540, 300), P2, fontsize=11)
    b = doc.new_page()
    b.insert_textbox((50, 60, 540, 160), P3, fontsize=11)
    return doc


def test_locates_each_paragraph_with_page_and_order():
    rects = locate_paragraphs(_pdf(), 0, 2, [P1, P2, P3])
    assert [len(r) >= 1 for r in rects] == [True, True, True]
    assert [r[0][0] for r in rects] == [1, 1, 2]  # páginas 1-indexadas
    assert rects[0][0][2] < rects[1][0][2]  # y do 1º acima do 2º
    for r in rects:
        for _, x0, y0, x1, y1 in r:
            assert 0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1


def test_unmatched_paragraph_has_no_rects_but_does_not_break_the_next():
    rects = locate_paragraphs(_pdf(), 0, 2, [P1, "texto que não está no pdf algum, de jeito nenhum aqui", P3])
    assert rects[0] and rects[1] == [] and rects[2]


def test_matches_across_hyphenation_and_case():
    doc = pymupdf.open()
    doc.new_page().insert_textbox((50, 60, 540, 160), "A conver-\nsão de recor-\nrências é útil.", fontsize=11)
    assert locate_paragraphs(doc, 0, 1, ["A conversão de recorrências é útil."])[0]


def test_estimate_timeline_covers_duration_in_order():
    tl = estimate_timeline("Título", ["um dois três", "quatro cinco seis sete oito"], 60.0)
    assert [e["p"] for e in tl] == [-1, 0, 1]
    assert abs(tl[-1]["t"] + tl[-1]["d"] - 60.0) < 0.1
    assert tl[1]["t"] > tl[0]["t"]


def test_chunk_indexed_tracks_paragraph_and_skips_silent():
    out = chunk_indexed("Título.\n\n•\n\nPrimeiro.\n\nSegundo.")
    assert [(t, i) for t, _, i in out] == [("Título.", 0), ("Primeiro.", 2), ("Segundo.", 3)]
    assert split_paragraphs("a\n\n\n\nb") == ["a", "b"]
