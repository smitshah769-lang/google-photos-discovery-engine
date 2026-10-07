from __future__ import annotations

import re
from typing import Any

from pipeline.analysis.inference import InferenceUnavailable

_CROSS_ENCODER: Any = None
_CROSS_ENCODER_MODEL: str | None = None


def lexical_overlap_boost(query: str, document: str) -> float:
    """Cheap hybrid signal: token overlap in [0, 1]."""
    qtok = set(re.findall(r"[a-z0-9]+", (query or "").lower()))
    if not qtok:
        return 0.0
    dtok = set(re.findall(r"[a-z0-9]+", (document or "").lower()))
    return len(qtok & dtok) / len(qtok)


def cross_encoder_rerank(
    query: str,
    candidates: list[tuple[dict[str, Any], float]],
    *,
    model_id: str,
    top_k: int,
) -> list[tuple[dict[str, Any], float]]:
    if not candidates:
        return []
    try:
        from sentence_transformers import CrossEncoder  # type: ignore
    except ImportError as exc:
        raise InferenceUnavailable(
            "Cross-encoder rerank requires sentence-transformers. pip install -e '.[analysis]'"
        ) from exc

    global _CROSS_ENCODER, _CROSS_ENCODER_MODEL
    mid = model_id or "BAAI/bge-reranker-base"
    if _CROSS_ENCODER is None or _CROSS_ENCODER_MODEL != mid:
        _CROSS_ENCODER = CrossEncoder(mid)
        _CROSS_ENCODER_MODEL = mid

    pairs = [(query, (chunk.get("text") or "")[:1500]) for chunk, _ in candidates]
    try:
        scores = _CROSS_ENCODER.predict(pairs, show_progress_bar=False)
    except Exception as exc:
        raise InferenceUnavailable(f"Cross-encoder rerank failed ({exc}).") from exc

    scored: list[tuple[dict[str, Any], float]] = []
    for (chunk, _vec_rel), ce in zip(candidates, scores):
        scored.append((chunk, float(ce)))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]
