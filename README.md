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
- **Vídeos por capítulo** (menu de vídeo em cada capítulo pronto): *vídeo da leitura* (PDF com o trecho lido em destaque + texto + áudio, MP4 1280×720) e
  *vídeo resumo* (resumo extrativo: seleciona e narra os trechos mais representativos, sem reescrever). Gerados em segundo plano, com
  progresso; assistir no app ou baixar.
- **Vídeo-aula** (formato educacional): um LLM escreve o roteiro do capítulo (cenas com tópicos, explicação, resumo e 3 perguntas com resposta),
  que é narrado e montado em vídeo com os tópicos aparecendo junto da fala e a página do PDF de origem em destaque. Exige `OPENCODE_API_KEY`
  (ou `LLM_API_KEY` + `LLM_BASE_URL`) no `.env`; o texto do capítulo é enviado ao provedor. O roteiro fica em cache (`NN.aula.json`).
  Custo: o texto enviado por capítulo é limitado a `LESSON_BUDGET_CHARS` (padrão 20 mil caracteres, ~6 mil tokens): acima disso vão só os trechos
  mais representativos. Com um servidor local (Ollama/LM Studio em `LLM_BASE_URL`) não há chave nem custo.
- **Vídeo-aula econômica** (sem IA, custo zero): mesmo formato, com as frases mais representativas como tópicos, os títulos do próprio livro
  como cenas e perguntas de completar. Não reescreve nem explica; a qualidade é bem inferior à da aula com IA.
- TTS local **Kokoro** (GPU Apple/MPS se disponível); tradução local **Argos** (pt ↔ en). Azure TTS como adapter opcional.
- OCR (Tesseract) das páginas sem texto; pausas por parágrafo na narração.
- Tradutores: Argos (local), DeepL e Claude (precisam de `DEEPL_API_KEY` / `ANTHROPIC_API_KEY`).
- Ainda não: EPUB/DOCX, contas/login, banco e fila externos (Fase 1).

## Acesso e usuários

Todo o `/api` exige login (cookie de sessão HttpOnly, 30 dias). Cada livro pertence a quem o enviou; cada pessoa vê só os seus e o administrador vê todos.

- **Primeiro admin:** defina `ADMIN_EMAIL` e `ADMIN_PASSWORD` antes do primeiro start. Só valem quando não há nenhum usuário; os livros que já existiam passam a ser dele.
- **Contas:** só administradores criam, editam, desativam e excluem usuários (tela **Usuários**, ou `/api/users`). O sistema não deixa excluir ou rebaixar o último admin ativo. Excluir uma conta entrega os livros dela a quem excluiu.
- **Senhas:** argon2; trocar a senha ou desativar a conta derruba as sessões abertas; 5 tentativas erradas bloqueiam o login por 15 minutos (por e-mail e IP).
- **Banco:** Postgres em produção (`DATABASE_URL`, já definido no `docker-compose.yml`); sem a variável, SQLite em `AUDIOPDF_DATA/audiopdf.db`. As migrations (Alembic, em `src/audiopdf/db/migrations`) rodam sozinhas ao iniciar. Áudios, vídeos e metadados dos capítulos continuam como arquivos no volume `/data`; o banco guarda usuários, sessões e o dono de cada livro.

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

### IA local para a vídeo-aula (custo zero)
Testado com o **Qwen 3 8B** no Ollama (Mac M4, 16 GB): ~6 GB de memória enquanto gera, ~5 min por capítulo de 27 mil caracteres (4 cenas),
JSON válido na primeira tentativa em 10 de 10 chamadas. Instale o Ollama, rode `ollama pull qwen3:8b`, defina `LLM_BASE_URL=http://localhost:11434/v1` e
`LESSON_MODEL=qwen3:8b` no `.env` e use `scripts/start-local.sh`. Não gere aulas com o modelo local ao mesmo tempo que converte o livro: as duas tarefas
disputam o mesmo chip e a memória.

## Estrutura

```
src/audiopdf/
  extract.py    PyMuPDF: blocos de texto, bookmarks, páginas sem texto
  clean.py      cabeçalhos/rodapés, nº de página, hifenização, parágrafos
  chapters.py   capítulos por bookmarks (nível 2 sob "Partes"), pula copyright/sumário/índice
  chunk.py      trechos por frase para o limite do TTS
  llm.py        cliente de chat compatível com OpenAI (retry/backoff, erros claros)
  lesson_local.py roteiro de aula sem IA (extrativo + perguntas de lacuna)
  lesson.py     roteiro de aula por LLM (cenas, resumo, perguntas) com validação
  lesson_video.py quadros e montagem do vídeo-aula
  summarize.py  resumo extrativo (parágrafos mais representativos)
  video.py      quadros (PyMuPDF) + ffmpeg → MP4 da leitura acompanhada
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
