import shutil
import types

import httpx
import pymupdf
import pytest

from audiopdf.chunk import chunk_paragraphs
from audiopdf.extract import extract
from audiopdf.translate.claude import ClaudeTranslator
from audiopdf.translate.claude import _blocks as claude_blocks
from audiopdf.translate.deepl import DeepLTranslator, _batches

TEXT = ("A programação dinâmica resolve problemas de otimização dividindo-os em subproblemas. "
        "Cada subproblema é resolvido apenas uma vez e a solução é armazenada para reutilização.")


def _tess_has(lang: str) -> bool:
    import subprocess
    if not shutil.which("tesseract"):
        return False
    out = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True, check=False)
    return lang in out.stdout.split()


def _scanned_pdf() -> bytes:
    """PDF só com imagem (sem camada de texto), como um livro escaneado."""
    src = pymupdf.open()
    src.new_page().insert_textbox((50, 80, 540, 400), TEXT, fontsize=16)
    pix = src[0].get_pixmap(dpi=200)
    out = pymupdf.open()
    out.new_page(width=pix.width, height=pix.height).insert_image(pymupdf.Rect(0, 0, pix.width, pix.height), pixmap=pix)
    return out.tobytes()


@pytest.mark.skipif(not _tess_has("por"), reason="Tesseract com idioma 'por' ausente")
def test_ocr_recovers_text_from_scanned_pdf(tmp_path):
    f = tmp_path / "scan.pdf"
    f.write_bytes(_scanned_pdf())
    content = extract(str(f))
    assert content.ocr_pages == [0] and content.scanned_pages == []
    words = TEXT.lower().replace(".", "").replace(",", "").split()
    got = content.pages[0].lower()
    assert sum(w in got for w in words) / len(words) > 0.85


def test_ocr_disabled_leaves_page_flagged(tmp_path):
    f = tmp_path / "scan.pdf"
    f.write_bytes(_scanned_pdf())
    content = extract(str(f), ocr=False)
    assert content.scanned_pages == [0] and content.ocr_pages == []


def test_chunk_paragraphs_marks_paragraph_ends_and_starts_short():
    text = "Título.\n\n" + ("Frase um. " * 100).strip() + "\n\nÚltimo parágrafo."
    chunks = chunk_paragraphs(text, max_chars=1000)
    assert chunks[0] == ("Título.", True)
    assert chunks[-1] == ("Último parágrafo.", True)
    assert all(len(c) <= 350 for c, _ in chunks[:2])
    long_para = [e for _, e in chunks[1:-1]]
    assert long_para[-1] is True and not all(long_para[:-1])  # só o último trecho encerra o parágrafo


def test_deepl_translates_paragraphs_and_retries():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429)
        body = __import__("json").loads(request.content)
        assert body["source_lang"] == "PT" and body["target_lang"] == "EN-US"
        assert request.headers["authorization"] == "DeepL-Auth-Key k:fx"
        assert request.url.host == "api-free.deepl.com"
        return httpx.Response(200, json={"translations": [{"text": t.upper()} for t in body["text"]]})

    tr = DeepLTranslator(client=httpx.Client(transport=httpx.MockTransport(handler)), key="k:fx")
    import audiopdf.translate.deepl as mod
    mod.time.sleep = lambda s: None
    assert tr.translate("um\n\ndois", "pt", "en") == "UM\n\nDOIS"
    assert calls["n"] == 2  # 1 falha 429 + 1 sucesso


def test_deepl_batches_respect_limits():
    batches = _batches(["x"] * 95)
    assert [len(b) for b in batches] == [40, 40, 15]


def test_claude_translator_preserves_blocks_and_passes_context():
    seen = []

    def create(**kw):
        seen.append(kw["messages"][0]["content"])
        return types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text=f"T{len(seen)}")])

    client = types.SimpleNamespace(messages=types.SimpleNamespace(create=create))
    tr = ClaudeTranslator(client=client, model="m")
    text = "\n\n".join("p" * 1400 for _ in range(4))  # 2 blocos de ~2800
    assert len(claude_blocks(text)) == 2
    assert tr.translate(text, "pt", "en") == "T1\n\nT2"
    assert "previous_translation_for_context_only" in seen[1] and "T1" in seen[1]
    assert tr.translate("x", "pt", "pt") == "x"


def test_chunk_paragraphs_drops_chunks_without_speech():
    chunks = chunk_paragraphs("Título.\n\n•\n\nTexto real.\n\n—\n\n6.1")
    assert [c for c, _ in chunks] == ["Título.", "Texto real.", "6.1"]
