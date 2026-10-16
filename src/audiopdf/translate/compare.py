"""Compara tradutores no mesmo trecho de um capítulo: audiopdf-compare livro.pdf --chapter 8."""
import argparse
import time
from pathlib import Path

from ..chapters import split_chapters
from ..clean import clean_pages
from ..extract import extract
from ..lang import detect
from . import available_translators, get_translator


def main() -> None:
    ap = argparse.ArgumentParser(prog="audiopdf-compare")
    ap.add_argument("pdf")
    ap.add_argument("--chapter", type=int, default=1)
    ap.add_argument("--to", default="en", help="idioma de saída (ISO 639-1)")
    ap.add_argument("--chars", type=int, default=2500, help="tamanho do trecho comparado")
    ap.add_argument("--out", default="out")
    args = ap.parse_args()

    content = extract(args.pdf, ocr=False)
    chapters = split_chapters(clean_pages(content.pages), content.outline, title=Path(args.pdf).stem)
    ch = next(c for c in chapters if c.index == args.chapter)
    sample = ch.text[: args.chars].rsplit("\n\n", 1)[0] or ch.text[: args.chars]
    src = detect(sample) or "pt"
    report = [f"# Comparação de tradutores\n\nCapítulo {ch.index}: {ch.title} · {src} → {args.to} · {len(sample)} caracteres\n",
              f"## Original\n\n{sample}\n"]
    for name in available_translators():
        t0 = time.time()
        try:
            text = get_translator(name).translate(sample, src, args.to)
            report.append(f"## {name} ({time.time() - t0:.1f} s)\n\n{text}\n")
        except Exception as e:  # noqa: BLE001
            report.append(f"## {name}\n\nFalhou: {e}\n")
    out = Path(args.out)
    out.mkdir(exist_ok=True)
    dest = out / f"compare-ch{ch.index}-{src}-{args.to}.md"
    dest.write_text("\n".join(report))
    print(f"traduzido por: {', '.join(available_translators())} -> {dest}")
    skipped = {"deepl", "claude"} - set(available_translators())
    if skipped:
        print(f"sem chave (ignorados): {', '.join(sorted(skipped))} — defina DEEPL_API_KEY / ANTHROPIC_API_KEY")


if __name__ == "__main__":
    main()
