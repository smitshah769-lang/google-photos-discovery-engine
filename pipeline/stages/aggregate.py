from __future__ import annotations

import json
import sqlite3

from pipeline.db.connection import assert_not_frozen
from pipeline.db.repository import load_run_spec
from pipeline.paths import resolve_data_dir
from pipeline.run_context import complete_stage_receipt
from pipeline.serve.read import insights


def run_aggregate(conn: sqlite3.Connection, analysis_run_id: str) -> dict:
    assert_not_frozen(conn, analysis_run_id)
    payload = insights(conn, analysis_run_id)
    spec = load_run_spec(conn, analysis_run_id)
    out_dir = resolve_data_dir(spec) / "aggregates"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{analysis_run_id}.json"
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    complete_stage_receipt(
        conn,
        analysis_run_id,
        "aggregate",
        status="success",
        item_count=int(payload.get("relevant_count") or 0),
        notes=(
            f"Precomputed dashboard aggregates; relevant={payload.get('relevant_count')} "
            f"categories={len(payload.get('categories') or [])}."
        ),
    )
    conn.commit()
    return {
        "stage": "aggregate",
        "status": "success",
        "item_count": payload.get("relevant_count"),
        "path": str(path),
        "incomplete_source_mix": payload.get("incomplete_source_mix"),
        "meets_target": payload.get("meets_target"),
    }
