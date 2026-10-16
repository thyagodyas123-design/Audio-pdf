import os
from collections.abc import Callable
from typing import Protocol


class Translator(Protocol):
    def translate(self, text: str, src: str, tgt: str,
                  on_progress: Callable[[float], None] | None = None) -> str: ...


def available_translators() -> list[str]:
    """Argos é local e sempre disponível; os de API só com a chave no ambiente."""
    names = ["argos"]
    if os.environ.get("DEEPL_API_KEY"):
        names.append("deepl")
    if os.environ.get("ANTHROPIC_API_KEY"):
        names.append("claude")
    return names


def get_translator(name: str | None = None) -> Translator:
    name = name or os.environ.get("TRANSLATOR", "argos")
    if name == "argos":
        from .argos import ArgosTranslator
        return ArgosTranslator()
    if name == "deepl":
        from .deepl import DeepLTranslator
        return DeepLTranslator()
    if name == "claude":
        from .claude import ClaudeTranslator
        return ClaudeTranslator()
    raise ValueError(f"tradutor desconhecido: {name}")
