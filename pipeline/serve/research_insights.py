from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from typing import Any

from pipeline.analysis.research_tags import (
    SEARCH_AI_SEARCH_TYPE_ID,
    SEARCH_TYPE_IDS,
    SEARCH_TYPE_IDS_FOR_THEME_CHARTS,
    SEARCH_TYPE_NAMES,
    engagement_rank,
)
from pipeline.db.repository import load_run_spec
from pipeline.rag.quotes import expand_to_sentence_boundary
from pipeline.taxonomy import load_taxonomy
from pipeline.taxonomy_aliases import resolve_taxonomy_label

OVERARCHING_IDS = (
    "design_issues",
    "system_issues",
    "query_inference",
    "knowledge_awareness_gaps",
)

SENTIMENT_ORDER = ("positive", "negative", "neutral")
SIGNAL_ORDER = ("actionable", "no_signal")

YEAR_COVERAGE_BUCKETS = ("2026", "2025", "2024")


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


def _taxonomy_for_run(conn: sqlite3.Connection, analysis_run_id: str):
    spec = load_run_spec(conn, analysis_run_id)
    version = str((spec.get("analysis") or {}).get("taxonomy_version") or "v0")
    return load_taxonomy(version=version)


def build_research_dashboard(
    conn: sqlite3.Connection,
    analysis_run_id: str,
    *,
    relevant_count: int,
) -> dict[str, Any]:
    taxonomy = _taxonomy_for_run(conn, analysis_run_id)
    node_map = {n.id: n for n in taxonomy.nodes}
    parent_names = {n.id: n.name for n in taxonomy.nodes if n.parent_id is None}

    item_rows = conn.execute(
        """
        SELECT id, source, source_url, authored_at, text, segments_json
        FROM feedback_item
        WHERE analysis_run_id = ? AND relevance_label = 'retrieval_related'
        """,
        (analysis_run_id,),
    ).fetchall()

    class_rows = conn.execute(
        """
        SELECT feedback_item_id, taxonomy_node_id, snippets_json
        FROM classification
        WHERE feedback_item_id IN (
          SELECT id FROM feedback_item
          WHERE analysis_run_id = ? AND relevance_label = 'retrieval_related'
        )
        """,
        (analysis_run_id,),
    ).fetchall()

    item_text: dict[str, str] = {r["id"]: r["text"] or "" for r in item_rows}
    item_meta: dict[str, dict[str, Any]] = {
        r["id"]: {
            "source": r["source"],
            "source_url": r["source_url"],
            "authored_at": r["authored_at"],
            "segments": _json_obj(r["segments_json"]),
        }
        for r in item_rows
    }
    item_labels: dict[str, list[str]] = defaultdict(list)
    item_snippets: dict[str, list[str]] = defaultdict(list)
    for row in class_rows:
        fid = row["feedback_item_id"]
        nid = resolve_taxonomy_label(str(row["taxonomy_node_id"] or ""))
        if nid and nid not in item_labels[fid]:
            item_labels[fid].append(nid)
        for snip in _json_list(row["snippets_json"]):
            if snip and snip not in item_snippets[fid]:
                item_snippets[fid].append(str(snip))

    sub_freq: Counter[str] = Counter()
    parent_item_counts: Counter[str] = Counter()
    sentiment_counts: Counter[str] = Counter()
    signal_counts: Counter[str] = Counter()
    search_type_counts: Counter[str] = Counter()
    search_type_sentiment: dict[str, Counter[str]] = {
        tid: Counter() for tid in SEARCH_TYPE_IDS
    }
    suggestion_candidates: list[dict[str, Any]] = []

    year_bucket_counts: Counter[str] = Counter()
    for row in item_rows:
        authored = row["authored_at"]
        if authored and len(str(authored)) >= 4 and str(authored)[:4].isdigit():
            year = str(authored)[:4]
            if year in YEAR_COVERAGE_BUCKETS:
                year_bucket_counts[year] += 1
            else:
                year_bucket_counts["Unknown"] += 1
        else:
            year_bucket_counts["Unknown"] += 1
        segs = _json_obj(row["segments_json"])
        sentiment = str(segs.get("sentiment") or "neutral")
        if sentiment not in SENTIMENT_ORDER:
            sentiment = "neutral"
        sentiment_counts[sentiment] += 1
        signal = str(segs.get("signal") or "no_signal")
        if signal not in SIGNAL_ORDER:
            signal = "no_signal"
        signal_counts[signal] += 1
        types = segs.get("search_types") or []
        if isinstance(types, list):
            for tid in types:
                if tid in SEARCH_TYPE_IDS:
                    search_type_counts[tid] += 1
                    search_type_sentiment[tid][sentiment] += 1
        if segs.get("is_suggestion") and not segs.get("is_forum_reply"):
            engagement = segs.get("engagement") if isinstance(segs.get("engagement"), dict) else {}
            snippet = expand_to_sentence_boundary(row["text"] or "", (row["text"] or "")[:220])
            suggestion_candidates.append(
                {
                    "id": row["id"],
                    "source": row["source"],
                    "source_url": row["source_url"],
                    "authored_at": row["authored_at"],
                    "snippet": snippet,
                    "engagement": engagement,
                    "rank": engagement_rank(engagement),
                    "priority": _suggestion_priority(row["text"] or ""),
                }
            )

    for fid, labels in item_labels.items():
        parents: set[str] = set()
        for lab in labels:
            node = node_map.get(lab)
            if not node:
                continue
            if node.parent_id:
                sub_freq[lab] += 1
                if node.parent_id in OVERARCHING_IDS:
                    parents.add(node.parent_id)
            elif lab in OVERARCHING_IDS:
                parents.add(lab)
        for pid in parents:
            parent_item_counts[pid] += 1

    sub_theme_rows = []
    for node in taxonomy.nodes:
        if node.parent_id is None:
            continue
        freq = sub_freq.get(node.id, 0)
        if freq == 0:
            continue
        sub_theme_rows.append(
            {
                "taxonomy_node_id": node.id,
                "name": node.name,
                "parent_id": node.parent_id,
                "parent_name": parent_names.get(node.parent_id or "", node.parent_id),
                "frequency": freq,
            }
        )
    sub_theme_rows.sort(key=lambda r: r["frequency"], reverse=True)

    pain_points = [
        {
            "taxonomy_node_id": pid,
            "name": parent_names.get(pid, pid),
            "frequency": parent_item_counts.get(pid, 0),
        }
        for pid in OVERARCHING_IDS
        if parent_item_counts.get(pid, 0) > 0
    ]
    pain_points.sort(key=lambda r: r["frequency"], reverse=True)

    search_types = [
        {
            "id": tid,
            "name": SEARCH_TYPE_NAMES[tid],
            "frequency": search_type_counts.get(tid, 0),
        }
        for tid in SEARCH_TYPE_IDS_FOR_THEME_CHARTS
        if search_type_counts.get(tid, 0) > 0
    ]
    search_types.sort(key=lambda r: r["frequency"], reverse=True)

    search_type_sentiment_rows = []
    for tid in SEARCH_TYPE_IDS_FOR_THEME_CHARTS:
        counts = search_type_sentiment[tid]
        total = sum(counts.values())
        if total == 0:
            continue
        search_type_sentiment_rows.append(
            {
                "id": tid,
                "name": SEARCH_TYPE_NAMES[tid],
                "positive": counts.get("positive", 0),
                "negative": counts.get("negative", 0),
                "neutral": counts.get("neutral", 0),
                "total": total,
            }
        )
    search_type_sentiment_rows.sort(key=lambda r: r["total"], reverse=True)

    ai_counts = search_type_sentiment[SEARCH_AI_SEARCH_TYPE_ID]
    search_ai_search = {
        "id": SEARCH_AI_SEARCH_TYPE_ID,
        "name": SEARCH_TYPE_NAMES[SEARCH_AI_SEARCH_TYPE_ID],
        "frequency": search_type_counts.get(SEARCH_AI_SEARCH_TYPE_ID, 0),
        "positive": ai_counts.get("positive", 0),
        "negative": ai_counts.get("negative", 0),
        "neutral": ai_counts.get("neutral", 0),
    }

    suggestion_candidates.sort(key=lambda r: (r["rank"], r.get("priority", 0)), reverse=True)
    top_suggestions = [
        {k: v for k, v in row.items() if k != "priority"}
        for row in suggestion_candidates[:5]
    ]
    suggestion_summary = _suggestion_summary(top_suggestions)

    year_rows = [
        {"year": year, "count": year_bucket_counts.get(year, 0)} for year in (*YEAR_COVERAGE_BUCKETS, "Unknown")
    ]
    featured = _featured_snippets(conn, analysis_run_id, item_meta, item_text, limit=8)
    key_findings = _qualitative_summary(
        relevant_count=relevant_count,
        pain_points=pain_points,
        sub_theme_rows=sub_theme_rows[:6],
        search_types=search_types[:4],
        sentiment_counts=sentiment_counts,
        signal_counts=signal_counts,
    )

    return {
        "key_findings": key_findings,
        "pain_points": pain_points,
        "sub_themes": sub_theme_rows,
        "overall_sentiment": [
            {"id": key, "label": key, "value": sentiment_counts.get(key, 0)}
            for key in SENTIMENT_ORDER
        ],
        "signal_mix": [
            {
                "id": key,
                "label": "Actionable signal" if key == "actionable" else "No signal",
                "value": signal_counts.get(key, 0),
            }
            for key in SIGNAL_ORDER
        ],
        "search_types": search_types,
        "search_type_sentiment": search_type_sentiment_rows,
        "search_ai_search": search_ai_search,
        "top_suggestions": top_suggestions,
        "suggestion_summary": suggestion_summary,
        "year_coverage": year_rows,
        "featured_snippets": featured,
        "kpi": {
            "sub_theme_count": len(sub_theme_rows),
            "suggestion_items": len(suggestion_candidates),
            "overarching_theme_count": len(pain_points),
            "actionable_count": signal_counts.get("actionable", 0),
            "search_typed_count": sum(1 for meta in item_meta.values() if meta["segments"].get("search_types")),
        },
    }


def _suggestion_priority(text: str) -> int:
    blob = (text or "").lower()
    score = 0
    for token in (
        "search bar",
        "search function",
        "bring back",
        "date grouping",
        "face",
        "please add",
        "filename",
        "file name",
        "text search",
    ):
        if token in blob:
            score += 1
    if len(text or "") > 900:
        score -= 1
    return score


def _suggestion_summary(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return (
            "No in-scope suggestion snippets with a clear product request were tagged in this snapshot."
        )
    bits = []
    joined = " ".join(r["snippet"].lower() for r in rows)
    if "date" in joined or "group" in joined:
        bits.append("restore date grouping")
    if "search bar" in joined or "search button" in joined:
        bits.append("bring back a visible search control")
    if "face" in joined or "people" in joined:
        bits.append("improve people and face search")
    if "filter" in joined or "video" in joined:
        bits.append("add more result filters")
    if not bits:
        bits.append("fix or restore search behaviour users already relied on")
    return (
        f"The {len(rows)} highest-engagement suggestion snippets ask to {', then '.join(bits[:3])}."
    )


def _featured_snippets(
    conn: sqlite3.Connection,
    analysis_run_id: str,
    item_meta: dict[str, dict[str, Any]],
    item_text: dict[str, str],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT fi.id, fi.segments_json, MAX(ca.severity) AS severity
        FROM feedback_item fi
        JOIN classification c ON c.feedback_item_id = fi.id
        LEFT JOIN category_aggregate ca ON ca.analysis_run_id = fi.analysis_run_id
          AND ca.taxonomy_node_id = c.taxonomy_node_id
        WHERE fi.analysis_run_id = ?
          AND fi.relevance_label = 'retrieval_related'
        GROUP BY fi.id
        ORDER BY severity DESC NULLS LAST
        LIMIT ?
        """,
        (analysis_run_id, limit * 6),
    ).fetchall()
    featured: list[dict[str, Any]] = []
    for row in rows:
        segs = _json_obj(row["segments_json"] if "segments_json" in row.keys() else None)
        if segs.get("signal") != "actionable":
            continue
        meta = item_meta.get(row["id"], {})
        text = item_text.get(row["id"], "")
        featured.append(
            {
                "id": row["id"],
                "source": meta.get("source"),
                "source_url": meta.get("source_url"),
                "authored_at": meta.get("authored_at"),
                "snippet": expand_to_sentence_boundary(text, text[:220]),
                "severity": row["severity"],
            }
        )
        if len(featured) >= limit:
            break
    return featured


def _qualitative_summary(
    *,
    relevant_count: int,
    pain_points: list[dict[str, Any]],
    sub_theme_rows: list[dict[str, Any]],
    search_types: list[dict[str, Any]],
    sentiment_counts: Counter[str],
    signal_counts: Counter[str],
) -> str:
    lead = pain_points[0]["name"] if pain_points else "Search retrieval"
    lead_share = pain_points[0]["frequency"] if pain_points else 0
    sub_bits = ", ".join(f"{r['name']} ({r['frequency']})" for r in sub_theme_rows[:3])
    type_bits = ", ".join(f"{r['name']} ({r['frequency']})" for r in search_types[:3])
    parts = [
        f"Across {relevant_count:,} search-related items, {signal_counts.get('actionable', 0):,} carry an "
        f"actionable pain point and {sentiment_counts.get('negative', 0):,} are negative about search.",
        f"{lead} is the most cited overarching theme ({lead_share:,} items).",
    ]
    if sub_bits:
        parts.append(f"The most common sub-themes are {sub_bits}.")
    if type_bits:
        parts.append(f"Search types mentioned most often are {type_bits}.")
    return " ".join(parts)
