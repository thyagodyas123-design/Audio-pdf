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
