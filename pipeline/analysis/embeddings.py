from __future__ import annotations

import hashlib
import math
import re
from typing import Sequence

from pipeline.analysis.inference import InferenceUnavailable


def hashing_embed(text: str, dim: int = 128) -> list[float]:
    vec = [0.0] * dim
    tokens = re.findall(r"[a-z0-9]+", (text or "").lower())
    if not tokens:
        return vec
    for tok in tokens:
        digest = hashlib.sha256(tok.encode()).digest()
        idx = int.from_bytes(digest[:2], "big") % dim
        sign = 1.0 if digest[2] % 2 == 0 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def embed_texts(texts: list[str], *, provider: str, model_id: str | None) -> list[list[float]]:
    provider = (provider or "hashing").lower()
    if provider in {"hashing", "heuristic"}:
        return [hashing_embed(t) for t in texts]
    if provider in {"sentence-transformers", "sentence_transformers"}:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except ImportError as exc:
            raise InferenceUnavailable(
                "sentence-transformers is not installed (required for this vector index). "
                "Install with: pip install -e '.[analysis]'"
            ) from exc
        mid = model_id or "BAAI/bge-small-en-v1.5"
        try:
            model = SentenceTransformer(mid)
            vectors = model.encode(texts, normalize_embeddings=True)
        except Exception as exc:
            raise InferenceUnavailable(
                f"sentence-transformers failed ({exc}). No paid API fallback."
            ) from exc
        return [list(map(float, row)) for row in vectors]
    if provider == "ollama":
        return _ollama_embed(texts, model_id=model_id)

    raise InferenceUnavailable(f"Unknown embedding provider {provider!r}")


def _ollama_embed(texts: list[str], *, model_id: str | None) -> list[list[float]]:
    import json as _json
    import urllib.error
    import urllib.request

    mid = model_id or "nomic-embed-text"
    host = "http://127.0.0.1:11434"
    vectors: list[list[float]] = []
    for text in texts:
        body = _json.dumps({"model": mid, "input": text or ""}).encode()
        req = urllib.request.Request(
            f"{host}/api/embed",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                payload = _json.loads(resp.read().decode())
        except (urllib.error.URLError, TimeoutError, _json.JSONDecodeError) as exc:
            raise InferenceUnavailable(
                f"Ollama embeddings failed at {host} ({exc}). No paid API fallback."
            ) from exc
        emb = payload.get("embeddings")
        if isinstance(emb, list) and emb and isinstance(emb[0], list):
            vectors.append([float(x) for x in emb[0]])
            continue
        single = payload.get("embedding")
        if isinstance(single, list):
            vectors.append([float(x) for x in single])
            continue
        raise InferenceUnavailable("Ollama /api/embed returned no embedding vector.")
    return vectors
