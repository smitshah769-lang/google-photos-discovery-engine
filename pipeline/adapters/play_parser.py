from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


class PlayParseError(ValueError):
    pass


def unwrap_batchexecute_body(text: str) -> Any:
    """Strip Google's )]}' prefix and parse outer JSON (edge §3)."""
    stripped = text.strip()
    if stripped.startswith(")]}'"):
        stripped = stripped[4:].strip()
    if stripped.startswith("<"):
        raise PlayParseError("Response looks like HTML/CAPTCHA interstitial, not RPC JSON")
    try:
        return json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise PlayParseError(f"Invalid batchexecute JSON envelope: {exc}") from exc


@dataclass
class PlayReview:
    review_id: str
    text: str
    score: int | None
    authored_at: str | None
    developer_reply: str | None
    locale: str | None


@dataclass
class PlayParseResult:
    reviews: list[PlayReview]
    continuation_token: str | None


def _parse_review_object(obj: dict[str, Any], locale: str | None) -> PlayReview | None:
    review_id = obj.get("reviewId") or obj.get("id")
    if not review_id:
        return None
    text = obj.get("text") or obj.get("comment") or ""
    reply = obj.get("developerReply") or obj.get("replyText")
    if isinstance(reply, dict):
        reply = reply.get("text")
    score = obj.get("score")
    if score is not None:
        score = int(score)
    date = obj.get("date") or obj.get("at")
    return PlayReview(
        review_id=str(review_id),
        text=str(text),
        score=score,
        authored_at=str(date) if date else None,
        developer_reply=str(reply) if reply else None,
        locale=locale,
    )


def _date_from_play_array(date_array: Any) -> str | None:
    if not isinstance(date_array, list) or not date_array:
        return None
    ms_tail = str(date_array[1] if len(date_array) > 1 else "000")
    ms_total = f"{date_array[0]}{ms_tail[:3]}"
    try:
        from datetime import datetime, timezone

        return datetime.fromtimestamp(int(ms_total) / 1000, tz=timezone.utc).isoformat()
    except (ValueError, OSError):
        return None


def parse_scraper_review_rows(rows: list[Any], locale: str | None) -> list[PlayReview]:
    """Parse nested arrays from google-play-scraper / UsvDTd payload."""
    reviews: list[PlayReview] = []
    for row in rows:
        if not isinstance(row, list) or not row:
            continue
        review_id = row[0]
        if review_id is None:
            continue
        text = str(row[4]) if len(row) > 4 and row[4] is not None else ""
        score = int(row[2]) if len(row) > 2 and row[2] is not None else None
        authored_at = _date_from_play_array(row[5]) if len(row) > 5 else None
        reply_text = None
        if len(row) > 7 and isinstance(row[7], list) and len(row[7]) > 1:
            reply_text = row[7][1]
        reviews.append(
            PlayReview(
                review_id=str(review_id),
                text=text,
                score=score,
                authored_at=authored_at,
                developer_reply=str(reply_text) if reply_text else None,
                locale=locale,
            )
        )
    return reviews


def parse_scraper_inner_data(data: Any, locale: str | None) -> PlayParseResult:
    if data is None:
        raise PlayParseError("Play RPC returned null payload (possible PlayDataError)")
    if not isinstance(data, list):
        raise PlayParseError("Unrecognized UsvDTd inner shape (not a list)")

    reviews_raw = data[0] if data else []
    if not isinstance(reviews_raw, list):
        reviews_raw = []

    token: str | None = None
    if len(data) > 1:
        token_container = data[1]
        if isinstance(token_container, list) and len(token_container) > 1:
            token = token_container[1]

    reviews = parse_scraper_review_rows(reviews_raw, locale)
    return PlayParseResult(reviews=reviews, continuation_token=token)


def parse_usvdt_payload(inner: Any, locale: str | None) -> PlayParseResult:
    if isinstance(inner, str):
        try:
            inner = json.loads(inner)
        except json.JSONDecodeError as exc:
            raise PlayParseError(f"Inner RPC JSON is not valid: {exc}") from exc

    if isinstance(inner, list) and inner and isinstance(inner[0], list):
        first = inner[0]
        if first and isinstance(first[0], list):
            return parse_scraper_inner_data(inner, locale)

    reviews: list[PlayReview] = []
    continuation: str | None = None

    if isinstance(inner, list) and inner and all(isinstance(x, dict) for x in inner):
        for obj in inner:
            parsed = _parse_review_object(obj, locale)
            if parsed:
                reviews.append(parsed)
        return PlayParseResult(reviews=reviews, continuation_token=continuation)

    if isinstance(inner, list) and len(inner) >= 1:
        first = inner[0]
        if isinstance(first, list):
            for obj in first:
                if isinstance(obj, dict):
                    parsed = _parse_review_object(obj, locale)
                    if parsed:
                        reviews.append(parsed)
        if len(inner) > 1 and isinstance(inner[1], str):
            continuation = inner[1] or None
        if reviews or continuation is not None:
            return PlayParseResult(reviews=reviews, continuation_token=continuation)

    raise PlayParseError("Unrecognized UsvDTd payload shape")


def _extract_rpc_inner(outer: Any, rpc_id: str = "UsvDTd") -> Any:
    if not isinstance(outer, list):
        raise PlayParseError("batchexecute envelope is not a list")
    for chunk in outer:
        if not isinstance(chunk, list) or len(chunk) < 3:
            continue
        if chunk[0] == "wrb.fr" and chunk[1] == rpc_id:
            payload = chunk[2]
            if payload is None:
                raise PlayParseError("Play RPC error (null UsvDTd payload)")
            return payload
    raise PlayParseError(f"RPC id {rpc_id} not found in batchexecute response")


def parse_batchexecute_response(text: str, locale: str | None) -> PlayParseResult:
    outer = unwrap_batchexecute_body(text)
    inner = _extract_rpc_inner(outer)
    return parse_usvdt_payload(inner, locale)


def should_stop_pagination(
    seen: set[str],
    previous_token: str | None,
    next_token: str | None,
) -> bool:
    if not next_token:
        return True
    if next_token in seen:
        return True
    if previous_token is not None and next_token == previous_token:
        return True
    return False
