from __future__ import annotations

import json
import sqlite3
from typing import Any


def get_run_status(conn: sqlite3.Connection, analysis_run_id: str) -> dict[str, Any]:
    run = conn.execute(
        """
        SELECT id, status, frozen_at, corpus_target_relevant, created_at
        FROM analysis_run WHERE id = ?
        """,
        (analysis_run_id,),
    ).fetchone()
    if run is None:
        raise ValueError(f"Unknown analysis run: {analysis_run_id}")

    sources = [
        dict(row)
        for row in conn.execute(
            """
            SELECT source, status, item_count, notes, started_at, finished_at
            FROM source_run WHERE analysis_run_id = ?
            ORDER BY source
            """,
            (analysis_run_id,),
        ).fetchall()
    ]

    raw_by_source = {
        row["source"]: row["cnt"]
        for row in conn.execute(
            """
            SELECT sr.source AS source, COUNT(rr.id) AS cnt
            FROM source_run sr
            LEFT JOIN raw_record rr ON rr.source_run_id = sr.id
            WHERE sr.analysis_run_id = ?
            GROUP BY sr.source
            """,
            (analysis_run_id,),
        ).fetchall()
    }

    feedback = conn.execute(
        """
        SELECT
          COUNT(*) AS total,
          SUM(CASE WHEN relevance_label = 'retrieval_related' THEN 1 ELSE 0 END) AS relevant,
          SUM(CASE WHEN relevance_label = 'ambiguous' THEN 1 ELSE 0 END) AS ambiguous,
          SUM(CASE WHEN relevance_label = 'unrelated' THEN 1 ELSE 0 END) AS unrelated
        FROM feedback_item WHERE analysis_run_id = ?
        """,
        (analysis_run_id,),
    ).fetchone()

    coverage_row = conn.execute(
        "SELECT coverage_stats_json FROM methodology_snapshot WHERE analysis_run_id = ?",
        (analysis_run_id,),
    ).fetchone()
    coverage = None
    if coverage_row and coverage_row["coverage_stats_json"]:
        coverage = json.loads(coverage_row["coverage_stats_json"])

    target = int(run["corpus_target_relevant"])
    relevant = int(feedback["relevant"] or 0) if feedback else 0

    return {
        "analysis_run_id": analysis_run_id,
        "status": run["status"],
        "frozen_at": run["frozen_at"],
        "created_at": run["created_at"],
        "corpus_target_relevant": target,
        "source_runs": sources,
        "raw_record_counts": raw_by_source,
        "feedback_items": {
            "total": int(feedback["total"] or 0) if feedback else 0,
            "relevant": relevant,
            "ambiguous": int(feedback["ambiguous"] or 0) if feedback else 0,
            "unrelated": int(feedback["unrelated"] or 0) if feedback else 0,
            "meets_target": relevant >= target,
        },
        "coverage_stats": coverage,
    }
