#!/bin/bash
# Sobe o Ollama (se ainda não estiver rodando) e o app local. Uso: scripts/start-local.sh [--sem-ollama]
# O Ollama é configurado para usar pouca memória: um pedido por vez e o modelo sai da memória 90 s depois do uso.
set -e
cd "$(dirname "$0")/.."
OLLAMA="${OLLAMA_BIN:-$HOME/.local/ollama/dist/ollama}"
if [ "$1" != "--sem-ollama" ] && [ -x "$OLLAMA" ] && ! curl -s -m 2 localhost:11434/api/version >/dev/null; then
  OLLAMA_HOST=127.0.0.1:11434 OLLAMA_CONTEXT_LENGTH=8192 OLLAMA_KEEP_ALIVE=90s OLLAMA_NUM_PARALLEL=1 OLLAMA_MAX_LOADED_MODELS=1 \
    nohup "$OLLAMA" serve > "$HOME/.local/ollama/serve.log" 2>&1 &
  echo "Ollama iniciado (modelo só é carregado quando uma aula é gerada)"
fi
AUDIOPDF_DATA="$PWD/data" PORT="${PORT:-8765}" exec .venv/bin/audiopdf-web
