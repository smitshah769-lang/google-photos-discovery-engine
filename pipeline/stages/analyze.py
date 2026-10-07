from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from pipeline.analysis.classify import build_classifier, classify_text
from pipeline.analysis.cluster import cluster_items
from pipeline.analysis.curated_labels import (
    apply_curated_label,
    item_key,
    load_curated_labels,
    resolve_curated_path,
)
from pipeline.analysis.embeddings import embed_texts
from pipeline.analysis.eval_gold import evaluate_gold_set, load_gold_set
from pipeline.analysis.hypothesis import overlay_for_labels, summarize_overlays
from pipeline.analysis.inference import InferenceUnavailable
from pipeline.analysis.research_tags import annotate_research_item, parse_payload_json
from pipeline.analysis.score import MULTI_LABEL_COUNTING_RULE, score_categories
from pipeline.analysis.segments import tag_segments, unknown_rates
from pipeline.db.connection import assert_not_frozen, json_dumps
from pipeline.db.repository import load_run_spec, update_methodology_coverage
from pipeline.model_run import log_model_run
from pipeline.paths import PROJECT_ROOT
from pipeline.run_context import complete_stage_receipt, utc_now_iso
from pipeline.taxonomy import load_taxonomy


def _merge_coverage(conn: sqlite3.Connection, analysis_run_id: str, extra: dict[str, Any]) -> dict[str, Any]:
    row = conn.execute(
        "SELECT coverage_stats_json FROM methodology_snapshot WHERE analysis_run_id = ?",
        (analysis_run_id,),
    ).fetchone()
    base: dict[str, Any] = {}
    if row and row["coverage_stats_json"]:
        base = json.loads(row["coverage_stats_json"])
    base.update(extra)
    update_methodology_coverage(conn, analysis_run_id, base)
    return base


def _clear_analysis_outputs(conn: sqlite3.Connection, analysis_run_id: str) -> None:
    conn.execute(
        """
        DELETE FROM classification
        WHERE feedback_item_id IN (
          SELECT id FROM feedback_item WHERE analysis_run_id = ?
        )
        """,
        (analysis_run_id,),
    )
    conn.execute("DELETE FROM cluster WHERE analysis_run_id = ?", (analysis_run_id,))
    conn.execute("DELETE FROM category_aggregate WHERE analysis_run_id = ?", (analysis_run_id,))


def run_analyze(conn: sqlite3.Connection, analysis_run_id: str) -> dict:
    assert_not_frozen(conn, analysis_run_id)
    run_spec = load_run_spec(conn, analysis_run_id)
    analysis_cfg = run_spec.get("analysis") or {}
    tax_version = str(analysis_cfg.get("taxonomy_version") or "v0")
    taxonomy = load_taxonomy(version=tax_version)
    models = run_spec.get("models") or {}
    analysis_cfg = run_spec.get("analysis") or {}
    clf_cfg = models.get("classification") or {}
    embed_cfg = models.get("embedding") or {}
    temperature = float(clf_cfg.get("temperature") if clf_cfg.get("temperature") is not None else 0.1)
    prompt_version = str(clf_cfg.get("prompt_version") or "classify_v0")
    fallback = clf_cfg.get("fallback_provider")
    fallback_provider = str(fallback).lower() if fallback else None

    try:
        provider, client = build_classifier(models)
    except InferenceUnavailable as exc:
        complete_stage_receipt(
            conn,
            analysis_run_id,
            "analyze",
            status="failed",
            notes=str(exc),
        )
        conn.commit()
        raise

    _clear_analysis_outputs(conn, analysis_run_id)
    curated = load_curated_labels(resolve_curated_path(run_spec))

    rows = conn.execute(
        """
        SELECT f.id, f.source, f.text, f.relevance_label, rr.payload_json
        FROM feedback_item f
        LEFT JOIN raw_record rr ON rr.id = f.raw_record_id
        WHERE f.analysis_run_id = ? AND f.relevance_label = 'retrieval_related'
        """,
        (analysis_run_id,),
    ).fetchall()

    classified_payloads: list[dict[str, Any]] = []
    overlays: list[str] = []
    unclassified = 0
    classified_n = 0

    try:
        for idx, row in enumerate(rows, start=1):
            text = row["text"] or ""
            payload = parse_payload_json(row["payload_json"] if "payload_json" in row.keys() else None)
            result = classify_text(
                text,
                taxonomy,
                provider=provider,
                client=client,
                temperature=temperature,
                fallback_provider=fallback_provider,
                source=row["source"] or "",
                payload=payload,
            )
            model_id = str(
                (clf_cfg.get("model_id") or provider)
            )
            model_run_id = log_model_run(
                conn,
                analysis_run_id,
                purpose="classification",
                model_id=model_id,
                prompt_version=prompt_version,
                temperature=temperature,
                payload_for_hash={"item_id": row["id"], "text": text, "prompt_version": prompt_version},
                output_summary=json_dumps(
                    {
                        "labels": result.labels,
                        "unclassified": result.unclassified,
                        "confidence": result.confidence,
                    }
                ),
            )
            segments = tag_segments(text)
            if taxonomy.version == "research_v1":
                result.extra = result.extra or annotate_research_item(
                    text, source=row["source"] or "", payload=payload
                )
                reviewed = curated.get(item_key(row["source"] or "", payload) or "")
                if reviewed is not None:
                    apply_curated_label(result, reviewed, text, taxonomy)
                extra = result.extra
                segments.update(extra)
                if extra.get("signal") != "actionable":
                    result.labels = []
                    result.unclassified = True
                    result.rationale = "no_actionable_pain_point"
            overlay = overlay_for_labels(result.labels)
            segments["hypothesis_overlay"] = overlay
            overlays.append(overlay)
            conn.execute(
                "UPDATE feedback_item SET segments_json = ? WHERE id = ?",
                (json_dumps(segments), row["id"]),
            )
            if result.unclassified:
                unclassified += 1
                continue
            classified_n += 1
            snippets_json = json_dumps(result.snippets)
            for node_id in result.labels:
                conn.execute(
                    """
                    INSERT INTO classification
                      (id, feedback_item_id, taxonomy_node_id, taxonomy_version,
                       confidence, rationale, model_run_id, snippets_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        row["id"],
                        node_id,
                        taxonomy.version,
                        result.confidence,
                        result.rationale,
                        model_run_id,
                        snippets_json,
                    ),
                )
            classified_payloads.append(
                {
                    "id": row["id"],
                    "source": row["source"],
                    "text": text,
                    "labels": result.labels,
                    "confidence": result.confidence,
                    "segments": segments,
                }
            )
            if idx % 25 == 0:
                conn.commit()
    except InferenceUnavailable as exc:
        complete_stage_receipt(
            conn,
            analysis_run_id,
            "analyze",
            status="failed",
            notes=str(exc),
        )
        conn.commit()
        raise

    # Clusters (classified items only). Tiny / giant-other are flagged, not new roots.
    cluster_threshold = float(analysis_cfg.get("cluster_similarity_threshold") or 0.42)
    embed_provider = str((embed_cfg.get("provider") or "hashing")).lower()
    embed_model = embed_cfg.get("model_id")
    cluster_summary: dict[str, Any] = {
        "count": 0,
        "tiny_not_promoted": 0,
        "giant_other_not_ranked": 0,
    }
    if classified_payloads:
        try:
            vectors = embed_texts(
                [p["text"] for p in classified_payloads],
                provider=embed_provider,
                model_id=str(embed_model) if embed_model else None,
            )
        except InferenceUnavailable as exc:
            complete_stage_receipt(
                conn,
                analysis_run_id,
                "analyze",
                status="failed",
                notes=str(exc),
            )
            conn.commit()
            raise
        clusters = cluster_items(
            vectors,
            [p["labels"] for p in classified_payloads],
            threshold=cluster_threshold,
        )
        cluster_summary["count"] = len(clusters)
        for cl in clusters:
            member_ids = [classified_payloads[i]["id"] for i in cl.member_indices]
            if cl.needs_human_review:
                cluster_summary["tiny_not_promoted"] += 1
            if not cl.ranked_opportunity and cl.label == "other":
                cluster_summary["giant_other_not_ranked"] += 1
            conn.execute(
                """
                INSERT INTO cluster
                  (id, analysis_run_id, label, member_ids_json, cohesion_score)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    analysis_run_id,
                    cl.label,
                    json_dumps(
                        {
                            "ids": member_ids,
                            "ranked_opportunity": cl.ranked_opportunity,
                            "needs_human_review": cl.needs_human_review,
                            "reason": cl.reason,
                        }
                    ),
                    cl.cohesion,
                ),
            )

    aggregates = score_categories(classified_payloads)
    for agg in aggregates:
        source_mix = {
            "sources": agg["source_mix"],
            "consistent_across_sources": agg["consistent_across_sources"],
            "segment_unknown_rates": agg["segment_unknown_rates"],
            "ranked_opportunity": agg["ranked_opportunity"],
            "ranking_scope": "within_this_snapshot",
        }
        conn.execute(
            """
            INSERT INTO category_aggregate
              (id, analysis_run_id, taxonomy_node_id, taxonomy_version,
               frequency, severity, source_mix_json, avg_confidence, workaround_ids_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                analysis_run_id,
                agg["taxonomy_node_id"],
                taxonomy.version,
                agg["frequency"],
                agg["severity"],
                json_dumps(source_mix),
                agg["avg_confidence"],
                json_dumps(agg["workaround_ids"]),
            ),
        )

    gold_path = analysis_cfg.get("gold_set")
    gold = load_gold_set(Path(gold_path) if gold_path else None)
    gold_eval = evaluate_gold_set(
        gold,
        taxonomy,
        provider=provider,
        client=client,
        temperature=temperature,
        fallback_provider=fallback_provider,
    )

    segment_rows = [p["segments"] for p in classified_payloads]
    hypothesis = summarize_overlays(overlays)
    coverage_extra = {
        "status": "phase_2",
        "classified_count": classified_n,
        "unclassified_count": unclassified,
        "multi_label_counting_rule": MULTI_LABEL_COUNTING_RULE,
        "hypothesis_overlay": hypothesis,
        "segment_unknown_rates": unknown_rates(segment_rows),
        "clusters": cluster_summary,
        "gold_eval": {
            k: v
            for k, v in gold_eval.items()
            if k != "items"
        },
        "embedding_model": {
            "provider": embed_provider,
            "model_id": embed_model,
        },
        "classification_model": {
            "provider": provider,
            "model_id": clf_cfg.get("model_id"),
            "prompt_version": prompt_version,
            "fallback_provider": fallback_provider,
        },
    }
    _merge_coverage(conn, analysis_run_id, coverage_extra)

    conn.execute(
        """
        UPDATE methodology_snapshot
        SET model_ids_json = ?, prompts_json = ?
        WHERE analysis_run_id = ?
        """,
        (
            json_dumps(
                {
                    "embedding": embed_cfg,
                    "classification": {**clf_cfg, "resolved_provider": provider},
                }
            ),
            json_dumps(
                {
                    "classification": {
                        "prompt_version": prompt_version,
                        "path": str((PROJECT_ROOT / "config" / "prompts" / "classify_v0.txt")),
                    }
                }
            ),
            analysis_run_id,
        ),
    )

    notes = (
        f"Classified {classified_n} retrieval_related items "
        f"({unclassified} unclassified); "
        f"hypothesis overall={hypothesis['overall']}; "
        f"gold exact_match={gold_eval['exact_match_accuracy']}."
    )
    complete_stage_receipt(
        conn,
        analysis_run_id,
        "analyze",
        status="success",
        item_count=classified_n,
        notes=notes,
    )
    conn.commit()
    return {
        "stage": "analyze",
        "status": "success",
        "classified_count": classified_n,
        "unclassified_count": unclassified,
        "cluster_count": cluster_summary["count"],
        "category_count": len(aggregates),
        "hypothesis_overlay": hypothesis,
        "gold_exact_match_accuracy": gold_eval["exact_match_accuracy"],
        "multi_label_counting_rule": MULTI_LABEL_COUNTING_RULE,
        "analyzed_at": utc_now_iso(),
    }
