from typing import Protocol


class TTSProvider(Protocol):
    max_chars: int

    def synthesize(self, text: str, voice: str, speed: float = 1.0) -> bytes:
        """Retorna áudio MP3."""
        ...
