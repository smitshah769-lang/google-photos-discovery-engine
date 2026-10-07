from __future__ import annotations

import sqlite3

from pipeline.adapters.runner import run_all_adapters
from pipeline.db.connection import assert_not_frozen
from pipeline.db.repository import load_run_spec
from pipeline.run_context import utc_now_iso


def _merge_live_adapter_config(run_spec: dict, live_spec: dict | None) -> dict:
    """Overlay adapter sections from config/run.yaml onto the run snapshot."""
    if not live_spec:
        return run_spec
    merged = dict(run_spec)
    for key in ("app_store", "play_store", "reddit", "help_community"):
        if key not in live_spec:
            continue
        merged[key] = {**(merged.get(key) or {}), **(live_spec.get(key) or {})}
    return merged


def _with_fixtures_mode(run_spec: dict, use_fixtures: bool) -> dict:
    if not use_fixtures:
        return run_spec
    spec = dict(run_spec)
    collection = dict(spec.get("collection") or {})
    collection["mode"] = "fixtures"
    collection.setdefault("fixtures_dir", "tests/fixtures")
    spec["collection"] = collection
    return spec


def run_collect(
    conn: sqlite3.Connection,
    analysis_run_id: str,
    *,
    use_fixtures: bool = False,
    only: str | None = None,
    live_run_spec: dict | None = None,
) -> dict:
    assert_not_frozen(conn, analysis_run_id)
    run_spec = _with_fixtures_mode(load_run_spec(conn, analysis_run_id), use_fixtures)
    run_spec = _merge_live_adapter_config(run_spec, live_run_spec)
    receipts = run_all_adapters(conn, analysis_run_id, run_spec, only=only)
    conn.commit()
    return {
        "stage": "collect",
        "finished_at": utc_now_iso(),
        "receipts": receipts,
    }
