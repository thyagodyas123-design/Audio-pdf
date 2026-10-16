"""Divide o texto em trechos <= max_chars, sempre em fronteira de frase."""
import re

_SENT = re.compile(r"(?<=[.!?…])\s+")


def chunk_text(text: str, max_chars: int = 3000) -> list[str]:
    chunks: list[str] = []
    cur = ""
    for sent in _SENT.split(text.replace("\n\n", " \n\n ")):
        sent = sent.strip()
        if not sent:
            continue
        while len(sent) > max_chars:  # frase gigante: corta em espaço
            cut = sent.rfind(" ", 0, max_chars)
            cut = cut if cut > 0 else max_chars
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(sent[:cut])
            sent = sent[cut:].strip()
        if len(cur) + len(sent) + 1 > max_chars and cur:
            chunks.append(cur)
            cur = sent
        else:
            cur = f"{cur} {sent}".strip()
    if cur:
        chunks.append(cur)
    return chunks


def chunk_paragraphs(text: str, max_chars: int = 1000, early_max: int = 350, early_n: int = 2) -> list[tuple[str, bool]]:
    """Trechos por parágrafo: (texto, termina_parágrafo). Os primeiros trechos são curtos para o player
    começar a tocar mais cedo."""
    out: list[tuple[str, bool]] = []
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        pieces = [c for c in chunk_text(para, early_max if len(out) < early_n else max_chars) if re.search(r"\w", c)]
        out.extend((piece, j == len(pieces) - 1) for j, piece in enumerate(pieces))
    return out
