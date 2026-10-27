import json
import shutil
import subprocess

import pymupdf
import pytest

from audiopdf.summarize import select
from audiopdf.video import build_video, segments_from_timeline

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg ausente")

PARAS = [
    "Título curto",
    "A programação dinâmica resolve problemas de otimização dividindo-os em subproblemas sobrepostos e guardando as soluções. "
    "Cada subproblema é resolvido uma única vez, o que reduz drasticamente o tempo de execução do algoritmo.",
    "Um exemplo clássico é o cálculo de números de Fibonacci, em que a recursão ingênua repete o mesmo trabalho várias vezes. "
    "Com memorização, o tempo cai de exponencial para linear no tamanho da entrada.",
    "Texto de transição sem muito conteúdo técnico relevante para o assunto tratado neste capítulo do livro em questão.",
    "A tabela de soluções parciais é preenchida de baixo para cima, e cada célula depende apenas de células já calculadas, "
    "o que torna a análise de tempo e de espaço do algoritmo direta e previsível.",
]


def test_select_keeps_order_budget_and_skips_headings():
    out = select(PARAS, ratio=0.5, min_paras=2)
    idx = [i for i, _ in out]
    assert idx == sorted(idx) and 0 not in idx and len(out) >= 2
    assert all(text and text in PARAS[i] or PARAS[i].startswith(text[:20]) for i, text in out)
    small = select(PARAS, ratio=0.01, min_paras=1)
    assert len(small) == 1


def test_select_truncates_long_paragraph_at_sentence_boundary():
    long = " ".join(f"Frase número {i} sobre algoritmos e estruturas de dados importantes." for i in range(30))
    [(i, ex)] = select([long], ratio=1, min_paras=1, excerpt_chars=200)
    assert i == 0 and len(ex) <= 200 and ex.endswith(".")


def _fixture(tmp_path):
    doc = pymupdf.open()
    doc.new_page().insert_textbox((50, 60, 540, 200), PARAS[1], fontsize=11)
    doc.new_page().insert_textbox((50, 60, 540, 200), PARAS[2], fontsize=11)
    pdf = tmp_path / "s.pdf"
    doc.save(pdf)
    audio = tmp_path / "a.mp3"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=6", str(audio)], check=True)
    paragraphs = [{"text": PARAS[1], "rects": [[1, 0.08, 0.07, 0.92, 0.22]]}, {"text": PARAS[2], "rects": [[2, 0.08, 0.07, 0.92, 0.22]]}]
    timeline = [{"t": 0, "d": 1.0, "p": -1}, {"t": 1.0, "d": 2.0, "p": 0}, {"t": 3.0, "d": 1.0, "p": 0}, {"t": 4.0, "d": 2.0, "p": 1}]
    return pdf, audio, paragraphs, timeline


def test_segments_merge_consecutive_chunks_and_fill_missing_pages(tmp_path):
    _, _, paragraphs, timeline = _fixture(tmp_path)
    segs = segments_from_timeline(timeline, paragraphs, "Capítulo X", page_start=0)
    assert [s["p"] for s in segs] == [-1, 0, 1] and segs[1]["d"] == 3.0
    assert segs[0]["title"] and segs[0]["text"] == "Capítulo X" and segs[0]["page"] == 1  # título usa a 1ª página conhecida


def test_build_video_makes_h264_aac_matching_audio_duration(tmp_path):
    pdf, audio, paragraphs, timeline = _fixture(tmp_path)
    segs = segments_from_timeline(timeline, paragraphs, "Capítulo X", 0)
    seen = []
    out = tmp_path / "v.mp4"
    dur = build_video(pdf, audio, out, book_title="Livro", label="Capítulo 1 · X", segments=segs, on_progress=seen.append)
    info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,width,height", "-of", "json", str(out)],
                                     capture_output=True, text=True, check=True).stdout)["streams"]
    assert {(s["codec_name"]) for s in info} == {"h264", "aac"}
    assert (info[0]["width"], info[0]["height"]) == (1280, 720)
    assert abs(dur - 6.0) < 0.7
    assert seen[-1] == 1.0 and seen == sorted(seen)
    assert not list(tmp_path.glob(".*.frames"))  # quadros temporários removidos
