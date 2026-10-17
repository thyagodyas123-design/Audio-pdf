"""Vídeo da leitura: página do PDF com o parágrafo narrado em destaque + texto + o áudio (PyMuPDF + FFmpeg)."""
import subprocess
from collections.abc import Callable
from html import escape
from pathlib import Path

import pymupdf

from .audio import duration_of

W, H = 1280, 720
BG, PAPER = (0.055, 0.071, 0.075), (1, 1, 1)
ACCENT = (0.37, 0.80, 0.77)
INK, MUTED = "#E9EDEA", "#9AA5A9"
CSS = "* { font-family: sans-serif; } p, div { margin: 0; }"


def segments_from_timeline(timeline: list[dict], paragraphs: list[dict], title: str, page_start: int,
                           text_of: Callable[[int], str] | None = None) -> list[dict]:
    """Junta trechos consecutivos do mesmo parágrafo em um quadro. p = -1 é o título do capítulo."""
    segs: list[dict] = []
    for e in timeline:
        if segs and segs[-1]["p"] == e["p"]:
            segs[-1]["d"] += e["d"]
            continue
        p = e["p"]
        para = paragraphs[p] if 0 <= p < len(paragraphs) else None
        rects = para["rects"] if para else []
        text = title if p < 0 else (text_of(p) if text_of else para["text"])
        page = rects[0][0] if rects else None
        segs.append({"d": e["d"], "p": p, "text": text, "rects": rects, "page": page, "title": p < 0})
    for s in segs:  # sem região conhecida: mostra a página onde o capítulo começa
        if s["page"] is None:
            s["page"] = next((x["page"] for x in segs if x["page"]), page_start + 1)
    return segs


def _frame(src: pymupdf.Document, seg: dict, book_title: str, label: str, frac: float, png: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=W, height=H)
    page.draw_rect(page.rect, color=None, fill=BG)
    pno = min(max(seg["page"] - 1, 0), len(src) - 1)
    sp = src[pno]
    ar = sp.rect.width / sp.rect.height
    ph = H - 56
    pw = ph * ar
    if pw > 560:
        pw, ph = 560, 560 / ar
    x0, y0 = 32, (H - ph) / 2
    box = pymupdf.Rect(x0, y0, x0 + pw, y0 + ph)
    page.draw_rect(box + (-3, -3, 3, 3), color=None, fill=PAPER)
    page.show_pdf_page(box, src, pno)
    for pg, fx0, fy0, fx1, fy1 in seg["rects"]:
        if pg - 1 == pno:
            r = pymupdf.Rect(box.x0 + fx0 * pw, box.y0 + fy0 * ph, box.x0 + fx1 * pw, box.y0 + fy1 * ph)
            page.draw_rect(r, color=ACCENT, fill=ACCENT, fill_opacity=0.27, stroke_opacity=1, width=1.6)
    px, right = x0 + pw + 48, W - 56
    page.insert_htmlbox(pymupdf.Rect(px, 28, right, 100), css=CSS, text=(
        f'<div style="color:{MUTED};font-size:19px">{escape(book_title)}</div>'
        f'<div style="color:{INK};font-size:23px;font-weight:bold">{escape(label)}</div>'))
    size = 46 if seg["title"] else 32
    page.insert_htmlbox(pymupdf.Rect(px, 112, right, H - 84), css=CSS, scale_low=0.4, text=(
        f'<p style="color:{INK};font-size:{size}px;line-height:1.42">{escape(seg["text"])}</p>'))
    bar = pymupdf.Rect(px, H - 56, right, H - 50)
    page.draw_rect(bar, color=None, fill=(0.16, 0.19, 0.2))
    page.draw_rect(pymupdf.Rect(bar.x0, bar.y0, bar.x0 + bar.width * max(0.0, min(frac, 1.0)), bar.y1), color=None, fill=ACCENT)
    page.insert_htmlbox(pymupdf.Rect(px, H - 44, right, H - 14), css=CSS, text=f'<div style="color:{MUTED};font-size:17px">Página {pno + 1}</div>')
    page.get_pixmap(dpi=72).save(str(png))


def build_video(pdf_path: Path, audio_path: Path, out_path: Path, *, book_title: str, label: str,
                segments: list[dict], on_progress: Callable[[float], None] | None = None) -> float:
    """Gera o MP4 (H.264 + AAC, 1280x720). Retorna a duração em segundos."""
    pdf_path, audio_path, out_path = Path(pdf_path).resolve(), Path(audio_path).resolve(), Path(out_path).resolve()
    audio_dur = duration_of(audio_path) or sum(s["d"] for s in segments)
    segs = [dict(s) for s in segments if s["d"] > 0] or [dict(segments[0], d=audio_dur)]
    total = sum(s["d"] for s in segs)
    if total < audio_dur:  # o último quadro cobre a sobra (marcações arredondadas)
        segs[-1]["d"] += audio_dur - total + 0.2
    work = out_path.parent / f".{out_path.stem}.frames"
    work.mkdir(exist_ok=True)
    try:
        src = pymupdf.open(pdf_path)
        lines, elapsed = [], 0.0
        for i, s in enumerate(segs):
            png = work / f"{i:05d}.png"
            _frame(src, s, book_title, label, elapsed / max(audio_dur, 1), png)
            lines += [f"file '{png}'", f"duration {s['d']:.3f}"]
            elapsed += s["d"]
            if on_progress:
                on_progress(0.85 * (i + 1) / len(segs))
        lines.append(f"file '{work / f'{len(segs) - 1:05d}.png'}'")  # o demuxer ignora a duração do último arquivo
        (work / "list.txt").write_text("\n".join(lines))
        tmp = out_path.with_suffix(".tmp.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(work / "list.txt"),
             "-i", str(audio_path), "-c:v", "libx264", "-tune", "stillimage", "-preset", "veryfast", "-crf", "24",
             "-pix_fmt", "yuv420p", "-r", "10", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", "-shortest", str(tmp)],
            check=True,
        )
        tmp.replace(out_path)
    finally:
        for f in work.glob("*"):
            f.unlink(missing_ok=True)
        work.rmdir()
    if on_progress:
        on_progress(1.0)
    return duration_of(out_path) or audio_dur
