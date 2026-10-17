"""Alinha os parágrafos do texto narrado com as regiões do PDF (para destacar o que está sendo lido)."""
import re
from dataclasses import dataclass

import pymupdf

_NON_WORD = re.compile(r"[\W_]+")
KEY_LEN = 40  # caracteres normalizados usados para achar o início do parágrafo
COVER = 0.92  # fração do texto do parágrafo que precisa ser coberta pelos blocos


def _norm(s: str) -> str:
    return _NON_WORD.sub("", s.lower())


@dataclass
class _Block:
    page: int
    rect: tuple[float, float, float, float]  # fração da página (0..1)
    norm: str


def _blocks(doc: pymupdf.Document, start: int, end: int) -> list[_Block]:
    out: list[_Block] = []
    for pn in range(start, min(end, len(doc))):
        page = doc[pn]
        w, h = page.rect.width, page.rect.height
        for b in page.get_text("blocks", sort=True):
            if b[6] != 0:
                continue
            n = _norm(b[4])
            if n:
                out.append(_Block(pn, (b[0] / w, b[1] / h, b[2] / w, b[3] / h), n))
    return out


def locate_paragraphs(doc: pymupdf.Document, start: int, end: int, paragraphs: list[str]) -> list[list[list[float]]]:
    """Para cada parágrafo, lista de retângulos [página(1-indexada), x0, y0, x1, y1] em fração da página.
    Parágrafo não localizado → lista vazia (a leitura continua, só sem destaque)."""
    blocks = _blocks(doc, start, end)
    result: list[list[list[float]]] = []
    ptr = 0
    for para in paragraphs:
        pn = _norm(para)
        if not pn:
            result.append([])
            continue
        key = pn[:KEY_LEN]
        found = next((j for j in range(ptr, len(blocks)) if blocks[j].norm.startswith(key[:20]) or key in blocks[j].norm), None)
        if found is None:
            result.append([])
            continue
        rects, acc, j = [], 0, found
        while j < len(blocks) and acc < COVER * len(pn):
            b = blocks[j]
            rects.append([b.page + 1, *(round(v, 4) for v in b.rect)])
            acc += len(b.norm)
            j += 1
        result.append(rects)
        ptr = max(found + 1, j)
    return result


def estimate_timeline(title: str, paragraphs: list[str], duration: float) -> list[dict]:
    """Linha do tempo aproximada (áudio sem marcação): tempo proporcional ao tamanho do texto."""
    pause = 12  # pausa de parágrafo ≈ 12 caracteres de fala
    items = [(-1, len(title) + 1 + pause)] + [(i, len(p) + pause) for i, p in enumerate(paragraphs)]
    total = sum(w for _, w in items) or 1
    t, out = 0.0, []
    for pi, w in items:
        d = duration * w / total
        out.append({"t": round(t, 2), "d": round(d, 2), "p": pi})
        t += d
    return out
