import json
import sqlite3
from pathlib import Path

import yaml

from pipeline.adapters.runner import run_all_adapters
from pipeline.db.connection import get_connection, init_database
from pipeline.stages.normalize import run_normalize
from pipeline.run_context import create_analysis_run
from pipeline.taxonomy import load_taxonomy

PROJECT = Path(__file__).resolve().parent.parent


def test_fixture_collect_and_normalize(tmp_path: Path):
    db = tmp_path / "phase1.db"
    init_database(db, load_taxonomy(), {"limitations_seed": [], "open_decisions": {}})
    run_spec = yaml.safe_load((PROJECT / "config" / "run.yaml").read_text())
    run_spec["paths"] = {"data_dir": str(tmp_path), "db_filename": "phase1.db"}
    run_spec["collection"] = {"mode": "fixtures", "fixtures_dir": "tests/fixtures"}

    with get_connection(db) as conn:
        run_id = create_analysis_run(conn, run_spec)
        receipts = run_all_adapters(conn, run_id, run_spec)
        conn.commit()
        assert len(receipts) == 4
        stats = run_normalize(conn, run_id)

    assert stats["normalized_count"] >= 4
    assert stats["relevant_count"] >= 2
    assert stats["meets_target"] is False

    with get_connection(db) as conn:
        row = conn.execute(
            "SELECT coverage_stats_json FROM methodology_snapshot WHERE analysis_run_id = ?",
            (run_id,),
        ).fetchone()
        coverage = json.loads(row["coverage_stats_json"])
        assert coverage["target_miss_visible"] is True
