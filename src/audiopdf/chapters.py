"""Divisão em capítulos: bookmarks de nível 1; fallback = livro inteiro."""
from dataclasses import dataclass

from .extract import Outline


@dataclass
class Chapter:
    index: int
    title: str
    text: str


def split_chapters(pages: list[str], outline: list[Outline], title: str = "Livro") -> list[Chapter]:
    tops = [o for o in outline if o.level == 1]
    if not tops:
        return [Chapter(1, title, "\n\n".join(p for p in pages if p))]
    chapters = []
    for i, o in enumerate(tops):
        end = tops[i + 1].page if i + 1 < len(tops) else len(pages)
        text = "\n\n".join(p for p in pages[o.page:end] if p)
        if text.strip():
            chapters.append(Chapter(len(chapters) + 1, o.title.strip(), text))
    return chapters
