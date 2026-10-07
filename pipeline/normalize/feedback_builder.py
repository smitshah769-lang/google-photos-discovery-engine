from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from pipeline.analysis.curated_labels import curated_relevance, item_key
from pipeline.normalize.relevance import classify_relevance
from pipeline.normalize.text_clean import strip_help_community_chrome, strip_html_markdown
from pipeline.run_context import utc_now_iso


def _synthesize_url(source: str, native_id: str, existing: str | None) -> str | None:
    if existing:
        return existing
    if source == "reddit" and native_id:
        return f"https://www.reddit.com/comments/{native_id}"
    if source == "help_community" and native_id:
        return f"https://support.google.com/photos/thread/{native_id}"
    return None


def build_feedback_from_raw(
    payload: dict[str, Any],
    curated: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    if not payload.get("has_user_text", True):
        return None
    source = str(payload.get("source", ""))
    title = payload.get("title")
    raw_text = str(payload.get("text") or "")
    if source == "help_community":
        text = strip_help_community_chrome(raw_text, title)
    else:
        text = strip_html_markdown(raw_text)
        if title and str(title) not in text:
            text = f"{strip_html_markdown(str(title))}\n{text}".strip()
    if not text:
        return None
    native_id = str(payload.get("native_id", ""))
    reviewed = (curated or {}).get(item_key(source, payload) or "")
    if reviewed is not None:
        label, confidence = curated_relevance(reviewed)
    else:
        label, confidence = classify_relevance(text, source, title=str(title) if title else None)
    return {
        "source": source,
        "source_url": _synthesize_url(source, native_id, payload.get("source_url")),
        "authored_at": payload.get("authored_at"),
        "locale": payload.get("locale"),
        "text": text,
        "thread_context": payload.get("thread_context"),
        "relevance_label": label,
        "relevance_confidence": confidence,
    }


def normalize_analysis_run(
    conn: sqlite3.Connection,
    analysis_run_id: str,
    curated: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT rr.id AS raw_id, rr.payload_json, sr.source
        FROM raw_record rr
        JOIN source_run sr ON sr.id = rr.source_run_id
        WHERE sr.analysis_run_id = ?
        """,
        (analysis_run_id,),
    ).fetchall()

    now = utc_now_iso()
    created = 0
    relevant = 0
    ambiguous = 0
    unrelated = 0
    by_source: dict[str, int] = {}

    for row in rows:
        payload = json.loads(row["payload_json"])
        built = build_feedback_from_raw(payload, curated)
        if not built:
            continue
        item_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO feedback_item
              (id, analysis_run_id, raw_record_id, source, source_url, authored_at,
               captured_at, locale, text, thread_context, relevance_label,
               relevance_confidence, segments_json, redaction_flag)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                item_id,
                analysis_run_id,
                row["raw_id"],
                built["source"],
                built["source_url"],
                built["authored_at"],
                now,
                built["locale"],
                built["text"],
                built["thread_context"],
                built["relevance_label"],
                built["relevance_confidence"],
                json.dumps({}),
            ),
        )
        created += 1
        by_source[built["source"]] = by_source.get(built["source"], 0) + 1
        if built["relevance_label"] == "retrieval_related":
            relevant += 1
        elif built["relevance_label"] == "ambiguous":
            ambiguous += 1
        else:
            unrelated += 1

    target_row = conn.execute(
        "SELECT corpus_target_relevant FROM analysis_run WHERE id = ?",
        (analysis_run_id,),
    ).fetchone()
    target = int(target_row["corpus_target_relevant"]) if target_row else 500

    return {
        "normalized_count": created,
        "relevant_count": relevant,
        "ambiguous_count": ambiguous,
        "unrelated_count": unrelated,
        "by_source": by_source,
        "corpus_target_relevant": target,
        "meets_target": relevant >= target,
    }
