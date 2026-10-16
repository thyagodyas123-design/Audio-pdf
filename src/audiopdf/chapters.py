"""Divisão em capítulos a partir dos bookmarks; fallback = livro inteiro."""
import re
from dataclasses import dataclass

from .clean import merge_broken_paragraphs
from .extract import Outline

_SKIP = re.compile(
    r"^(folha de rosto|copyright|sum[áa]rio|[íi]ndice|bibliografia|refer[êe]ncias|"
    r"title page|contents|table of contents|index|bibliography|references)\b",
    re.IGNORECASE,
)


@dataclass
class Chapter:
    index: int
    title: str
    text: str


def _boundaries(outline: list[Outline]) -> list[Outline]:
    """Nível 1 sem filhos (prefácio, apêndice) + nível 2 (capítulos sob 'Partes')."""
    out: list[Outline] = []
    for i, o in enumerate(outline):
        if o.level == 1:
            has_child = i + 1 < len(outline) and outline[i + 1].level == 2
            if not has_child:
                out.append(o)
        elif o.level == 2:
            out.append(o)
    return out


def split_chapters(
    pages: list[str], outline: list[Outline], title: str = "Livro", skip_matter: bool = True
) -> list[Chapter]:
    bounds = sorted(_boundaries(outline), key=lambda o: o.page)
    if not bounds:
        return [Chapter(1, title, merge_broken_paragraphs("\n\n".join(p for p in pages if p)))]
    chapters: list[Chapter] = []
    for i, o in enumerate(bounds):
        end = bounds[i + 1].page if i + 1 < len(bounds) else len(pages)
        if end <= o.page:
            end = o.page + 1  # entradas na mesma página
        if skip_matter and _SKIP.match(o.title.strip()):
            continue
        text = merge_broken_paragraphs("\n\n".join(p for p in pages[o.page:end] if p))
        if text.strip():
            chapters.append(Chapter(len(chapters) + 1, o.title.strip(), text))
    return chapters
