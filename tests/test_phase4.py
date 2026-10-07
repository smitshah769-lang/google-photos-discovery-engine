import json
from pathlib import Path

from pipeline.db.connection import assert_not_frozen, get_connection, init_database
from pipeline.serve.read import categories, chrome, evidence, insights, methodology, quality, search_payload
from pipeline.serve.methodology_copy import REQUIRED_LIMITATIONS
from pipeline.stages.aggregate import run_aggregate
from pipeline.stages.analyze import run_analyze
from pipeline.stages.freeze import run_freeze
from pipeline.stages.index import run_index
from pipeline.run_context import create_analysis_run
from pipeline.taxonomy import load_taxonomy


def _seed(db_path: Path, tmp_path: Path):
    init_database(db_path, load_taxonomy(), {"open_decisions": {}, "limitations_seed": []})
    run_spec = {
        "analysis": {
            "taxonomy_version": "v0",
            "corpus_target_relevant": 500,
            "gold_set": str(tmp_path / "gold.json"),
            "cluster_similarity_threshold": 0.3,
        },
        "paths": {"data_dir": str(tmp_path), "db_filename": db_path.name},
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
    }
    (tmp_path / "gold.json").write_text(json.dumps({"items": []}))
    with get_connection(db_path) as conn:
        run_id = create_analysis_run(conn, run_spec)
        samples = [
            (
                "item-old-photos",
                "reddit",
                "https://reddit.test/comments/abc",
                "I cannot find my old pictures from the trip even when I scroll years view.",
            ),
            (
                "item-gave-up",
                "play_store",
                "https://play.test/review/1",
                "I tried search three times and gave up finding screenshots.",
            ),
            (
                "item-workaround",
                "app_store",
                "https://apps.test/review/2",
                "Years view workaround finally found the holiday photos with my brother.",
            ),
        ]
        for item_id, source, url, text in samples:
            conn.execute(
                """
                INSERT INTO feedback_item
                  (id, analysis_run_id, raw_record_id, source, source_url, authored_at,
                   captured_at, locale, text, thread_context, relevance_label,
                   relevance_confidence, segments_json, redaction_flag)
                VALUES (?, ?, NULL, ?, ?, '2024-06-01', '2026-01-01T00:00:00+00:00', 'en',
                        ?, NULL, 'retrieval_related', 0.9, '{}', 0)
                """,
                (item_id, run_id, source, url, text),
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
            UPDATE source_run SET status = 'gap', item_count = 0, notes = 'CSE quota exhausted'
            WHERE analysis_run_id = ? AND source = 'help_community'
            """,
            (run_id,),
        )
        conn.commit()
        run_analyze(conn, run_id)
        run_index(conn, run_id)
        run_aggregate(conn, run_id)
    return run_id, run_spec


def test_insights_visible_miss_and_incomplete_mix(tmp_path: Path):
    db_path = tmp_path / "snap.db"
    run_id, _spec = _seed(db_path, tmp_path)
    with get_connection(db_path) as conn:
        payload = insights(conn, run_id)
        chrome_payload = chrome(conn, run_id)
    assert chrome_payload["run_id"] == run_id
    assert payload["target_miss_visible"] is True
    assert payload["relevant_count"] < 500
    assert payload["incomplete_source_mix"] is True
    assert payload["ranking_copy"].startswith("Ranking is within this snapshot")
    assert "unknown" in payload["segments"]["geo"]
    overlay = payload["hypothesis_overlay"]
    assert set(overlay["counts"]) == {"support", "contradict", "insufficient"}
    cats = categories
    with get_connection(db_path) as conn:
        cat_payload = cats(conn, run_id)
    for cat in cat_payload["categories"]:
        if cat["consistent_across_sources"]:
            assert len([s for s, n in (cat["source_mix"] or {}).items() if n]) >= 2


def test_evidence_sums_to_category_frequency(tmp_path: Path):
    db_path = tmp_path / "snap.db"
    run_id, _ = _seed(db_path, tmp_path)
    with get_connection(db_path) as conn:
        payload = insights(conn, run_id)
        for cat in payload["categories"]:
            ev = evidence(
                conn,
                run_id,
                kind="category_frequency",
                taxonomy_node_id=cat["taxonomy_node_id"],
            )
            assert ev["count"] == cat["frequency"]


def test_methodology_required_copy(tmp_path: Path):
    db_path = tmp_path / "snap.db"
    run_id, _ = _seed(db_path, tmp_path)
    with get_connection(db_path) as conn:
        payload = methodology(conn, run_id)
        q = quality(conn, run_id)
    ext = payload["data_extraction"]
    assert len(ext["by_source"]) == 4
    assert ext["totals"]["normalized_total"] >= 3
    assert "extracted_raw" in ext["totals"]
    text = " ".join(payload["required_limitations"])
    assert "500" in text
    assert "batchexecute" in text.lower() or "RPC" in text
    assert "Arctic Shift" in text
    assert "Custom Search" in text or "CSE" in text
    assert any("telemetry" in x.lower() for x in REQUIRED_LIMITATIONS)
    assert q["hypothesis_overlay"]["values_supported"] == [
        "support",
        "contradict",
        "insufficient",
    ]


def test_search_out_of_scope_empty(tmp_path: Path):
    db_path = tmp_path / "snap.db"
    run_id, spec = _seed(db_path, tmp_path)
    with get_connection(db_path) as conn:
        out = search_payload(conn, run_id, {"query": "how do I train the model?"}, run_spec=spec)
    assert out["in_scope"] is False
    assert out["hits"] == []
    assert "cited_summary" not in out
    assert out.get("related_themes") in (None, [])


def test_freeze_immutable_and_export(tmp_path: Path):
    db_path = tmp_path / "snap.db"
    run_id, _ = _seed(db_path, tmp_path)
    with get_connection(db_path) as conn:
        dry = run_freeze(conn, run_id, dry_run=True)
        assert dry["status"] == "dry_run"
        result = run_freeze(conn, run_id, redact=True)
        second = run_freeze(conn, run_id)
        try:
            assert_not_frozen(conn, run_id)
            raised = False
        except RuntimeError:
            raised = True
    assert result["status"] == "frozen"
    assert second["status"] == "already_frozen"
    assert raised
    export = Path(result["export_dir"])
    assert (export / "snapshot.db").is_file()
    assert (export / "FREEZE.json").is_file()
    assert (export / "receipts.json").is_file()
    freeze_meta = json.loads((export / "FREEZE.json").read_text())
    assert freeze_meta["run_id"] == run_id
    assert freeze_meta["immutable"] is True
