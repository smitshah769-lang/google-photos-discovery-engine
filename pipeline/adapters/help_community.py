from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlencode, urlparse, urlunparse

from pipeline.adapters.http_util import HttpError, fetch_text
from collections.abc import Callable

from pipeline.adapters.types import AdapterReceipt, AdapterResult, CollectedItem

HelpItemHook = Callable[[CollectedItem], None]

FETCH_TIMEOUT = 90.0
FORUM_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _is_login_interstitial(html: str) -> bool:
    """Real login walls lack forum thread markup; public threads embed sign-in links in JS."""
    if "SUPPORT_FORUM_THREAD" in html:
        return False
    lowered = html.lower()
    if "service login" in lowered or "sign in - google accounts" in lowered:
        return True
    return False


def fetch_forum_html(url: str) -> str:
    return fetch_text(url, timeout=FETCH_TIMEOUT, headers={"User-Agent": FORUM_USER_AGENT})

THREAD_PATH_RE = re.compile(
    r"https?://support\.google\.com/photos/thread/([a-zA-Z0-9_-]+)",
    re.IGNORECASE,
)
RELATIVE_THREAD_RE = re.compile(
    r"/photos/thread/([a-zA-Z0-9_-]+)",
    re.IGNORECASE,
)
COVERAGE_NOTE = (
    "Help Community: CSE ranking is not a complete census; browse crawl is recency-biased."
)


def canonical_thread_id(url: str) -> str | None:
    match = THREAD_PATH_RE.search(url)
    if match:
        return match.group(1)
    match = RELATIVE_THREAD_RE.search(url)
    if match:
        return match.group(1)
    return None


def extract_thread_urls_from_html(html: str) -> list[str]:
    """Google forum HTML usually uses relative /photos/thread/… links."""
    seen: set[str] = set()
    out: list[str] = []
    for pattern in (THREAD_PATH_RE, RELATIVE_THREAD_RE):
        for match in pattern.finditer(html):
            tid = match.group(1)
            if tid in seen:
                continue
            seen.add(tid)
            out.append(
                normalize_thread_url(f"https://support.google.com/photos/thread/{tid}")
            )
    return out


def is_allowed_thread_url(url: str) -> bool:
    return canonical_thread_id(url) is not None


def normalize_thread_url(url: str) -> str:
    parsed = urlparse(url.strip())
    path = parsed.path.rstrip("/")
    return urlunparse(("https", "support.google.com", path, "", "", ""))


def filter_cse_urls(urls: list[str]) -> list[str]:
    """Discard anything not under support.google.com/photos/thread (edge §5 blocker)."""
    out: list[str] = []
    seen: set[str] = set()
    for url in urls:
        if not is_allowed_thread_url(url):
            continue
        tid = canonical_thread_id(url)
        if tid and tid not in seen:
            seen.add(tid)
            out.append(normalize_thread_url(url))
    return out


def default_forum_search_queries() -> list[str]:
    """Public forum search terms (support.google.com/photos/search); not a complete census."""
    phrases = [
        "can't find photos",
        "cannot find photos",
        "find old photos",
        "search photos",
        "find my photos",
        "photos disappeared",
        "missing photos",
        "lost photos",
        "search not working",
        "magic eraser",
        "locked folder",
        "shared library",
        "partner sharing",
        "face grouping",
        "people search",
        "location search",
        "date search",
        "years view",
        "remember when",
        "old pictures",
        "find picture",
        "screenshot search",
        "metadata search",
        "restore deleted photos",
        "trash photos",
        "archive photos",
        "hide photos",
        "duplicate photos",
        "storage full",
        "not syncing",
        "backup photos",
        "upload photos",
        "download photos",
        "sync photos",
        "google photos search",
        "search by name",
        "search by place",
        "album search",
        "video search",
        "live photo",
        "pixel photos",
        "iphone photos",
        "android photos",
        "ipad photos",
        "mac photos",
        "web photos",
        "chromecast photos",
        "print photos",
        "edit photos",
        "crop photos",
        "blur photos",
        "memory highlight",
        "photo book",
        "collage",
        "favorite photos",
        "star photos",
        "select photos",
        "bulk download",
        "export photos",
        "move photos",
        "copy photos",
        "account recovery",
        "sign in photos",
        "billing storage",
        "google one photos",
    ]
    words = [
        "find",
        "search",
        "photo",
        "photos",
        "picture",
        "pictures",
        "album",
        "face",
        "faces",
        "person",
        "people",
        "pet",
        "video",
        "backup",
        "sync",
        "upload",
        "download",
        "share",
        "storage",
        "delete",
        "deleted",
        "missing",
        "lost",
        "hidden",
        "archive",
        "trash",
        "restore",
        "recover",
        "duplicate",
        "metadata",
        "location",
        "map",
        "date",
        "timeline",
        "scroll",
        "filter",
        "organize",
        "sort",
        "edit",
        "crop",
        "rotate",
        "blur",
        "memory",
        "library",
        "partner",
        "screenshot",
        "quality",
        "compression",
        "original",
        "pixel",
        "iphone",
        "ipad",
        "android",
        "samsung",
        "error",
        "bug",
        "crash",
        "slow",
        "freeze",
        "update",
        "help",
        "wedding",
        "vacation",
        "trip",
        "birthday",
        "baby",
        "family",
        "school",
        "graduation",
        "holiday",
        "christmas",
        "document",
        "receipt",
        "passport",
        "selfie",
        "portrait",
        "panorama",
        "burst",
        "gif",
        "heic",
        "raw",
        "hdr",
        "caption",
        "filename",
        "rename",
        "favorite",
        "widget",
        "shortcut",
        "dark mode",
        "beta",
        "feature",
        "feedback",
        "suggestion",
    ]
    combos = [f"google photos {w}" for w in words[:60]]
    combos += [f"photos {w}" for w in words[:40]]
    out: list[str] = []
    seen: set[str] = set()
    for q in phrases + words + combos:
        key = q.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(q)
    return out


def _merge_discovered(urls: list[str], found: set[str], cap: int) -> list[str]:
    for url in urls:
        if len(found) >= cap:
            break
        tid = canonical_thread_id(url)
        if tid and tid not in found:
            found.add(tid)
    return [normalize_thread_url(f"https://support.google.com/photos/thread/{tid}") for tid in found]


def discover_urls_cse(
    queries: list[str],
    site_restrict: str,
    *,
    budget: int = 100,
    query_delay: float = 0.35,
    max_urls: int = 500,
) -> tuple[list[str], str]:
    api_key = os.environ.get("GOOGLE_CSE_API_KEY")
    cx = os.environ.get("GOOGLE_CSE_CX")
    if not api_key or not cx:
        return [], "CSE credentials missing; skipped CSE discovery."

    found: set[str] = set()
    notes: list[str] = []
    api_calls = 0
    rate_limited = False
    for query in queries:
        if rate_limited or api_calls >= budget or len(found) >= max_urls:
            break
        for start in range(1, 101, 10):
            if rate_limited or api_calls >= budget or len(found) >= max_urls:
                break
            params = {
                "key": api_key,
                "cx": cx,
                "q": query,
                "siteSearch": site_restrict,
                "siteSearchFilter": "i",
                "start": str(start),
            }
            url = f"https://www.googleapis.com/customsearch/v1?{urlencode(params)}"
            api_calls += 1
            try:
                data = json.loads(fetch_text(url, timeout=45.0))
            except HttpError as exc:
                short = str(exc).split(" for ")[0] if " for " in str(exc) else str(exc)
                notes.append(f"CSE query failed for '{query[:50]}': {short}")
                print(f"help_community CSE: failed ({exc})", flush=True)
                if "429" in str(exc):
                    notes.append(
                        "CSE rate limited (429); skipped remaining CSE (use browse/search)."
                    )
                    rate_limited = True
                break
            if "error" in data:
                err = data["error"].get("message", data["error"])
                notes.append(f"CSE API error: {err}")
                print(f"help_community CSE: API error: {err}", flush=True)
                break
            items = data.get("items") or []
            if not items:
                break
            before = len(found)
            _merge_discovered(
                [item.get("link", "") for item in items if item.get("link")],
                found,
                max_urls,
            )
            if len(found) > before:
                print(
                    f"help_community CSE '{query[:40]}' page {start}: "
                    f"+{len(found) - before} ({len(found)} unique)",
                    flush=True,
                )
            time.sleep(query_delay)
    if api_calls >= budget:
        notes.append(f"CSE query budget ({budget}) reached.")
    ordered = [
        normalize_thread_url(f"https://support.google.com/photos/thread/{tid}") for tid in found
    ]
    return ordered, "; ".join(notes) if notes else "CSE discovery complete."


def discover_urls_browse(
    seed_urls: list[str],
    *,
    listing_max_results: int = 100,
    delay: float = 0.8,
) -> list[str]:
    found: set[str] = set()
    for seed in seed_urls:
        if "threads" in seed:
            listing = (
                f"https://support.google.com/photos/threads?hl=en"
                f"&max_results={listing_max_results}"
            )
            targets = [listing]
        else:
            targets = [seed]
        for target in targets:
            try:
                html = fetch_forum_html(target)
            except HttpError:
                continue
            _merge_discovered(extract_thread_urls_from_html(html), found, 10_000)
            time.sleep(delay)
    return [
        normalize_thread_url(f"https://support.google.com/photos/thread/{tid}") for tid in found
    ]


def discover_urls_forum_search(
    queries: list[str],
    *,
    delay: float = 0.8,
    max_urls: int = 500,
) -> tuple[list[str], str]:
    found: set[str] = set()
    used = 0
    for query in queries:
        if len(found) >= max_urls:
            break
        used += 1
        url = f"https://support.google.com/photos/search?q={quote_plus(query)}&hl=en"
        try:
            html = fetch_forum_html(url)
        except HttpError:
            time.sleep(delay)
            continue
        matches = extract_thread_urls_from_html(html)
        before = len(found)
        _merge_discovered(matches, found, max_urls)
        if len(found) > before:
            print(
                f"help_community search '{query[:40]}': "
                f"+{len(found) - before} threads ({len(found)} unique)",
                flush=True,
            )
        time.sleep(delay)
    note = f"Forum search: {used} queries, {len(found)} unique thread URLs."
    return [
        normalize_thread_url(f"https://support.google.com/photos/thread/{tid}") for tid in found
    ], note


def parse_thread_html(html: str, url: str) -> CollectedItem | None:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        raise RuntimeError("beautifulsoup4 is required to parse Help Community HTML")

    if _is_login_interstitial(html):
        raise HttpError("Login wall detected; aborting URL")

    soup = BeautifulSoup(html, "html.parser")
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""
    question = ""
    replies: list[str] = []
    for tag in soup.select("div[data-message-type], .cc-reply, article"):
        text = tag.get_text("\n", strip=True)
        if not text:
            continue
        if not question:
            question = text
        else:
            replies.append(text)
    if not question:
        question = soup.get_text("\n", strip=True)[:8000]
    body = question
    thread_context = "\n---\n".join(replies[:30]) if replies else None
    tid = canonical_thread_id(url)
    if not tid:
        return None
    return CollectedItem(
        native_id=tid,
        source="help_community",
        text=body,
        title=title or None,
        authored_at=None,
        source_url=url,
        thread_context=thread_context,
        has_user_text=bool(body.strip()),
        raw_api_payload={"reply_count": len(replies)},
    )


def collect_help_community(
    config: dict[str, Any],
    *,
    fixtures_dir: Path | None = None,
    on_item: HelpItemHook | None = None,
) -> AdapterResult:
    discovery = config.get("discovery") or {}
    mode = discovery.get("mode", "cse_then_browse")
    site_restrict = discovery.get("site_restrict", "support.google.com/photos/thread")
    seeds = list(discovery.get("browse_seed_urls") or [])
    notes_parts: list[str] = []
    discovery_without_fetch = 0

    if fixtures_dir:
        urls = json.loads((fixtures_dir / "help_thread_urls.json").read_text(encoding="utf-8"))
        urls = filter_cse_urls(urls + [
            "https://reddit.com/r/googlephotos",  # must be discarded
        ])
        html = (fixtures_dir / "help_thread.html").read_text(encoding="utf-8")
        items: list[CollectedItem] = []
        for url in urls:
            item = parse_thread_html(html, url)
            if item:
                items.append(item)
        return AdapterResult(
            items=items,
            receipt=AdapterReceipt(
                status="success",
                item_count=len(items),
                notes="Loaded from fixtures; off-site URLs discarded.",
                coverage_limits=[COVERAGE_NOTE],
            ),
        )

    max_threads = int(discovery.get("max_threads", 500))
    search_delay = float(discovery.get("search_delay_seconds", 0.8))
    fetch_delay = float(discovery.get("fetch_delay_seconds", 1.2))
    listing_max = int(discovery.get("browse_listing_max_results", 100))
    cse_budget = int(discovery.get("cse_daily_query_budget", 100))
    cse_delay = float(discovery.get("cse_query_delay_seconds", 0.35))

    search_queries = list(discovery.get("search_queries") or [])
    if not search_queries:
        search_queries = default_forum_search_queries()
    cse_queries = list(discovery.get("queries") or search_queries[:50])

    seen_ids: set[str] = set()
    urls: list[str] = []

    def add_urls(batch: list[str]) -> None:
        for url in filter_cse_urls(batch):
            tid = canonical_thread_id(url)
            if tid and tid not in seen_ids:
                seen_ids.add(tid)
                urls.append(url)
            if len(urls) >= max_threads:
                break

    print("help_community: discovering thread URLs…", flush=True)
    skip_cse = bool(discovery.get("skip_cse", False))
    if skip_cse:
        notes_parts.append("CSE skipped (skip_cse=true in run.yaml).")
        print("help_community: CSE skipped (config)", flush=True)
    elif mode in ("cse_only", "cse_then_browse"):
        print("help_community: CSE discovery (may take 1–3 min, up to 100 API calls)…", flush=True)
        cse_urls, cse_note = discover_urls_cse(
            cse_queries,
            site_restrict,
            budget=cse_budget,
            query_delay=cse_delay,
            max_urls=max_threads,
        )
        add_urls(cse_urls)
        if cse_note:
            notes_parts.append(cse_note)
        print(f"help_community: after CSE, {len(urls)} thread URL(s)", flush=True)

    if len(urls) < max_threads and mode in ("browse_only", "cse_then_browse"):
        print("help_community: browse listing…", flush=True)
        browse_urls = discover_urls_browse(
            seeds,
            listing_max_results=listing_max,
            delay=search_delay,
        )
        add_urls(browse_urls)
        print(f"help_community: after browse, {len(urls)} thread URL(s)", flush=True)

    if len(urls) < max_threads and mode in ("browse_only", "cse_then_browse", "cse_only"):
        print("help_community: forum search queries…", flush=True)
        forum_urls, forum_note = discover_urls_forum_search(
            search_queries,
            delay=search_delay,
            max_urls=max_threads - len(urls),
        )
        add_urls(forum_urls)
        notes_parts.append(forum_note)

    urls = urls[:max_threads]
    print(f"help_community: discovered {len(urls)} thread URLs; fetching…", flush=True)
    items: list[CollectedItem] = []
    persisted = 0
    target = max_threads if on_item is not None else len(urls)
    for i, url in enumerate(urls, start=1):
        if on_item is not None and persisted >= max_threads:
            break
        try:
            html = fetch_forum_html(url)
        except HttpError:
            discovery_without_fetch += 1
            time.sleep(fetch_delay)
            continue
        try:
            item = parse_thread_html(html, url)
        except HttpError as exc:
            notes_parts.append(str(exc))
            time.sleep(fetch_delay)
            continue
        if item:
            if on_item is not None:
                on_item(item)
                persisted += 1
            else:
                items.append(item)
            count = persisted if on_item is not None else len(items)
            if count % 25 == 0 or i == len(urls):
                print(
                    f"help_community fetched {count}/{target} threads ({i} requests)",
                    flush=True,
                )
        time.sleep(fetch_delay)

    total = persisted if on_item is not None else len(items)
    status = "success" if total else "partial"
    if not total and not urls:
        status = "gap"
    notes = "; ".join(notes_parts) if notes_parts else "Community collection complete."
    if discovery_without_fetch:
        notes += f" discovery-without-fetch={discovery_without_fetch}."
    notes += f" fetch_delay={fetch_delay}s search_delay={search_delay}s."
    return AdapterResult(
        items=items if on_item is None else [],
        receipt=AdapterReceipt(
            status=status,
            item_count=total,
            notes=notes,
            coverage_limits=[COVERAGE_NOTE],
        ),
    )
