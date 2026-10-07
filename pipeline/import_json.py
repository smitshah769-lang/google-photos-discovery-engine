from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipeline.adapters.types import CollectedItem
from pipeline.db.connection import assert_not_frozen, json_dumps
from pipeline.db.repository import (
    finalize_source_run,
    get_source_run_id,
    insert_collected_items,
)
from pipeline.paths import PROJECT_ROOT

SOURCE_KEYS = ("app_store", "play_store", "reddit", "help_community")
DEFAULT_JSON = PROJECT_ROOT / "photo_retrieval_feedback.json"

VALID_RECEIPT_STATUS = frozenset(
    {"pending", "running", "success", "partial", "failed", "gap", "skipped"}
)


def _has_text(value: str | None) -> bool:
    return bool(value and str(value).strip())


def item_from_app_store(row: dict[str, Any]) -> CollectedItem:
    text = str(row.get("text") or "")
    title = row.get("title")
    return CollectedItem(
        native_id=str(row["native_id"]),
        source="app_store",
        text=text,
        title=str(title) if title else None,
        authored_at=row.get("authored_at"),
        source_url=row.get("source_url"),
        locale=row.get("storefront"),
        has_user_text=_has_text(text),
        raw_api_payload=row.get("raw_entry"),
    )


def item_from_play_store(row: dict[str, Any]) -> CollectedItem:
    text = str(row.get("text") or "")
    return CollectedItem(
        native_id=str(row["native_id"]),
        source="play_store",
        text=text,
        authored_at=row.get("authored_at"),
        source_url=row.get("source_url"),
        locale=None,
        developer_reply=row.get("developer_reply"),
        has_user_text=_has_text(text),
        raw_api_payload=row.get("raw"),
    )


def item_from_reddit(row: dict[str, Any]) -> CollectedItem:
    text = str(row.get("text") or "")
    return CollectedItem(
        native_id=str(row["native_id"]),
        source="reddit",
        text=text,
        title=row.get("title"),
        authored_at=row.get("authored_at"),
        source_url=row.get("source_url"),
        locale=row.get("subreddit"),
        thread_context=row.get("thread_context"),
        has_user_text=_has_text(text),
        raw_api_payload={"kind": row.get("kind"), "query": row.get("query"), "raw": row.get("raw")},
    )


def item_from_help_community(row: dict[str, Any]) -> CollectedItem:
    text = str(row.get("text") or "")
    return CollectedItem(
        native_id=str(row["native_id"]),
        source="help_community",
        text=text,
        title=row.get("title"),
        authored_at=row.get("authored_at"),
        source_url=row.get("source_url"),
        thread_context=row.get("thread_context"),
        has_user_text=_has_text(text),
        raw_api_payload={"reply_count": row.get("reply_count")},
    )


CONVERTERS = {
    "app_store": item_from_app_store,
    "play_store": item_from_play_store,
    "reddit": item_from_reddit,
    "help_community": item_from_help_community,
}


def load_export(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object")
    if "raw" not in data:
        raise ValueError("Expected photos-discovery-raw-v1 export with a 'raw' object")
    return data


def _receipt_notes(receipt: dict[str, Any], item_count: int) -> tuple[str, str, str]:
    status = str(receipt.get("status", "success"))
    if status not in VALID_RECEIPT_STATUS:
        status = "partial"
    notes = str(receipt.get("notes", "Imported from photo_retrieval_feedback.json"))
    limits = receipt.get("coverage_limits") or []
    if limits:
        notes = f"{notes} Limits: {' | '.join(limits)}"
    notes = f"{notes} (imported {item_count} raw items)"
    return status, notes, notes


def clear_raw_for_run(conn, analysis_run_id: str) -> None:
    assert_not_frozen(conn, analysis_run_id)
    conn.execute(
        """
        DELETE FROM raw_record
        WHERE source_run_id IN (
          SELECT id FROM source_run WHERE analysis_run_id = ?
        )
        """,
        (analysis_run_id,),
    )


def clear_raw_for_source(conn, analysis_run_id: str, source: str) -> None:
    assert_not_frozen(conn, analysis_run_id)
    from pipeline.db.repository import get_source_run_id

    source_run_id = get_source_run_id(conn, analysis_run_id, source)
    conn.execute("DELETE FROM raw_record WHERE source_run_id = ?", (source_run_id,))


def import_raw_json(
    conn,
    analysis_run_id: str,
    export: dict[str, Any],
    *,
    replace: bool = True,
    sources: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    assert_not_frozen(conn, analysis_run_id)
    raw = export.get("raw") or {}
    receipts_in = export.get("receipts") or {}
    selected = sources or SOURCE_KEYS
    if replace:
        if sources:
            for source in selected:
                clear_raw_for_source(conn, analysis_run_id, source)
        else:
            clear_raw_for_run(conn, analysis_run_id)

    summary: dict[str, Any] = {"sources": {}, "total": 0}
    for source in SOURCE_KEYS:
        if source not in selected:
            continue
        rows = raw.get(source) or []
        if not isinstance(rows, list):
            raise ValueError(f"raw.{source} must be a list")

        converter = CONVERTERS[source]
        items: list[CollectedItem] = []
        seen: set[str] = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            native_id = str(row.get("native_id", ""))
            if not native_id or native_id in seen:
                continue
            seen.add(native_id)
            items.append(converter(row))

        source_run_id = get_source_run_id(conn, analysis_run_id, source)
        count = insert_collected_items(conn, source_run_id, items)

        receipt = receipts_in.get(source) or {}
        status, notes, _ = _receipt_notes(receipt, count)
        finalize_source_run(
            conn,
            analysis_run_id,
            source,
            status=status,
            item_count=count,
            notes=notes,
        )
        summary["sources"][source] = {"imported": count, "status": status}
        summary["total"] += count

    summary["imported_from"] = export.get("collection_date")
    summary["schema"] = export.get("schema")
    return summary
