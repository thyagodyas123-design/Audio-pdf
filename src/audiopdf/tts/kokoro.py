import io
import os
import re
import threading

os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")  # antes de importar torch

import numpy as np
import soundfile as sf

SAMPLE_RATE = 24000
_LANG = {"p": "p", "a": "a", "b": "b", "e": "e", "f": "f", "i": "i", "h": "h", "j": "j", "z": "z"}


def _device() -> str:
    if os.environ.get("KOKORO_DEVICE"):
        return os.environ["KOKORO_DEVICE"]
    import torch

    return "mps" if torch.backends.mps.is_available() else "cpu"


class KokoroTTS:
    """TTS local (Kokoro-82M). Sem SSML: pausas e velocidade tratadas aqui."""

    max_chars = 1000  # modelo aceita ~500 tokens por vez
    audio_ext = "wav"
    default_voice = "pf_dora"  # pt-BR feminina; também pm_alex, pm_santa

    def __init__(self) -> None:
        self._pipes: dict[str, object] = {}
        self._lock = threading.Lock()  # MPS/PyTorch: uma síntese por vez

    def _pipe(self, voice: str):
        lang = _LANG.get(voice[:1], "a")
        if lang not in self._pipes:
            from kokoro import KPipeline

            self._pipes[lang] = KPipeline(lang_code=lang, repo_id="hexgrad/Kokoro-82M", device=_device())
        return self._pipes[lang]

    def warmup(self) -> None:
        self.synthesize("Aquecendo o modelo.", self.default_voice, 1.0)

    def synthesize(self, text: str, voice: str, speed: float = 1.0, pause_s: float = 0.25) -> bytes:
        voice = voice or self.default_voice
        with self._lock:
            pieces = [
                np.asarray(audio, dtype=np.float32)
                for _, _, audio in self._pipe(voice)(text, voice=voice, speed=speed)
            ]
        if not pieces and re.search(r"\w", text):
            raise RuntimeError("Kokoro não gerou áudio")
        pause = np.zeros(int(SAMPLE_RATE * pause_s), dtype=np.float32)  # pausa ao fim do trecho
        wav = np.concatenate([np.concatenate([p, pause]) for p in pieces] or [pause])  # sem fala: só a pausa
        buf = io.BytesIO()
        sf.write(buf, wav, SAMPLE_RATE, format="WAV", subtype="PCM_16")
        return buf.getvalue()
