from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any


def build_chunk_records(
    conn: sqlite3.Connection,
    analysis_run_id: str,
) -> list[dict[str, Any]]:
    """
    One chunk per retrieval_related feedback item with classifications joined.
    Items without source_url are excluded from RAG (edge §7).
    """
    rows = conn.execute(
        """
        SELECT
          f.id AS feedback_item_id,
          f.source,
          f.source_url,
          f.authored_at,
          f.text,
          f.thread_context
        FROM feedback_item f
        WHERE f.analysis_run_id = ?
          AND f.relevance_label = 'retrieval_related'
          AND f.source_url IS NOT NULL
          AND TRIM(f.source_url) != ''
        """,
        (analysis_run_id,),
    ).fetchall()

    cls_rows = conn.execute(
        """
        SELECT c.feedback_item_id, c.taxonomy_node_id, c.confidence, c.snippets_json
        FROM classification c
        JOIN feedback_item f ON f.id = c.feedback_item_id
        WHERE f.analysis_run_id = ?
        """,
        (analysis_run_id,),
    ).fetchall()

    by_item: dict[str, list[sqlite3.Row]] = {}
    for row in cls_rows:
        by_item.setdefault(row["feedback_item_id"], []).append(row)

    sev_rows = conn.execute(
        """
        SELECT taxonomy_node_id, severity
        FROM category_aggregate
        WHERE analysis_run_id = ?
        """,
        (analysis_run_id,),
    ).fetchall()
    sev_by_node = {r["taxonomy_node_id"]: float(r["severity"] or 0.0) for r in sev_rows}

    chunks: list[dict[str, Any]] = []
    for row in rows:
        item_id = row["feedback_item_id"]
        body = (row["text"] or "").strip()
        if row["thread_context"]:
            body = f"{body}\n\n--- thread context ---\n{row['thread_context']}".strip()
        if not body:
            continue

        labels = by_item.get(item_id, [])
        categories = [lab["taxonomy_node_id"] for lab in labels]
        confidences = [float(lab["confidence"] or 0.0) for lab in labels]
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
        snippet_candidates: list[str] = []
        for lab in labels:
            try:
                snippet_candidates.extend(json.loads(lab["snippets_json"] or "[]"))
            except json.JSONDecodeError:
                pass

        severities = [sev_by_node.get(c, 0.0) for c in categories]
        impact = max(severities) if severities else 0.0

        theme_prefix = ", ".join(categories[:6]) if categories else "retrieval"
        embedding_text = (
            f"Google Photos search and retrieval feedback. Themes: {theme_prefix}. {body}"
        )[:4000]

        chunk_id = str(uuid.uuid4())
        chunks.append(
            {
                "id": chunk_id,
                "feedback_item_id": item_id,
                "text": body,
                "embedding_text": embedding_text,
                "stored_text": row["text"] or "",
                "metadata": {
                    "item_id": item_id,
                    "source": row["source"],
                    "source_url": row["source_url"],
                    "authored_at": row["authored_at"],
                    "categories": categories,
                    "confidence": round(avg_conf, 4),
                    "impact": round(impact, 4),
                    "snippet_candidates": snippet_candidates[:5],
                },
            }
        )
    return chunks
