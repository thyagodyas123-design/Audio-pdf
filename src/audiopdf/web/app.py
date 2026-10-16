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

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from ..audio import concat_normalize, to_mp3
from ..chapters import split_chapters
from ..chunk import chunk_paragraphs
from ..clean import clean_pages
from ..extract import extract
from ..lang import detect
from ..translate import available_translators, get_translator
from ..tts import get_provider

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
    chunks = chunk_paragraphs(f"{title}.\n\n{body}", tts.max_chars)
    parts_dir = d / f"{idx:02d}.parts"
    shutil.rmtree(parts_dir, ignore_errors=True)
    parts_dir.mkdir()
    audio_parts = []
    for i, (ch, para_end) in enumerate(chunks):
        if book_id in _cancel:
            raise InterruptedError
        pause = 1.0 if i == 0 else (0.7 if para_end else 0.25)  # título > parágrafo > frase longa
        data = tts.synthesize(ch, voice, speed, pause_s=pause)
        audio_parts.append(data)
        to_mp3(data, tts.audio_ext, parts_dir / f"{i:04d}.mp3")
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
        pending = [c["index"] for c in meta["chapters"] if c["status"] in ("running", "queued", "translating")]
        if not pending:
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
    }


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
    return {"index": c.index, "title": c.title, "chars": len(c.text), "status": "idle", "progress": 0, "error": None}


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
        shutil.rmtree(d / "translated", ignore_errors=True)  # o texto mudou: traduções antigas não valem
        meta.update(chapters=new, pages=len(content.pages), scanned_pages=len(content.scanned_pages),
                    ocr_pages=len(content.ocr_pages), language=detect(" ".join(c.text[:2000] for c in chapters[:6])))
        _save(book_id, meta)
        return meta


@app.get("/api/books/{book_id}")
def get_book(book_id: str):
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
