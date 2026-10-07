import json
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent


def _run(args: list[str], env_db_dir: Path) -> subprocess.CompletedProcess:
    run_spec = PROJECT / "config" / "run.yaml"
    # Use a temp run spec path by copying - tests use monkeypatched path via env
    import yaml

    spec = yaml.safe_load(run_spec.read_text())
    spec["paths"] = {"data_dir": str(env_db_dir), "db_filename": "cli_test.db"}
    spec["collection"] = {"mode": "fixtures", "fixtures_dir": "tests/fixtures"}
    spec.setdefault("models", {})
    spec["models"]["embedding"] = {"provider": "hashing", "model_id": "hashing-v0"}
    spec["models"]["classification"] = {
        "provider": "heuristic",
        "model_id": "heuristic_v0",
        "temperature": 0.0,
        "prompt_version": "classify_v0",
    }
    spec_path = env_db_dir / "run.yaml"
    spec_path.write_text(yaml.dump(spec))
    cmd = [sys.executable, "-m", "pipeline", "--run-spec", str(spec_path)] + args
    return subprocess.run(cmd, cwd=PROJECT, capture_output=True, text=True, check=True)


def test_stages_write_receipts(tmp_path: Path):
    _run(["init-db"], tmp_path)
    out = _run(["new-run"], tmp_path)
    run_id = out.stdout.strip()

    _run(["collect", run_id], tmp_path)
    _run(["normalize", run_id], tmp_path)
    _run(["analyze", run_id], tmp_path)

    import sqlite3

    db = tmp_path / "cli_test.db"
    conn = sqlite3.connect(db)
    sources = conn.execute(
        "SELECT COUNT(*) FROM source_run WHERE analysis_run_id = ?", (run_id,)
    ).fetchone()[0]
    stages = conn.execute(
        "SELECT status, notes FROM stage_receipt WHERE analysis_run_id = ? AND stage = 'normalize'",
        (run_id,),
    ).fetchone()
    analyze = conn.execute(
        "SELECT status, notes FROM stage_receipt WHERE analysis_run_id = ? AND stage = 'analyze'",
        (run_id,),
    ).fetchone()
    conn.close()

    assert sources == 4
    assert stages[0] == "success"
    assert "relevant=" in stages[1]
    assert analyze[0] == "success"
    assert "Classified" in analyze[1]
