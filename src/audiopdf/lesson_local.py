"""Roteiro de aula SEM IA (custo zero): escolhe as frases mais representativas de cada trecho do capítulo,
usa os títulos do próprio livro como títulos de cena e monta as perguntas por lacunas (cloze).
Não reescreve nem explica: é o modo econômico, com o mesmo formato do vídeo-aula com LLM."""
import re
from collections import Counter

from .lesson import blocks
from .summarize import _words

SCENE_CHARS, MAX_SCENES = 4500, 10
_SENT = re.compile(r"(?<=[.!?…])\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ“\"(])")
_CUE = re.compile(r"\b(é|são|define|definimos|chamamos|denominamos|significa|consiste|chamado|chamada|is|are|defined|called|means)\b", re.IGNORECASE)
_EXAMPLE = re.compile(r"\b(por exemplo|exemplo|for example|for instance)\b", re.IGNORECASE)
TEXTS = {
    "pt": {"intro": "Nesta aula sobre {title}, você vai ver: {agenda}.", "recap": "Resumindo: {items}.", "cloze": "Complete a frase",
           "main": "Qual é a ideia principal de {scene}?", "scene": "Trecho", "and": "e"},
    "en": {"intro": "In this lesson on {title}, you will see: {agenda}.", "recap": "To sum up: {items}.", "cloze": "Complete the sentence",
           "main": "What is the main idea of {scene}?", "scene": "Part", "and": "and"},
}
BLANK = "_____"
_WEAK_START = re.compile(r"^(tal|essa|esse|essas|esses|isso|assim|portanto|al[ée]m disso|em (segundo|terceiro) lugar|por outro lado|por exemplo|ent[ãa]o|mas|por[ée]m|contudo|"
                         r"this|these|that|thus|however|also|then|but)\b", re.IGNORECASE)
_EXERCISE_HEAD = re.compile(r"^(exerc[ií]cios?|problemas?|exercises?|problems?)$", re.IGNORECASE)


def _exercise_flags(paragraphs: list[str]) -> list[bool]:
    """Marca parágrafos das seções de exercícios/problemas (perguntas e comandos não servem de tópico)."""
    flags, skip = [], False
    for p in paragraphs:
        q = p.strip()
        if _heading(q) and _EXERCISE_HEAD.match(q):
            skip = True
        elif skip and _heading(q) and not _NOT_TITLE.match(q) and not re.fullmatch(r"[\d.\s]+", q) and len(q) > 12:
            skip = False  # título da próxima seção
        flags.append(skip)
    return flags


_NOT_TITLE = re.compile(r"^(\d+(\.\d+)*\s*[-–]\s*\d+\s*\*?|exerc[ií]cios?|problemas?|exercises?|problems?|notas? do cap[ií]tulo|chapter notes)$", re.IGNORECASE)


def _heading(p: str) -> bool:
    p = p.strip()
    return len(p) < 80 and not p.endswith((".", "!", "?", ":", ";", ",")) and (p[:1].isupper() or p[:1].isdigit())


def _title_at(paragraphs: list[str], j: int) -> str:
    p = " ".join(paragraphs[j].split())
    if re.fullmatch(r"[\d.]+", p) and j + 1 < len(paragraphs) and len(paragraphs[j + 1]) < 80:
        p = f"{p} {paragraphs[j + 1]}"  # "2.2" + "Análise de algoritmos"
    return p.capitalize() if p.isupper() else p


def _scene_title(paragraphs: list[str], idxs: list[int], used: set[str]) -> str | None:
    """Primeiro título do livro ainda não usado dentro do trecho; senão o mais próximo antes dele."""
    inside = [j for j in range(idxs[0], idxs[-1] + 1) if _heading(paragraphs[j])]
    before = [j for j in range(idxs[0] - 1, -1, -1) if _heading(paragraphs[j])][:6]
    near = [j for j in before if j >= idxs[0] - 3]  # título logo antes do trecho é o dele
    for j in near + inside + before:
        title = _title_at(paragraphs, j)
        if title and title not in used and not _NOT_TITLE.match(title) and not re.fullmatch(r"[\d.\s]+", title):
            return title
    return None


def shorten(s: str, limit: int = 110) -> str:
    s = " ".join(s.split())
    if len(s) <= limit:
        return s
    cut = max((s.rfind(c, 0, limit) for c in ",;:—–"), default=-1)
    if cut < 50:
        cut = s.rfind(" ", 0, limit)
    return s[:cut].rstrip(" ,;:—–") + "…"


def _join(items: list[str], word: str) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + f" {word} " + items[-1]


def build_local_lesson(title: str, paragraphs: list[str], lang_code: str = "pt") -> dict:
    t = TEXTS.get(lang_code, TEXTS["en"])
    tf = Counter(w for p in paragraphs for w in _words(p))
    skipped = _exercise_flags(paragraphs)
    body_idx = [i for i, p in enumerate(paragraphs) if not _heading(p) and not skipped[i]]
    groups = blocks([paragraphs[i] for i in body_idx], SCENE_CHARS, MAX_SCENES)
    scenes: list[dict] = []
    used: set[str] = set()
    for n, g in enumerate(groups):
        idxs = [body_idx[k] for k in g]
        sents = []  # (frase, parágrafo, pontuação)
        for i in idxs:
            for s in _SENT.split(paragraphs[i]):
                ws = set(_words(s))
                if len(s) < 40 or not ws:
                    continue
                score = sum(tf[w] for w in ws) / (len(ws) + 5) ** 0.6
                score *= 0.6 if len(s) > 220 else 1.0
                score *= 0.5 if sum(not (c.isalnum() or c.isspace() or c in ".,;:!?()-–“”\"'") for c in s) > 0.06 * len(s) else 1.0  # fórmulas e símbolos
                score *= 1.25 if _CUE.search(s[:90]) else 1.0
                score *= 0.5 if _WEAK_START.match(s) else 1.0  # depende do contexto anterior
                score *= 0.4 if s.rstrip().endswith("?") else 1.0
                sents.append((s, i, score))
        if not sents:
            continue
        top = sorted(sorted(sents, key=lambda x: -x[2])[:4], key=lambda x: (x[1], sents.index(x)))
        narration = ""
        for s, _, _ in top:
            if narration and len(narration) + len(s) > 760:
                break
            narration = f"{narration} {s}".strip()
        title_n = _scene_title(paragraphs, idxs, used) or f"{t['scene']} {n + 1}"
        used.add(title_n)
        ex = next((shorten(s, 150) for s, _, _ in sents if _EXAMPLE.search(s)), None)
        scenes.append({"title": title_n, "bullets": [shorten(s) for s, _, _ in top], "narration": narration,
                       "refs": [max(top, key=lambda x: x[2])[1]], "example": ex, "_cands": [x[0] for x in top if len(x[0]) <= 200]})
    if not scenes:
        raise ValueError("texto insuficiente para montar a aula")
    titles = [s["title"] for s in scenes][:6]
    recap = [s["bullets"][0] for s in scenes[:5]]
    quiz = []
    for k in range(min(3, len(scenes))):
        sc = scenes[k * len(scenes) // min(3, len(scenes))]
        sent, words = "", []
        for cand in sc["_cands"]:  # primeira frase curta que tenha um termo-chave para esconder
            words = [w for w in dict.fromkeys(re.findall(r"[^\W\d_]{6,}", cand)) if tf[w.lower()] >= 2]
            if words:
                sent = cand
                break
        if words:
            term = max(words, key=lambda w: (tf[w.lower()], len(w)))
            blank = re.sub(rf"\b{re.escape(term)}\b", BLANK, sent, count=1)
            quiz.append({"q": f"{t['cloze']}: {shorten(blank, 200)}", "q_say": f"{t['cloze']}. " + shorten(blank, 200).replace(BLANK, " ... "),
                         "a": f"{term}. {shorten(sent, 150)}"})
        else:
            quiz.append({"q": t["main"].format(scene=sc["title"]), "a": sc["bullets"][0]})
    for s in scenes:
        s.pop("_cands")
    return {"title": title, "lang": lang_code, "model": "extrativo (sem IA)",
            "intro": t["intro"].format(title=title, agenda=_join(titles, t["and"])), "scenes": scenes, "recap": recap,
            "recap_narration": t["recap"].format(items="; ".join(recap)), "quiz": quiz}
