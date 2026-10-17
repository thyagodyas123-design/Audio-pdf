"""Etapa 6 (parcial): concatena trechos MP3 e normaliza volume com FFmpeg."""
import subprocess
import tempfile
from pathlib import Path


def concat_normalize(parts: list[bytes], dest: Path, ext: str = "mp3", lufs: int = -16) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        listing = []
        for i, data in enumerate(parts):
            f = t / f"{i:05d}.{ext}"
            f.write_bytes(data)
            listing.append(f"file '{f}'")
        (t / "list.txt").write_text("\n".join(listing))
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
             "-i", str(t / "list.txt"), "-af", f"loudnorm=I={lufs}:TP=-1.5:LRA=11",
             "-ar", "44100", "-ac", "1", "-b:a", "128k", str(dest)],
            check=True,
        )


def to_mp3(data: bytes, ext: str, dest: Path) -> None:
    """Converte um trecho para MP3 (pré-escuta durante a conversão; sem normalização)."""
    if ext == "mp3":
        dest.write_bytes(data)
        return
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", ext, "-i", "pipe:0",
         "-ar", "44100", "-ac", "1", "-b:a", "128k", str(dest)],
        input=data, check=True,
    )


def duration_of(path: Path) -> float | None:
    """Duração em segundos (ffprobe) ou None se não for possível ler."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        return round(float(out), 1)
    except (subprocess.CalledProcessError, ValueError, FileNotFoundError):
        return None
