from __future__ import annotations

import json
import sqlite3
from typing import Any

from pipeline.analysis.embeddings import embed_texts
from pipeline.analysis.inference import InferenceUnavailable
from pipeline.db.connection import assert_not_frozen, json_dumps
from pipeline.db.repository import load_run_spec, update_methodology_coverage
from pipeline.paths import resolve_data_dir
from pipeline.rag.chunk import build_chunk_records
from pipeline.rag.store import VectorIndex, index_path_for_run
from pipeline.run_context import complete_stage_receipt, utc_now_iso


def _merge_coverage(conn: sqlite3.Connection, analysis_run_id: str, extra: dict[str, Any]) -> None:
    row = conn.execute(
        "SELECT coverage_stats_json FROM methodology_snapshot WHERE analysis_run_id = ?",
        (analysis_run_id,),
    ).fetchone()
    base: dict[str, Any] = {}
    if row and row["coverage_stats_json"]:
        base = json.loads(row["coverage_stats_json"])
    base.update(extra)
    update_methodology_coverage(conn, analysis_run_id, base)


def run_index(conn: sqlite3.Connection, analysis_run_id: str) -> dict:
    assert_not_frozen(conn, analysis_run_id)
    run_spec = load_run_spec(conn, analysis_run_id)
    models = run_spec.get("models") or {}
    embed_cfg = models.get("embedding") or {}
    embed_provider = str(embed_cfg.get("provider") or "hashing").lower()
    embed_model = str(embed_cfg.get("model_id") or "hashing-v0")

    conn.execute(
        "DELETE FROM embedding_chunk WHERE analysis_run_id = ?",
        (analysis_run_id,),
    )

    chunks = build_chunk_records(conn, analysis_run_id)
    if not chunks:
        complete_stage_receipt(
            conn,
            analysis_run_id,
            "index",
            status="partial",
            item_count=0,
            notes="No citable retrieval_related items to index.",
        )
        conn.commit()
        return {"stage": "index", "status": "partial", "item_count": 0}

    try:
        vectors = embed_texts(
            [c.get("embedding_text") or c["text"] for c in chunks],
            provider=embed_provider,
            model_id=embed_model,
        )
    except InferenceUnavailable as exc:
        complete_stage_receipt(
            conn,
            analysis_run_id,
            "index",
            status="failed",
            notes=str(exc),
        )
        conn.commit()
        raise

    for chunk, vector in zip(chunks, vectors):
        chunk["vector"] = vector
        meta = chunk["metadata"]
        conn.execute(
            """
            INSERT INTO embedding_chunk
              (id, analysis_run_id, feedback_item_id, text, vector_id, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                chunk["id"],
                analysis_run_id,
                chunk["feedback_item_id"],
                chunk["text"],
                chunk["id"],
                json_dumps(meta),
            ),
        )

    index = VectorIndex(
        analysis_run_id=analysis_run_id,
        embedding_provider=embed_provider,
        embedding_model_id=embed_model,
        chunks=chunks,
    )
    index_path = index_path_for_run(resolve_data_dir(run_spec), analysis_run_id)
    index.save(index_path)

    frozen_embed = {"provider": embed_provider, "model_id": embed_model}
    row = conn.execute(
        "SELECT model_ids_json FROM methodology_snapshot WHERE analysis_run_id = ?",
        (analysis_run_id,),
    ).fetchone()
    model_ids: dict[str, Any] = {}
    if row and row["model_ids_json"]:
        model_ids = json.loads(row["model_ids_json"])
    model_ids["embedding"] = frozen_embed
    model_ids["embedding_frozen_at"] = utc_now_iso()
    conn.execute(
        """
        UPDATE methodology_snapshot
        SET model_ids_json = ?
        WHERE analysis_run_id = ?
        """,
        (json_dumps(model_ids), analysis_run_id),
    )

    _merge_coverage(
        conn,
        analysis_run_id,
        {
            "status": "phase_3",
            "rag_index_path": str(index_path),
            "embedding_model": frozen_embed,
            "chunk_count": len(chunks),
        },
    )

    complete_stage_receipt(
        conn,
        analysis_run_id,
        "index",
        status="success",
        item_count=len(chunks),
        notes=f"Indexed {len(chunks)} chunks with {embed_provider}/{embed_model} → {index_path.name}",
    )
    conn.commit()
    return {
        "stage": "index",
        "status": "success",
        "item_count": len(chunks),
        "index_path": str(index_path),
        "embedding_model": frozen_embed,
    }
