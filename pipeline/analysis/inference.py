from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Protocol


class InferenceUnavailable(RuntimeError):
    """Local model missing or failed. Do not fall back to a paid API."""


class CompletionClient(Protocol):
    def complete(self, prompt: str, *, temperature: float) -> str: ...


class OllamaClient:
    def __init__(self, model_id: str, host: str = "http://127.0.0.1:11434") -> None:
        if not model_id:
            raise InferenceUnavailable(
                "Ollama classification requires models.classification.model_id in run.yaml."
            )
        self.model_id = model_id
        self.host = host.rstrip("/")

    def complete(self, prompt: str, *, temperature: float) -> str:
        body = json.dumps(
            {
                "model": self.model_id,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": temperature},
            }
        ).encode()
        last_exc: Exception | None = None
        for attempt in range(4):
            req = urllib.request.Request(
                f"{self.host}/api/chat",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=180) as resp:
                    payload = json.loads(resp.read().decode())
                last_exc = None
                break
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_exc = exc
                if attempt < 3:
                    import time

                    time.sleep(2.0 * (attempt + 1))
                    continue
        if last_exc is not None:
            raise InferenceUnavailable(
                f"Ollama is not available at {self.host} ({last_exc}). "
                "Analysis stage failed; no paid API fallback."
            ) from last_exc
        message = payload.get("message") or {}
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise InferenceUnavailable("Ollama returned an empty completion.")
        return content


_ZS_PIPELINE: Any = None


def huggingface_zero_shot(text: str, candidate_labels: list[str]) -> dict[str, float]:
    global _ZS_PIPELINE
    try:
        from transformers import pipeline  # type: ignore
    except ImportError as exc:
        raise InferenceUnavailable(
            "Hugging Face transformers is not installed. "
            "Install extras or run Ollama. Analysis failed; no paid API fallback."
        ) from exc
    try:
        if _ZS_PIPELINE is None:
            _ZS_PIPELINE = pipeline("zero-shot-classification", model="facebook/bart-large-mnli")
        clf = _ZS_PIPELINE
        result = clf(text, candidate_labels, multi_label=True)
    except Exception as exc:  # model download / CPU OOM
        raise InferenceUnavailable(
            f"Hugging Face zero-shot failed ({exc}). Analysis failed; no paid API fallback."
        ) from exc
    labels = result.get("labels") or []
    scores = result.get("scores") or []
    return {str(lab): float(score) for lab, score in zip(labels, scores)}


def ping_ollama(host: str = "http://127.0.0.1:11434") -> bool:
    try:
        with urllib.request.urlopen(f"{host.rstrip('/')}/api/tags", timeout=2) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError):
        return False
