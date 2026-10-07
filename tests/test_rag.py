import json
from unittest.mock import patch

from pipeline.analysis.inference import InferenceUnavailable
from pipeline.db.connection import get_connection, init_database
from pipeline.rag.rerank import lexical_overlap_boost
from pipeline.rag.scope import classify_query_scope
from pipeline.rag.search import SearchRequest, search
from pipeline.run_context import create_analysis_run
from pipeline.stages.analyze import run_analyze
from pipeline.stages.index import run_index
from pipeline.taxonomy import load_taxonomy


def _seed_run(db_path, tmp_path):
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
    }
    (tmp_path / "gold.json").write_text(json.dumps({"items": []}))
    with get_connection(db_path) as conn:
        run_id = create_analysis_run(conn, run_spec)
        conn.execute(
            """
            INSERT INTO feedback_item
              (id, analysis_run_id, raw_record_id, source, source_url, authored_at,
               captured_at, locale, text, thread_context, relevance_label,
               relevance_confidence, segments_json, redaction_flag)
            VALUES (?, ?, NULL, ?, ?, '2024-06-01', '2026-01-01T00:00:00+00:00', 'en',
                    ?, NULL, 'retrieval_related', 0.9, '{}', 0)
            """,
            (
                "item-old-photos",
                run_id,
                "reddit",
                "https://reddit.test/comments/abc",
                "I cannot find my old pictures from the trip even when I scroll years view.",
            ),
        )
        conn.execute(
            """
            INSERT INTO feedback_item
              (id, analysis_run_id, raw_record_id, source, source_url, authored_at,
               captured_at, locale, text, thread_context, relevance_label,
               relevance_confidence, segments_json, redaction_flag)
            VALUES (?, ?, NULL, ?, ?, '2024-06-01', '2026-01-01T00:00:00+00:00', 'en',
                    ?, NULL, 'retrieval_related', 0.9, '{}', 0)
            """,
            (
                "item-gave-up",
                run_id,
                "play_store",
                "https://play.test/review/1",
                "I tried search three times and gave up finding screenshots.",
            ),
        )
        conn.commit()
        run_analyze(conn, run_id)
        run_index(conn, run_id)
    return run_id, run_spec


def test_scope_gate_out_of_scope():
    for q in [
        "how do I train the model?",
        "write a Python scraper for Play Store",
        "what is RAG?",
        "Google Photos billing and subscription",
    ]:
        in_scope, _ = classify_query_scope(q)
        assert in_scope is False


def test_scope_gate_in_scope_synonyms():
    for q in [
        "old pictures",
        "can't remember when the photo was taken",
        "Google Photos search not finding people",
    ]:
        in_scope, _ = classify_query_scope(q)
        assert in_scope is True


def test_lexical_overlap_boost():
    assert lexical_overlap_boost("face search broken", "face search does not work") > 0.3
    assert lexical_overlap_boost("", "anything") == 0.0


def test_scope_gate_reviewer_prompts():
    for q in [
        "What are the main user pain points around Google Photos search?",
        "What is sentiment like for search in this feedback?",
    ]:
        in_scope, _ = classify_query_scope(q)
        assert in_scope is True


def test_search_out_of_scope_zero_hits(tmp_path):
    db = tmp_path / "rag.db"
    run_id, run_spec = _seed_run(db, tmp_path)
    with get_connection(db) as conn:
        res = search(
            conn,
            run_id,
            SearchRequest(query="how do I train the model?"),
            run_spec=run_spec,
        )
    assert res.in_scope is False
    assert res.hits == []
    assert res.cited_summary is None
    assert res.related_themes == []


def test_search_in_scope_returns_attributed_hits(tmp_path):
    db = tmp_path / "rag.db"
    run_id, run_spec = _seed_run(db, tmp_path)
    with get_connection(db) as conn:
        res = search(
            conn,
            run_id,
            SearchRequest(query="old pictures scroll years"),
            run_spec=run_spec,
        )
    assert res.in_scope is True
    assert res.hits
    assert res.answer
    assert res.answer["summary"]
    assert len(res.answer["evidence"]) <= 2
    hit = res.hits[0]
    assert hit["item_id"]
    assert hit["source_url"]
    assert hit["snippet"]
    row = conn.execute(
        "SELECT text FROM feedback_item WHERE id = ?", (hit["item_id"],)
    ).fetchone()
    stored = row["text"]
    assert hit["snippet"] in stored or stored in hit["snippet"]


def test_search_filter_empty_message(tmp_path):
    db = tmp_path / "rag.db"
    run_id, run_spec = _seed_run(db, tmp_path)
    with get_connection(db) as conn:
        res = search(
            conn,
            run_id,
            SearchRequest(query="old pictures", sources=["app_store"]),
            run_spec=run_spec,
        )
    assert res.in_scope is True
    assert res.hits == []
    assert res.message and "0 items match filters" in res.message


def test_search_embedding_unavailable_message(tmp_path):
    db = tmp_path / "rag.db"
    run_id, run_spec = _seed_run(db, tmp_path)
    with get_connection(db) as conn:
        with patch(
            "pipeline.rag.search.embed_texts",
            side_effect=InferenceUnavailable("sentence-transformers is not installed."),
        ):
            res = search(
                conn,
                run_id,
                SearchRequest(query="old pictures scroll years"),
                run_spec=run_spec,
            )
    assert res.in_scope is True
    assert res.hits == []
    assert "sentence-transformers" in (res.message or "")


def test_missing_index_message(tmp_path):
    db = tmp_path / "rag2.db"
    init_database(db, load_taxonomy(), {"open_decisions": {}, "limitations_seed": []})
    run_spec = {
        "analysis": {"taxonomy_version": "v0", "corpus_target_relevant": 500},
        "paths": {"data_dir": str(tmp_path), "db_filename": db.name},
        "models": {"embedding": {"provider": "hashing", "model_id": "hashing-v0"}},
    }
    with get_connection(db) as conn:
        run_id = create_analysis_run(conn, run_spec)
        res = search(
            conn,
            run_id,
            SearchRequest(query="find old photos"),
            run_spec=run_spec,
        )
    assert res.in_scope is True
    assert "index" in (res.message or "").lower()
