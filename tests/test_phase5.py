import json
from pathlib import Path

from pipeline.db.connection import assert_not_frozen, get_connection, init_database
from pipeline.export_bundle import redact_obj
from pipeline.handoff import known_gaps
from pipeline.serve.auth import authorized_basic, bind_without_auth_warning, serving_credentials
from pipeline.serve.read import methodology
from pipeline.stages.analyze import run_analyze
from pipeline.stages.freeze import run_export, run_freeze
from pipeline.stages.index import run_index
from pipeline.stages.normalize import run_normalize
from pipeline.stages.rebuild import rebuild_from_export, run_rebuild
from pipeline.run_context import create_analysis_run
from pipeline.taxonomy import load_taxonomy


def _spec(tmp_path: Path, db_name: str = "snap.db") -> dict:
    return {
        "analysis": {
            "taxonomy_version": "v0",
            "corpus_target_relevant": 500,
            "gold_set": str(tmp_path / "gold.json"),
            "cluster_similarity_threshold": 0.3,
        },
        "paths": {"data_dir": str(tmp_path), "db_filename": db_name},
        "rag": {"top_k": 10, "min_relevance": 0.05},
        "models": {
            "classification": {
                "provider": "heuristic",
                "model_id": "heuristic_v0",
                "temperature": 0.0,
                "prompt_version": "classify_v0",
            },
            "embedding": {"provider": "hashing", "model_id": "hashing-v0"},
        },
        "date_window": {"after": "2020-01-01", "before": None},
        "serving": {"bind_host": "127.0.0.1", "auth": {"enabled": False}},
    }


def _seed_with_raw(db_path: Path, tmp_path: Path) -> tuple[str, dict]:
    init_database(db_path, load_taxonomy(), {"open_decisions": {}, "limitations_seed": []})
    (tmp_path / "gold.json").write_text(json.dumps({"items": []}))
    spec = _spec(tmp_path, db_path.name)
    with get_connection(db_path) as conn:
        run_id = create_analysis_run(conn, spec)
        payload = {
            "source": "reddit",
            "native_id": "abc123",
            "text": "I cannot find my old pictures from the trip even when I scroll years view.",
            "source_url": "https://reddit.test/comments/abc",
            "authored_at": "2024-06-01",
            "locale": "en",
            "has_user_text": True,
            "author_handle": "secret_user",
            "author": {"name": "Secret User"},
        }
        source_run = conn.execute(
            "SELECT id FROM source_run WHERE analysis_run_id = ? AND source = 'reddit'",
            (run_id,),
        ).fetchone()["id"]
        conn.execute(
            """
            INSERT INTO raw_record (id, source_run_id, source_native_id, payload_json, captured_at)
            VALUES ('raw-1', ?, 'abc123', ?, '2026-01-01T00:00:00+00:00')
            """,
            (source_run, json.dumps(payload)),
        )
        conn.execute(
            """
            UPDATE source_run SET status = 'success', item_count = 1, notes = 'ok'
            WHERE analysis_run_id = ? AND source IN ('app_store', 'play_store', 'reddit')
            """,
            (run_id,),
        )
        conn.execute(
            """
            UPDATE source_run SET status = 'gap', item_count = 0,
              notes = 'Arctic Shift outage; CSE quota exhausted on community'
            WHERE analysis_run_id = ? AND source = 'help_community'
            """,
            (run_id,),
        )
        conn.commit()
        run_normalize(conn, run_id)
        run_analyze(conn, run_id)
        run_index(conn, run_id)
    return run_id, spec


def test_bind_warning_only_without_auth():
    assert bind_without_auth_warning("0.0.0.0", None)
    assert bind_without_auth_warning("0.0.0.0", ("u", "p")) is None
    assert bind_without_auth_warning("127.0.0.1", None) is None


def test_basic_auth_header(monkeypatch):
    monkeypatch.delenv("DISCOVERY_BASIC_USER", raising=False)
    monkeypatch.delenv("DISCOVERY_BASIC_PASSWORD", raising=False)
    spec = {"serving": {"auth": {"enabled": True, "user": "reviewer", "password": "s3cret"}}}
    creds = serving_credentials(spec)
    assert creds == ("reviewer", "s3cret")
    import base64

    good = "Basic " + base64.b64encode(b"reviewer:s3cret").decode()
    bad = "Basic " + base64.b64encode(b"reviewer:nope").decode()
    assert authorized_basic(good, creds) is True
    assert authorized_basic(bad, creds) is False
    assert authorized_basic(None, creds) is False
    assert authorized_basic(None, None) is True


def test_redact_obj_strips_handles():
    out = redact_obj({"author_handle": "bob", "text": "keep", "author": {"name": "Bob"}})
    assert out["author_handle"] == "[redacted]"
    assert out["author"] == "[redacted]"
    assert out["text"] == "keep"


def test_known_gaps_from_receipts():
    receipts = [
        {"source": "help_community", "status": "gap", "notes": "CSE quota exhausted"},
        {"source": "reddit", "status": "success", "notes": "ok"},
    ]
    gaps = known_gaps(receipts, relevant_count=12, corpus_target=500, index_exists=False)
    kinds = {g["kind"] for g in gaps}
    assert "adapter" in kinds
    assert "cse_quota" in kinds
    assert "corpus_target" in kinds
    assert "vector_index" in kinds


def test_methodology_non_claims_and_handoff_export(tmp_path: Path):
    db_path = tmp_path / "snap.db"
    run_id, _ = _seed_with_raw(db_path, tmp_path)
    with get_connection(db_path) as conn:
        method = methodology(conn, run_id)
        assert any("not a census" in c.lower() for c in method["non_claims"])
        assert any("Phase 2" in c for c in method["out_of_repo_scope"])
        freeze = run_freeze(conn, run_id, redact=True)
    export = Path(freeze["export_dir"])
    assert (export / "HANDOFF.md").is_file()
    assert (export / "REBUILD.md").is_file()
    assert "not a census" in (export / "HANDOFF.md").read_text().lower()
    with get_connection(export / "snapshot.db") as exported:
        raw = exported.execute("SELECT payload_json FROM raw_record").fetchone()
        payload = json.loads(raw["payload_json"])
        assert payload["author_handle"] == "[redacted]"
        item = exported.execute("SELECT redaction_flag FROM feedback_item").fetchone()
        assert int(item["redaction_flag"]) == 1
    with get_connection(db_path) as live:
        live_raw = json.loads(live.execute("SELECT payload_json FROM raw_record").fetchone()["payload_json"])
        assert live_raw["author_handle"] == "secret_user"


def test_export_after_freeze_does_not_unfreeze(tmp_path: Path):
    db_path = tmp_path / "snap.db"
    run_id, _ = _seed_with_raw(db_path, tmp_path)
    with get_connection(db_path) as conn:
        run_freeze(conn, run_id)
        again = run_export(conn, run_id, redact=True)
        status = conn.execute("SELECT status FROM analysis_run WHERE id = ?", (run_id,)).fetchone()
        try:
            assert_not_frozen(conn, run_id)
            raised = False
        except RuntimeError:
            raised = True
    assert again["status"] == "ok"
    assert status["status"] == "frozen"
    assert raised


def test_rebuild_from_raw_and_refused_when_frozen(tmp_path: Path):
    db_path = tmp_path / "snap.db"
    run_id, spec = _seed_with_raw(db_path, tmp_path)
    with get_connection(db_path) as conn:
        rebuilt = run_rebuild(conn, run_id)
        assert rebuilt["collected"] is False
        assert rebuilt["raw_count"] >= 1
        freeze = run_freeze(conn, run_id)
        try:
            run_rebuild(conn, run_id)
            frozen_rebuild = True
        except RuntimeError:
            frozen_rebuild = False
    assert frozen_rebuild is False
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    (dest_dir / "gold.json").write_text(json.dumps({"items": []}))
    dest_spec = _spec(dest_dir, "dest.db")
    cloned = rebuild_from_export(Path(freeze["export_dir"]), dest_run_spec=dest_spec)
    assert cloned["analysis_run_id"] != run_id
    assert cloned["raw_copied"] >= 1
    assert cloned["rebuild"]["status"] == "success"
