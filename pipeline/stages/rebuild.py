"""Rebuild aggregates from stored raw + run spec without collecting (architecture §15)."""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from pipeline.config_loader import load_methodology_template, load_run_spec as load_yaml_spec
from pipeline.db.connection import assert_not_frozen, get_connection, init_database
from pipeline.db.repository import load_run_spec
from pipeline.export_bundle import overlay_export_run_spec
from pipeline.paths import db_path
from pipeline.run_context import create_analysis_run
from pipeline.taxonomy import load_taxonomy
from pipeline.stages.aggregate import run_aggregate
from pipeline.stages.analyze import run_analyze
from pipeline.stages.index import run_index
from pipeline.stages.normalize import run_normalize


def clone_run_from_existing(
    conn: sqlite3.Connection,
    source_analysis_run_id: str,
    run_spec: dict[str, Any],
) -> str:
    """Copy source receipts + raw records into a new draft run (frozen source stays intact)."""
    new_id = create_analysis_run(conn, run_spec)
    src_runs = conn.execute(
        """
        SELECT id, source, query_spec_json, started_at, finished_at, item_count, status, notes
        FROM source_run WHERE analysis_run_id = ?
        """,
        (source_analysis_run_id,),
    ).fetchall()
    for srun in src_runs:
        conn.execute(
            """
            UPDATE source_run
            SET query_spec_json = ?, started_at = ?, finished_at = ?,
                item_count = ?, status = ?, notes = ?
            WHERE analysis_run_id = ? AND source = ?
            """,
            (
                srun["query_spec_json"],
                srun["started_at"],
                srun["finished_at"],
                srun["item_count"],
                srun["status"],
                srun["notes"],
                new_id,
                srun["source"],
            ),
        )
        dest = conn.execute(
            "SELECT id FROM source_run WHERE analysis_run_id = ? AND source = ?",
            (new_id, srun["source"]),
        ).fetchone()
        if dest is None:
            continue
        _copy_raw_into_new_run(conn, conn, srun["id"], dest["id"])
    conn.commit()
    return new_id


def run_rebuild(conn: sqlite3.Connection, analysis_run_id: str) -> dict[str, Any]:
    """Recompute normalize → analyze → index → aggregate from stored raw (no collect)."""
    assert_not_frozen(conn, analysis_run_id)
    raw_count = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM raw_record rr
        JOIN source_run sr ON sr.id = rr.source_run_id
        WHERE sr.analysis_run_id = ?
        """,
        (analysis_run_id,),
    ).fetchone()["n"]
    if int(raw_count) == 0:
        raise ValueError(
            f"No stored raw_record rows for {analysis_run_id}. "
            "Rebuild needs raw + run spec; collect or import-raw first."
        )
    results = {
        "normalize": run_normalize(conn, analysis_run_id),
        "analyze": run_analyze(conn, analysis_run_id),
        "index": run_index(conn, analysis_run_id),
        "aggregate": run_aggregate(conn, analysis_run_id),
    }
    return {
        "stage": "rebuild",
        "status": "success",
        "analysis_run_id": analysis_run_id,
        "raw_count": int(raw_count),
        "collected": False,
        "stages": {k: v.get("status") for k, v in results.items()},
        "relevant_count": (results["normalize"] or {}).get("relevant_count"),
    }


def _copy_raw_into_new_run(
    src: sqlite3.Connection,
    dest: sqlite3.Connection,
    source_run_id: str,
    dest_source_run_id: str,
) -> int:
    count = 0
    rows = src.execute(
        """
        SELECT source_native_id, payload_json, payload_path, captured_at
        FROM raw_record WHERE source_run_id = ?
        """,
        (source_run_id,),
    ).fetchall()
    for row in rows:
        payload = row["payload_json"]
        if not payload and row["payload_path"]:
            path = Path(row["payload_path"])
            if path.is_file():
                payload = path.read_text(encoding="utf-8")
        dest.execute(
            """
            INSERT INTO raw_record
              (id, source_run_id, source_native_id, payload_json, payload_path, captured_at)
            VALUES (?, ?, ?, ?, NULL, ?)
            """,
            (
                str(uuid.uuid4()),
                dest_source_run_id,
                row["source_native_id"],
                payload,
                row["captured_at"],
            ),
        )
        count += 1
    return count


def rebuild_from_export(
    export_dir: Path,
    *,
    dest_run_spec: dict[str, Any] | None = None,
    dest_run_spec_path: Path | None = None,
) -> dict[str, Any]:
    """Create a new analysis run from an export's raw + run.yaml, then rebuild aggregates."""
    export_dir = export_dir.resolve()
    src_db = export_dir / "snapshot.db"
    if not src_db.is_file():
        raise ValueError(f"Export is missing snapshot.db: {src_db}")
    freeze_meta = {}
    freeze_file = export_dir / "FREEZE.json"
    if freeze_file.is_file():
        freeze_meta = json.loads(freeze_file.read_text())
    export_yaml = export_dir / "run.yaml"
    spec = dest_run_spec
    if spec is None and export_yaml.is_file():
        spec = load_yaml_spec(export_yaml)
    if spec is None:
        spec = load_yaml_spec(dest_run_spec_path)
    dest_db = db_path(spec)
    init_database(dest_db, load_taxonomy(), load_methodology_template())
    with get_connection(src_db) as src, get_connection(dest_db) as dest:
        source_run_id_old = freeze_meta.get("run_id")
        if not source_run_id_old:
            row = src.execute("SELECT id FROM analysis_run ORDER BY created_at DESC LIMIT 1").fetchone()
            if row is None:
                raise ValueError("Export snapshot has no analysis_run")
            source_run_id_old = row["id"]
        old_spec = load_run_spec(src, source_run_id_old)
        merged = dict(old_spec)
        merged.update(spec)
        new_id = create_analysis_run(dest, merged)
        copied = 0
        src_runs = src.execute(
            """
            SELECT id, source, query_spec_json, started_at, finished_at, item_count, status, notes
            FROM source_run WHERE analysis_run_id = ?
            """,
            (source_run_id_old,),
        ).fetchall()
        for srun in src_runs:
            dest.execute(
                """
                UPDATE source_run
                SET query_spec_json = ?, started_at = ?, finished_at = ?,
                    item_count = ?, status = ?, notes = ?
                WHERE analysis_run_id = ? AND source = ?
                """,
                (
                    srun["query_spec_json"],
                    srun["started_at"],
                    srun["finished_at"],
                    srun["item_count"],
                    srun["status"],
                    srun["notes"],
                    new_id,
                    srun["source"],
                ),
            )
            dest_sr = dest.execute(
                "SELECT id FROM source_run WHERE analysis_run_id = ? AND source = ?",
                (new_id, srun["source"]),
            ).fetchone()
            copied += _copy_raw_into_new_run(src, dest, srun["id"], dest_sr["id"])
        dest.commit()
        rebuilt = run_rebuild(dest, new_id)
    return {
        "stage": "rebuild_from_export",
        "status": "success",
        "source_export": str(export_dir),
        "source_run_id": source_run_id_old,
        "analysis_run_id": new_id,
        "raw_copied": copied,
        "rebuild": rebuilt,
    }


def load_serve_spec_from_export(export_dir: Path, fallback_spec: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    export_dir = export_dir.resolve()
    freeze_file = export_dir / "FREEZE.json"
    if not freeze_file.is_file():
        raise ValueError(f"Missing FREEZE.json in {export_dir}")
    meta = json.loads(freeze_file.read_text())
    run_id = str(meta["run_id"])
    spec = overlay_export_run_spec(fallback_spec, export_dir)
    return run_id, spec
