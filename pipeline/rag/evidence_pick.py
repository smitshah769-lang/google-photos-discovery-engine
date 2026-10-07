from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from pipeline.rag.quotes import expand_to_sentence_boundary
from pipeline.rag.rerank import lexical_overlap_boost


def _json_obj(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        val = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return val if isinstance(val, dict) else {}


def _row_to_evidence(row: sqlite3.Row, *, context: str) -> dict[str, Any]:
    text = row["text"] or ""
    snippet = expand_to_sentence_boundary(text, text[:240])
    return {
        "item_id": row["id"],
        "snippet": snippet,
        "source": row["source"],
        "source_url": row["source_url"],
        "context": context,
    }


def _items_for_sentiment(
    conn: sqlite3.Connection,
    analysis_run_id: str,
    sentiment: str,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, source, source_url, text, segments_json
        FROM feedback_item
        WHERE analysis_run_id = ?
          AND relevance_label = 'retrieval_related'
          AND source_url IS NOT NULL AND TRIM(source_url) != ''
          AND LENGTH(text) > 40
        """,
        (analysis_run_id,),
    ).fetchall()
    matches: list[tuple[int, sqlite3.Row]] = []
    for row in rows:
        segs = _json_obj(row["segments_json"])
        if str(segs.get("sentiment") or "neutral").lower() != sentiment:
            continue
        blob = (row["text"] or "").lower()
        score = 0
        for term in ("search", "find", "photo", "face", "ai", "ask photos"):
            if term in blob:
                score += 1
        matches.append((score, row))
    matches.sort(key=lambda x: x[0], reverse=True)
    out: list[dict[str, Any]] = []
    label = sentiment.capitalize()
    for _score, row in matches[:limit]:
        out.append(
            _row_to_evidence(
                row,
                context=f"Example of {label.lower()} sentiment about search/retrieval in this snapshot.",
            )
        )
    return out


def _items_for_taxonomy(
    conn: sqlite3.Connection,
    analysis_run_id: str,
    taxonomy_node_id: str,
    theme_name: str,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT fi.id, fi.source, fi.source_url, fi.text
        FROM feedback_item fi
        JOIN classification c ON c.feedback_item_id = fi.id
        WHERE fi.analysis_run_id = ?
          AND fi.relevance_label = 'retrieval_related'
          AND fi.source_url IS NOT NULL AND TRIM(fi.source_url) != ''
          AND c.taxonomy_node_id = ?
        ORDER BY c.confidence DESC NULLS LAST
        LIMIT ?
        """,
        (analysis_run_id, taxonomy_node_id, limit * 3),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows[:limit]:
        out.append(
            _row_to_evidence(
                row,
                context=f"Tagged under “{theme_name}” in this snapshot’s taxonomy.",
            )
        )
    return out


def _items_from_hits(
    query: str,
    hits: list[dict[str, Any]],
    *,
    limit: int,
    min_overlap: float = 0.22,
) -> list[dict[str, Any]]:
    scored: list[tuple[float, dict[str, Any]]] = []
    for hit in hits:
        snippet = hit.get("snippet") or ""
        overlap = lexical_overlap_boost(query, snippet)
        if overlap < min_overlap:
            continue
        scored.append((overlap, hit))
    scored.sort(key=lambda x: x[0], reverse=True)
    if not scored and hits:
        scored = [(0.0, h) for h in hits[:limit]]
    out: list[dict[str, Any]] = []
    for rel, hit in scored[:limit]:
        out.append(
            {
                "item_id": hit["item_id"],
                "snippet": hit.get("snippet") or "",
                "source": hit.get("source"),
                "source_url": hit.get("source_url"),
                "context": "Closest verbatim match to your question in retrieved feedback.",
            }
        )
    return out


def pick_supporting_evidence(
    query: str,
    hits: list[dict[str, Any]],
    *,
    conn: sqlite3.Connection | None,
    analysis_run_id: str,
    research: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    q = (query or "").lower()

    if conn and re.search(r"\bsentiment\b", q):
        neg = _items_for_sentiment(conn, analysis_run_id, "negative", limit=1)
        other = _items_for_sentiment(conn, analysis_run_id, "neutral", limit=1)
        if not other:
            other = _items_for_sentiment(conn, analysis_run_id, "positive", limit=1)
        combined = neg + other
        if combined:
            return combined[:2]

    if conn and research and re.search(r"\bpain\s+points?\b", q):
        pain = research.get("pain_points") or []
        if pain:
            top = pain[0]
            picked = _items_for_taxonomy(
                conn,
                analysis_run_id,
                str(top["taxonomy_node_id"]),
                str(top["name"]),
                limit=2,
            )
            if picked:
                return picked

    if conn and re.search(r"\bai\s+search\b|ask\s+photos", q):
        rows = conn.execute(
            """
            SELECT id, source, source_url, text, segments_json
            FROM feedback_item
            WHERE analysis_run_id = ?
              AND relevance_label = 'retrieval_related'
              AND source_url IS NOT NULL
            """,
            (analysis_run_id,),
        ).fetchall()
        ai_rows: list[sqlite3.Row] = []
        for row in rows:
            segs = _json_obj(row["segments_json"])
            types = segs.get("search_types") or []
            if isinstance(types, list) and "search_ai_search" in types:
                ai_rows.append(row)
        if ai_rows:
            return [
                _row_to_evidence(
                    ai_rows[0],
                    context="Mentions Search / AI Search / Ask Photos in labeled segments.",
                )
            ][:2]

    return _items_from_hits(query, hits, limit=2)
