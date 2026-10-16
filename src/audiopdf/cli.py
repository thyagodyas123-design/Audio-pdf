import argparse
import re
from pathlib import Path

from dotenv import load_dotenv

from .audio import concat_normalize
from .chapters import split_chapters
from .chunk import chunk_text
from .clean import clean_pages
from .extract import extract
from .tts import get_provider


def _slug(s: str) -> str:
    return re.sub(r"[^\w]+", "-", s.lower()).strip("-")[:50] or "capitulo"


def main() -> None:
    load_dotenv()
    ap = argparse.ArgumentParser(prog="audiopdf", description="PDF -> MP3 por capítulo")
    ap.add_argument("pdf")
    ap.add_argument("--voice", default=None, help="padrão: voz do provedor")
    ap.add_argument("--provider", default=None, help="azure | kokoro (ou TTS_PROVIDER)")
    ap.add_argument("--chapters", default=None, help="intervalo, ex.: 3-5 ou 7")
    ap.add_argument("--keep-matter", action="store_true", help="não pular copyright/sumário/índice")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--out", default="out")
    ap.add_argument("--dry-run", action="store_true", help="só extrai/limpa e mostra estimativa")
    args = ap.parse_args()

    content = extract(args.pdf)
    if content.scanned_pages:
        print(f"aviso: {len(content.scanned_pages)} página(s) sem texto (OCR não suportado na Fase 0)")
    pages = clean_pages(content.pages)
    chapters = split_chapters(pages, content.outline, title=Path(args.pdf).stem,
                              skip_matter=not args.keep_matter)
    if args.chapters:
        a, _, b = args.chapters.partition("-")
        lo, hi = int(a), int(b or a)
        chapters = [c for c in chapters if lo <= c.index <= hi]
    total = sum(len(c.text) for c in chapters)
    print(f"{len(chapters)} capítulo(s), {total} caracteres (~{total / 900 / 60:.1f} h de áudio)")
    if args.dry_run:
        for c in chapters:
            print(f"  {c.index:02d} {c.title} ({len(c.text)} chars)")
        return

    tts = get_provider(args.provider)
    voice = args.voice or tts.default_voice
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for c in chapters:
        dest = out / f"{c.index:02d}-{_slug(c.title)}.mp3"
        if dest.exists():  # retoma por capítulo (RNF-05)
            print(f"  {dest.name} já existe, pulando")
            continue
        text = f"{c.title}.\n\n{c.text}"
        parts = [tts.synthesize(t, voice, args.speed) for t in chunk_text(text, tts.max_chars)]
        concat_normalize(parts, dest, ext=tts.audio_ext)
        print(f"  ok {dest.name}")


if __name__ == "__main__":
    main()
