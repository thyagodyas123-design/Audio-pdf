"""Tradução literária via Claude (ANTHROPIC_API_KEY). Cada bloco leva o fim do anterior como contexto."""
import os
from collections.abc import Callable

MAX_BLOCK = 3000
NAMES = {"pt": "Brazilian Portuguese", "en": "American English", "es": "Spanish", "fr": "French",
         "de": "German", "it": "Italian"}
SYSTEM = (
    "You are a professional book translator. Translate the text from {src} to {tgt}. "
    "Keep the paragraph structure exactly (paragraphs are separated by a blank line). "
    "Keep proper nouns, code, identifiers and mathematical notation unchanged. "
    "Use the established technical terminology of the field. "
    "Reply with the translation only: no comments, no notes."
)


def _blocks(text: str, limit: int = MAX_BLOCK) -> list[str]:
    out, cur = [], ""
    for para in (p.strip() for p in text.split("\n\n")):
        if not para:
            continue
        if cur and len(cur) + len(para) + 2 > limit:
            out.append(cur)
            cur = ""
        cur = f"{cur}\n\n{para}" if cur else para
    if cur:
        out.append(cur)
    return out


class ClaudeTranslator:
    def __init__(self, client=None, model: str | None = None) -> None:
        if client is None:
            import anthropic

            client = anthropic.Anthropic(max_retries=5)  # backoff exponencial embutido no SDK (RNF-06)
        self._client = client
        self._model = model or os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")

    def translate(self, text: str, src: str, tgt: str,
                  on_progress: Callable[[float], None] | None = None) -> str:
        if src == tgt or not text.strip():
            return text
        system = SYSTEM.format(src=NAMES.get(src, src), tgt=NAMES.get(tgt, tgt))
        blocks, out = _blocks(text), []
        for i, block in enumerate(blocks):
            prompt = block
            if out:
                prompt = f"<previous_translation_for_context_only>\n{out[-1][-600:]}\n</previous_translation_for_context_only>\n\n<translate>\n{block}\n</translate>"
            msg = self._client.messages.create(
                model=self._model, max_tokens=4096, system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            out.append("".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip())
            if on_progress:
                on_progress((i + 1) / len(blocks))
        return "\n\n".join(out)
