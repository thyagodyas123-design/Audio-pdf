# Audio-PDF

Converte o PDF de um livro em audiobook narrado, com tradução opcional.
Documentação: [`docs/requisitos.md`](docs/requisitos.md) · decisões pendentes: [`docs/analise.md`](docs/analise.md)

## Status: Fase 0 (prova de conceito)

CLI que converte um PDF com texto selecionável em MP3 por capítulo, em um idioma, sem tradução.

## Uso

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # preencha AZURE_SPEECH_KEY / AZURE_SPEECH_REGION
brew install ffmpeg

audiopdf livro.pdf --dry-run                      # estimativa, sem gastar TTS
audiopdf livro.pdf --voice pt-BR-FranciscaNeural  # gera out/NN-capitulo.mp3
pytest
```

## Estrutura

```
src/audiopdf/
  extract.py   PyMuPDF: texto, bookmarks, páginas sem texto
  clean.py     cabeçalhos/rodapés, nº de página, hifenização, parágrafos
  chapters.py  capítulos por bookmarks (fallback: livro inteiro)
  chunk.py     trechos por frase para o limite do TTS
  tts/         adapter (base + azure); novos provedores = novo arquivo
  audio.py     FFmpeg: concat + loudnorm -16 LUFS, MP3 44,1 kHz mono 128k
  cli.py
```

## Roadmap

0. **PoC (aqui)** · 1. MVP web (Must) · 2. Refinamento (Should) · 3. Expansão (Could)
