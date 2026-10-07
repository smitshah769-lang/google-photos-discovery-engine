from pathlib import Path

from pipeline.db.connection import get_connection, init_database
from pipeline.run_context import create_analysis_run
from pipeline.taxonomy import load_taxonomy


def test_init_empty_snapshot_db(tmp_path: Path):
    db_file = tmp_path / "test.db"
    init_database(db_file, load_taxonomy(), {"open_decisions": {}, "limitations_seed": []})

    with get_connection(db_file) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "analysis_run" in tables
    assert "methodology_snapshot" in tables
    assert "taxonomy_node" in tables


def test_frozen_run_rejects_mutations(tmp_path: Path):
    db_file = tmp_path / "test.db"
    init_database(db_file, load_taxonomy(), {"open_decisions": {}, "limitations_seed": []})
    run_spec = {"analysis": {"taxonomy_version": "v0", "corpus_target_relevant": 500}}

    with get_connection(db_file) as conn:
        run_id = create_analysis_run(conn, run_spec)
        conn.execute(
            "UPDATE analysis_run SET status = 'frozen', frozen_at = '2026-01-01T00:00:00+00:00' WHERE id = ?",
            (run_id,),
        )
        conn.commit()

    from pipeline.db.connection import assert_not_frozen

    with get_connection(db_file) as conn:
        try:
            assert_not_frozen(conn, run_id)
            raised = False
        except RuntimeError:
            raised = True
    assert raised
