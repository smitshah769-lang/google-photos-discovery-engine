from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from pipeline.adapters.http_util import HttpError, fetch_json
from pipeline.adapters.types import AdapterReceipt, AdapterResult, CollectedItem

# API: https://github.com/ArthurHeitmann/arctic_shift/tree/master/api
ARCTIC_BASE = "https://arctic-shift.photon-reddit.com"
COVERAGE_NOTE = (
    "Reddit via Arctic Shift: subreddit-scoped keyword search only; "
    "if Arctic Shift is unavailable, Reddit is recorded as a gap (no paid API fallback)."
)


def _parse_arctic_payload(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    if payload.get("error"):
        raise HttpError(str(payload["error"]))
    data = payload.get("data")
    if data is None:
        return []
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        children = data.get("children") or data.get("items") or []
        if isinstance(children, list):
            return [row for row in children if isinstance(row, dict)]
    return []


def _unwrap_row(row: dict[str, Any]) -> dict[str, Any]:
    inner = row.get("data")
    return inner if isinstance(inner, dict) else row


def _in_window(iso_or_epoch: str | int | float | None, after: str | None, before: str | None) -> bool:
    if iso_or_epoch is None:
        return True
    if isinstance(iso_or_epoch, (int, float)):
        dt = datetime.utcfromtimestamp(iso_or_epoch)
    else:
        try:
            dt = datetime.fromisoformat(str(iso_or_epoch).replace("Z", "+00:00"))
        except ValueError:
            return True
    if after:
        try:
            if dt < datetime.fromisoformat(after):
                return False
        except ValueError:
            pass
    if before:
        try:
            if dt > datetime.fromisoformat(before):
                return False
        except ValueError:
            pass
    return True


def _post_item(post: dict[str, Any], subreddit: str, keyword: str) -> CollectedItem:
    pid = str(post.get("id") or post.get("name", ""))
    title = post.get("title") or ""
    selftext = post.get("selftext") or post.get("body") or ""
    if selftext in ("[deleted]", "[removed]"):
        selftext = ""
    text = f"{title}\n{selftext}".strip()
    created = post.get("created_utc") or post.get("created")
    permalink = post.get("permalink") or ""
    if permalink and not permalink.startswith("http"):
        permalink = f"https://www.reddit.com{permalink}"
    return CollectedItem(
        native_id=pid,
        source="reddit",
        text=text,
        title=title or None,
        authored_at=str(created) if created is not None else None,
        source_url=permalink or None,
        locale=subreddit,
        thread_context=None,
        has_user_text=bool(text),
        raw_api_payload={"kind": "post", "subreddit": subreddit, "keyword": keyword},
    )


def _comment_item(comment: dict[str, Any], subreddit: str, keyword: str) -> CollectedItem:
    cid = str(comment.get("id") or comment.get("name", ""))
    body = comment.get("body") or ""
    if body in ("[deleted]", "[removed]"):
        body = ""
    created = comment.get("created_utc") or comment.get("created")
    permalink = comment.get("permalink") or ""
    if permalink and not permalink.startswith("http"):
        permalink = f"https://www.reddit.com{permalink}"
    return CollectedItem(
        native_id=cid,
        source="reddit",
        text=body,
        authored_at=str(created) if created is not None else None,
        source_url=permalink or None,
        locale=subreddit,
        thread_context=None,
        has_user_text=bool(body),
        raw_api_payload={"kind": "comment", "subreddit": subreddit, "keyword": keyword},
    )


def _arctic_get(path: str, params: dict[str, Any], retries: int = 2) -> list[dict[str, Any]]:
    url = f"{ARCTIC_BASE}{path}?{urlencode(params)}"
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            payload = fetch_json(url)
            return _parse_arctic_payload(payload)
        except HttpError as exc:
            last_err = exc
            if "Timeout" in str(exc) or "slow down" in str(exc).lower():
                time.sleep(2 + attempt)
                continue
            raise
    raise HttpError(str(last_err))


def collect_reddit(
    config: dict[str, Any],
    date_window: dict[str, Any],
    *,
    fixtures_dir: Path | None = None,
) -> AdapterResult:
    subreddits = list(config.get("subreddits") or ["googlephotos"])
    keywords = list(config.get("keywords") or ["search"])
    include_comments = bool(config.get("include_comments", True))
    after = date_window.get("after")
    before = date_window.get("before")
    limit = min(int(config.get("posts_per_request", 100)), 100)
    items: list[CollectedItem] = []
    seen: set[str] = set()
    errors: list[str] = []

    if fixtures_dir:
        posts = json.loads((fixtures_dir / "reddit_posts.json").read_text(encoding="utf-8"))
        comments = json.loads((fixtures_dir / "reddit_comments.json").read_text(encoding="utf-8"))
        for post in posts:
            item = _post_item(post, "googlephotos", "fixture")
            if item.native_id not in seen:
                seen.add(item.native_id)
                items.append(item)
        if include_comments:
            for comment in comments:
                item = _comment_item(comment, "googlephotos", "fixture")
                if item.native_id not in seen:
                    seen.add(item.native_id)
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

    try:
        for sub in subreddits:
            for keyword in keywords:
                post_params: dict[str, Any] = {
                    "subreddit": sub,
                    "query": keyword,
                    "limit": limit,
                    "sort": "asc",
                }
                if after:
                    post_params["after"] = after
                if before:
                    post_params["before"] = before

                try:
                    posts = _arctic_get("/api/posts/search", post_params)
                except HttpError as exc:
                    errors.append(f"posts r/{sub} '{keyword}': {exc}")
                    time.sleep(1)
                    continue

                for raw_post in posts:
                    post = _unwrap_row(raw_post)
                    if not post.get("id"):
                        continue
                    if not _in_window(post.get("created_utc"), after, before):
                        continue
                    item = _post_item(post, sub, keyword)
                    key = f"post:{item.native_id}"
                    if key in seen:
                        continue
                    seen.add(key)
                    items.append(item)

                if include_comments:
                    comment_params: dict[str, Any] = {
                        "subreddit": sub,
                        "body": keyword,
                        "limit": limit,
                        "sort": "asc",
                    }
                    if after:
                        comment_params["after"] = after
                    if before:
                        comment_params["before"] = before
                    try:
                        comments = _arctic_get("/api/comments/search", comment_params)
                    except HttpError as exc:
                        errors.append(f"comments r/{sub} '{keyword}': {exc}")
                        time.sleep(1)
                        continue

                    for raw_comment in comments:
                        comment = _unwrap_row(raw_comment)
                        if not comment.get("id"):
                            continue
                        if not _in_window(comment.get("created_utc"), after, before):
                            continue
                        item = _comment_item(comment, sub, keyword)
                        key = f"comment:{item.native_id}"
                        if key in seen:
                            continue
                        seen.add(key)
                        items.append(item)

                time.sleep(1)
    except HttpError as exc:
        return AdapterResult(
            items=items,
            receipt=AdapterReceipt(
                status="gap",
                item_count=len(items),
                notes=f"Arctic Shift unavailable: {exc}. Reddit frozen as documented gap.",
                coverage_limits=[COVERAGE_NOTE],
            ),
        )

    if errors and items:
        status = "partial"
        notes = "; ".join(errors[:5])
        if len(errors) > 5:
            notes += f" (+{len(errors) - 5} more)"
    elif errors and not items:
        status = "gap"
        notes = "; ".join(errors)
    elif items:
        status = "success"
        notes = "Arctic Shift collection complete (query/body params per API docs)."
    else:
        status = "partial"
        notes = "No Reddit items returned for configured keywords."

    return AdapterResult(
        items=items,
        receipt=AdapterReceipt(
            status=status,
            item_count=len(items),
            notes=notes,
            coverage_limits=[COVERAGE_NOTE],
        ),
    )
