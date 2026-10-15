"""Etapa 6 (parcial): concatena trechos MP3 e normaliza volume com FFmpeg."""
import subprocess
import tempfile
from pathlib import Path


def concat_normalize(parts: list[bytes], dest: Path, lufs: int = -16) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        listing = []
        for i, data in enumerate(parts):
            f = t / f"{i:05d}.mp3"
            f.write_bytes(data)
            listing.append(f"file '{f}'")
        (t / "list.txt").write_text("\n".join(listing))
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
             "-i", str(t / "list.txt"), "-af", f"loudnorm=I={lufs}:TP=-1.5:LRA=11",
             "-ar", "44100", "-ac", "1", "-b:a", "128k", str(dest)],
            check=True,
        )
