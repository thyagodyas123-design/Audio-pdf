import os
from collections.abc import Callable
from typing import Protocol


class Translator(Protocol):
    def translate(self, text: str, src: str, tgt: str,
                  on_progress: Callable[[float], None] | None = None) -> str: ...


def get_translator(name: str | None = None) -> Translator:
    name = name or os.environ.get("TRANSLATOR", "argos")
    if name == "argos":
        from .argos import ArgosTranslator
        return ArgosTranslator()
    raise ValueError(f"tradutor desconhecido: {name}")
