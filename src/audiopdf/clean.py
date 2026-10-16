"""Etapa 3: limpeza (cabeçalho/rodapé, nº de página, hifenização, parágrafos)."""
import re
from collections import Counter

_END = re.compile(r"[.!?…:;»”\"\)\]]\s*$")
_PAGE_NUM = re.compile(r"^\s*(?:[-–—]?\s*\d{1,4}\s*[-–—]?|página\s+\d+|page\s+\d+)\s*$", re.IGNORECASE)


def _edge_lines(page: str, n: int = 2) -> list[str]:
    lines = [l.strip() for l in page.splitlines() if l.strip()]
    return lines[:n] + lines[-n:]


def find_repeated_edges(pages: list[str], threshold: float = 0.4) -> set[str]:
    """Linhas de borda que se repetem em >= threshold das páginas."""
    if len(pages) < 4:
        return set()
    counts: Counter[str] = Counter()
    for p in pages:
        counts.update(set(_edge_lines(p)))
    return {l for l, c in counts.items() if c / len(pages) >= threshold and len(l) < 120}


def clean_page(page: str, repeated: set[str]) -> str:
    out = []
    for line in page.splitlines():
        s = line.strip()
        if s in repeated or _PAGE_NUM.match(s):
            continue
        out.append(line.rstrip())
    return "\n".join(out)


def join_hyphenation(text: str) -> str:
    return re.sub(r"(\w)-\n(\w)", r"\1\2", text)


def rebuild_paragraphs(text: str) -> str:
    """Linha em branco separa parágrafos; quebras simples viram espaço."""
    paras = re.split(r"\n\s*\n", text)
    return "\n\n".join(re.sub(r"\s*\n\s*", " ", p).strip() for p in paras if p.strip())


def merge_broken_paragraphs(text: str) -> str:
    """Junta parágrafos cortados por quebra de bloco/página: o anterior não termina em pontuação
    e o seguinte começa em minúscula."""
    out: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        if out and para[0].islower() and not _END.search(out[-1]):
            out[-1] = out[-1][:-1] + para if out[-1].endswith("-") else f"{out[-1]} {para}"
        else:
            out.append(para)
    return "\n\n".join(out)


def clean_pages(pages: list[str]) -> list[str]:
    repeated = find_repeated_edges(pages)
    return [merge_broken_paragraphs(rebuild_paragraphs(join_hyphenation(clean_page(p, repeated)))) for p in pages]
