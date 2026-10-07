from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.config_loader import load_methodology_template, load_run_spec, run_spec_as_json
from pipeline.db.connection import assert_not_frozen, get_connection, init_database, json_dumps
from pipeline.paths import db_path, resolve_data_dir
from pipeline.taxonomy import load_taxonomy


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


SOURCES = ("app_store", "play_store", "reddit", "help_community")
PIPELINE_STAGES = ("normalize", "analyze", "index", "aggregate", "freeze")


def ensure_database(run_spec_path: Path | None = None) -> Path:
    run_spec = load_run_spec(run_spec_path)
    taxonomy = load_taxonomy()
    methodology = load_methodology_template()
    db_file = db_path(run_spec)
    init_database(db_file, taxonomy, methodology)
    raw_dir = resolve_data_dir(run_spec) / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    return db_file


def create_analysis_run(
    conn: sqlite3.Connection,
    run_spec: dict[str, Any],
    run_id: str | None = None,
) -> str:
    analysis = run_spec.get("analysis") or {}
    run_uuid = run_id or str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO analysis_run
          (id, run_spec_json, taxonomy_version, created_at, frozen_at, status, corpus_target_relevant)
        VALUES (?, ?, ?, ?, NULL, 'draft', ?)
        """,
        (
            run_uuid,
            run_spec_as_json(run_spec),
            str(analysis.get("taxonomy_version", "v0")),
            utc_now_iso(),
            int(analysis.get("corpus_target_relevant", 500)),
        ),
    )
    _seed_source_runs(conn, run_uuid, run_spec)
    _seed_stage_receipts(conn, run_uuid)
    _seed_methodology_snapshot(conn, run_uuid, run_spec)
    conn.commit()
    return run_uuid


def _query_spec_for_source(source: str, run_spec: dict[str, Any]) -> dict[str, Any]:
    if source == "app_store":
        return run_spec.get("app_store") or {}
    if source == "play_store":
        return run_spec.get("play_store") or {}
    if source == "reddit":
        return run_spec.get("reddit") or {}
    if source == "help_community":
        return run_spec.get("help_community") or {}
    raise ValueError(source)


def _seed_source_runs(conn: sqlite3.Connection, analysis_run_id: str, run_spec: dict[str, Any]) -> None:
    now = utc_now_iso()
    for source in SOURCES:
        conn.execute(
            """
            INSERT INTO source_run
              (id, analysis_run_id, source, query_spec_json, started_at, finished_at,
               item_count, status, notes)
            VALUES (?, ?, ?, ?, ?, NULL, 0, 'pending', ?)
            """,
            (
                str(uuid.uuid4()),
                analysis_run_id,
                source,
                json_dumps(_query_spec_for_source(source, run_spec)),
                now,
                "Pending collection.",
            ),
        )


def _seed_stage_receipts(conn: sqlite3.Connection, analysis_run_id: str) -> None:
    now = utc_now_iso()
    for stage in PIPELINE_STAGES:
        conn.execute(
            """
            INSERT INTO stage_receipt
              (id, analysis_run_id, stage, started_at, finished_at, status, item_count, notes)
            VALUES (?, ?, ?, ?, NULL, 'pending', 0, ?)
            """,
            (
                str(uuid.uuid4()),
                analysis_run_id,
                stage,
                now,
                "Phase 0 placeholder; stage logic arrives in later phases.",
            ),
        )


def _seed_methodology_snapshot(
    conn: sqlite3.Connection,
    analysis_run_id: str,
    run_spec: dict[str, Any],
) -> None:
    template = load_methodology_template()
    models = run_spec.get("models") or {}
    conn.execute(
        """
        INSERT INTO methodology_snapshot
          (id, analysis_run_id, run_id, prompts_json, model_ids_json, coverage_stats_json,
           bias_notes, limitations_json, open_decisions_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid.uuid4()),
            analysis_run_id,
            analysis_run_id,
            json_dumps(
                {
                    "relevance": models.get("relevance"),
                    "classification": models.get("classification"),
                }
            ),
            json_dumps(
                {
                    "embedding": models.get("embedding"),
                    "classification": models.get("classification"),
                }
            ),
            json_dumps({"relevant_count": 0, "raw_by_source": {}, "status": "phase_0"}),
            "Public-feedback bias; see limitations list.",
            json_dumps(template.get("limitations_seed") or []),
            json_dumps(template.get("open_decisions") or {}),
            utc_now_iso(),
        ),
    )


def complete_stage_receipt(
    conn: sqlite3.Connection,
    analysis_run_id: str,
    stage: str,
    *,
    status: str = "skipped",
    item_count: int = 0,
    notes: str,
) -> None:
    assert_not_frozen(conn, analysis_run_id)
    conn.execute(
        """
        UPDATE stage_receipt
        SET finished_at = ?, status = ?, item_count = ?, notes = ?
        WHERE analysis_run_id = ? AND stage = ?
        """,
        (utc_now_iso(), status, item_count, notes, analysis_run_id, stage),
    )


def complete_source_runs_noop(
    conn: sqlite3.Connection,
    analysis_run_id: str,
    notes: str,
) -> None:
    assert_not_frozen(conn, analysis_run_id)
    now = utc_now_iso()
    conn.execute(
        """
        UPDATE source_run
        SET finished_at = ?, status = 'skipped', item_count = 0, notes = ?
        WHERE analysis_run_id = ?
        """,
        (now, notes, analysis_run_id),
    )
