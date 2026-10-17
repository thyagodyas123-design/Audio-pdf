import json

import httpx
import pytest

import audiopdf.llm as llm_mod
from audiopdf.lesson import blocks, build_lesson, validate_final, validate_scene
from audiopdf.lesson_video import lesson_segments, narration_items
from audiopdf.llm import LLM, LLMError, extract_json


def _llm(handler, **kw):
    return LLM(client=httpx.Client(transport=httpx.MockTransport(handler)), key="k", base_url="https://x/v1", model="m", **kw)


def _ok(text):
    return httpx.Response(200, json={"choices": [{"message": {"content": text}}]})


def test_extract_json_handles_fences_and_surrounding_prose():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Claro! Aqui está: {"a": {"b": 2}} Espero ajudar.') == {"a": {"b": 2}}
    with pytest.raises(ValueError):
        extract_json("sem json")


def test_llm_error_messages_are_actionable():
    with pytest.raises(LLMError, match="sem créditos"):
        _llm(lambda r: httpx.Response(402, json={"error": {"message": "Insufficient account funds"}})).chat("s", "u")
    with pytest.raises(LLMError, match="recusou a chave ou o modelo 'm'"):
        _llm(lambda r: httpx.Response(403, json={"error": {"message": "free tier"}})).chat("s", "u")


def test_llm_retries_with_backoff_then_succeeds(monkeypatch):
    monkeypatch.setattr(llm_mod.time, "sleep", lambda s: None)
    calls = []

    def handler(req):
        calls.append(json.loads(req.content))
        return httpx.Response(429) if len(calls) < 3 else _ok("oi")

    assert _llm(handler).chat("s", "u") == "oi" and len(calls) == 3
    assert calls[0]["model"] == "m" and calls[0]["messages"][0]["role"] == "system"


def test_llm_requires_a_key(monkeypatch):
    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with pytest.raises(LLMError, match="chave"):
        LLM()


def test_blocks_cover_every_paragraph_once_and_respect_scene_cap():
    paras = [("palavra " * 100).strip() for _ in range(60)]  # ~48 mil caracteres
    groups = blocks(paras, target=2000, max_scenes=8)
    assert len(groups) <= 8
    assert [i for g in groups for i in g] == list(range(60))


class ScriptedLLM:
    model = "roteirizado"

    def __init__(self, replies):
        self.replies, self.calls = list(replies), 0

    def chat(self, system, user, max_tokens=0, temperature=0):
        self.calls += 1
        return self.replies.pop(0)


SCENE = {"title": "Cena", "bullets": ["a", "b", "c"], "narration": "Uma explicação didática bem completa do trecho.", "refs": [1, 99, "x"], "example": None}
FINAL = {"intro": "Bem-vindo à aula, vamos começar agora.", "recap": ["um", "dois"], "recap_narration": "Resumindo o que vimos nesta aula.",
         "quiz": [{"q": "P?", "a": "R"}, {"q": "", "a": "ignorada"}]}


def test_build_lesson_filters_invalid_refs_and_retries_bad_json():
    llm = ScriptedLLM(["isto não é json", json.dumps(SCENE), json.dumps(FINAL)])
    lesson = build_lesson(llm, "Cap", ["p0", "p1", "p2"], "pt")
    assert llm.calls == 3  # 1 resposta inválida + 1 cena + 1 final
    assert lesson["scenes"][0]["refs"] == [1] and lesson["model"] == "roteirizado"
    assert len(lesson["quiz"]) == 1 and lesson["lang"] == "pt"


def test_build_lesson_gives_up_after_two_invalid_answers():
    with pytest.raises(LLMError, match="inválida"):
        build_lesson(ScriptedLLM(["{}", "{}"]), "Cap", ["p0"], "pt")


def test_validators_reject_thin_content():
    with pytest.raises(ValueError):
        validate_scene({"title": "t", "bullets": ["a"], "narration": "curta", "refs": []}, [0])
    with pytest.raises(ValueError):
        validate_final({"intro": "x", "recap": [], "recap_narration": "", "quiz": []})


def _lesson():
    sc = lambda t, b, ex: {"title": t, "bullets": b, "narration": "n" * 60, "refs": [0], "example": ex}
    return {"title": "Cap", "lang": "pt", "intro": "i" * 30, "scenes": [sc("A", ["1", "2", "3"], "ex"), sc("B", ["1", "2"], None)],
            "recap": ["r1", "r2"], "recap_narration": "r" * 30, "quiz": [{"q": "P1", "a": "R1"}, {"q": "P2", "a": "R2"}]}


def test_lesson_segments_reveal_bullets_and_keep_total_time():
    lesson = _lesson()
    items = narration_items(lesson)
    keys = [k for k, _, _ in items]
    assert keys == ["intro", "scene:0", "scene:1", "recap", "q:0", "a:0", "q:1", "a:1"]
    assert "Pergunta 1" in items[4][1] and items[5][1].startswith("Resposta.")
    durations = {k: 4.0 + i for i, k in enumerate(keys)}
    paragraphs = [{"text": "p", "rects": [[7, 0.1, 0.1, 0.9, 0.2]]}]
    segs = lesson_segments(lesson, durations, paragraphs, page_start=3)
    assert abs(sum(s["d"] for s in segs) - sum(durations.values())) < 1e-6
    assert [s["kind"] for s in segs].count("scene") == 3 + 2  # um quadro por tópico revelado
    scene_a = [s for s in segs if s["kind"] == "scene" and s["title"] == "A"]
    assert [s["shown"] for s in scene_a] == [1, 2, 3] and scene_a[-1]["note"] == "ex" and scene_a[0]["page"] == 7
    assert [s["kind"] for s in segs[-4:]] == ["quiz_q", "quiz_a", "quiz_q", "quiz_a"]
    assert segs[-1]["note"] == "R2" and segs[-2]["note"] is None
