import json
from pathlib import Path

from pipeline.analysis.classify import build_classifier, classify_heuristic, classify_with_llm
from pipeline.analysis.inference import InferenceUnavailable
from pipeline.analysis.cluster import cluster_items
from pipeline.analysis.embeddings import hashing_embed
from pipeline.analysis.eval_gold import evaluate_gold_set, load_gold_set
from pipeline.analysis.hypothesis import overlay_for_labels, summarize_overlays
from pipeline.analysis.json_parse import parse_json_object
from pipeline.analysis.score import score_categories
from pipeline.analysis.segments import tag_segments
from pipeline.analysis.snippets import snippets_in_text
from pipeline.db.connection import get_connection, init_database
from pipeline.stages.analyze import run_analyze
from pipeline.run_context import create_analysis_run
from pipeline.taxonomy import load_taxonomy


class _FakeClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls = 0

    def complete(self, prompt: str, *, temperature: float) -> str:
        self.calls += 1
        if not self.responses:
            return ""
        return self.responses.pop(0)


def test_parse_json_object_strips_prose():
    raw = 'Here you go:\n```json\n{"labels": ["search_abandonment"], "confidence": 0.7, "rationale": "gave up", "snippets": []}\n```\n'
    parsed = parse_json_object(raw)
    assert parsed is not None
    assert parsed["labels"] == ["search_abandonment"]


def test_ollama_without_model_id_fails_without_paid_fallback():
    try:
        build_classifier({"classification": {"provider": "ollama", "model_id": None}})
        raised = False
    except InferenceUnavailable:
        raised = True
    assert raised


def test_invalid_llm_json_retries_once_then_unclassified():
    taxonomy = load_taxonomy()
    client = _FakeClient(["not json", "still not { valid"])
    result = classify_with_llm("I gave up searching.", taxonomy, client, temperature=0.1)
    assert client.calls == 2
    assert result.unclassified
    assert result.labels == []
    assert result.rationale == "invalid_llm_json"


def test_llm_does_not_regex_guess_after_invalid_json():
    taxonomy = load_taxonomy()
    client = _FakeClient(["I think this is search_abandonment but not JSON"])
    # only one extra retry, still invalid
    client.responses.append("garbage")
    result = classify_with_llm("I gave up after two or three times.", taxonomy, client, temperature=0.0)
    assert "search_abandonment" not in result.labels
    assert result.unclassified


def test_snippets_must_be_verbatim():
    text = "I cannot find last year's screenshots."
    kept = snippets_in_text(["last year's screenshots", "invented quote"], text)
    assert kept == ["last year's screenshots"]


def test_segments_unknown_unless_user_states_and_goa_is_not_india():
    tagged = tag_segments(
        "We photographed a café in Goa but I forgot the date. About 3000 photos on my Pixel."
    )
    assert tagged["library_size"] == "large"
    assert tagged["device"] == "android"
    assert tagged["geo"] == "unknown"
    asserted = tag_segments("This is hard in Canada with a huge library.")
    assert asserted["geo"].lower() == "canada"


def test_hypothesis_supports_all_three_values():
    assert overlay_for_labels(["incomplete_memory_place_event"]) == "support"
    assert overlay_for_labels(["backup_sync_storage"]) == "contradict"
    assert overlay_for_labels(["search_abandonment"]) == "insufficient"
    summary = summarize_overlays(["support", "contradict", "insufficient"])
    assert summary["counts"]["support"] == 1
    assert summary["counts"]["contradict"] == 1
    assert summary["counts"]["insufficient"] == 1
    assert set(summary["values_supported"]) == {"support", "contradict", "insufficient"}


def test_tiny_cluster_not_new_root_and_other_not_ranked():
    vectors = [
        hashing_embed("alpha unique token zzz"),
        hashing_embed("beta unique token yyy"),
        hashing_embed("shared theme photo search memory"),
        hashing_embed("shared theme photo search memory again"),
        hashing_embed("shared theme photo search memory third"),
        hashing_embed("shared theme photo search memory fourth"),
        hashing_embed("shared theme photo search memory fifth"),
        hashing_embed("shared theme photo search memory sixth"),
        hashing_embed("shared theme photo search memory seventh"),
        hashing_embed("shared theme photo search memory eighth"),
    ]
    labels = [[], []] + [["incomplete_memory"]] * 8
    clusters = cluster_items(vectors, labels, threshold=0.99)
    # Isolated first two should be tiny if they do not match.
    tiny = [c for c in clusters if c.needs_human_review]
    assert tiny
    for c in tiny:
        assert c.ranked_opportunity is False

    mixed = cluster_items(
        [hashing_embed(f"unrelated {i} {i*7} xyz") for i in range(12)],
        [[f"lab{i}"] for i in range(12)],
        threshold=0.01,
    )
    others = [c for c in mixed if c.label == "other"]
    assert others
    assert all(c.ranked_opportunity is False for c in others)


def test_scoring_uses_source_diversity_not_stars_and_consistent_flag():
    items = [
        {
            "id": "a",
            "source": "reddit",
            "text": "I can't find family photos and I'm frustrated.",
            "labels": ["incomplete_memory_person_occasion"],
            "confidence": 0.8,
            "segments": {"library_size": "unknown", "photo_age": "unknown", "geo": "unknown", "device": "unknown"},
        },
        {
            "id": "b",
            "source": "app_store",
            "text": "I can't find family photos either.",
            "labels": ["incomplete_memory_person_occasion"],
            "confidence": 0.7,
            "segments": {"library_size": "unknown", "photo_age": "unknown", "geo": "unknown", "device": "unknown"},
        },
        {
            "id": "c",
            "source": "reddit",
            "text": "Backup quota is full.",
            "labels": ["backup_sync_storage"],
            "confidence": 0.6,
            "segments": {"library_size": "unknown", "photo_age": "unknown", "geo": "unknown", "device": "unknown"},
        },
    ]
    rows = score_categories(items)
    memory = next(r for r in rows if r["taxonomy_node_id"] == "incomplete_memory_person_occasion")
    backup = next(r for r in rows if r["taxonomy_node_id"] == "backup_sync_storage")
    assert memory["consistent_across_sources"] is True
    assert backup["consistent_across_sources"] is False
    assert memory["frequency"] == 2
    assert "geo" in memory["segment_unknown_rates"]
    assert 0 <= memory["severity"] <= 1
    assert 0 <= backup["severity"] <= 1


def test_gold_set_covers_required_cases_and_eval_runs():
    gold = load_gold_set()
    cases = {item["case"] for item in gold["items"]}
    assert "retrieval_vs_backup" in cases
    assert "retrieval_vs_delete" in cases
    assert "complete_info_search_failure" in cases
    assert "incomplete_memory_phrasing_not_prompt_examples" in cases
    assert "workaround_succeeded" in cases
    assert "abandonment_only" in cases
    assert "multi_label" in cases
    texts = " ".join(item["text"] for item in gold["items"]).lower()
    assert "goa" not in texts
    assert "café" not in texts and "cafe" not in texts
    taxonomy = load_taxonomy()
    report = evaluate_gold_set(
        gold,
        taxonomy,
        provider="heuristic",
        client=None,
        temperature=0.0,
    )
    assert report["n"] == 12
    assert "per_label" in report
    assert report["exact_match_accuracy"] >= 0.5
    hyps = {overlay_for_labels(i["labels"]) for i in gold["items"]}
    assert hyps == {"support", "contradict", "insufficient"}


def test_heuristic_matches_gold_incomplete_memory_without_prompt_examples():
    taxonomy = load_taxonomy()
    result = classify_heuristic(
        "I know we photographed the lakeside cabin with my cousin but I cannot remember which summer it was.",
        taxonomy,
    )
    assert "incomplete_memory_person_occasion" in result.labels


def test_analyze_stage_persists_classifications_and_methodology(tmp_path: Path):
    db = tmp_path / "a.db"
    init_database(db, load_taxonomy(), {"open_decisions": {}, "limitations_seed": []})
    run_spec = {
        "analysis": {
            "taxonomy_version": "v0",
            "corpus_target_relevant": 500,
            "gold_set": "config/gold_set.json",
            "cluster_similarity_threshold": 0.3,
        },
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
    with get_connection(db) as conn:
        run_id = create_analysis_run(conn, run_spec)
        # retrieval_related items covering all three hypothesis values
        samples = [
            (
                "reddit",
                "I cannot find last year's screenshots of the warranty card from last autumn.",
            ),
            (
                "app_store",
                "Backup never finished after I switched phones and storage quota is full.",
            ),
            (
                "play_store",
                "I tried search two or three times, then gave up. I do not know what kind of problem it was.",
            ),
            (
                "help_community",
                "I searched the exact date 12 March 2019 with the right album name and it still failed.",
            ),
        ]
        for i, (source, text) in enumerate(samples):
            conn.execute(
                """
                INSERT INTO feedback_item
                  (id, analysis_run_id, raw_record_id, source, source_url, authored_at,
                   captured_at, locale, text, thread_context, relevance_label,
                   relevance_confidence, segments_json, redaction_flag)
                VALUES (?, ?, NULL, ?, 'https://example.test/x', NULL,
                        '2026-01-01T00:00:00+00:00', 'en', ?, NULL, 'retrieval_related',
                        0.9, '{}', 0)
                """,
                (f"item-{i}", run_id, source, text),
            )
        conn.commit()
        result = run_analyze(conn, run_id)

    assert result["status"] == "success"
    assert result["classified_count"] >= 3
    overlay = result["hypothesis_overlay"]
    assert overlay["counts"]["support"] >= 1
    assert overlay["counts"]["contradict"] >= 1
    assert overlay["counts"]["insufficient"] >= 1

    with get_connection(db) as conn:
        n_cls = conn.execute(
            """
            SELECT COUNT(*) FROM classification c
            JOIN feedback_item f ON f.id = c.feedback_item_id
            WHERE f.analysis_run_id = ?
            """,
            (run_id,),
        ).fetchone()[0]
        assert n_cls >= 3
        coverage = json.loads(
            conn.execute(
                "SELECT coverage_stats_json FROM methodology_snapshot WHERE analysis_run_id = ?",
                (run_id,),
            ).fetchone()[0]
        )
        assert coverage["status"] == "phase_2"
        assert "multi_label_counting_rule" in coverage
        assert coverage["hypothesis_overlay"]["values_supported"] == [
            "support",
            "contradict",
            "insufficient",
        ]
        assert "geo" in coverage["segment_unknown_rates"]
        mix = json.loads(
            conn.execute(
                "SELECT source_mix_json FROM category_aggregate WHERE analysis_run_id = ? LIMIT 1",
                (run_id,),
            ).fetchone()[0]
        )
        assert "consistent_across_sources" in mix
        assert mix["ranking_scope"] == "within_this_snapshot"
        receipt = conn.execute(
            "SELECT status FROM stage_receipt WHERE analysis_run_id = ? AND stage = 'analyze'",
            (run_id,),
        ).fetchone()
        assert receipt[0] == "success"
