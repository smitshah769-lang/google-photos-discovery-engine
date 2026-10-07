from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from pipeline.analysis.inference import CompletionClient, InferenceUnavailable


def _post_json(url: str, payload: dict[str, Any], *, headers: dict[str, str]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise InferenceUnavailable(f"LLM HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise InferenceUnavailable(f"LLM request failed: {exc}") from exc


class GroqClient:
    """Groq chat completions (OpenAI-compatible). Free tier: console.groq.com."""

    def __init__(self, model_id: str) -> None:
        key = (os.environ.get("GROQ_API_KEY") or "").strip()
        if not key:
            raise InferenceUnavailable(
                "GROQ_API_KEY is not set. Get a free key at https://console.groq.com/keys"
            )
        if not model_id:
            raise InferenceUnavailable("Groq synthesis requires a model_id in config/run.yaml.")
        self.model_id = model_id
        self._api_key = key

    def complete(self, prompt: str, *, temperature: float) -> str:
        payload = _post_json(
            "https://api.groq.com/openai/v1/chat/completions",
            {
                "model": self.model_id,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
            },
            headers={"Authorization": f"Bearer {self._api_key}"},
        )
        choices = payload.get("choices") or []
        if not choices:
            raise InferenceUnavailable("Groq returned no choices.")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise InferenceUnavailable("Groq returned an empty completion.")
        return content


class GeminiClient:
    """Google AI Studio Gemini. Free tier: aistudio.google.com/apikey."""

    def __init__(self, model_id: str) -> None:
        key = (os.environ.get("GEMINI_API_KEY") or "").strip()
        if not key:
            raise InferenceUnavailable(
                "GEMINI_API_KEY is not set. Get a free key at https://aistudio.google.com/apikey"
            )
        if not model_id:
            raise InferenceUnavailable("Gemini synthesis requires a model_id in config/run.yaml.")
        self.model_id = model_id
        self._api_key = key

    def complete(self, prompt: str, *, temperature: float) -> str:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model_id}:generateContent?key={self._api_key}"
        )
        payload = _post_json(
            url,
            {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": temperature},
            },
            headers={},
        )
        candidates = payload.get("candidates") or []
        if not candidates:
            raise InferenceUnavailable("Gemini returned no candidates.")
        parts = (candidates[0].get("content") or {}).get("parts") or []
        texts = [p.get("text") for p in parts if isinstance(p.get("text"), str)]
        content = "\n".join(texts).strip()
        if not content:
            raise InferenceUnavailable("Gemini returned an empty completion.")
        return content


def _hf_token() -> str:
    return (os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_API_KEY") or "").strip()


class HuggingFaceClient:
    """
    Hugging Face Inference Providers (OpenAI-compatible chat).
    Token: https://huggingface.co/settings/tokens
    """

    def __init__(self, model_id: str) -> None:
        token = _hf_token()
        if not token:
            raise InferenceUnavailable(
                "HF_TOKEN is not set. Create a read token at https://huggingface.co/settings/tokens"
            )
        if not model_id:
            raise InferenceUnavailable(
                "Hugging Face synthesis requires rag.synthesis.model_id or the default in run.yaml."
            )
        self.model_id = model_id
        self._token = token

    def complete(self, prompt: str, *, temperature: float) -> str:
        payload = _post_json(
            "https://router.huggingface.co/v1/chat/completions",
            {
                "model": self.model_id,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": 1024,
            },
            headers={"Authorization": f"Bearer {self._token}"},
        )
        choices = payload.get("choices") or []
        if not choices:
            raise InferenceUnavailable("Hugging Face returned no choices.")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise InferenceUnavailable("Hugging Face returned an empty completion.")
        return content


DEFAULT_SYNTHESIS_MODELS = {
    "gemini": "gemini-2.0-flash",
    "groq": "llama-3.1-8b-instant",
    "huggingface": "Qwen/Qwen2.5-7B-Instruct",
}


def detect_synthesis_provider() -> str | None:
    if (os.environ.get("GEMINI_API_KEY") or "").strip():
        return "gemini"
    if (os.environ.get("GROQ_API_KEY") or "").strip():
        return "groq"
    if _hf_token():
        return "huggingface"
    return None


def build_synthesis_client(provider: str, model_id: str) -> CompletionClient:
    p = (provider or "ollama").lower()
    if p in {"huggingface", "hf"}:
        return HuggingFaceClient(model_id)
    if p == "gemini":
        return GeminiClient(model_id)
    if p == "groq":
        return GroqClient(model_id)
    if p == "ollama":
        from pipeline.analysis.inference import OllamaClient

        return OllamaClient(model_id)
    raise InferenceUnavailable(
        f"Unknown synthesis provider {provider!r}. Use gemini, groq, huggingface, or ollama."
    )


def resolve_synthesis_settings(
    synthesis_cfg: dict[str, Any],
    models_cfg: dict[str, Any],
) -> tuple[bool, str, str]:
    """
    Returns (enabled, provider, model_id).
    Enables automatically when GEMINI_API_KEY, GROQ_API_KEY, or HF_TOKEN is set.
    """
    enabled = bool(synthesis_cfg.get("enabled"))
    env_provider = detect_synthesis_provider()
    if env_provider and not enabled:
        enabled = True

    configured = synthesis_cfg.get("provider")
    if configured:
        provider = str(configured).lower()
    else:
        provider = str(env_provider or "ollama").lower()

    model_id = synthesis_cfg.get("model_id")
    if model_id:
        model_id = str(model_id)
    elif provider in DEFAULT_SYNTHESIS_MODELS:
        model_id = DEFAULT_SYNTHESIS_MODELS[provider]
    else:
        model_id = str((models_cfg.get("classification") or {}).get("model_id") or "")

    return enabled, provider, model_id
