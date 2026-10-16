from typing import Protocol


class TTSProvider(Protocol):
    max_chars: int
    audio_ext: str
    default_voice: str

    def synthesize(self, text: str, voice: str, speed: float = 1.0) -> bytes:
        """Retorna áudio nos bytes de `audio_ext` (mp3 ou wav)."""
        ...
