# Audio-PDF

Converte o PDF de um livro em audiobook narrado, com tradução opcional.
Documentação: [`docs/requisitos.md`](docs/requisitos.md) · decisões pendentes: [`docs/analise.md`](docs/analise.md)

## Status: Fase 0 + app local

- CLI: PDF com texto selecionável → MP3 por capítulo.
- App local (FastAPI + página única): upload, capítulos, idioma de saída, voz, fila, player que toca
  enquanto converte, pré-busca do próximo capítulo e download (ZIP ou por capítulo).
- TTS local **Kokoro** (GPU Apple/MPS se disponível); tradução local **Argos** (pt ↔ en). Azure TTS como adapter opcional.
- Ainda não: OCR, EPUB/DOCX, contas/login, banco e fila externos (Fase 1).

## Instalação

```bash
brew install ffmpeg espeak-ng
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e ".[dev,web,kokoro,translate]"
cp .env.example .env     # só necessário para o Azure TTS
```

## Uso

```bash
# App local (http://localhost:8000; mude com PORT=8765). Dados em ./data (AUDIOPDF_DATA)
.venv/bin/audiopdf-web

# CLI
.venv/bin/audiopdf livro.pdf --dry-run                              # estimativa, sem gastar TTS
.venv/bin/audiopdf livro.pdf --provider kokoro --chapters 3-5       # gera out/NN-capitulo.mp3
.venv/bin/pytest
```

Ao converter para outro idioma, o modelo do par (~100 MB) é baixado na primeira vez.

## Estrutura

```
src/audiopdf/
  extract.py    PyMuPDF: blocos de texto, bookmarks, páginas sem texto
  clean.py      cabeçalhos/rodapés, nº de página, hifenização, parágrafos
  chapters.py   capítulos por bookmarks (nível 2 sob "Partes"), pula copyright/sumário/índice
  chunk.py      trechos por frase para o limite do TTS
  lang.py       detecção de idioma (lingua-py)
  translate/    adapter + Argos (local)
  tts/          adapter: kokoro (local), azure
  audio.py      FFmpeg: concat + loudnorm -16 LUFS, MP3 44,1 kHz mono 128k
  web/          API FastAPI + static/index.html
  cli.py
```

## Limitações conhecidas
- Figuras e pseudocódigo que são imagens no PDF não são narrados (sem OCR).
- Argos erra terminologia técnica; o adapter permite trocar por DeepL/Claude.
- Só pt-BR e en-US (vozes disponíveis).

## Roadmap
0. PoC + app local (aqui) · 1. MVP web (Next.js, Postgres, fila) · 2. Refinamento · 3. Expansão
