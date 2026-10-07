from __future__ import annotations

import sqlite3

from pipeline.analysis.curated_labels import load_curated_labels, resolve_curated_path
from pipeline.db.connection import assert_not_frozen
from pipeline.db.repository import clear_items_and_derived, load_run_spec, update_methodology_coverage
from pipeline.normalize.feedback_builder import normalize_analysis_run
from pipeline.run_context import complete_stage_receipt


def run_normalize(conn: sqlite3.Connection, analysis_run_id: str) -> dict:
    assert_not_frozen(conn, analysis_run_id)
    run_spec = load_run_spec(conn, analysis_run_id)
    clear_items_and_derived(conn, analysis_run_id)
    curated = load_curated_labels(resolve_curated_path(run_spec))
    stats = normalize_analysis_run(conn, analysis_run_id, curated)
    stats["curated_label_count"] = len(curated)

    raw_by_source = {
        row["source"]: row["item_count"]
        for row in conn.execute(
            """
            SELECT source, item_count FROM source_run WHERE analysis_run_id = ?
            """,
            (analysis_run_id,),
        ).fetchall()
    }
    target = stats["corpus_target_relevant"]
    coverage = {
        "raw_by_source": raw_by_source,
        "normalized_count": stats["normalized_count"],
        "relevant_count": stats["relevant_count"],
        "ambiguous_count": stats["ambiguous_count"],
        "unrelated_count": stats["unrelated_count"],
        "corpus_target_relevant": target,
        "meets_target": stats["meets_target"],
        "target_miss_visible": not stats["meets_target"],
        "status": "phase_1",
    }
    update_methodology_coverage(conn, analysis_run_id, coverage)

    notes = (
        f"Normalized {stats['normalized_count']} items; "
        f"relevant={stats['relevant_count']} (target {target})."
    )
    if not stats["meets_target"]:
        notes += " Target miss recorded on methodology snapshot."

    complete_stage_receipt(
        conn,
        analysis_run_id,
        "normalize",
        status="success",
        item_count=stats["relevant_count"],
        notes=notes,
    )
    conn.commit()
    return {"stage": "normalize", "status": "success", **stats, "collection_mode": (run_spec.get("collection") or {}).get("mode", "live")}
