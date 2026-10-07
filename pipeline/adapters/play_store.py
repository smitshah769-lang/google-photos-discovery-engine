from __future__ import annotations

import http.cookiejar
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from collections.abc import Callable
from typing import Any

import certifi
import ssl

from pipeline.adapters.http_util import HttpError
from pipeline.adapters.play_parser import (
    PlayParseError,
    parse_batchexecute_response,
    should_stop_pagination,
)
from pipeline.adapters.types import AdapterReceipt, AdapterResult, CollectedItem

PagePersistHook = Callable[[list[CollectedItem], dict[str, Any]], None]

EXPECTED_PACKAGE = "com.google.android.apps.photos"
COVERAGE_NOTE = (
    "Play batchexecute RPC is undocumented; parsers may break. "
    "No official review history ceiling."
)
SORT_NEWEST = 2
USER_AGENT = "PhotosDiscoveryEngine/0.1 (research; public data only)"


def _sort_from_config(config: dict[str, Any]) -> int:
    sort = str(config.get("sort", "newest")).lower()
    if sort == "rating":
        return 3
    if sort == "helpfulness":
        return 1
    return SORT_NEWEST


def _build_req_body(
    package: str,
    sort: int,
    page_size: int,
    token: str | None,
) -> bytes:
    """Body format aligned with google-play-scraper UsvDTd requests."""
    inner = [
        None,
        None,
        [2, sort, [page_size, None, token], None, []],
        [package, 7],
    ]
    inner_str = json.dumps(inner, separators=(",", ":"))
    freq = json.dumps([[["UsvDTd", inner_str, None, "generic"]]], separators=(",", ":"))
    return urllib.parse.urlencode({"f.req": freq}).encode("utf-8")


def _play_fetch(
    opener: urllib.request.OpenerDirector,
    url: str,
    body: bytes,
    timeout: float = 60.0,
) -> str:
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with opener.open(req, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, errors="replace")
    except urllib.error.HTTPError as exc:
        raise HttpError(f"HTTP {exc.code} for Play batchexecute") from exc
    except urllib.error.URLError as exc:
        raise HttpError(f"Play request failed: {exc}") from exc


def collect_play_store(
    config: dict[str, Any],
    *,
    fixtures_dir: Path | None = None,
    on_page: PagePersistHook | None = None,
) -> AdapterResult:
    package = str(config.get("package_name", ""))
    if package != EXPECTED_PACKAGE:
        return AdapterResult(
            items=[],
            receipt=AdapterReceipt(
                status="failed",
                item_count=0,
                notes=f"Wrong package {package}; expected {EXPECTED_PACKAGE}",
                coverage_limits=[COVERAGE_NOTE],
            ),
        )

    locales = list(config.get("locales") or [{"hl": "en", "gl": "us"}])
    max_pages = config.get("max_pages")
    page_size = int(config.get("reviews_per_page", 100))
    page_delay = float(config.get("page_delay_seconds", 3.0))
    sort = _sort_from_config(config)
    seen_review_ids: set[str] = set()
    items: list[CollectedItem] = []

    if fixtures_dir:
        raw = (fixtures_dir / "play_batchexecute.txt").read_text(encoding="utf-8")
        try:
            parsed = parse_batchexecute_response(raw, "en-us")
        except PlayParseError as exc:
            return AdapterResult(
                items=[],
                receipt=AdapterReceipt(
                    status="failed",
                    item_count=0,
                    notes=str(exc),
                    coverage_limits=[COVERAGE_NOTE],
                ),
            )
        for review in parsed.reviews:
            if review.review_id in seen_review_ids:
                continue
            seen_review_ids.add(review.review_id)
            items.append(
                CollectedItem(
                    native_id=review.review_id,
                    source="play_store",
                    text=review.text,
                    authored_at=review.authored_at,
                    source_url=f"https://play.google.com/store/apps/details?id={package}&reviewId={review.review_id}",
                    locale=review.locale,
                    developer_reply=review.developer_reply,
                    has_user_text=bool(review.text.strip()),
                    raw_api_payload={"score": review.score},
                )
            )
        return AdapterResult(
            items=items,
            receipt=AdapterReceipt(
                status="success",
                item_count=len(items),
                notes="Loaded from fixtures.",
                coverage_limits=[COVERAGE_NOTE],
            ),
        )

    ctx = ssl.create_default_context(cafile=certifi.where())
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar),
        urllib.request.HTTPSHandler(context=ctx),
    )

    errors: list[str] = []
    pages_fetched = 0

    for loc in locales:
        hl = loc.get("hl", "en")
        gl = loc.get("gl", "us")
        locale_tag = f"{hl}-{gl}"
        token: str | None = None
        seen_tokens: set[str] = set()
        page = 0
        while True:
            page += 1
            if max_pages is not None and page > int(max_pages):
                break
            url = (
                f"https://play.google.com/_/PlayStoreUi/data/batchexecute?"
                f"rpcids=UsvDTd&hl={hl}&gl={gl}"
            )
            try:
                body = _build_req_body(package, sort, page_size, token)
                text = _play_fetch(opener, url, body)
            except HttpError as exc:
                errors.append(f"{locale_tag} page {page}: {exc}")
                break
            try:
                parsed = parse_batchexecute_response(text, locale_tag)
            except PlayParseError as exc:
                return AdapterResult(
                    items=items,
                    receipt=AdapterReceipt(
                        status="failed" if not items else "partial",
                        item_count=len(items),
                        notes=str(exc),
                        coverage_limits=[COVERAGE_NOTE],
                    ),
                )
            pages_fetched += 1
            if not parsed.reviews and not parsed.continuation_token:
                break
            page_batch: list[CollectedItem] = []
            for review in parsed.reviews:
                if review.review_id in seen_review_ids:
                    continue
                seen_review_ids.add(review.review_id)
                item = CollectedItem(
                    native_id=review.review_id,
                    source="play_store",
                    text=review.text,
                    authored_at=review.authored_at,
                    source_url=f"https://play.google.com/store/apps/details?id={package}&reviewId={review.review_id}",
                    locale=locale_tag,
                    developer_reply=review.developer_reply,
                    has_user_text=bool(review.text.strip()),
                    raw_api_payload={"score": review.score},
                )
                if on_page is not None:
                    page_batch.append(item)
                else:
                    items.append(item)
            if on_page is not None and page_batch:
                on_page(
                    page_batch,
                    {
                        "locale": locale_tag,
                        "page": page,
                        "page_new": len(page_batch),
                        "total_unique": len(seen_review_ids),
                    },
                )
            elif on_page is not None:
                print(
                    f"play_store {locale_tag} page {page}: 0 new reviews "
                    f"({len(seen_review_ids)} unique total)",
                    flush=True,
                )
            next_token = parsed.continuation_token
            if should_stop_pagination(seen_tokens, token, next_token):
                break
            if next_token:
                seen_tokens.add(next_token)
            token = next_token
            time.sleep(page_delay)

    collected = len(seen_review_ids) if on_page is not None else len(items)
    status = "success" if collected and not errors else ("partial" if collected else "failed")
    if not collected and errors:
        status = "failed"
    notes = "; ".join(errors) if errors else (
        f"batchexecute collection complete; {pages_fetched} page(s); "
        f"{page_delay}s delay between pages."
    )
    total = len(seen_review_ids) if on_page is not None else len(items)
    return AdapterResult(
        items=items if on_page is None else [],
        receipt=AdapterReceipt(
            status=status,
            item_count=total,
            notes=notes,
            coverage_limits=[COVERAGE_NOTE],
        ),
    )
