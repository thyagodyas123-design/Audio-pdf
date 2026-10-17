# Audio-PDF

Converte o PDF de um livro em audiobook narrado, com tradução opcional.
Documentação: [`docs/requisitos.md`](docs/requisitos.md) · decisões pendentes: [`docs/analise.md`](docs/analise.md)

## Status: Fase 0 + app local

- CLI: PDF com texto selecionável → MP3 por capítulo.
- App local (FastAPI + HTML/CSS/JS sem build): upload com progresso, escolha de capítulos/idioma/voz, fila, linha do tempo
  do livro, **player fixo** que continua ao navegar (toca enquanto converte, retoma de onde parou, timer de sono,
  teclas espaço/←/→, controles do sistema), pré-busca do próximo capítulo e download (ZIP ou por capítulo). Claro/escuro automático.
- **Leitura sincronizada** (branch `feature/leitura-sincronizada`): botão "Acompanhar" no player abre o PDF com o parágrafo lido
  em destaque (vira a página sozinho), aba de texto (traduzido, se for o caso) e clique no PDF/texto para ouvir dali.
  Capítulos novos têm marcação exata por trecho; áudios anteriores usam uma estimativa (erro típico ~1 s).
- TTS local **Kokoro** (GPU Apple/MPS se disponível); tradução local **Argos** (pt ↔ en). Azure TTS como adapter opcional.
- OCR (Tesseract) das páginas sem texto; pausas por parágrafo na narração.
- Tradutores: Argos (local), DeepL e Claude (precisam de `DEEPL_API_KEY` / `ANTHROPIC_API_KEY`).
- Ainda não: EPUB/DOCX, contas/login, banco e fila externos (Fase 1).

## Instalação

```bash
brew install ffmpeg espeak-ng tesseract
# OCR em português: baixe por.traineddata (tessdata_fast) para a pasta do tessdata
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
.venv/bin/audiopdf-compare livro.pdf --chapter 8 --to en            # compara tradutores (out/compare-*.md)
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
  align.py      parágrafo narrado → região do PDF (destaque) e linha do tempo estimada
  lang.py       detecção de idioma (lingua-py)
  translate/    adapter + Argos (local)
  tts/          adapter: kokoro (local), azure
  audio.py      FFmpeg: concat + loudnorm -16 LUFS, MP3 44,1 kHz mono 128k
  web/          API FastAPI + static/ (index.html, app.css, app.js)
  cli.py
```

## Limitações conhecidas
- Figuras e pseudocódigo que são imagens dentro de páginas com texto não são narrados (o OCR só cobre páginas inteiras sem texto).
- OCR roda no upload, de forma síncrona (até `OCR_MAX_PAGES`, padrão 150); sem medição de confiança.
- Argos erra terminologia técnica (ex.: "merge sort" vira "ordenação por intercalação" → "sorting by intercalation"); prefira DeepL ou Claude para livros técnicos.
- Só pt-BR e en-US (vozes disponíveis).

## Roadmap
0. PoC + app local (aqui) · 1. MVP web (Next.js, Postgres, fila) · 2. Refinamento · 3. Expansão
