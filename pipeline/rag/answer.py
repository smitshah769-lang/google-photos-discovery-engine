from __future__ import annotations

import re
from typing import Any

import sqlite3

from pipeline.rag.evidence_pick import pick_supporting_evidence
from pipeline.serve.research_insights import build_research_dashboard


def _pct(part: int, whole: int) -> int:
    if whole <= 0:
        return 0
    return round(100 * part / whole)


def _sentiment_payload(research: dict[str, Any], relevant: int) -> dict[str, Any]:
    rows = {r["id"]: int(r["value"]) for r in research.get("overall_sentiment") or []}
    total = sum(rows.values()) or relevant or 1
    neg, neu, pos = (rows.get("negative", 0), rows.get("neutral", 0), rows.get("positive", 0))
    ai = research.get("search_ai_search") or {}
    ai_total = int(ai.get("frequency") or 0) or (
        int(ai.get("positive") or 0) + int(ai.get("negative") or 0) + int(ai.get("neutral") or 0)
    )
    stats = [
        {"label": "Negative", "value": f"{_pct(neg, total)}%", "detail": f"{neg:,} items"},
        {"label": "Neutral", "value": f"{_pct(neu, total)}%", "detail": f"{neu:,} items"},
        {"label": "Positive", "value": f"{_pct(pos, total)}%", "detail": f"{pos:,} items"},
    ]
    bullets = [
        f"Labels come from the frozen research pass on {total:,} retrieval-related items—not live ratings.",
    ]
    if ai_total:
        bullets.append(
            f"Among {ai_total:,} items that mention Search / AI Search / Ask Photos, "
            f"{_pct(int(ai.get('negative') or 0), ai_total)}% are negative."
        )
    plain = (
        f"Search-related sentiment is {_pct(neg, total)}% negative, "
        f"{_pct(neu, total)}% neutral, and {_pct(pos, total)}% positive."
    )
    return {
        "format": "sentiment",
        "headline": "Overall search sentiment in this snapshot",
        "summary": plain,
        "stats": stats,
        "bullets": bullets,
    }


def _pain_payload(research: dict[str, Any], relevant: int) -> dict[str, Any]:
    pain = research.get("pain_points") or []
    if not pain:
        return {
            "format": "narrative",
            "headline": "Pain points",
            "summary": "Limited pain-point labels in this snapshot.",
            "stats": [],
            "bullets": [],
        }
    stats = [
        {"label": p["name"], "value": f"{p['frequency']:,}", "detail": "items tagged"}
        for p in pain[:4]
    ]
    lead = pain[0]["name"]
    bullets = [
        f"Across {relevant:,} retrieval-related items, “{lead}” is the most frequent overarching theme.",
        "Counts reflect taxonomy labels in this freeze, not production telemetry.",
    ]
    return {
        "format": "pain_points",
        "headline": "Top pain themes (taxonomy)",
        "summary": f"Lead theme: {lead} ({pain[0]['frequency']:,} items).",
        "stats": stats,
        "bullets": bullets,
    }


def _summary_from_hits(query: str, hits: list[dict[str, Any]]) -> str:
    if not hits:
        return "No closely matching feedback was retrieved for that wording."
    themes: list[str] = []
    for h in hits[:6]:
        for cat in h.get("categories") or []:
            if cat not in themes:
                themes.append(str(cat))
            if len(themes) >= 3:
                break
    theme_bit = f" Themes that show up in the top matches include {', '.join(themes)}." if themes else ""
    return (
        f"Based on the closest-matching feedback in this snapshot, users often describe issues "
        f"related to “{query.strip()}”.{theme_bit} "
        "The two quotes below are the strongest supporting examples from retrieved items."
    )


def _pick_presentation(
    query: str, research: dict[str, Any] | None, relevant: int, hits: list[dict[str, Any]]
) -> dict[str, Any]:
    q = (query or "").lower()
    if research:
        if re.search(r"\bpain\s+points?\b|\bfrustrations?\b|\bcomplaints?\b", q):
            return _pain_payload(research, relevant)
        if re.search(r"\bsentiment\b|\bnegative\b|\bpositive\b|\bfeel\b", q):
            return _sentiment_payload(research, relevant)
        if re.search(r"\bkey\s+findings?\b|\boverall\b|\bthemes?\b", q):
            text = str(research.get("key_findings") or _summary_from_hits(query, hits))
            return {
                "format": "narrative",
                "headline": "Key findings",
                "summary": text,
                "stats": [],
                "bullets": [],
            }
    text = _summary_from_hits(query, hits)
    return {
        "format": "narrative",
        "headline": "From matching feedback",
        "summary": text,
        "stats": [],
        "bullets": [],
    }


def query_wants_snapshot_metrics(query: str) -> bool:
    q = (query or "").lower()
    return bool(
        re.search(
            r"pain\s+points?|sentiment|key\s+findings?|overall|themes?|how\s+(?:is|are)\s+users?",
            q,
        )
    )


def compose_search_answer(
    query: str,
    hits: list[dict[str, Any]],
    *,
    conn: sqlite3.Connection | None,
    analysis_run_id: str,
    relevant_count: int | None = None,
    cited_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Reviewer-facing answer: narrative summary plus at most two supporting quotes.
    """
    relevant = relevant_count or 0
    research: dict[str, Any] | None = None
    q = (query or "").lower()
    if query_wants_snapshot_metrics(query) and conn is not None:
        research = build_research_dashboard(conn, analysis_run_id, relevant_count=relevant)

    if cited_summary and cited_summary.get("summary"):
        presentation = {
            "format": "narrative",
            "headline": "Summary",
            "summary": str(cited_summary["summary"]).strip(),
            "stats": [],
            "bullets": [],
        }
    else:
        presentation = _pick_presentation(query, research, relevant, hits)

    evidence: list[dict[str, Any]] = []
    if cited_summary:
        for cite in (cited_summary.get("citations") or [])[:2]:
            if not isinstance(cite, dict):
                continue
            item_id = str(cite.get("item_id") or "")
            quote = str(cite.get("quote") or "")
            if not item_id or not quote:
                continue
            base = next((h for h in hits if h["item_id"] == item_id), None)
            evidence.append(
                {
                    "item_id": item_id,
                    "snippet": quote,
                    "source": base.get("source") if base else None,
                    "source_url": base.get("source_url") if base else None,
                    "context": "Cited by the synthesis model from retrieved evidence.",
                }
            )

    if len(evidence) < 2:
        picked = pick_supporting_evidence(
            query,
            hits,
            conn=conn,
            analysis_run_id=analysis_run_id,
            research=research,
        )
        for item in picked:
            if any(e["item_id"] == item["item_id"] for e in evidence):
                continue
            evidence.append(item)
            if len(evidence) >= 2:
                break

    return {
        **presentation,
        "evidence": evidence[:2],
    }
