"""Resumo extrativo: escolhe os parágrafos mais representativos do capítulo, sem reescrever.
Mantém a ligação com o PDF (cada trecho vem de um parágrafo real). Um resumo abstrativo exigiria um LLM."""
import re
from collections import Counter

_STOP = set(["para", "como", "mais", "pela", "pelo", "pelos", "pelas", "porque", "quando", "onde", "esta", "este", "esse", "essa", "isso", "aquilo", "estes", "essas", "esses", "tambem", "também", "entre", "sobre", "sendo", "seja", "serem", "foram", "será", "ainda", "assim", "apenas", "cada", "qualquer", "todos", "todas", "toda", "todo", "muito", "muita", "outros", "outras", "outro", "outra", "mesmo", "mesma", "depois", "antes", "quanto", "desse", "dessa", "deste", "desta", "numa", "nesse", "nessa", "neste", "nesta", "ele", "ela", "eles", "elas", "that", "this", "with", "from", "have", "they", "their", "there", "which", "would", "about", "into", "than", "then", "them", "these", "those", "were", "been", "being", "also", "such", "when", "what", "where", "while", "will", "your", "more", "most", "some", "other", "only", "each", "over", "very", "just", "like"])
_SENT = re.compile(r"(?<=[.!?…])\s+")


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[^\W\d_]{4,}", text.lower()) if w not in _STOP]


def _excerpt(par: str, limit: int) -> str:
    out = ""
    for s in _SENT.split(par):
        if out and len(out) + len(s) + 1 > limit:
            break
        out = f"{out} {s}".strip()
    return out


def select(paragraphs: list[str], ratio: float = 0.2, max_chars: int = 6000, min_paras: int = 3,
           excerpt_chars: int = 700, min_len: int = 80) -> list[tuple[int, str]]:
    """[(índice do parágrafo, trecho a narrar)] na ordem original, ~`ratio` do texto (teto `max_chars`)."""
    tf = Counter(w for p in paragraphs for w in _words(p))
    cands = []
    for i, p in enumerate(paragraphs):
        if len(p) < min_len:  # títulos e legendas curtas ficam de fora
            continue
        ws = set(_words(p))
        score = sum(tf[w] for w in ws) / (len(ws) + 8) ** 0.7
        cands.append((score * (1.15 if not cands else 1.0), i))
    budget = min(max_chars, ratio * sum(len(p) for p in paragraphs))
    chosen, used = [], 0
    for _, i in sorted(cands, reverse=True):
        if used >= budget and len(chosen) >= min_paras:
            break
        ex = _excerpt(paragraphs[i], excerpt_chars)
        chosen.append((i, ex))
        used += len(ex)
    return sorted(chosen)
