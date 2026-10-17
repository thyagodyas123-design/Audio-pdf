"""Roteiro de aula a partir de um capítulo, escrito por um LLM: cenas (tópicos + narração), resumo e perguntas.
O texto do capítulo vai ao provedor de LLM configurado; use apenas conteúdo que você pode enviar."""
from collections.abc import Callable

from .llm import LLM, LLMError, extract_json
from .summarize import select

BLOCK_CHARS = 5500
MAX_SCENES = 14
LANGS = {"pt": "Brazilian Portuguese", "en": "American English", "es": "Spanish", "fr": "French", "de": "German", "it": "Italian"}
LABELS = {  # rótulos falados e exibidos no vídeo
    "pt": {"lesson": "Aula", "agenda": "Nesta aula", "recap": "Resumo", "question": "Pergunta", "answer": "Resposta", "source": "Fonte: página"},
    "en": {"lesson": "Lesson", "agenda": "In this lesson", "recap": "Recap", "question": "Question", "answer": "Answer", "source": "Source: page"},
}
SYSTEM = (
    "You are an experienced teacher turning a book chapter into a short educational video lesson. Write in {lang}. "
    "Be accurate: use only information found in the text you are given and never invent facts. "
    "Output ONLY one JSON object, with no commentary."
)
SCENE_PROMPT = """Chapter: {title}
Section {i} of {n}. The paragraphs are numbered in brackets.

{body}

Return this JSON:
{{"title": "scene title, at most 8 words",
 "bullets": ["3 to 5 key points, each at most 14 words"],
 "narration": "70 to 130 words explaining this section the way a teacher speaks to a student: plain spoken sentences, no lists, no markdown, no symbols that are hard to read aloud",
 "refs": [numbers of the 1 to 3 paragraphs that best support this scene],
 "example": "one short concrete example from the text (at most 25 words) or null"}}"""
FINAL_PROMPT = """Chapter: {title}
Scenes of the lesson:
{scenes}

Return this JSON:
{{"intro": "35 to 60 words welcoming the student and saying what they will learn in this chapter",
 "recap": ["3 to 5 bullets summarizing the chapter, each at most 14 words"],
 "recap_narration": "40 to 70 words, spoken, reviewing the main ideas",
 "quiz": [{{"q": "question that checks understanding", "a": "short answer, at most 25 words"}}, exactly 3 items]}}"""


def blocks(paragraphs: list[str], target: int = BLOCK_CHARS, max_scenes: int = MAX_SCENES) -> list[list[int]]:
    """Agrupa parágrafos consecutivos (índices) em blocos de ~`target` caracteres; no máximo `max_scenes` blocos."""
    total = sum(len(p) for p in paragraphs)
    target = max(target, -(-total // max_scenes))
    out: list[list[int]] = []
    cur: list[int] = []
    size = 0
    for i, p in enumerate(paragraphs):
        if cur and size + len(p) > target:
            out.append(cur)
            cur, size = [], 0
        cur.append(i)
        size += len(p)
    if cur:
        if out and size < 0.3 * target:  # sobra pequena: junta ao bloco anterior
            out[-1].extend(cur)
        else:
            out.append(cur)
    size_of = lambda g: sum(len(paragraphs[i]) for i in g)
    while len(out) > max_scenes:  # os limites de bloco podem passar do teto: funde os vizinhos menores
        k = min(range(len(out) - 1), key=lambda j: size_of(out[j]) + size_of(out[j + 1]))
        out[k:k + 2] = [out[k] + out[k + 1]]
    return out


def _clip(s: object, n: int) -> str:
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0] + "…"


def _list(v: object, lo: int, hi: int, n: int) -> list[str]:
    items = [_clip(x, n) for x in (v if isinstance(v, list) else []) if str(x).strip()]
    if len(items) < lo:
        raise ValueError("lista curta demais")
    return items[:hi]


def validate_scene(obj: dict, valid_refs: list[int]) -> dict:
    refs = [r for r in (obj.get("refs") or []) if isinstance(r, int) and r in valid_refs][:3]
    narration = _clip(obj.get("narration"), 1100)
    if len(narration) < 40:
        raise ValueError("narração curta demais")
    ex = obj.get("example")
    return {"title": _clip(obj.get("title"), 80) or "…", "bullets": _list(obj.get("bullets"), 2, 5, 120), "narration": narration,
            "refs": refs or valid_refs[:1], "example": _clip(ex, 200) if ex else None}


def validate_final(obj: dict) -> dict:
    quiz = [{"q": _clip(x.get("q"), 220), "a": _clip(x.get("a"), 220)} for x in (obj.get("quiz") or []) if isinstance(x, dict) and x.get("q") and x.get("a")]
    if not quiz:
        raise ValueError("sem perguntas")
    intro, rec = _clip(obj.get("intro"), 500), _clip(obj.get("recap_narration"), 600)
    if len(intro) < 20 or len(rec) < 20:
        raise ValueError("introdução/recapitulação curtas demais")
    return {"intro": intro, "recap": _list(obj.get("recap"), 2, 5, 120), "recap_narration": rec, "quiz": quiz[:3]}


def _ask(llm: LLM, lang: str, prompt: str, check: Callable[[dict], dict], max_tokens: int) -> dict:
    last: Exception | None = None
    for _ in range(2):  # uma nova tentativa se o JSON vier inválido
        text = llm.chat(SYSTEM.format(lang=lang), prompt, max_tokens=max_tokens)
        try:
            return check(extract_json(text))
        except (ValueError, TypeError, KeyError) as e:
            last = e
    raise LLMError(f"O modelo devolveu uma resposta inválida: {last}")


def build_lesson(llm: LLM, title: str, paragraphs: list[str], lang_code: str = "pt",
                 on_progress: Callable[[float], None] | None = None, budget_chars: int | None = None) -> dict:
    """`budget_chars` limita o texto enviado ao LLM (custo): acima disso, só os trechos mais representativos
    (resumo extrativo) vão ao modelo, mantendo a numeração original dos parágrafos."""
    lang = LANGS.get(lang_code, "the same language as the text")
    total = sum(len(p) for p in paragraphs)
    if budget_chars and total > budget_chars:
        picked = select(paragraphs, ratio=budget_chars / total, max_chars=budget_chars, min_paras=4, excerpt_chars=700)
    else:
        picked = list(enumerate(paragraphs))
    ids, texts = [i for i, _ in picked], [t for _, t in picked]
    groups = [[ids[k] for k in g] for g in blocks(texts)]
    by_id = dict(picked)
    scenes = []
    for k, idxs in enumerate(groups):
        body = "\n\n".join(f"[{i}] {by_id[i]}" for i in idxs)
        prompt = SCENE_PROMPT.format(title=title, i=k + 1, n=len(groups), body=body)
        scenes.append(_ask(llm, lang, prompt, lambda o, v=idxs: validate_scene(o, v), 1500))
        if on_progress:
            on_progress((k + 1) / (len(groups) + 1))
    listing = "\n".join(f"{n + 1}. {s['title']}: " + "; ".join(s["bullets"]) for n, s in enumerate(scenes))
    final = _ask(llm, lang, FINAL_PROMPT.format(title=title, scenes=listing), validate_final, 1500)
    if on_progress:
        on_progress(1.0)
    return {"title": title, "lang": lang_code, "model": llm.model, "scenes": scenes, **final}
