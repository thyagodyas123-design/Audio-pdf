"""Tradução via DeepL API (DEEPL_API_KEY; chaves do plano gratuito terminam em ':fx')."""
import os
import time
from collections.abc import Callable

import httpx

_TARGET = {"en": "EN-US", "pt": "PT-BR", "es": "ES", "fr": "FR", "de": "DE", "it": "IT"}
MAX_PARAS, MAX_CHARS = 40, 60_000  # limites de itens e de tamanho por requisição
RETRIES = 5  # RNF-06


def _batches(paras: list[str]) -> list[list[str]]:
    out, cur, size = [], [], 0
    for p in paras:
        if cur and (len(cur) >= MAX_PARAS or size + len(p) > MAX_CHARS):
            out.append(cur)
            cur, size = [], 0
        cur.append(p)
        size += len(p)
    if cur:
        out.append(cur)
    return out


class DeepLTranslator:
    def __init__(self, client: httpx.Client | None = None, key: str | None = None) -> None:
        self._key = key or os.environ["DEEPL_API_KEY"]
        host = "api-free.deepl.com" if self._key.endswith(":fx") else "api.deepl.com"
        self._url = f"https://{host}/v2/translate"
        self._client = client or httpx.Client(timeout=60)

    def _post(self, batch: list[str], src: str, tgt: str) -> list[str]:
        body = {"text": batch, "source_lang": src.upper(), "target_lang": _TARGET[tgt],
                "preserve_formatting": True}
        for attempt in range(RETRIES):
            r = self._client.post(self._url, json=body, headers={"Authorization": f"DeepL-Auth-Key {self._key}"})
            if r.status_code in (429, 500, 502, 503, 504) and attempt < RETRIES - 1:
                time.sleep(min(2 ** attempt, 30))  # backoff exponencial
                continue
            r.raise_for_status()
            return [t["text"] for t in r.json()["translations"]]
        raise RuntimeError("DeepL: tentativas esgotadas")

    def translate(self, text: str, src: str, tgt: str,
                  on_progress: Callable[[float], None] | None = None) -> str:
        if src == tgt or not text.strip():
            return text
        batches = _batches([p.strip() for p in text.split("\n\n") if p.strip()])
        out: list[str] = []
        for i, b in enumerate(batches):
            out.extend(self._post(b, src, tgt))
            if on_progress:
                on_progress((i + 1) / len(batches))
        return "\n\n".join(out)
