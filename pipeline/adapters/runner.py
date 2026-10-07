from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from pipeline.adapters.app_store import collect_app_store
from pipeline.adapters.help_community import collect_help_community
from pipeline.adapters.play_store import collect_play_store
from pipeline.adapters.reddit import collect_reddit
from pipeline.adapters.types import AdapterResult
from pipeline.db.repository import (
    finalize_source_run,
    insert_collected_items,
    mark_source_run_running,
)
from pipeline.paths import PROJECT_ROOT


def _fixtures_dir(run_spec: dict[str, Any]) -> Path | None:
    collection = run_spec.get("collection") or {}
    mode = collection.get("mode", "live")
    if mode != "fixtures":
        return None
    rel = collection.get("fixtures_dir", "tests/fixtures")
    path = Path(rel)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _run_adapter(
    conn: sqlite3.Connection,
    analysis_run_id: str,
    source: str,
    result: AdapterResult,
) -> dict[str, Any]:
    mark_source_run_running(conn, analysis_run_id, source)
    from pipeline.db.repository import get_source_run_id

    source_run_id = get_source_run_id(conn, analysis_run_id, source)
    count = insert_collected_items(conn, source_run_id, result.items)
    notes = result.receipt.notes
    if result.receipt.coverage_limits:
        notes = f"{notes} Limits: {' | '.join(result.receipt.coverage_limits)}"
    finalize_source_run(
        conn,
        analysis_run_id,
        source,
        status=result.receipt.status,
        item_count=count,
        notes=notes,
    )
    return {
        "source": source,
        "status": result.receipt.status,
        "item_count": count,
        "notes": notes,
    }


def _run_help_community_with_persist(
    conn: sqlite3.Connection,
    analysis_run_id: str,
    run_spec: dict[str, Any],
    fixtures: Path | None,
) -> dict[str, Any]:
    from pipeline.db.repository import get_source_run_id

    mark_source_run_running(conn, analysis_run_id, "help_community")
    source_run_id = get_source_run_id(conn, analysis_run_id, "help_community")
    persisted = 0

    def on_item(item) -> None:
        nonlocal persisted
        persisted += insert_collected_items(conn, source_run_id, [item])
        conn.commit()

    help_result = collect_help_community(
        run_spec.get("help_community") or {},
        fixtures_dir=fixtures,
        on_item=on_item if fixtures is None else None,
    )
    if fixtures is not None:
        return _run_adapter(conn, analysis_run_id, "help_community", help_result)

    notes = help_result.receipt.notes
    if help_result.receipt.coverage_limits:
        notes = f"{notes} Limits: {' | '.join(help_result.receipt.coverage_limits)}"
    finalize_source_run(
        conn,
        analysis_run_id,
        "help_community",
        status=help_result.receipt.status,
        item_count=persisted,
        notes=notes,
    )
    return {
        "source": "help_community",
        "status": help_result.receipt.status,
        "item_count": persisted,
        "notes": notes,
    }


def _run_play_store_with_page_persist(
    conn: sqlite3.Connection,
    analysis_run_id: str,
    run_spec: dict[str, Any],
    fixtures: Path | None,
) -> dict[str, Any]:
    from pipeline.db.repository import get_source_run_id

    mark_source_run_running(conn, analysis_run_id, "play_store")
    source_run_id = get_source_run_id(conn, analysis_run_id, "play_store")
    persisted = 0

    def on_page(batch: list, meta: dict[str, Any]) -> None:
        nonlocal persisted
        persisted += insert_collected_items(conn, source_run_id, batch)
        conn.commit()
        print(
            f"play_store {meta['locale']} page {meta['page']}: "
            f"+{meta['page_new']} reviews ({meta['total_unique']} unique, {persisted} rows in DB)",
            flush=True,
        )

    play_result = collect_play_store(
        run_spec.get("play_store") or {},
        fixtures_dir=fixtures,
        on_page=on_page if fixtures is None else None,
    )
    if fixtures is not None:
        return _run_adapter(conn, analysis_run_id, "play_store", play_result)

    notes = play_result.receipt.notes
    if play_result.receipt.coverage_limits:
        notes = f"{notes} Limits: {' | '.join(play_result.receipt.coverage_limits)}"
    finalize_source_run(
        conn,
        analysis_run_id,
        "play_store",
        status=play_result.receipt.status,
        item_count=persisted,
        notes=notes,
    )
    return {
        "source": "play_store",
        "status": play_result.receipt.status,
        "item_count": persisted,
        "notes": notes,
    }


def run_all_adapters(
    conn: sqlite3.Connection,
    analysis_run_id: str,
    run_spec: dict[str, Any],
    *,
    only: str | None = None,
) -> list[dict]:
    fixtures = _fixtures_dir(run_spec)
    date_window = run_spec.get("date_window") or {}
    receipts: list[dict] = []

    sources = ("app_store", "reddit", "play_store", "help_community")
    if only is not None:
        if only not in sources:
            raise ValueError(f"Unknown source: {only}")
        sources = (only,)

    if "app_store" in sources:
        app_result = collect_app_store(run_spec.get("app_store") or {}, fixtures_dir=fixtures)
        receipts.append(_run_adapter(conn, analysis_run_id, "app_store", app_result))

    if "reddit" in sources:
        reddit_result = collect_reddit(
            run_spec.get("reddit") or {},
            date_window,
            fixtures_dir=fixtures,
        )
        receipts.append(_run_adapter(conn, analysis_run_id, "reddit", reddit_result))

    if "play_store" in sources:
        receipts.append(
            _run_play_store_with_page_persist(conn, analysis_run_id, run_spec, fixtures)
        )

    if "help_community" in sources:
        receipts.append(
            _run_help_community_with_persist(conn, analysis_run_id, run_spec, fixtures)
        )

    return receipts
