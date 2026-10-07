from __future__ import annotations

import json
import sqlite3
from collections import Counter
from typing import Any
from urllib.parse import parse_qs

from pipeline.db.repository import load_run_spec
from pipeline.paths import resolve_data_dir
from pipeline.rag.quotes import expand_to_sentence_boundary
from pipeline.rag.search import SearchRequest, search
from pipeline.rag.store import index_path_for_run
from pipeline.taxonomy_aliases import classification_node_ids_for_query
from pipeline.serve.methodology_copy import (
    BIAS_NOTES,
    COLLECTION_METHODS,
    NON_CLAIMS,
    OUT_OF_REPO_SCOPE,
    RANKING_COPY,
    REQUIRED_LIMITATIONS,
    TREND_SUBTITLE,
)
from pipeline.serve.research_insights import build_research_dashboard
from pipeline.taxonomy import load_taxonomy

LOW_SUPPORT_N = 5
SOURCES = ("app_store", "play_store", "reddit", "help_community")
SEGMENT_KEYS = ("library_size", "photo_age", "geo", "device")
HYPOTHESIS_VALUES = ("support", "contradict", "insufficient")


def _json_obj(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        val = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return val if isinstance(val, dict) else {}


def _json_list(raw: str | None) -> list[Any]:
    if not raw:
        return []
    try:
        val = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return val if isinstance(val, list) else []


def chrome(conn: sqlite3.Connection, analysis_run_id: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT id, status, frozen_at, created_at, corpus_target_relevant, taxonomy_version
        FROM analysis_run WHERE id = ?
        """,
        (analysis_run_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Unknown analysis run: {analysis_run_id}")
    return {
        "run_id": row["id"],
        "status": row["status"],
        "frozen_at": row["frozen_at"],
        "created_at": row["created_at"],
        "taxonomy_version": row["taxonomy_version"],
        "corpus_target_relevant": int(row["corpus_target_relevant"]),
        "ranking_copy": RANKING_COPY,
    }


def _source_receipts(conn: sqlite3.Connection, analysis_run_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT source, status, item_count, notes, started_at, finished_at, query_spec_json
        FROM source_run WHERE analysis_run_id = ?
        ORDER BY source
        """,
        (analysis_run_id,),
    ).fetchall()
    receipts: list[dict[str, Any]] = []
    seen = {r["source"] for r in rows}
    for row in rows:
        receipts.append(
            {
                "source": row["source"],
                "status": row["status"],
                "item_count": row["item_count"],
                "notes": row["notes"],
                "started_at": row["started_at"],
                "finished_at": row["finished_at"],
                "query_spec": _json_obj(row["query_spec_json"]),
                "collection_method": COLLECTION_METHODS.get(row["source"]),
            }
        )
    for source in SOURCES:
        if source not in seen:
            receipts.append(
                {
                    "source": source,
                    "status": "gap",
                    "item_count": 0,
                    "notes": "No receipt — silent skip is not allowed.",
                    "started_at": None,
                    "finished_at": None,
                    "query_spec": {},
                    "collection_method": COLLECTION_METHODS.get(source),
                }
            )
    return receipts


def _incomplete_source_mix(receipts: list[dict[str, Any]]) -> bool:
    ok = {"success", "partial"}
    return any(r["status"] not in ok for r in receipts)


def _methodology_row(conn: sqlite3.Connection, analysis_run_id: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT prompts_json, model_ids_json, coverage_stats_json, bias_notes,
               limitations_json, open_decisions_json
        FROM methodology_snapshot WHERE analysis_run_id = ?
        """,
        (analysis_run_id,),
    ).fetchone()
    if row is None:
        return {
            "prompts": {},
            "model_ids": {},
            "coverage": {},
            "bias_notes": BIAS_NOTES,
            "limitations": list(REQUIRED_LIMITATIONS),
            "open_decisions": {},
        }
    limitations = _json_list(row["limitations_json"])
    merged_limits = list(REQUIRED_LIMITATIONS)
    for item in limitations:
        if item not in merged_limits:
            merged_limits.append(item)
    return {
        "prompts": _json_obj(row["prompts_json"]),
        "model_ids": _json_obj(row["model_ids_json"]),
        "coverage": _json_obj(row["coverage_stats_json"]),
        "bias_notes": row["bias_notes"] or BIAS_NOTES,
        "limitations": merged_limits,
        "open_decisions": _json_obj(row["open_decisions_json"]),
    }


def _relevant_items(conn: sqlite3.Connection, analysis_run_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT id, source, source_url, authored_at, captured_at, locale, text,
               thread_context, relevance_label, relevance_confidence, segments_json
        FROM feedback_item
        WHERE analysis_run_id = ? AND relevance_label = 'retrieval_related'
        """,
        (analysis_run_id,),
    ).fetchall()


def _taxonomy_map(conn: sqlite3.Connection | None = None, analysis_run_id: str | None = None) -> dict[str, dict[str, Any]]:
    if conn is not None and analysis_run_id:
        spec = load_run_spec(conn, analysis_run_id)
        version = str((spec.get("analysis") or {}).get("taxonomy_version") or "v0")
        tax = load_taxonomy(version=version)
    else:
        tax = load_taxonomy()
    return {
        n.id: {
            "id": n.id,
            "name": n.name,
            "definition": n.definition,
            "parent_id": n.parent_id,
        }
        for n in tax.nodes
    }


def _category_rows(conn: sqlite3.Connection, analysis_run_id: str) -> list[dict[str, Any]]:
    tax = _taxonomy_map(conn, analysis_run_id)
    rows = conn.execute(
        """
        SELECT taxonomy_node_id, taxonomy_version, frequency, severity,
               source_mix_json, avg_confidence, workaround_ids_json
        FROM category_aggregate
        WHERE analysis_run_id = ?
        ORDER BY severity DESC, frequency DESC
        """,
        (analysis_run_id,),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        mix = _json_obj(row["source_mix_json"])
        sources = mix.get("sources") or {}
        source_count = len([k for k, v in sources.items() if v])
        consistent = bool(mix.get("consistent_across_sources")) and source_count >= 2
        freq = int(row["frequency"] or 0)
        low_support = freq < LOW_SUPPORT_N or source_count < 2
        node = tax.get(row["taxonomy_node_id"]) or {
            "id": row["taxonomy_node_id"],
            "name": row["taxonomy_node_id"],
            "definition": "",
            "parent_id": None,
        }
        out.append(
            {
                "taxonomy_node_id": row["taxonomy_node_id"],
                "taxonomy_version": row["taxonomy_version"],
                "name": node["name"],
                "definition": node["definition"],
                "parent_id": node["parent_id"],
                "frequency": freq,
                "severity": row["severity"],
                "avg_confidence": row["avg_confidence"],
                "source_mix": sources,
                "consistent_across_sources": consistent,
                "segment_unknown_rates": mix.get("segment_unknown_rates") or {},
                "ranked_opportunity": bool(mix.get("ranked_opportunity", True)),
                "ranking_scope": mix.get("ranking_scope") or "within_this_snapshot",
                "workaround_ids": _json_list(row["workaround_ids_json"]),
                "low_support": low_support,
                "low_support_reason": (
                    "n<5 or single source — do not lead the default view"
                    if low_support
                    else None
                ),
            }
        )
    return out


def _segment_rollups(items: list[sqlite3.Row]) -> dict[str, dict[str, int]]:
    roll: dict[str, Counter[str]] = {k: Counter() for k in SEGMENT_KEYS}
    for item in items:
        segs = _json_obj(item["segments_json"])
        for key in SEGMENT_KEYS:
            val = segs.get(key) or "unknown"
            roll[key][str(val)] += 1
        if not items:
            break
    out: dict[str, dict[str, int]] = {}
    for key in SEGMENT_KEYS:
        counts = dict(roll[key])
        counts.setdefault("unknown", 0)
        out[key] = counts
    return out


def _hypothesis(coverage: dict[str, Any], items: list[sqlite3.Row]) -> dict[str, Any]:
    stored = coverage.get("hypothesis_overlay") or {}
    counts = stored.get("counts") or {}
    normalized = {k: int(counts.get(k) or 0) for k in HYPOTHESIS_VALUES}
    if not any(normalized.values()) and items:
        for item in items:
            segs = _json_obj(item["segments_json"])
            val = segs.get("hypothesis_overlay") or "insufficient"
            if val not in normalized:
                val = "insufficient"
            normalized[val] += 1
    overall = stored.get("overall")
    if overall not in HYPOTHESIS_VALUES:
        overall = max(normalized, key=lambda k: normalized[k]) if any(normalized.values()) else "insufficient"
    return {
        "counts": normalized,
        "overall": overall,
        "values_supported": list(HYPOTHESIS_VALUES),
    }


def _trend(items: list[sqlite3.Row]) -> dict[str, Any]:
    buckets: Counter[str] = Counter()
    authored_vals = [i["authored_at"] for i in items if i["authored_at"]]
    for val in authored_vals:
        buckets[str(val)[:7]] += 1
    return {
        "granularity": "month",
        "buckets": [{"period": k, "count": buckets[k]} for k in sorted(buckets)],
        "window_start": min(authored_vals) if authored_vals else None,
        "window_end": max(authored_vals) if authored_vals else None,
        "subtitle": TREND_SUBTITLE,
    }


def _index_status(conn: sqlite3.Connection, analysis_run_id: str) -> dict[str, Any]:
    spec = load_run_spec(conn, analysis_run_id)
    path = index_path_for_run(resolve_data_dir(spec), analysis_run_id)
    exists = path.is_file()
    return {
        "exists": exists,
        "path": str(path),
        "rebuild_instruction": (
            None
            if exists
            else f"Vector index is missing. Rebuild with: python -m pipeline index {analysis_run_id}"
        ),
    }


def insights(conn: sqlite3.Connection, analysis_run_id: str) -> dict[str, Any]:
    meta = chrome(conn, analysis_run_id)
    receipts = _source_receipts(conn, analysis_run_id)
    items = _relevant_items(conn, analysis_run_id)
    categories = _category_rows(conn, analysis_run_id)
    coverage = _methodology_row(conn, analysis_run_id)["coverage"]
    target = int(meta["corpus_target_relevant"])
    relevant = int(coverage.get("relevant_count") or len(items))
    source_breakdown = Counter(i["source"] for i in items)
    high_impact = [c for c in categories if not c["low_support"] and c["ranked_opportunity"]]
    low_support = [c for c in categories if c["low_support"]]
    workarounds = [c for c in categories if c["taxonomy_node_id"] == "workarounds_succeeded"]
    workaround_ids: list[str] = []
    for c in workarounds:
        workaround_ids.extend(c.get("workaround_ids") or [])
    authored = [i["authored_at"] for i in items if i["authored_at"]]
    research = build_research_dashboard(
        conn, analysis_run_id, relevant_count=relevant
    )
    return {
        **meta,
        "relevant_count": relevant,
        "meets_target": relevant >= target,
        "target_miss_visible": relevant < target,
        "incomplete_source_mix": _incomplete_source_mix(receipts),
        "source_receipts": receipts,
        "source_breakdown": {s: int(source_breakdown.get(s) or 0) for s in SOURCES},
        "analysis_scope": {
            "date_range_authored_at": {
                "start": min(authored) if authored else None,
                "end": max(authored) if authored else None,
            },
            "sources": list(SOURCES),
            "run_id": analysis_run_id,
            "taxonomy_version": meta["taxonomy_version"],
        },
        "hypothesis_overlay": _hypothesis(coverage, items),
        "segments": _segment_rollups(items),
        "trend": _trend(items),
        "categories": categories,
        "high_impact": high_impact[:5],
        "low_support_categories": low_support,
        "workarounds": {
            "category": workarounds[0] if workarounds else None,
            "item_ids": workaround_ids,
            "count": len(set(workaround_ids)),
        },
        "index": _index_status(conn, analysis_run_id),
        "filters_empty_message": "filters exclude all items",
        "ranking_copy": RANKING_COPY,
        "research": research,
    }


def categories(conn: sqlite3.Connection, analysis_run_id: str) -> dict[str, Any]:
    spec = load_run_spec(conn, analysis_run_id)
    version = str((spec.get("analysis") or {}).get("taxonomy_version") or "v0")
    tax = load_taxonomy(version=version)
    return {
        **chrome(conn, analysis_run_id),
        "taxonomy": [
            {
                "id": n.id,
                "name": n.name,
                "definition": n.definition,
                "parent_id": n.parent_id,
            }
            for n in tax.nodes
        ],
        "categories": _category_rows(conn, analysis_run_id),
        "ranking_copy": RANKING_COPY,
    }


def get_item(conn: sqlite3.Connection, analysis_run_id: str, item_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id, source, source_url, authored_at, captured_at, locale, text,
               thread_context, relevance_label, relevance_confidence, segments_json,
               redaction_flag
        FROM feedback_item
        WHERE id = ? AND analysis_run_id = ?
        """,
        (item_id, analysis_run_id),
    ).fetchone()
    if row is None:
        return None
    class_rows = conn.execute(
        """
        SELECT taxonomy_node_id, confidence, rationale, snippets_json
        FROM classification WHERE feedback_item_id = ?
        """,
        (item_id,),
    ).fetchall()
    tax = _taxonomy_map(conn, analysis_run_id)
    classifications = []
    for c in class_rows:
        node = tax.get(c["taxonomy_node_id"]) or {"name": c["taxonomy_node_id"]}
        snippets = _json_list(c["snippets_json"])
        expanded = [expand_to_sentence_boundary(row["text"] or "", s) for s in snippets]
        classifications.append(
            {
                "taxonomy_node_id": c["taxonomy_node_id"],
                "name": node.get("name"),
                "confidence": c["confidence"],
                "rationale": c["rationale"],
                "snippets": snippets,
                "expanded_snippets": expanded,
            }
        )
    return {
        "id": row["id"],
        "source": row["source"],
        "source_url": row["source_url"],
        "authored_at": row["authored_at"],
        "captured_at": row["captured_at"],
        "locale": row["locale"],
        "text": row["text"],
        "thread_context": row["thread_context"],
        "relevance_label": row["relevance_label"],
        "relevance_confidence": row["relevance_confidence"],
        "segments": _json_obj(row["segments_json"]),
        "redaction_flag": bool(row["redaction_flag"]),
        "classifications": classifications,
        "citable": bool(row["source_url"]),
    }


def evidence(
    conn: sqlite3.Connection,
    analysis_run_id: str,
    *,
    kind: str,
    taxonomy_node_id: str | None = None,
    source: str | None = None,
    overlay: str | None = None,
    segment_key: str | None = None,
    segment_value: str | None = None,
    sentiment: str | None = None,
    signal: str | None = None,
    search_type: str | None = None,
) -> dict[str, Any]:
    """Evidence lists that must sum to the dashboard number (edge §11 blocker)."""
    items = _relevant_items(conn, analysis_run_id)
    ids: list[str] = []
    if kind == "relevant":
        ids = [i["id"] for i in items]
    elif kind == "source":
        ids = [i["id"] for i in items if i["source"] == source]
    elif kind == "sentiment":
        wanted = (sentiment or "").lower()
        for i in items:
            val = str(_json_obj(i["segments_json"]).get("sentiment") or "neutral")
            if wanted and val == wanted:
                ids.append(i["id"])
    elif kind == "signal":
        wanted = (signal or "").lower()
        for i in items:
            val = str(_json_obj(i["segments_json"]).get("signal") or "no_signal")
            if wanted and val == wanted:
                ids.append(i["id"])
    elif kind == "search_type":
        wanted = search_type or ""
        sent_wanted = (sentiment or "").lower() if sentiment else None
        for i in items:
            segs = _json_obj(i["segments_json"])
            types = segs.get("search_types") or []
            if not (wanted and isinstance(types, list) and wanted in types):
                continue
            if sent_wanted:
                val = str(segs.get("sentiment") or "neutral").lower()
                if val != sent_wanted:
                    continue
            ids.append(i["id"])
    elif kind == "suggestion":
        for i in items:
            if _json_obj(i["segments_json"]).get("is_suggestion"):
                ids.append(i["id"])
    elif kind == "category_frequency":
        if not taxonomy_node_id:
            return {"kind": kind, "count": 0, "items": [], "error": "taxonomy_node_id required"}
        node_ids = classification_node_ids_for_query(taxonomy_node_id)
        placeholders = ", ".join("?" for _ in node_ids)
        rows = conn.execute(
            f"""
            SELECT DISTINCT fi.id, fi.source, fi.source_url, fi.authored_at, fi.text
            FROM feedback_item fi
            JOIN classification c ON c.feedback_item_id = fi.id
            WHERE fi.analysis_run_id = ?
              AND fi.relevance_label = 'retrieval_related'
              AND c.taxonomy_node_id IN ({placeholders})
            ORDER BY fi.authored_at
            """,
            (analysis_run_id, *node_ids),
        ).fetchall()
        payload = [
            {
                "id": r["id"],
                "source": r["source"],
                "source_url": r["source_url"],
                "authored_at": r["authored_at"],
                "snippet": expand_to_sentence_boundary(r["text"] or "", (r["text"] or "")[:160]),
            }
            for r in rows
        ]
        return {
            "kind": kind,
            "taxonomy_node_id": taxonomy_node_id,
            "count": len(payload),
            "items": payload,
        }
    elif kind == "hypothesis":
        key = overlay if overlay in HYPOTHESIS_VALUES else None
        for i in items:
            val = _json_obj(i["segments_json"]).get("hypothesis_overlay") or "insufficient"
            if key and val == key:
                ids.append(i["id"])
    elif kind == "segment":
        sk = segment_key if segment_key in SEGMENT_KEYS else None
        sv = segment_value or "unknown"
        if sk:
            for i in items:
                val = _json_obj(i["segments_json"]).get(sk) or "unknown"
                if val == sv:
                    ids.append(i["id"])
    elif kind == "workaround":
        rows = conn.execute(
            """
            SELECT DISTINCT fi.id
            FROM feedback_item fi
            JOIN classification c ON c.feedback_item_id = fi.id
            WHERE fi.analysis_run_id = ?
              AND fi.relevance_label = 'retrieval_related'
              AND c.taxonomy_node_id = 'workarounds_succeeded'
            """,
            (analysis_run_id,),
        ).fetchall()
        ids = [r["id"] for r in rows]
    else:
        return {"kind": kind, "count": 0, "items": [], "error": "unknown evidence kind"}

    payload = []
    by_id = {i["id"]: i for i in items}
    for item_id in ids:
        row = by_id.get(item_id)
        if row is None:
            continue
        payload.append(
            {
                "id": row["id"],
                "source": row["source"],
                "source_url": row["source_url"],
                "authored_at": row["authored_at"],
                "snippet": expand_to_sentence_boundary(row["text"] or "", (row["text"] or "")[:160]),
            }
        )
    return {"kind": kind, "count": len(payload), "items": payload}


def extraction_stats(conn: sqlite3.Connection, analysis_run_id: str) -> dict[str, Any]:
    """Raw records collected per adapter and normalized feedback counts by source."""
    raw_by_source = {
        row["source"]: int(row["raw_count"] or 0)
        for row in conn.execute(
            """
            SELECT sr.source AS source, COUNT(rr.id) AS raw_count
            FROM source_run sr
            LEFT JOIN raw_record rr ON rr.source_run_id = sr.id
            WHERE sr.analysis_run_id = ?
            GROUP BY sr.source
            """,
            (analysis_run_id,),
        ).fetchall()
    }
    receipt_counts = {
        row["source"]: int(row["item_count"] or 0)
        for row in conn.execute(
            "SELECT source, item_count FROM source_run WHERE analysis_run_id = ?",
            (analysis_run_id,),
        ).fetchall()
    }
    label_counts: dict[str, dict[str, int]] = {s: {} for s in SOURCES}
    for row in conn.execute(
        """
        SELECT source, relevance_label, COUNT(*) AS cnt
        FROM feedback_item
        WHERE analysis_run_id = ?
        GROUP BY source, relevance_label
        """,
        (analysis_run_id,),
    ).fetchall():
        src = row["source"]
        if src not in label_counts:
            label_counts[src] = {}
        lab = row["relevance_label"] or "unknown"
        label_counts[src][lab] = int(row["cnt"] or 0)

    by_source: list[dict[str, Any]] = []
    totals = {
        "extracted_raw": 0,
        "normalized_total": 0,
        "retrieval_related": 0,
        "unrelated": 0,
        "ambiguous": 0,
    }
    for src in SOURCES:
        labels = label_counts.get(src) or {}
        normalized = sum(labels.values())
        rel = int(labels.get("retrieval_related") or 0)
        unrel = int(labels.get("unrelated") or 0)
        amb = int(labels.get("ambiguous") or 0)
        raw = int(raw_by_source.get(src) or 0)
        by_source.append(
            {
                "source": src,
                "extracted_raw": raw,
                "receipt_reported": int(receipt_counts.get(src) or 0),
                "normalized_total": normalized,
                "retrieval_related": rel,
                "unrelated": unrel,
                "ambiguous": amb,
            }
        )
        totals["extracted_raw"] += raw
        totals["normalized_total"] += normalized
        totals["retrieval_related"] += rel
        totals["unrelated"] += unrel
        totals["ambiguous"] += amb

    return {
        "by_source": by_source,
        "totals": totals,
        "note": (
            "extracted_raw is immutable raw_record rows from collection. "
            "normalized_total is feedback_item rows after normalize; "
            "retrieval_related is the analysis corpus for dashboard and RAG."
        ),
    }


def methodology(conn: sqlite3.Connection, analysis_run_id: str) -> dict[str, Any]:
    meta = chrome(conn, analysis_run_id)
    receipts = _source_receipts(conn, analysis_run_id)
    method = _methodology_row(conn, analysis_run_id)
    spec = load_run_spec(conn, analysis_run_id)
    coverage = method["coverage"]
    return {
        **meta,
        "sources": list(SOURCES),
        "collection_methods": COLLECTION_METHODS,
        "source_receipts": receipts,
        "data_extraction": extraction_stats(conn, analysis_run_id),
        "date_window": spec.get("date_window") or {},
        "run_spec_summary": {
            "app_store_storefronts": (spec.get("app_store") or {}).get("storefronts"),
            "play_package": (spec.get("play_store") or {}).get("package_name"),
            "reddit_subreddits": (spec.get("reddit") or {}).get("subreddits"),
            "reddit_keywords": (spec.get("reddit") or {}).get("keywords"),
            "help_community_discovery": (spec.get("help_community") or {}).get("discovery"),
        },
        "prompts": method["prompts"],
        "model_ids": method["model_ids"],
        "coverage": coverage,
        "taxonomy": list(_taxonomy_map(conn, analysis_run_id).values()),
        "multi_label_counting_rule": coverage.get("multi_label_counting_rule"),
        "bias_notes": method["bias_notes"] or BIAS_NOTES,
        "required_limitations": REQUIRED_LIMITATIONS,
        "limitations": method["limitations"],
        "open_decisions": method["open_decisions"],
        "human_review": (
            "Human review is required when classification confidence is low, "
            "items are ambiguous, or a category would drive a roadmap bet."
        ),
        "ranking_copy": RANKING_COPY,
        "non_claims": list(NON_CLAIMS),
        "out_of_repo_scope": list(OUT_OF_REPO_SCOPE),
        "pipeline_required_for_serving": False,
    }


def quality(conn: sqlite3.Connection, analysis_run_id: str) -> dict[str, Any]:
    meta = chrome(conn, analysis_run_id)
    coverage = _methodology_row(conn, analysis_run_id)["coverage"]
    gold = coverage.get("gold_eval") or {}
    segments = coverage.get("segment_unknown_rates") or {}
    for key in SEGMENT_KEYS:
        segments.setdefault(key, None)
    overlay = coverage.get("hypothesis_overlay") or {}
    counts = overlay.get("counts") or {}
    for k in HYPOTHESIS_VALUES:
        counts.setdefault(k, 0)
    return {
        **meta,
        "gold_eval": gold,
        "segment_unknown_rates": segments,
        "hypothesis_overlay": {
            "counts": {k: int(counts.get(k) or 0) for k in HYPOTHESIS_VALUES},
            "overall": overlay.get("overall") or "insufficient",
            "values_supported": list(HYPOTHESIS_VALUES),
        },
        "classified_count": coverage.get("classified_count"),
        "unclassified_count": coverage.get("unclassified_count"),
        "clusters": coverage.get("clusters"),
        "bias_notes": BIAS_NOTES,
        "index": _index_status(conn, analysis_run_id),
    }


def search_payload(
    conn: sqlite3.Connection,
    analysis_run_id: str,
    body: dict[str, Any],
    *,
    run_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    req = SearchRequest(
        query=str(body.get("query") or ""),
        sources=body.get("sources"),
        category=body.get("category"),
        date_after=body.get("date_after"),
        date_before=body.get("date_before"),
        min_confidence=body.get("min_confidence"),
        include_synthesis=body.get("include_synthesis"),
    )
    result = search(conn, analysis_run_id, req, run_spec=run_spec)
    payload = result.to_dict()
    payload.update(chrome(conn, analysis_run_id))
    payload["index"] = _index_status(conn, analysis_run_id)
    return payload


def parse_query(qs: str) -> dict[str, str]:
    parsed = parse_qs(qs or "", keep_blank_values=True)
    return {k: (v[-1] if v else "") for k, v in parsed.items()}
