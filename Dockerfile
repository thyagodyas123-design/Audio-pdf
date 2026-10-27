# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

# ffmpeg/ffprobe (concat + loudnorm), tesseract com por/eng (OCR),
# espeak-ng (fonemas do Kokoro), libsndfile (soundfile)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        tesseract-ocr \
        tesseract-ocr-por \
        tesseract-ocr-eng \
        espeak-ng \
        libsndfile1 \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

# torch CPU primeiro: evita baixar as wheels CUDA (~2.5 GB) que o PyPI entrega por padrão
RUN pip install --upgrade pip \
    && pip install --index-url https://download.pytorch.org/whl/cpu torch \
    && pip install ".[web,kokoro,translate]"

# Dados e caches de modelo dentro de /data (montar volume para persistir)
ENV AUDIOPDF_DATA=/data \
    HOME=/data \
    HF_HOME=/data/.cache/huggingface \
    XDG_CACHE_HOME=/data/.cache \
    XDG_DATA_HOME=/data/.local/share \
    TTS_PROVIDER=kokoro \
    KOKORO_DEVICE=cpu \
    OCR_LANG=por+eng \
    OCR_MAX_PAGES=150 \
    HOST=0.0.0.0 \
    PORT=8000 \
    FORWARDED_ALLOW_IPS=*

RUN mkdir -p /data

VOLUME ["/data"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/" > /dev/null || exit 1

CMD ["audiopdf-web"]
