"""Etapa 1: extrai texto por página e sumário (bookmarks) com PyMuPDF."""
from dataclasses import dataclass

import pymupdf


@dataclass
class Outline:
    level: int
    title: str
    page: int  # 0-indexed


@dataclass
class PdfContent:
    pages: list[str]
    outline: list[Outline]
    scanned_pages: list[int]  # páginas sem texto (precisam de OCR, fora da Fase 0)


def extract(path: str, min_chars: int = 20) -> PdfContent:
    doc = pymupdf.open(path)
    if doc.needs_pass:
        raise ValueError("PDF protegido por senha")
    pages = [p.get_text("text") for p in doc]
    outline = [Outline(lvl, title, max(pg - 1, 0)) for lvl, title, pg in doc.get_toc()]
    scanned = [i for i, t in enumerate(pages) if len(t.strip()) < min_chars]
    return PdfContent(pages=pages, outline=outline, scanned_pages=scanned)
