from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from pipeline.adapters.types import CollectedItem
from pipeline.db.connection import json_dumps
from pipeline.run_context import utc_now_iso


def get_source_run_id(conn: sqlite3.Connection, analysis_run_id: str, source: str) -> str:
    row = conn.execute(
        """
        SELECT id FROM source_run
        WHERE analysis_run_id = ? AND source = ?
        """,
        (analysis_run_id, source),
    ).fetchone()
    if row is None:
        raise ValueError(f"No source_run for {analysis_run_id} / {source}")
    return row["id"]


def mark_source_run_running(conn: sqlite3.Connection, analysis_run_id: str, source: str) -> None:
    conn.execute(
        """
        UPDATE source_run
        SET status = 'running', started_at = ?
        WHERE analysis_run_id = ? AND source = ?
        """,
        (utc_now_iso(), analysis_run_id, source),
    )


def finalize_source_run(
    conn: sqlite3.Connection,
    analysis_run_id: str,
    source: str,
    *,
    status: str,
    item_count: int,
    notes: str,
) -> None:
    conn.execute(
        """
        UPDATE source_run
        SET finished_at = ?, status = ?, item_count = ?, notes = ?
        WHERE analysis_run_id = ? AND source = ?
        """,
        (utc_now_iso(), status, item_count, notes, analysis_run_id, source),
    )


def insert_collected_items(
    conn: sqlite3.Connection,
    source_run_id: str,
    items: list[CollectedItem],
) -> int:
    now = utc_now_iso()
    rows = 0
    for item in items:
        conn.execute(
            """
            INSERT INTO raw_record
              (id, source_run_id, source_native_id, payload_json, payload_path, captured_at)
            VALUES (?, ?, ?, ?, NULL, ?)
            """,
            (
                str(uuid.uuid4()),
                source_run_id,
                item.native_id,
                json_dumps(item.to_payload()),
                now,
            ),
        )
        rows += 1
    return rows


def load_run_spec(conn: sqlite3.Connection, analysis_run_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT run_spec_json FROM analysis_run WHERE id = ?",
        (analysis_run_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Unknown analysis run: {analysis_run_id}")
    return json.loads(row["run_spec_json"])


def update_methodology_coverage(
    conn: sqlite3.Connection,
    analysis_run_id: str,
    coverage_stats: dict[str, Any],
) -> None:
    conn.execute(
        """
        UPDATE methodology_snapshot
        SET coverage_stats_json = ?
        WHERE analysis_run_id = ?
        """,
        (json_dumps(coverage_stats), analysis_run_id),
    )


def clear_items_and_derived(conn: sqlite3.Connection, analysis_run_id: str) -> None:
    """Delete feedback items and rows that reference them so normalize can re-run."""
    conn.execute(
        """
        DELETE FROM classification
        WHERE feedback_item_id IN (
          SELECT id FROM feedback_item WHERE analysis_run_id = ?
        )
        """,
        (analysis_run_id,),
    )
    conn.execute("DELETE FROM embedding_chunk WHERE analysis_run_id = ?", (analysis_run_id,))
    conn.execute("DELETE FROM cluster WHERE analysis_run_id = ?", (analysis_run_id,))
    conn.execute("DELETE FROM category_aggregate WHERE analysis_run_id = ?", (analysis_run_id,))
    conn.execute("DELETE FROM feedback_item WHERE analysis_run_id = ?", (analysis_run_id,))
