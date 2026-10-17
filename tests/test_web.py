import io
import json
import shutil
import time
import zipfile
from typing import ClassVar

import numpy as np
import pymupdf
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg ausente")

def page_text(n: int) -> str:
    # cada frase é única: o limpador não pode confundir o corpo com cabeçalho/rodapé repetido
    return " ".join(
        f"A programação dinâmica número {n}.{i} é uma técnica poderosa para resolver problemas de otimização "
        f"e o subproblema {n * 100 + i} é resolvido uma única vez."
        for i in range(8)
    )


class FakeTTS:
    max_chars = 400
    audio_ext = "wav"
    default_voice = "pf_dora"
    calls: ClassVar[list[str]] = []

    def synthesize(self, text, voice, speed=1.0, pause_s=0.25):
        FakeTTS.calls.append(voice)
        buf = io.BytesIO()
        tone = 0.3 * np.sin(2 * np.pi * 440 * np.arange(24000) / 24000)  # 1 s: o LAME falha em silêncio curtíssimo
        sf.write(buf, tone.astype("float32"), 24000, format="WAV", subtype="PCM_16")
        return buf.getvalue()


class FakeTranslator:
    def translate(self, text, src, tgt, on_progress=None):
        if on_progress:
            on_progress(1.0)
        return f"[{src}->{tgt}] {text}"


@pytest.fixture(scope="module")
def client():
    from audiopdf.web import app as web

    web._provider = lambda: FakeTTS()
    web.get_translator = lambda *_: FakeTranslator()
    return TestClient(web.app)


def make_pdf(chapters=2, pages_each=2) -> bytes:
    doc = pymupdf.open()
    toc = []
    for c in range(chapters):
        for p in range(pages_each):
            page = doc.new_page()
            page.insert_textbox((50, 60, 540, 780), page_text(len(doc)), fontsize=11)
            if p == 0:
                toc.append([1, f"Capitulo {c + 1}", len(doc)])
    doc.set_toc(toc)
    return doc.tobytes()


def upload(client, data: bytes, name="livro.pdf"):
    return client.post("/api/books", files={"file": (name, data, "application/pdf")})


def wait_done(client, book_id, indices, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        meta = client.get(f"/api/books/{book_id}").json()
        st = {c["index"]: c["status"] for c in meta["chapters"] if c["index"] in indices}
        if all(v in ("done", "failed") for v in st.values()):
            return meta
        time.sleep(0.2)
    raise AssertionError(f"timeout: {st}")


def test_rejects_non_pdf(client):
    r = upload(client, b"isto nao e um pdf", "x.pdf")
    assert r.status_code == 400


def test_upload_analysis_detects_language_and_chapters(client):
    r = upload(client, make_pdf())
    assert r.status_code == 200
    meta = r.json()
    assert meta["language"] == "pt"
    assert [c["title"] for c in meta["chapters"]] == ["Capitulo 1", "Capitulo 2"]
    assert any(b["id"] == meta["id"] for b in client.get("/api/books").json())


def test_convert_same_language_then_download(client):
    book = upload(client, make_pdf()).json()
    r = client.post(f"/api/books/{book['id']}/jobs", json={"chapters": [1, 2], "voice": "pf_dora"})
    assert r.status_code == 200
    meta = wait_done(client, book["id"], {1, 2})
    assert [c["status"] for c in meta["chapters"]] == ["done", "done"]
    assert client.get(f"/api/books/{book['id']}/audio/1").status_code == 200
    assert client.get(f"/api/books/{book['id']}/audio/1", headers={"Range": "bytes=0-9"}).status_code == 206
    dl = client.get(f"/api/books/{book['id']}/audio/1?download=1")
    assert "attachment" in dl.headers["content-disposition"]
    assert all(c["duration"] and c["duration"] > 0 for c in meta["chapters"])  # ffprobe grava a duração
    summary = next(b for b in client.get("/api/books").json() if b["id"] == book["id"])
    assert summary["duration"] > 0 and summary["done"] == 2
    z = zipfile.ZipFile(io.BytesIO(client.get(f"/api/books/{book['id']}/download").content))
    assert len(z.namelist()) == 2 and z.namelist()[0].startswith("01 - ")


def test_voice_must_match_language(client):
    book = upload(client, make_pdf()).json()
    r = client.post(f"/api/books/{book['id']}/jobs",
                    json={"chapters": [1], "voice": "pf_dora", "target_language": "en-US"})
    assert r.status_code == 400


def test_translation_path_uses_english_voice_and_caches(client):
    book = upload(client, make_pdf()).json()
    FakeTTS.calls.clear()
    r = client.post(f"/api/books/{book['id']}/jobs",
                    json={"chapters": [1], "voice": "af_heart", "target_language": "en-US"})
    assert r.status_code == 200
    meta = wait_done(client, book["id"], {1})
    assert meta["chapters"][0]["status"] == "done" and meta["chapters"][0]["lang"] == "en-US"
    assert set(FakeTTS.calls) == {"af_heart"}
    from audiopdf.web import app as web
    cached = web.DATA / "books" / book["id"] / "translated" / "argos-en" / "01.json"
    assert cached.exists() and "[pt->en]" in cached.read_text()


def test_changing_voice_regenerates_done_chapter(client):
    book = upload(client, make_pdf()).json()
    body = {"chapters": [1], "voice": "pf_dora"}
    client.post(f"/api/books/{book['id']}/jobs", json=body)
    wait_done(client, book["id"], {1})
    FakeTTS.calls.clear()
    client.post(f"/api/books/{book['id']}/jobs", json={**body, "voice": "pm_alex"})
    meta = wait_done(client, book["id"], {1})
    assert meta["chapters"][0]["voice"] == "pm_alex" and "pm_alex" in FakeTTS.calls


def test_prefetch_queues_next_chapter(client):
    book = upload(client, make_pdf(chapters=3)).json()
    client.post(f"/api/books/{book['id']}/jobs", json={"chapters": [1], "voice": "pf_dora"})
    wait_done(client, book["id"], {1})
    assert client.post(f"/api/books/{book['id']}/prefetch/1").json() == {"queued": 2}
    meta = wait_done(client, book["id"], {2})
    assert meta["chapters"][1]["status"] == "done"


def test_delete_book_and_unknown_id(client):
    book = upload(client, make_pdf()).json()
    assert client.delete(f"/api/books/{book['id']}").status_code == 200
    assert client.get(f"/api/books/{book['id']}").status_code == 404
    assert client.get("/api/books/../../etc/passwd").status_code in (404, 422)
    assert client.get("/api/books/" + "0" * 32).status_code == 404


def test_download_without_ready_chapters_is_404(client):
    book = upload(client, make_pdf()).json()
    assert client.get(f"/api/books/{book['id']}/download").status_code == 404


def test_translators_endpoint_and_missing_key_rejected(client, monkeypatch):
    monkeypatch.delenv("DEEPL_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert client.get("/api/translators").json() == ["argos"]
    book = upload(client, make_pdf()).json()
    r = client.post(f"/api/books/{book['id']}/jobs",
                    json={"chapters": [1], "voice": "af_heart", "target_language": "en-US", "translator": "deepl"})
    assert r.status_code == 400 and "indisponível" in r.json()["detail"]


def test_reanalyze_keeps_done_audio_and_blocks_while_busy(client):
    book = upload(client, make_pdf()).json()
    client.post(f"/api/books/{book['id']}/jobs", json={"chapters": [1], "voice": "pf_dora"})
    wait_done(client, book["id"], {1})
    r = client.post(f"/api/books/{book['id']}/reanalyze")
    assert r.status_code == 200
    chapters = r.json()["chapters"]
    assert chapters[0]["status"] == "done" and chapters[1]["status"] == "idle"
    assert client.get(f"/api/books/{book['id']}/audio/1").status_code == 200


def test_sync_and_page_image_follow_along(client):
    book = upload(client, make_pdf()).json()
    assert book["chapters"][0]["page_start"] == 0 and book["chapters"][1]["page_start"] == 2
    client.post(f"/api/books/{book['id']}/jobs", json={"chapters": [1], "voice": "pf_dora"})
    wait_done(client, book["id"], {1})
    sync = client.get(f"/api/books/{book['id']}/chapters/1/sync").json()
    tl = sync["timeline"]
    assert sync["approx"] is False and tl[0]["p"] == -1 and all(e["d"] > 0 for e in tl)
    assert all(b["t"] >= a["t"] + a["d"] - 0.01 for a, b in zip(tl, tl[1:], strict=False))  # tempos encadeados
    assert max(e["p"] for e in tl) == len(sync["paragraphs"]) - 1
    assert all(p["rects"] and p["rects"][0][0] in (1, 2) for p in sync["paragraphs"])
    img = client.get(f"/api/books/{book['id']}/pages/1")
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg" and img.content[:2] == b"\xff\xd8"
    assert client.get(f"/api/books/{book['id']}/pages/99").status_code == 404
    # sem marcação (áudio antigo): linha do tempo estimada, marcada como aproximada
    from audiopdf.web import app as web
    (web.DATA / "books" / book["id"] / "01.timeline.json").unlink()
    approx = client.get(f"/api/books/{book['id']}/chapters/1/sync").json()
    assert approx["approx"] is True and approx["timeline"][0]["p"] == -1
    assert abs(approx["timeline"][-1]["t"] + approx["timeline"][-1]["d"] - sync_total(tl)) < 3


def sync_total(tl):
    return tl[-1]["t"] + tl[-1]["d"]


def test_sync_translated_chapter_keeps_pdf_regions(client):
    book = upload(client, make_pdf()).json()
    client.post(f"/api/books/{book['id']}/jobs",
                json={"chapters": [1], "voice": "af_heart", "target_language": "en-US"})
    wait_done(client, book["id"], {1})
    sync = client.get(f"/api/books/{book['id']}/chapters/1/sync").json()
    assert sync["translated"] is True and sync["paragraphs"][0]["text"].startswith("[pt->en]")
    assert all(p["rects"] for p in sync["paragraphs"])  # texto traduzido ↔ regiões do PDF original
    assert sync["timeline"][0]["p"] == -1 and sync["approx"] is False


def wait_video(client, book_id, idx, kind, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        v = (client.get(f"/api/books/{book_id}").json()["chapters"][idx - 1].get("videos") or {}).get(kind) or {}
        if v.get("status") in ("done", "failed"):
            return v
        time.sleep(0.3)
    raise AssertionError("timeout no vídeo")


def test_video_reading_and_summary_flow(client):
    book = upload(client, make_pdf()).json()
    bid = book["id"]
    r = client.post(f"/api/books/{bid}/chapters/1/video", json={"kind": "leitura"})
    assert r.status_code == 409  # precisa do áudio do capítulo
    client.post(f"/api/books/{bid}/jobs", json={"chapters": [1], "voice": "pf_dora"})
    wait_done(client, bid, {1})
    assert client.post(f"/api/books/{bid}/chapters/1/video", json={"kind": "xyz"}).status_code == 422
    for kind in ("leitura", "resumo"):
        assert client.post(f"/api/books/{bid}/chapters/1/video", json={"kind": kind}).status_code == 200
        v = wait_video(client, bid, 1, kind)
        assert v["status"] == "done" and v["duration"] > 0 and v["size"] > 1000, v
        res = client.get(f"/api/books/{bid}/chapters/1/video/{kind}")
        assert res.status_code == 200 and res.headers["content-type"] == "video/mp4"
        assert client.get(f"/api/books/{bid}/chapters/1/video/{kind}", headers={"Range": "bytes=0-99"}).status_code == 206
        assert "attachment" in client.get(f"/api/books/{bid}/chapters/1/video/{kind}?download=1").headers["content-disposition"]
    assert client.delete(f"/api/books/{bid}/chapters/1/video/leitura").status_code == 200
    assert client.get(f"/api/books/{bid}/chapters/1/video/leitura").status_code == 404
    assert client.get(f"/api/books/{bid}/chapters/1/video/outro").status_code == 404
    # trocar a voz refaz o áudio e descarta os vídeos que dependiam dele
    client.post(f"/api/books/{bid}/jobs", json={"chapters": [1], "voice": "pm_alex"})
    wait_done(client, bid, {1})
    assert client.get(f"/api/books/{bid}/chapters/1/video/resumo").status_code == 404


class FakeLLM:
    model = "fake-llm"
    calls = 0

    def chat(self, system, user, max_tokens=0, temperature=0):
        import re
        FakeLLM.calls += 1
        if "Section" in user:
            nums = re.findall(r"\[(\d+)\]", user)
            return json.dumps({"title": "Cena de teste", "bullets": ["ponto um", "ponto dois", "ponto três"],
                               "narration": "Esta é uma explicação de teste bem longa para a cena. " * 3, "refs": [int(nums[0]), 999], "example": "um exemplo"})
        return json.dumps({"intro": "Bem-vindo à aula de teste, vamos aprender.", "recap": ["r1", "r2"],
                           "recap_narration": "Resumindo a aula de teste que fizemos aqui.", "quiz": [{"q": "P1?", "a": "R1"}, {"q": "P2?", "a": "R2"}]})


def test_lesson_video_flow_caches_script_and_reports_llm_errors(client, monkeypatch):
    from audiopdf.llm import LLMError
    from audiopdf.web import app as web

    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    assert client.get("/api/capabilities").json()["llm"] is False
    monkeypatch.setenv("LLM_API_KEY", "x")
    assert client.get("/api/capabilities").json()["llm"] is True

    book = upload(client, make_pdf()).json()
    bid = book["id"]
    client.post(f"/api/books/{bid}/jobs", json={"chapters": [1], "voice": "pf_dora"})
    wait_done(client, bid, {1})

    # provedor sem créditos: o erro chega à interface com a mensagem original
    def broke():
        raise LLMError("sem créditos na conta (HTTP 402)")

    monkeypatch.setattr(web, "LLM", broke)
    assert client.post(f"/api/books/{bid}/chapters/1/video", json={"kind": "aula"}).status_code == 200
    failed = wait_video(client, bid, 1, "aula")
    assert failed["status"] == "failed" and "sem créditos" in failed["error"]

    # com LLM: gera o vídeo e guarda o roteiro; gerar de novo não chama o LLM outra vez
    monkeypatch.setattr(web, "LLM", lambda: FakeLLM())
    FakeLLM.calls = 0
    client.post(f"/api/books/{bid}/chapters/1/video", json={"kind": "aula"})
    ok = wait_video(client, bid, 1, "aula", timeout=120)
    assert ok["status"] == "done" and ok["duration"] > 5 and ok["model"] == "fake-llm", ok
    first_calls = FakeLLM.calls
    assert first_calls >= 2
    lesson_file = web.DATA / "books" / bid / "01.aula.json"
    assert json.loads(lesson_file.read_text())["scenes"][0]["refs"]
    assert client.delete(f"/api/books/{bid}/chapters/1/video/aula").status_code == 200
    assert lesson_file.exists()  # o roteiro (pago) é mantido
    client.post(f"/api/books/{bid}/chapters/1/video", json={"kind": "aula"})
    assert wait_video(client, bid, 1, "aula", timeout=120)["status"] == "done"
    assert FakeLLM.calls == first_calls
    assert client.get(f"/api/books/{bid}/chapters/1/video/aula").headers["content-type"] == "video/mp4"


def test_deleting_one_video_kind_keeps_the_others(client):
    book = upload(client, make_pdf()).json()
    bid = book["id"]
    client.post(f"/api/books/{bid}/jobs", json={"chapters": [1], "voice": "pf_dora"})
    wait_done(client, bid, {1})
    for kind in ("leitura", "resumo"):
        client.post(f"/api/books/{bid}/chapters/1/video", json={"kind": kind})
        assert wait_video(client, bid, 1, kind)["status"] == "done"
    client.delete(f"/api/books/{bid}/chapters/1/video/resumo")
    assert client.get(f"/api/books/{bid}/chapters/1/video/leitura").status_code == 200  # não foi apagado junto
    assert client.get(f"/api/books/{bid}/chapters/1/video/resumo").status_code == 404
