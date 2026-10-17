"""Quadros do vídeo-aula: introdução, cenas com tópicos que aparecem junto da fala, resumo e perguntas."""
from html import escape
from pathlib import Path

import pymupdf

from .lesson import LABELS
from .video import ACCENT, BG, CSS, INK, MUTED, PAPER, H, W

BULLET_DIM = "#C3CBC8"
PANEL = (0.10, 0.125, 0.135)


def _weights(k: int) -> list[float]:
    w = [1.3] + [1.0] * (k - 1)
    w[-1] += 0.8  # o último tópico fica na tela até o fim da fala
    return w


def _reveal(base: dict, bullets: list[str], d: float, **extra) -> list[dict]:
    w = _weights(len(bullets))
    tot = sum(w)
    return [{**base, "d": d * wi / tot, "bullets": bullets, "shown": j + 1, **extra} for j, wi in enumerate(w)]


def lesson_segments(lesson: dict, durations: dict[str, float], paragraphs: list[dict], page_start: int) -> list[dict]:
    """Quadros na ordem da narração. `durations` tem as chaves intro, scene:i, recap, q:j e a:j (segundos)."""
    lab = LABELS.get(lesson.get("lang", "pt"), LABELS["en"])
    first_page = next((r[0][0] for p in paragraphs for r in [p["rects"]] if r), page_start + 1)
    n = len(lesson["scenes"])
    base = {"labels": lab, "title": "", "note": None, "rects": [], "page": first_page, "counter": None}
    segs = [{**base, "d": durations["intro"], "kind": "intro", "title": lesson["title"], "bullets": [s["title"] for s in lesson["scenes"]], "shown": n}]
    page = first_page
    for i, sc in enumerate(lesson["scenes"]):
        rects = [r for ref in sc["refs"] if 0 <= ref < len(paragraphs) for r in paragraphs[ref]["rects"]]
        if rects:
            page = rects[0][0]
        b = {**base, "kind": "scene", "title": sc["title"], "page": page, "rects": [r for r in rects if r[0] == page], "counter": (i + 1, n)}
        segs += _reveal(b, sc["bullets"], durations[f"scene:{i}"], note=sc.get("example"))
    segs += _reveal({**base, "kind": "recap", "title": lab["recap"]}, lesson["recap"], durations["recap"])
    for j, qa in enumerate(lesson["quiz"]):
        segs.append({**base, "d": durations[f"q:{j}"], "kind": "quiz_q", "title": f"{lab['question']} {j + 1}", "bullets": [qa["q"]], "shown": 1, "note": None})
        segs.append({**base, "d": durations[f"a:{j}"], "kind": "quiz_a", "title": f"{lab['question']} {j + 1}", "bullets": [qa["q"]], "shown": 1, "note": qa["a"]})
    return segs


def _bullets_html(items: list[str], shown: int, size: int, uniform: bool = False) -> str:
    out = []
    for i, t in enumerate(items[:shown]):
        cur = i == shown - 1 and not uniform
        color, weight = (INK, "bold") if cur else (BULLET_DIM, "normal")
        mark = '<span style="color:#5FCDC4">●</span>&nbsp;&nbsp;' if cur else '<span style="color:#5C6B69">●</span>&nbsp;&nbsp;'
        out.append(f'<p style="margin:0 0 {int(size * 0.5)}px 0;font-size:{size}px;line-height:1.35;color:{color};font-weight:{weight}">{mark}{escape(t)}</p>')
    return "".join(out)


def lesson_frame(src: pymupdf.Document, seg: dict, book_title: str, label: str, frac: float, png: Path) -> None:
    lab, kind = seg["labels"], seg["kind"]
    doc = pymupdf.open()
    page = doc.new_page(width=W, height=H)
    page.draw_rect(page.rect, color=None, fill=BG)
    page.insert_htmlbox(pymupdf.Rect(56, 22, W - 300, 62), css=CSS, text=f'<div style="color:{MUTED};font-size:19px">{escape(label)}</div>')
    if seg["counter"]:
        i, n = seg["counter"]
        page.insert_htmlbox(pymupdf.Rect(W - 300, 22, W - 56, 62), css=CSS, text=f'<div style="color:{MUTED};font-size:19px;text-align:right">{i} / {n}</div>')
    with_page = kind in ("scene", "intro")
    right = W - (520 if with_page else 56)
    if kind == "intro":
        page.insert_htmlbox(pymupdf.Rect(56, 84, right, 250), css=CSS, scale_low=0.5, text=(
            f'<div style="color:{MUTED};font-size:22px;margin-bottom:8px">{escape(book_title)}</div>'
            f'<div style="color:{INK};font-size:52px;font-weight:bold;line-height:1.12">{escape(seg["title"])}</div>'))
        page.insert_htmlbox(pymupdf.Rect(56, 275, right, H - 60), css=CSS, scale_low=0.5, text=(
            f'<div style="color:{ACCENT_HEX};font-size:24px;font-weight:bold;margin-bottom:12px">{escape(lab["agenda"])}</div>' + _bullets_html(seg["bullets"], len(seg["bullets"]), 30, uniform=True)))
    elif kind in ("quiz_q", "quiz_a"):
        page.insert_htmlbox(pymupdf.Rect(56, 100, right, 180), css=CSS, text=f'<div style="color:{ACCENT_HEX};font-size:34px;font-weight:bold">{escape(seg["title"])}</div>')
        page.insert_htmlbox(pymupdf.Rect(56, 190, right, 400), css=CSS, scale_low=0.5, text=f'<p style="color:{INK};font-size:42px;line-height:1.3">{escape(seg["bullets"][0])}</p>')
        if kind == "quiz_a":
            box = pymupdf.Rect(56, 410, right, 560)
            page.draw_rect(box, color=ACCENT, fill=PANEL, width=2, radius=0.04)
            page.insert_htmlbox(box + (24, 18, -24, -12), css=CSS, scale_low=0.5, text=(
                f'<div style="color:{ACCENT_HEX};font-size:22px;font-weight:bold;margin-bottom:6px">{escape(lab["answer"])}</div>'
                f'<p style="color:{INK};font-size:34px;line-height:1.3">{escape(seg["note"])}</p>'))
    else:  # scene, recap
        page.insert_htmlbox(pymupdf.Rect(56, 78, right, 160), css=CSS, scale_low=0.5, text=f'<div style="color:{INK};font-size:46px;font-weight:bold;line-height:1.15">{escape(seg["title"])}</div>')
        has_note = bool(seg["note"]) and seg["shown"] == len(seg["bullets"])
        page.insert_htmlbox(pymupdf.Rect(56, 175, right, H - (190 if seg["note"] else 70)), css=CSS, scale_low=0.45, text=_bullets_html(seg["bullets"], seg["shown"], 38))
        if has_note:
            box = pymupdf.Rect(56, H - 170, right, H - 56)
            page.draw_rect(box, color=ACCENT, fill=PANEL, width=1.5, radius=0.06)
            page.insert_htmlbox(box + (18, 10, -18, -6), css=CSS, scale_low=0.5, text=f'<p style="color:{INK};font-size:25px;line-height:1.3"><b style="color:{ACCENT_HEX}">{"Exemplo" if lab["agenda"] == "Nesta aula" else "Example"}.</b> {escape(seg["note"])}</p>')
    if with_page:  # miniatura do PDF com o trecho de origem em destaque
        pno = min(max(seg["page"] - 1, 0), len(src) - 1)
        sp = src[pno]
        ar = sp.rect.width / sp.rect.height
        pw, ph = 436, 436 / ar
        if ph > H - 190:
            ph, pw = H - 190, (H - 190) * ar
        x0, y0 = W - 56 - pw, 84
        box = pymupdf.Rect(x0, y0, x0 + pw, y0 + ph)
        page.draw_rect(box + (-3, -3, 3, 3), color=None, fill=PAPER)
        page.show_pdf_page(box, src, pno)
        for pg, fx0, fy0, fx1, fy1 in seg["rects"]:
            if pg - 1 == pno:
                r = pymupdf.Rect(box.x0 + fx0 * pw, box.y0 + fy0 * ph, box.x0 + fx1 * pw, box.y0 + fy1 * ph)
                page.draw_rect(r, color=ACCENT, fill=ACCENT, fill_opacity=0.3, stroke_opacity=1, width=1.6)
        page.insert_htmlbox(pymupdf.Rect(x0, y0 + ph + 12, W - 56, y0 + ph + 44), css=CSS, text=f'<div style="color:{MUTED};font-size:18px">{escape(lab["source"])} {pno + 1}</div>')
    bar = pymupdf.Rect(0, H - 8, W, H)
    page.draw_rect(bar, color=None, fill=(0.14, 0.17, 0.18))
    page.draw_rect(pymupdf.Rect(0, H - 8, W * max(0.0, min(frac, 1.0)), H), color=None, fill=ACCENT)
    page.get_pixmap(dpi=72).save(str(png))


ACCENT_HEX = "#5FCDC4"


# ---------- narração e montagem ----------
def narration_items(lesson: dict) -> list[tuple[str, str, float]]:
    """(chave, texto falado, pausa final em segundos) na ordem do vídeo."""
    lab = LABELS.get(lesson.get("lang", "pt"), LABELS["en"])
    items = [("intro", lesson["intro"], 1.0)]
    items += [(f"scene:{i}", s["narration"], 0.9) for i, s in enumerate(lesson["scenes"])]
    items.append(("recap", lesson["recap_narration"], 1.0))
    for j, qa in enumerate(lesson["quiz"]):
        items.append((f"q:{j}", f"{lab['question']} {j + 1}. {qa['q']}", 3.0))  # tempo para pensar
        items.append((f"a:{j}", f"{lab['answer']}. {qa['a']}", 1.2))
    return items


def narrate(items: list[tuple[str, str, float]], tts, voice: str, speed: float, work: Path, out_audio: Path, on_progress=None) -> dict[str, float]:
    """Sintetiza cada item, devolve a duração real de cada um e grava o áudio completo em `out_audio`."""
    from .audio import concat_normalize, duration_of, to_mp3
    from .chunk import chunk_text

    work.mkdir(parents=True, exist_ok=True)
    parts, durations, k = [], {}, 0
    for n, (key, text, pause) in enumerate(items):
        pieces = [c for c in chunk_text(text, tts.max_chars) if any(ch.isalnum() for ch in c)]
        total = 0.0
        for j, piece in enumerate(pieces):
            data = tts.synthesize(piece, voice, speed, pause_s=pause if j == len(pieces) - 1 else 0.25)
            f = work / f"{k:05d}.mp3"
            to_mp3(data, tts.audio_ext, f)
            total += duration_of(f) or 0.0
            parts.append(data)
            k += 1
        durations[key] = total
        if on_progress:
            on_progress((n + 1) / len(items))
    concat_normalize(parts, out_audio, ext=tts.audio_ext)
    return durations


def make_lesson_video(pdf: Path, out_mp4: Path, lesson: dict, paragraphs: list[dict], page_start: int, tts, voice: str, speed: float,
                      work: Path, book_title: str, label: str, on_progress=None) -> float:
    """Narra o roteiro e monta o vídeo. `on_progress` recebe 0..1 (narração 60%, quadros 40%)."""
    from .video import build_video

    prog = on_progress or (lambda _f: None)
    audio = work / "aula.mp3"
    durations = narrate(narration_items(lesson), tts, voice, speed, work / "pieces", audio, lambda f: prog(0.6 * f))
    segs = lesson_segments(lesson, durations, paragraphs, page_start)
    return build_video(pdf, audio, out_mp4, book_title=book_title, label=label, segments=segs,
                       on_progress=lambda f: prog(0.6 + 0.4 * f), frame_fn=lesson_frame)
