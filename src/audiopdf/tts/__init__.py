import os

from .base import TTSProvider


def get_provider(name: str | None = None) -> TTSProvider:
    name = name or os.environ.get("TTS_PROVIDER", "azure")
    if name == "azure":
        from .azure import AzureTTS
        return AzureTTS()
    if name == "kokoro":
        from .kokoro import KokoroTTS
        return KokoroTTS()
    raise ValueError(f"provedor TTS desconhecido: {name}")
