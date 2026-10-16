"""Etapa 1-2: texto por página, sumário (bookmarks) e OCR das páginas sem texto (PyMuPDF + Tesseract)."""
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field

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
    scanned_pages: list[int]  # páginas sem texto que continuam sem texto (OCR ausente ou falhou)
    ocr_pages: list[int] = field(default_factory=list)  # páginas recuperadas por OCR


def _tessdata() -> str | None:
    """Diretório do tessdata se o Tesseract estiver instalado."""
    if not shutil.which("tesseract"):
        return None
    if os.environ.get("TESSDATA_PREFIX"):
        return os.environ["TESSDATA_PREFIX"]
    out = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True, check=False)
    m = re.search(r'"(.+)"', out.stdout + out.stderr)
    return m.group(1) if m else None


def _blocks_text(page: pymupdf.Page, textpage=None) -> str:
    blocks = page.get_text("blocks", sort=True, textpage=textpage)
    return "\n\n".join(b[4].strip() for b in blocks if b[6] == 0 and b[4].strip())


def extract(path: str, min_chars: int = 20, ocr: bool = True, ocr_lang: str | None = None,
            max_ocr_pages: int | None = None) -> PdfContent:
    doc = pymupdf.open(path)
    if doc.needs_pass:
        raise ValueError("PDF protegido por senha")
    # blocos (não linhas soltas): preserva a separação entre parágrafos
    pages = [_blocks_text(p) for p in doc]
    outline = [Outline(lvl, title, max(pg - 1, 0)) for lvl, title, pg in doc.get_toc()]
    scanned = [i for i, t in enumerate(pages) if len(t.strip()) < min_chars]
    ocr_done: list[int] = []
    tessdata = _tessdata() if ocr and scanned else None
    if tessdata:
        lang = ocr_lang or os.environ.get("OCR_LANG", "por+eng")  # idioma do livro ainda é desconhecido
        limit = max_ocr_pages if max_ocr_pages is not None else int(os.environ.get("OCR_MAX_PAGES", "150"))
        for i in scanned[:limit]:
            try:
                page = doc[i]  # manter a referência: o textpage aponta para a página
                tp = page.get_textpage_ocr(language=lang, dpi=300, full=True, tessdata=tessdata)
                text = _blocks_text(page, tp)
            except Exception:  # noqa: BLE001 - página ilegível não derruba o livro
                continue
            if len(text.strip()) >= min_chars:
                pages[i] = text
                ocr_done.append(i)
    scanned = [i for i in scanned if i not in set(ocr_done)]
    return PdfContent(pages=pages, outline=outline, scanned_pages=scanned, ocr_pages=ocr_done)
