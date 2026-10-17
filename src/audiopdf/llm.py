"""Cliente mínimo para provedores compatíveis com a API de chat da OpenAI (OpenCode Zen, OpenAI, servidores locais).
Configuração por ambiente: LLM_API_KEY (ou OPENCODE_API_KEY), LLM_BASE_URL, LESSON_MODEL."""
import json
import os
import re
import time

import httpx

DEFAULT_BASE = "https://opencode.ai/zen/v1"
DEFAULT_MODEL = "gemini-3.8-flash"
RETRIES = 5  # RNF-06


class LLMError(RuntimeError):
    """Falha do provedor com mensagem pronta para o usuário."""


def _is_local(url: str) -> bool:
    return bool(re.match(r"https?://(localhost|127\.0\.0\.1|\[::1\])(:|/|$)", url))


def configured() -> bool:
    """Há chave, ou o endereço aponta para um servidor local (Ollama, LM Studio), que dispensa chave."""
    return bool(os.environ.get("LLM_API_KEY") or os.environ.get("OPENCODE_API_KEY") or _is_local(os.environ.get("LLM_BASE_URL", "")))


_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def extract_json(text: str) -> dict:
    """Aceita resposta com cercas ```json ou texto em volta do objeto (e ignora blocos <think> de modelos de raciocínio)."""
    text = _THINK.sub("", text)
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j <= i:
        raise ValueError("resposta sem JSON")
    return json.loads(t[i:j + 1])


class LLM:
    def __init__(self, client: httpx.Client | None = None, base_url: str | None = None,
                 key: str | None = None, model: str | None = None) -> None:
        self.base = (base_url or os.environ.get("LLM_BASE_URL") or DEFAULT_BASE).rstrip("/")
        self.local = _is_local(self.base)
        # servidor local não precisa de chave: nunca envia a chave de um provedor remoto para ele
        self.key = "local" if self.local else (key or os.environ.get("LLM_API_KEY") or os.environ.get("OPENCODE_API_KEY"))
        if not self.key:
            raise LLMError("Nenhuma chave de LLM configurada (OPENCODE_API_KEY ou LLM_API_KEY no .env).")
        self.model = model or os.environ.get("LESSON_MODEL") or DEFAULT_MODEL
        self._client = client or httpx.Client(timeout=900 if self.local else 120)  # modelo local é mais lento

    def chat(self, system: str, user: str, max_tokens: int = 2500, temperature: float = 0.3, json_mode: bool = False) -> str:
        if "qwen3" in self.model.lower() and "/no_think" not in user:
            user += "\n/no_think"  # Qwen3: desliga o raciocínio longo (mais rápido; o JSON vem direto)
        body = {"model": self.model, "temperature": temperature, "max_tokens": max_tokens,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if self.local and "qwen3" in self.model.lower():
            body["reasoning_effort"] = "none"  # medido: o "/no_think" no prompt não basta; isto corta ~3x os tokens gerados no Ollama
        if json_mode and self.local:
            body["response_format"] = {"type": "json_object"}  # Ollama/LM Studio: garante JSON sintaticamente válido
        for attempt in range(RETRIES):
            try:
                r = self._client.post(f"{self.base}/chat/completions", json=body, headers={"Authorization": f"Bearer {self.key}"})
            except httpx.TransportError as e:
                if attempt < RETRIES - 1:
                    time.sleep(min(2 ** attempt, 20))
                    continue
                raise LLMError(f"Sem conexão com o provedor de LLM: {e}") from e
            if r.status_code in (429, 500, 502, 503, 504) and attempt < RETRIES - 1:
                time.sleep(min(2 ** attempt, 20))  # backoff exponencial
                continue
            if r.status_code >= 400:
                detail = ""
                try:
                    detail = (r.json().get("error") or {}).get("message", "")
                except ValueError:
                    detail = r.text[:160]
                if r.status_code == 402:
                    raise LLMError(f"O provedor recusou: sem créditos na conta (HTTP 402). {detail} Adicione créditos ou troque o provedor.")
                if r.status_code in (401, 403):
                    raise LLMError(f"O provedor recusou a chave ou o modelo '{self.model}' (HTTP {r.status_code}). {detail}")
                raise LLMError(f"Erro do provedor de LLM (HTTP {r.status_code}). {detail}")
            try:
                return r.json()["choices"][0]["message"]["content"] or ""
            except (KeyError, IndexError, ValueError) as e:
                raise LLMError("Resposta inesperada do provedor de LLM.") from e
        raise LLMError("Provedor de LLM indisponível após várias tentativas.")
