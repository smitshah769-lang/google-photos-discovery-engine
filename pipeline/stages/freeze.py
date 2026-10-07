from __future__ import annotations

from pipeline.db.repository import load_run_spec
from pipeline.export_bundle import write_export_bundle
from pipeline.handoff import handoff_payload
from pipeline.paths import resolve_data_dir
from pipeline.run_context import complete_stage_receipt, utc_now_iso


def run_freeze(
    conn,
    analysis_run_id: str,
    *,
    dry_run: bool = False,
    redact: bool = False,
) -> dict:
    row = conn.execute(
        "SELECT status, frozen_at FROM analysis_run WHERE id = ?",
        (analysis_run_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Unknown analysis run: {analysis_run_id}")
    if row["status"] == "frozen":
        return {
            "stage": "freeze",
            "status": "already_frozen",
            "analysis_run_id": analysis_run_id,
            "frozen_at": row["frozen_at"],
            "message": "Writers cannot mutate a freeze id; start a new collect for a new snapshot.",
        }

    spec = load_run_spec(conn, analysis_run_id)
    export_dir = resolve_data_dir(spec) / "exports" / analysis_run_id

    if dry_run:
        return {
            "stage": "freeze",
            "status": "dry_run",
            "analysis_run_id": analysis_run_id,
            "export_dir": str(export_dir),
            "redact": redact,
            "message": "Would freeze snapshot and write versioned export; no writes performed.",
        }

    now = utc_now_iso()
    complete_stage_receipt(
        conn,
        analysis_run_id,
        "freeze",
        status="success",
        notes=f"Frozen snapshot export at {export_dir}; redact={redact}.",
    )
    conn.execute(
        """
        UPDATE analysis_run SET status = 'frozen', frozen_at = ? WHERE id = ?
        """,
        (now, analysis_run_id),
    )
    conn.commit()

    bundle = write_export_bundle(conn, analysis_run_id, redact=redact, frozen_at=now)
    return {
        "stage": "freeze",
        "status": "frozen",
        "frozen_at": now,
        "export_dir": bundle["export_dir"],
        "redacted": redact,
        "handoff": str(export_dir / "HANDOFF.md"),
    }


def run_export(
    conn,
    analysis_run_id: str,
    *,
    redact: bool = False,
) -> dict:
    """Write (or refresh) the versioned export without changing freeze status."""
    row = conn.execute(
        "SELECT frozen_at FROM analysis_run WHERE id = ?",
        (analysis_run_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Unknown analysis run: {analysis_run_id}")
    bundle = write_export_bundle(
        conn, analysis_run_id, redact=redact, frozen_at=row["frozen_at"]
    )
    return {
        "stage": "export",
        "status": "ok",
        **bundle,
        "handoff": handoff_payload(conn, analysis_run_id),
    }
