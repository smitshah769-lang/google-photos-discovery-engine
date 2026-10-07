from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipeline.adapters.http_util import HttpError, fetch_text
from pipeline.adapters.types import AdapterReceipt, AdapterResult, CollectedItem

EXPECTED_APP_ID = "962194608"
EXPECTED_APP_NAME = "Google Photos"
COVERAGE_NOTE = (
    "App Store RSS: ~500 most recent written reviews per storefront (pages 1–10); "
    "ratings without text and full history are not available."
)


def _feed_app_name(feed: dict[str, Any]) -> str | None:
    entries = feed.get("entry")
    if entries is None:
        return None
    if isinstance(entries, dict):
        entries = [entries]
    if not isinstance(entries, list) or not entries:
        return None
    first = entries[0]
    if not isinstance(first, dict):
        return None
    name = (first.get("im:name") or {}).get("label")
    return str(name) if name else None


def _is_review_entry(entry: dict[str, Any]) -> bool:
    if "im:rating" not in entry:
        return False
    entry_id = entry.get("id", {})
    label = entry_id.get("label") if isinstance(entry_id, dict) else None
    return bool(label)


def _normalize_feed_entries(feed: dict[str, Any]) -> list[dict[str, Any]]:
    """Apple returns one review as an object, many reviews as a list, none as missing."""
    entries = feed.get("entry")
    if entries is None:
        return []
    if isinstance(entries, dict):
        return [entries]
    if isinstance(entries, list):
        return [e for e in entries if isinstance(e, dict)]
    raise ValueError("App Store feed.entry is not a list or object")


def parse_feed_json(data: dict[str, Any], storefront: str) -> list[CollectedItem]:
    feed = data.get("feed") or {}
    entries = _normalize_feed_entries(feed)
    items: list[CollectedItem] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if not _is_review_entry(entry):
            continue
        review_id = str(entry["id"]["label"])
        title = (entry.get("title") or {}).get("label") or ""
        body = (entry.get("content") or {}).get("label") or ""
        combined = f"{title}\n{body}".strip() if body else title.strip()
        has_text = bool(combined)
        updated = (entry.get("updated") or {}).get("label")
        url = (entry.get("link") or {}).get("attributes", {}).get("href")
        items.append(
            CollectedItem(
                native_id=review_id,
                source="app_store",
                text=combined,
                title=title or None,
                authored_at=updated,
                source_url=url,
                locale=storefront,
                has_user_text=has_text,
                raw_api_payload={"storefront": storefront, "entry": entry},
            )
        )
    return items


def collect_app_store(
    config: dict[str, Any],
    *,
    fixtures_dir: Path | None = None,
) -> AdapterResult:
    app_id = str(config.get("app_id", ""))
    if app_id != EXPECTED_APP_ID:
        return AdapterResult(
            items=[],
            receipt=AdapterReceipt(
                status="failed",
                item_count=0,
                notes=(
                    f"Wrong app_id {app_id}; expected {EXPECTED_APP_ID} "
                    f"({EXPECTED_APP_NAME}). "
                    f"(1128416098 is a different app: My Story: Choose Your Own Path.)"
                ),
                coverage_limits=[COVERAGE_NOTE],
            ),
        )
    storefronts = list(config.get("storefronts") or ["us"])
    max_pages = int(config.get("max_pages_per_storefront", 10))
    seen_ids: set[str] = set()
    items: list[CollectedItem] = []
    errors: list[str] = []
    storefronts_seen: dict[str, list[str]] = {}

    if fixtures_dir:
        path = fixtures_dir / "app_store_us_page1.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        parsed = parse_feed_json(data, "us")
        for item in parsed:
            if item.native_id not in seen_ids:
                seen_ids.add(item.native_id)
                items.append(item)
        return AdapterResult(
            items=items,
            receipt=AdapterReceipt(
                status="success",
                item_count=len(items),
                notes="Loaded from fixtures.",
                coverage_limits=[COVERAGE_NOTE],
            ),
        )

    for storefront in storefronts:
        got_page_data = False
        for page in range(1, max_pages + 1):
            url = (
                f"https://itunes.apple.com/{storefront}/rss/customerreviews/"
                f"page={page}/id={app_id}/sortby=mostrecent/json"
            )
            try:
                text = fetch_text(url)
            except HttpError as exc:
                if "404" in str(exc):
                    errors.append(f"{storefront} page {page}: 404 skipped")
                    break
                errors.append(f"{storefront} page {page}: {exc}")
                continue
            try:
                data = json.loads(text)
            except json.JSONDecodeError as exc:
                return AdapterResult(
                    items=items,
                    receipt=AdapterReceipt(
                        status="failed",
                        item_count=len(items),
                        notes=f"Parse error on {storefront} page {page}: {exc}",
                        coverage_limits=[COVERAGE_NOTE],
                    ),
                )
            feed = data.get("feed") or {}
            app_name = _feed_app_name(feed)
            if app_name and EXPECTED_APP_NAME not in app_name:
                return AdapterResult(
                    items=items,
                    receipt=AdapterReceipt(
                        status="failed" if not items else "partial",
                        item_count=len(items),
                        notes=(
                            f"{storefront} page {page}: RSS app name is '{app_name}', "
                            f"not {EXPECTED_APP_NAME} (id={app_id})."
                        ),
                        coverage_limits=[COVERAGE_NOTE],
                    ),
                )
            try:
                page_items = parse_feed_json(data, storefront)
            except ValueError as exc:
                return AdapterResult(
                    items=items,
                    receipt=AdapterReceipt(
                        status="failed",
                        item_count=len(items),
                        notes=str(exc),
                        coverage_limits=[COVERAGE_NOTE],
                    ),
                )
            if not page_items:
                if page == 1:
                    errors.append(f"{storefront}: empty first page")
                if got_page_data:
                    break
                continue
            got_page_data = True
            for item in page_items:
                if item.native_id in seen_ids:
                    storefronts_seen.setdefault(item.native_id, []).append(storefront)
                    continue
                seen_ids.add(item.native_id)
                items.append(item)
    status = "success"
    if errors and items:
        status = "partial"
    elif errors and not items:
        status = "failed"
    notes = "; ".join(errors) if errors else "Collection complete."
    notes = f"{notes} Deduped by review id across storefronts."
    return AdapterResult(
        items=items,
        receipt=AdapterReceipt(
            status=status,
            item_count=len(items),
            notes=notes,
            coverage_limits=[COVERAGE_NOTE],
        ),
    )
