from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipeline.analysis.embeddings import cosine


class VectorIndex:
    """Portable vector index file co-located with the SQLite snapshot."""

    def __init__(
        self,
        *,
        analysis_run_id: str,
        embedding_provider: str,
        embedding_model_id: str,
        chunks: list[dict[str, Any]],
    ) -> None:
        self.analysis_run_id = analysis_run_id
        self.embedding_provider = embedding_provider
        self.embedding_model_id = embedding_model_id
        self.chunks = chunks

    def to_dict(self) -> dict[str, Any]:
        return {
            "analysis_run_id": self.analysis_run_id,
            "embedding": {
                "provider": self.embedding_provider,
                "model_id": self.embedding_model_id,
            },
            "chunks": self.chunks,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VectorIndex:
        return cls(
            analysis_run_id=str(data["analysis_run_id"]),
            embedding_provider=str((data.get("embedding") or {}).get("provider")),
            embedding_model_id=str((data.get("embedding") or {}).get("model_id")),
            chunks=list(data.get("chunks") or []),
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), separators=(",", ":")))

    @classmethod
    def load(cls, path: Path) -> VectorIndex:
        if not path.is_file():
            raise FileNotFoundError(f"Vector index not found: {path}")
        return cls.from_dict(json.loads(path.read_text()))

    def search(
        self,
        query_vector: list[float],
        *,
        top_k: int = 20,
        min_relevance: float = 0.0,
    ) -> list[tuple[dict[str, Any], float]]:
        scored: list[tuple[dict[str, Any], float]] = []
        for chunk in self.chunks:
            vec = chunk.get("vector")
            if not vec:
                continue
            rel = cosine(query_vector, vec)
            if rel < min_relevance:
                continue
            scored.append((chunk, rel))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]


def index_path_for_run(data_dir: Path, analysis_run_id: str) -> Path:
    return data_dir / "rag" / f"{analysis_run_id}.json"
