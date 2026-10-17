"""Fase A: app local (FastAPI + página estática). Um usuário, sem auth, só 127.0.0.1."""
import itertools
import json
import logging
import os
import queue
import re
import shutil
import tempfile
import threading
import time
import uuid
import zipfile
from pathlib import Path
from typing import Literal

import pymupdf
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from ..align import estimate_timeline, locate_paragraphs
from ..audio import concat_normalize, duration_of, to_mp3
from ..chapters import split_chapters
from ..chunk import chunk_indexed, chunk_text, split_paragraphs
from ..clean import clean_pages
from ..extract import extract
from ..lang import detect
from ..lesson import build_lesson
from ..lesson_video import make_lesson_video
from ..llm import LLM
from ..llm import configured as llm_configured
from ..summarize import select as select_summary
from ..translate import available_translators, get_translator
from ..tts import get_provider
from ..video import build_video, segments_from_timeline

DATA = Path(os.environ.get("AUDIOPDF_DATA", "data")).resolve()
MAX_BYTES = 200 * 1024 * 1024
ID_RE = re.compile(r"^[0-9a-f]{32}$")
VOICES = [
    {"id": "pf_dora", "label": "Dora", "gender": "Feminina", "lang": "pt-BR", "sample": "Olá, esta é uma amostra da minha voz."},
    {"id": "pm_alex", "label": "Alex", "gender": "Masculina", "lang": "pt-BR", "sample": "Olá, esta é uma amostra da minha voz."},
    {"id": "pm_santa", "label": "Santa", "gender": "Masculina", "lang": "pt-BR", "sample": "Olá, esta é uma amostra da minha voz."},
    {"id": "af_heart", "label": "Heart", "gender": "Feminina", "lang": "en-US", "sample": "Hello, this is a sample of my voice."},
    {"id": "am_michael", "label": "Michael", "gender": "Masculina", "lang": "en-US", "sample": "Hello, this is a sample of my voice."},
]

LANGUAGES = [
    {"code": "pt-BR", "name": "Português (Brasil)", "base": "pt"},
    {"code": "en-US", "name": "English (US)", "base": "en"},
]
_BASE_TO_CODE = {l["base"]: l["code"] for l in LANGUAGES}


def _base(code: str) -> str:
    return code.split("-")[0].lower()


log = logging.getLogger("audiopdf")
app = FastAPI(title="Audio-PDF (local)")
_lock = threading.Lock()
# (prioridade, seq, livro, capítulos, voz, velocidade): 0 = pré-busca do próximo capítulo, 1 = fila normal
_jobs: "queue.PriorityQueue" = queue.PriorityQueue()
_seq = itertools.count()
_cancel: set[str] = set()
_tts = None
_tts_lock = threading.Lock()


def _provider():
    global _tts
    with _tts_lock:
        if _tts is None:
            _tts = get_provider(os.environ.get("TTS_PROVIDER", "kokoro"))
        return _tts


def _dir(book_id: str) -> Path:
    if not ID_RE.match(book_id):
        raise HTTPException(404, "livro não encontrado")
    d = DATA / "books" / book_id
    if not d.is_dir():
        raise HTTPException(404, "livro não encontrado")
    return d


def _load(book_id: str) -> dict:
    meta = json.loads((_dir(book_id) / "meta.json").read_text())
    if "language" not in meta:  # livro enviado antes da detecção de idioma
        texts = json.loads((_dir(book_id) / "chapters.json").read_text())
        meta["language"] = detect(" ".join(t[:2000] for t in texts[:6]))
        _save(book_id, meta)
    return meta


def _save(book_id: str, meta: dict) -> None:
    p = DATA / "books" / book_id / "meta.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(meta, ensure_ascii=False))
    tmp.replace(p)


def _update_chapter(book_id: str, idx: int, **fields) -> None:
    with _lock:
        meta = _load(book_id)
        for c in meta["chapters"]:
            if c["index"] == idx:
                c.update(fields)
        _save(book_id, meta)


def _safe(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|\r\n]+', " ", name).strip()[:80] or "livro"


def _gc_parts(d: Path) -> None:
    """Apaga pré-escutas de capítulos já prontos há mais de 15 min."""
    for parts in d.glob("*.parts"):
        final = d / (parts.name.removesuffix(".parts") + ".mp3")
        if final.exists() and parts.stat().st_mtime < time.time() - 900:
            shutil.rmtree(parts, ignore_errors=True)


def _chapter_text(d: Path, book_id: str, idx: int, texts: list, src: str | None, tgt: str,
                  translator: str = "argos") -> tuple[str, str]:
    """Retorna (título, texto) no idioma de saída; traduz com cache em disco quando necessário."""
    meta = _load(book_id)
    title = next(c["title"] for c in meta["chapters"] if c["index"] == idx)
    if not src or src == tgt:
        return title, texts[idx - 1]
    cache = d / "translated" / f"{translator}-{tgt}"
    cache.mkdir(parents=True, exist_ok=True)
    f = cache / f"{idx:02d}.json"
    if f.exists():
        data = json.loads(f.read_text())
        return data["title"], data["text"]
    _update_chapter(book_id, idx, status="translating", progress=0, parts=0, error=None)
    tr = get_translator(translator)
    new_title = tr.translate(title, src, tgt)
    def progress(p: float) -> None:
        if book_id in _cancel:
            raise InterruptedError
        _update_chapter(book_id, idx, progress=round(p, 3))

    text = tr.translate(texts[idx - 1], src, tgt, on_progress=progress)
    f.write_text(json.dumps({"title": new_title, "text": text}, ensure_ascii=False))
    return new_title, text


def _synth_chapter(d: Path, book_id: str, idx: int, texts: list, tts, voice: str, speed: float,
                   src: str | None, tgt: str, translator: str = "argos") -> None:
    title, body = _chapter_text(d, book_id, idx, texts, src, tgt, translator)
    _update_chapter(book_id, idx, status="running", progress=0, parts=0, error=None)
    chunks = chunk_indexed(f"{title}.\n\n{body}", tts.max_chars)
    parts_dir = d / f"{idx:02d}.parts"
    shutil.rmtree(parts_dir, ignore_errors=True)
    parts_dir.mkdir()
    audio_parts = []
    timeline: list[dict] = []
    t = 0.0
    tl_file = d / f"{idx:02d}.timeline.json"
    tl_file.unlink(missing_ok=True)
    for i, (ch, para_end, pi) in enumerate(chunks):
        if book_id in _cancel:
            raise InterruptedError
        pause = 1.0 if i == 0 else (0.7 if para_end else 0.25)  # título > parágrafo > frase longa
        data = tts.synthesize(ch, voice, speed, pause_s=pause)
        audio_parts.append(data)
        to_mp3(data, tts.audio_ext, parts_dir / f"{i:04d}.mp3")
        dur = duration_of(parts_dir / f"{i:04d}.mp3") or 0.0
        timeline.append({"t": round(t, 2), "d": round(dur, 2), "p": pi - 1})  # p = -1: título; 0.. = parágrafos
        t += dur
        tl_file.write_text(json.dumps(timeline))  # parcial: o player acompanha mesmo durante a conversão
        _update_chapter(book_id, idx, progress=round((i + 1) / len(chunks), 3), parts=i + 1)
    concat_normalize(audio_parts, d / f"{idx:02d}.mp3", ext=tts.audio_ext)


def _worker() -> None:
    while True:
        _, _, book_id, indices, voice, speed, lang = _jobs.get()
        try:
            try:
                d = _dir(book_id)
            except HTTPException:
                continue  # livro excluído enquanto estava na fila
            texts = json.loads((d / "chapters.json").read_text())
            meta0 = _load(book_id)
            src = meta0.get("language")
            translator = (meta0.get("settings") or {}).get("translator") or "argos"
            tgt = _base(lang)
            tts = _provider()
            for idx in indices:
                if book_id in _cancel:
                    _update_chapter(book_id, idx, status="canceled", progress=0)
                    continue
                if (d / f"{idx:02d}.mp3").exists():
                    _update_chapter(book_id, idx, status="done", progress=1)
                    continue
                _gc_parts(d)
                try:
                    _synth_chapter(d, book_id, idx, texts, tts, voice, speed, src, tgt, translator)
                    _update_chapter(book_id, idx, status="done", progress=1, voice=voice, speed=speed, lang=lang,
                                    duration=duration_of(d / f"{idx:02d}.mp3"),
                                    translator=translator if src and src != tgt else None)
                except InterruptedError:
                    _update_chapter(book_id, idx, status="canceled", progress=0)
                except Exception as e:  # falha de um capítulo não derruba os demais
                    _update_chapter(book_id, idx, status="failed", error=str(e)[:300])
        except Exception:
            log.exception("falha no worker (livro removido durante o processamento?)")
        finally:
            _cancel.discard(book_id)
            _jobs.task_done()


def _resume() -> None:
    """Após reinício, retoma capítulos que estavam na fila/em andamento (retomada por capítulo, RNF-05)."""
    root = DATA / "books"
    for p in root.glob("*/meta.json") if root.is_dir() else []:
        meta = json.loads(p.read_text())
        stale_video = False
        for c in meta["chapters"]:
            for v in (c.get("videos") or {}).values():
                if v.get("status") in ("queued", "running"):
                    v.update(status="failed", error="interrompido pelo reinício; gere de novo")
                    stale_video = True
        pending = [c["index"] for c in meta["chapters"] if c["status"] in ("running", "queued", "translating")]
        if not pending:
            if stale_video:
                p.write_text(json.dumps(meta, ensure_ascii=False))
            continue
        st = meta.get("settings")
        for c in meta["chapters"]:
            if c["index"] in pending:
                c.update(status="queued" if st else "canceled", progress=0)
        p.write_text(json.dumps(meta, ensure_ascii=False))
        if st:
            _jobs.put((1, next(_seq), meta["id"], pending, st["voice"], st["speed"], st.get("lang", "pt-BR")))


_resume()
threading.Thread(target=_worker, daemon=True).start()


def _warmup() -> None:
    try:
        tts = _provider()
        if hasattr(tts, "warmup"):
            tts.warmup()
    except Exception:
        log.warning("aquecimento do modelo falhou", exc_info=True)


if not os.environ.get("AUDIOPDF_NO_WARMUP"):
    threading.Thread(target=_warmup, daemon=True).start()


def _summary(meta: dict) -> dict:
    ch = meta["chapters"]
    return {
        "id": meta["id"], "title": meta["title"], "pages": meta["pages"],
        "created": meta["created"], "chapter_count": len(ch),
        "done": sum(c["status"] == "done" for c in ch),
        "running": sum(c["status"] in ("running", "queued", "translating") for c in ch),
        "failed": sum(c["status"] == "failed" for c in ch),
        "duration": round(sum(c.get("duration") or 0 for c in ch)),
    }


@app.get("/api/capabilities")
def capabilities():
    """O que está disponível neste servidor (a interface esconde o que não funciona)."""
    return {"llm": llm_configured(), "llm_model": os.environ.get("LESSON_MODEL") or "gemini-3.8-flash"}


@app.get("/api/translators")
def translators():
    return available_translators()


@app.get("/api/languages")
def languages():
    return LANGUAGES


@app.get("/api/voices")
def voices():
    return VOICES


@app.get("/api/voices/{voice_id}/sample")
def sample(voice_id: str):
    v = next((x for x in VOICES if x["id"] == voice_id), None)
    if not v:
        raise HTTPException(404, "voz desconhecida")
    d = DATA / "samples"
    d.mkdir(parents=True, exist_ok=True)
    out = d / f"{voice_id}.mp3"
    if not out.exists():
        tts = _provider()
        concat_normalize([tts.synthesize(v["sample"], voice_id, 1.0)], out, ext=tts.audio_ext)
    return FileResponse(out, media_type="audio/mpeg")


@app.get("/api/books")
def list_books():
    books = []
    root = DATA / "books"
    if root.is_dir():
        for p in root.glob("*/meta.json"):
            _fill_durations(p.parent.name)
            books.append(_summary(json.loads(p.read_text())))
    return sorted(books, key=lambda b: b["created"], reverse=True)


def _analyze(pdf: Path, title: str):
    try:
        content = extract(str(pdf))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(400, "não foi possível ler o PDF") from e
    chapters = split_chapters(clean_pages(content.pages), content.outline, title=title)
    if not chapters:
        raise HTTPException(422, "nenhum texto encontrado (PDF escaneado sem Tesseract instalado?)")
    return content, chapters


def _chapter_meta(c) -> dict:
    return {"index": c.index, "title": c.title, "chars": len(c.text), "status": "idle", "progress": 0, "error": None,
            "page_start": c.page_start, "page_end": c.page_end}


def _write_align(d: Path, chapters) -> None:
    """Mapeia cada parágrafo de cada capítulo para regiões do PDF (align.json). Falha não impede o livro."""
    try:
        doc = pymupdf.open(d / "source.pdf")
        out = {str(c.index): locate_paragraphs(doc, c.page_start, c.page_end, split_paragraphs(c.text)) for c in chapters}
        (d / "align.json").write_text(json.dumps(out))
    except Exception:
        log.warning("alinhamento com o PDF falhou", exc_info=True)


def _align(book_id: str) -> dict:
    """align.json; livros anteriores a esta função são alinhados na primeira consulta."""
    d = _dir(book_id)
    f = d / "align.json"
    if not f.exists():
        meta = _load(book_id)
        _, chapters = _analyze(d / "source.pdf", meta["title"])
        texts = json.loads((d / "chapters.json").read_text())
        for c in chapters:  # parágrafos do texto já narrado, faixa de páginas da análise atual
            if c.index <= len(texts):
                c.text = texts[c.index - 1]
        _write_align(d, chapters)
    try:
        return json.loads(f.read_text())
    except (OSError, ValueError):
        return {}


@app.post("/api/books")
def upload(file: UploadFile = File(...)):  # noqa: B008
    book_id = uuid.uuid4().hex
    d = DATA / "books" / book_id
    d.mkdir(parents=True)
    pdf = d / "source.pdf"
    size = 0
    try:
        with pdf.open("wb") as f:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise HTTPException(413, "arquivo maior que 200 MB")
                f.write(chunk)
        with pdf.open("rb") as f:
            if f.read(5) != b"%PDF-":
                raise HTTPException(400, "o arquivo não é um PDF")
        title = Path(file.filename or "livro").stem
        content, chapters = _analyze(pdf, title)
        (d / "chapters.json").write_text(json.dumps([c.text for c in chapters], ensure_ascii=False))
        _write_align(d, chapters)
        meta = {
            "id": book_id, "title": title, "pages": len(content.pages),
            "language": detect(" ".join(c.text[:2000] for c in chapters[:6])),
            "scanned_pages": len(content.scanned_pages), "ocr_pages": len(content.ocr_pages),
            "created": time.time(), "chapters": [_chapter_meta(c) for c in chapters],
        }
        _save(book_id, meta)
        return meta
    except Exception:
        shutil.rmtree(d, ignore_errors=True)
        raise


@app.post("/api/books/{book_id}/reanalyze")
def reanalyze(book_id: str):
    """Refaz a extração do texto a partir do PDF original (ex.: após melhorias na limpeza).
    Capítulos já prontos mantêm o áudio; os demais passam a usar o texto novo."""
    d = _dir(book_id)
    with _lock:
        meta = _load(book_id)
        if any(c["status"] in ("running", "queued", "translating") for c in meta["chapters"]):
            raise HTTPException(409, "há conversão em andamento; cancele antes de reanalisar")
        content, chapters = _analyze(d / "source.pdf", meta["title"])
        old = {c["index"]: c for c in meta["chapters"]}
        new = []
        for c in chapters:
            m = _chapter_meta(c)
            o = old.get(c.index)
            if o and o["title"] == c.title and o["status"] == "done":
                m.update({k: o[k] for k in ("status", "progress", "voice", "speed", "lang", "parts", "translator") if k in o})
            new.append(m)
        (d / "chapters.json").write_text(json.dumps([c.text for c in chapters], ensure_ascii=False))
        for tl in d.glob("*.timeline.json"):  # o texto mudou: marcações antigas não valem
            tl.unlink()
        _write_align(d, chapters)
        shutil.rmtree(d / "translated", ignore_errors=True)  # o texto mudou: traduções antigas não valem
        meta.update(chapters=new, pages=len(content.pages), scanned_pages=len(content.scanned_pages),
                    ocr_pages=len(content.ocr_pages), language=detect(" ".join(c.text[:2000] for c in chapters[:6])))
        _save(book_id, meta)
        return meta


def _fill_durations(book_id: str) -> None:
    d = _dir(book_id)
    with _lock:
        meta = _load(book_id)
        dirty = False
        for c in meta["chapters"]:
            f = d / f"{c['index']:02d}.mp3"
            if c["status"] == "done" and c.get("duration") is None and f.exists():
                c["duration"] = duration_of(f)
                dirty = True
        if dirty:
            _save(book_id, meta)


@app.get("/api/books/{book_id}")
def get_book(book_id: str):
    _fill_durations(book_id)
    return _load(book_id)


class JobIn(BaseModel):
    chapters: list[int] = Field(min_length=1)
    voice: str
    speed: float = Field(1.0, ge=0.75, le=1.5)
    target_language: str | None = None  # ex.: pt-BR; padrão = idioma detectado
    translator: str | None = None  # argos | deepl | claude (precisa de chave)


@app.post("/api/books/{book_id}/jobs")
def start_job(book_id: str, job: JobIn):
    voice = next((v for v in VOICES if v["id"] == job.voice), None)
    if not voice:
        raise HTTPException(400, "voz desconhecida")
    with _lock:
        meta = _load(book_id)
        lang = job.target_language or voice["lang"]
        if lang not in {l["code"] for l in LANGUAGES}:
            raise HTTPException(400, "idioma de saída não suportado")
        if _base(voice["lang"]) != _base(lang):
            raise HTTPException(400, f"a voz {voice['label']} não fala {lang}")
        src = meta.get("language")
        if src and src != _base(lang) and src not in {l["base"] for l in LANGUAGES}:
            raise HTTPException(400, f"tradução a partir de '{src}' ainda não suportada")
        translator = job.translator or "argos"
        if translator not in available_translators():
            raise HTTPException(400, f"tradutor '{translator}' indisponível (chave de API ausente?)")
        d = _dir(book_id)
        valid = {c["index"] for c in meta["chapters"]}
        picked = sorted(set(job.chapters) & valid)
        if not picked:
            raise HTTPException(400, "nenhum capítulo válido")
        _cancel.discard(book_id)
        for c in meta["chapters"]:
            if c["index"] not in picked:
                continue
            translated = bool(src) and src != _base(lang)
            same = (c.get("lang"), c.get("voice")) == (lang, job.voice) and \
                (not translated or c.get("translator") == translator)
            if c["status"] == "done" and not same:
                (d / f"{c['index']:02d}.mp3").unlink(missing_ok=True)  # outra voz/idioma: refazer
                _drop_videos(d, c["index"])
                c.pop("videos", None)
                shutil.rmtree(d / f"{c['index']:02d}.parts", ignore_errors=True)
                c["status"] = "idle"
            if c["status"] != "done":
                c.update(status="queued", progress=0, error=None)
        meta["settings"] = {"voice": job.voice, "speed": job.speed, "lang": lang, "translator": translator}
        _save(book_id, meta)
    _jobs.put((1, next(_seq), book_id, picked, job.voice, job.speed, lang))
    return {"queued": picked}


@app.post("/api/books/{book_id}/cancel")
def cancel(book_id: str):
    _dir(book_id)
    _cancel.add(book_id)
    return {"ok": True}


@app.get("/api/books/{book_id}/audio/{index}")
def audio(book_id: str, index: int, download: bool = False):
    d = _dir(book_id)
    f = d / f"{index:02d}.mp3"
    if not f.exists():
        raise HTTPException(404, "áudio ainda não gerado")
    if not download:
        return FileResponse(f, media_type="audio/mpeg")
    title = next((c["title"] for c in _load(book_id)["chapters"] if c["index"] == index), "capitulo")
    return FileResponse(f, media_type="audio/mpeg", filename=f"{index:02d} - {_safe(title)}.mp3")


@app.get("/api/books/{book_id}/parts/{index}/{part}")
def part_audio(book_id: str, index: int, part: int):
    f = _dir(book_id) / f"{index:02d}.parts" / f"{part:04d}.mp3"
    if not f.exists():
        raise HTTPException(404, "trecho ainda não gerado")
    return FileResponse(f, media_type="audio/mpeg")


def _sync_data(book_id: str, index: int) -> dict:
    """Parágrafos (com regiões no PDF) e linha do tempo de um capítulo, para o leitor e para os vídeos."""
    d = _dir(book_id)
    meta = _load(book_id)
    c = next((x for x in meta["chapters"] if x["index"] == index), None)
    if c is None:
        raise HTTPException(404, "capítulo não encontrado")
    texts = json.loads((d / "chapters.json").read_text())
    src_paras = split_paragraphs(texts[index - 1])
    shown, translated, shown_title = src_paras, False, c["title"]
    if c.get("lang") and c.get("translator") and meta.get("language") and meta["language"] != _base(c["lang"]):
        f = d / "translated" / f"{c['translator']}-{_base(c['lang'])}" / f"{index:02d}.json"
        if f.exists():
            data = json.loads(f.read_text())
            shown, translated, shown_title = split_paragraphs(data["text"]), True, data["title"]
    rects = _align(book_id).get(str(index), [])
    n_src, n_shown = len(src_paras), len(shown)

    def src_of(i: int) -> int:  # parágrafo traduzido -> parágrafo do PDF (índice, ou proporcional se a contagem difere)
        return i if n_shown == n_src else min(n_src - 1, int(i * n_src / max(n_shown, 1)))

    paragraphs = [{"text": shown[i], "rects": rects[src_of(i)] if src_of(i) < len(rects) else []} for i in range(n_shown)]
    tl_file, approx = d / f"{index:02d}.timeline.json", False
    if tl_file.exists():
        timeline = json.loads(tl_file.read_text())
    elif c["status"] == "done" and c.get("duration"):
        timeline, approx = estimate_timeline(shown_title, shown, c["duration"]), True
    else:
        timeline = []
    first_page = next((r[0][0] - 1 for r in rects if r), 0)
    return {"timeline": timeline, "paragraphs": paragraphs, "translated": translated, "approx": approx,
            "pages": meta["pages"], "title": shown_title, "page_start": c.get("page_start", first_page)}


@app.get("/api/books/{book_id}/chapters/{index}/sync")
def chapter_sync(book_id: str, index: int):
    """Dados para acompanhar o PDF enquanto o áudio toca."""
    return _sync_data(book_id, index)


@app.get("/api/books/{book_id}/pages/{n}")
def page_image(book_id: str, n: int, w: int = 1000):
    """Página do PDF como JPEG (n começa em 1), com cache em disco."""
    d = _dir(book_id)
    w = max(400, min(w, 2000))
    cache = d / "pages" / f"{n:04d}-{w}.jpg"
    if not cache.exists():
        doc = pymupdf.open(d / "source.pdf")
        if n < 1 or n > len(doc):
            raise HTTPException(404, "página inexistente")
        page = doc[n - 1]
        zoom = w / page.rect.width
        cache.parent.mkdir(exist_ok=True)
        page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False).save(str(cache), jpg_quality=80)
    return FileResponse(cache, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


# ---------- vídeos (leitura acompanhada e resumo) ----------
VIDEO_KINDS = ("leitura", "resumo", "aula")
VIDEO_FILES = {"leitura": ["leitura.mp4"], "resumo": ["resumo.mp4", "resumo.mp3", "resumo.timeline.json"], "aula": ["aula.mp4"]}
_vjobs: "queue.Queue[tuple[str, int, str]]" = queue.Queue()


def _update_video(book_id: str, idx: int, kind: str, **fields) -> None:
    with _lock:
        meta = _load(book_id)
        for c in meta["chapters"]:
            if c["index"] == idx:
                c.setdefault("videos", {}).setdefault(kind, {}).update(fields)
        _save(book_id, meta)


def _drop_videos(d: Path, idx: int, kinds: tuple[str, ...] = VIDEO_KINDS) -> None:
    """Apaga os vídeos (e arquivos auxiliares) de um capítulo. Sem `kinds`, apaga tudo, inclusive o roteiro da aula."""
    for kind in kinds:
        for suffix in VIDEO_FILES[kind]:
            (d / f"{idx:02d}.{suffix}").unlink(missing_ok=True)
    if kinds == VIDEO_KINDS:
        (d / f"{idx:02d}.aula.json").unlink(missing_ok=True)


def _synth_summary(d: Path, idx: int, tts, voice: str, speed: float, title: str, chosen: list[tuple[int, str]], on_progress) -> list[dict]:
    """Narra só os trechos escolhidos (título + excerto de cada parágrafo) e devolve a linha do tempo."""
    items = [(-1, f"{title}.")] + chosen
    work = d / f".{idx:02d}.resumo.tmp"
    work.mkdir(exist_ok=True)
    parts, timeline, t, k = [], [], 0.0, 0
    try:
        for n, (p, text) in enumerate(items):
            pieces = [c for c in chunk_text(text, tts.max_chars) if re.search(r"\w", c)]
            for j, piece in enumerate(pieces):
                last = j == len(pieces) - 1
                data = tts.synthesize(piece, voice, speed, pause_s=(1.0 if p < 0 else 0.7) if last else 0.25)
                f = work / f"{k:05d}.mp3"
                to_mp3(data, tts.audio_ext, f)
                dur = duration_of(f) or 0.0
                timeline.append({"t": round(t, 2), "d": round(dur, 2), "p": p})
                parts.append(data)
                t += dur
                k += 1
            on_progress((n + 1) / len(items))
        concat_normalize(parts, d / f"{idx:02d}.resumo.mp3", ext=tts.audio_ext)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    (d / f"{idx:02d}.resumo.timeline.json").write_text(json.dumps(timeline))
    return timeline


def _make_lesson(d: Path, meta: dict, c: dict, data: dict, idx: int, title: str, label: str, prog) -> dict:
    """Vídeo-aula: roteiro por LLM (guardado em NN.aula.json para não pagar de novo), narração e quadros."""
    lesson_file = d / f"{idx:02d}.aula.json"
    if lesson_file.exists():
        lesson = json.loads(lesson_file.read_text())
    else:
        lang = _base(c["lang"]) if c.get("lang") else (meta.get("language") or "pt")
        lesson = build_lesson(LLM(), title, [p["text"] for p in data["paragraphs"]], lang, lambda f: prog(0.25 * f))
        lesson_file.write_text(json.dumps(lesson, ensure_ascii=False))
    s = meta.get("settings") or {}
    voice, speed = c.get("voice") or s.get("voice") or "pf_dora", c.get("speed") or s.get("speed") or 1.0
    work, out = d / f".{idx:02d}.aula.work", d / f"{idx:02d}.aula.mp4"
    try:
        dur = make_lesson_video(d / "source.pdf", out, lesson, data["paragraphs"], data["page_start"], _provider(), voice, speed,
                                work, meta["title"], f"Aula · {label}", on_progress=lambda f: prog(0.25 + 0.75 * f))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return {"duration": round(dur, 1), "size": out.stat().st_size, "model": lesson.get("model")}


def _make_video(book_id: str, idx: int, kind: str) -> dict:
    d = _dir(book_id)
    meta = _load(book_id)
    c = next(x for x in meta["chapters"] if x["index"] == idx)
    data = _sync_data(book_id, idx)
    title, label = data["title"], f"Capítulo {idx} · {data['title']}"
    prog = lambda f: _update_video(book_id, idx, kind, progress=round(f, 3))
    if kind == "aula":
        return _make_lesson(d, meta, c, data, idx, title, label, prog)
    if kind == "leitura":
        audio, timeline, text_of, scale, base = d / f"{idx:02d}.mp3", data["timeline"], None, 1.0, 0.0
    else:
        chosen = select_summary([p["text"] for p in data["paragraphs"]])
        if not chosen:
            raise RuntimeError("capítulo curto demais para resumir")
        s = meta.get("settings") or {}
        voice, speed = c.get("voice") or s.get("voice") or "pf_dora", c.get("speed") or s.get("speed") or 1.0
        timeline = _synth_summary(d, idx, _provider(), voice, speed, title, chosen, lambda f: prog(0.5 * f))
        audio, excerpt, scale, base = d / f"{idx:02d}.resumo.mp3", dict(chosen), 0.5, 0.5
        text_of = lambda p: excerpt[p]
    if not timeline:
        raise RuntimeError("sem linha do tempo para este capítulo")
    segs = segments_from_timeline(timeline, data["paragraphs"], title, data["page_start"], text_of)
    out = d / f"{idx:02d}.{kind}.mp4"
    dur = build_video(d / "source.pdf", audio, out, book_title=meta["title"], label=label, segments=segs,
                      on_progress=lambda f: prog(base + scale * f))
    return {"duration": round(dur, 1), "size": out.stat().st_size}


def _video_worker() -> None:
    while True:
        book_id, idx, kind = _vjobs.get()
        try:
            _update_video(book_id, idx, kind, status="running", progress=0, error=None)
            info = _make_video(book_id, idx, kind)
            _update_video(book_id, idx, kind, status="done", progress=1, **info)
        except Exception as e:
            log.warning("falha ao gerar vídeo %s/%s/%s", book_id, idx, kind, exc_info=True)
            try:
                _update_video(book_id, idx, kind, status="failed", error=str(e)[:400])
            except Exception:  # noqa: BLE001
                pass
        finally:
            _vjobs.task_done()


threading.Thread(target=_video_worker, daemon=True).start()


class VideoIn(BaseModel):
    kind: Literal["leitura", "resumo", "aula"]


@app.post("/api/books/{book_id}/chapters/{index}/video")
def create_video(book_id: str, index: int, body: VideoIn):
    meta = _load(book_id)
    c = next((x for x in meta["chapters"] if x["index"] == index), None)
    if c is None:
        raise HTTPException(404, "capítulo não encontrado")
    if c["status"] != "done":
        raise HTTPException(409, "Gere o áudio do capítulo antes do vídeo.")
    cur = (c.get("videos") or {}).get(body.kind) or {}
    if cur.get("status") in ("queued", "running"):
        return cur
    _update_video(book_id, index, body.kind, status="queued", progress=0, error=None)
    _vjobs.put((book_id, index, body.kind))
    return {"status": "queued"}


@app.get("/api/books/{book_id}/chapters/{index}/video/{kind}")
def get_video(book_id: str, index: int, kind: str, download: bool = False):
    if kind not in VIDEO_KINDS:
        raise HTTPException(404, "tipo de vídeo desconhecido")
    d = _dir(book_id)
    f = d / f"{index:02d}.{kind}.mp4"
    if not f.exists():
        raise HTTPException(404, "vídeo ainda não gerado")
    if not download:
        return FileResponse(f, media_type="video/mp4")
    title = next((c["title"] for c in _load(book_id)["chapters"] if c["index"] == index), "capitulo")
    return FileResponse(f, media_type="video/mp4", filename=f"{index:02d} - {_safe(title)} ({kind}).mp4")


@app.delete("/api/books/{book_id}/chapters/{index}/video/{kind}")
def delete_video(book_id: str, index: int, kind: str):
    if kind not in VIDEO_KINDS:
        raise HTTPException(404, "tipo de vídeo desconhecido")
    d = _dir(book_id)
    (d / f"{index:02d}.{kind}.mp4").unlink(missing_ok=True)
    _drop_videos(d, index, (kind,))
    with _lock:
        meta = _load(book_id)
        for c in meta["chapters"]:
            if c["index"] == index:
                c.get("videos", {}).pop(kind, None)
        _save(book_id, meta)
    return {"ok": True}


@app.post("/api/books/{book_id}/prefetch/{index}")
def prefetch(book_id: str, index: int):
    """Quem escuta o capítulo N provavelmente quer o N+1: converte com prioridade."""
    with _lock:
        meta = _load(book_id)
        st = meta.get("settings")
        nxt = next((c for c in meta["chapters"] if c["index"] == index + 1), None)
        if not st or not nxt or nxt["status"] not in ("idle", "failed", "canceled", "queued"):
            return {"queued": None}
        for c in meta["chapters"]:
            if c["index"] == nxt["index"]:
                c.update(status="queued", progress=0, error=None)
        _save(book_id, meta)
    _cancel.discard(book_id)
    _jobs.put((0, next(_seq), book_id, [nxt["index"]], st["voice"], st["speed"], st.get("lang", "pt-BR")))
    return {"queued": nxt["index"]}


@app.get("/api/books/{book_id}/download")
def download_zip(book_id: str):
    d = _dir(book_id)
    meta = _load(book_id)
    ready = [c for c in meta["chapters"] if c["status"] == "done" and (d / f"{c['index']:02d}.mp3").exists()]
    if not ready:
        raise HTTPException(404, "nenhum capítulo pronto")
    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)  # noqa: SIM115
    tmp.close()
    with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_STORED) as z:  # mp3 já é comprimido
        for c in ready:
            z.write(d / f"{c['index']:02d}.mp3", f"{c['index']:02d} - {_safe(c['title'])}.mp3")
    return FileResponse(tmp.name, media_type="application/zip", filename=f"{_safe(meta['title'])}.zip",
                        background=BackgroundTask(os.unlink, tmp.name))


@app.delete("/api/books/{book_id}")
def delete_book(book_id: str):
    shutil.rmtree(_dir(book_id))
    return {"ok": True}


app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")


def main() -> None:
    import uvicorn
    from dotenv import load_dotenv

    load_dotenv()
    uvicorn.run("audiopdf.web.app:app", host="127.0.0.1", port=int(os.environ.get("PORT", "8000")))
