from __future__ import annotations

import json
import re
from typing import Any

from pipeline.analysis.sentiment import classify_search_sentiment

SEARCH_AI_SEARCH_TYPE_ID = "search_ai_search"

SEARCH_TYPE_IDS = (
    "search_ai_search",
    "people_pets",
    "places",
    "date_time",
    "objects",
    "events",
    "file_type",
    "albums",
    "memories",
    "other",
)

# Dashboard “search types mentioned” / sentiment charts exclude Search/AI Search (separate widget).
SEARCH_TYPE_IDS_FOR_THEME_CHARTS = tuple(
    tid for tid in SEARCH_TYPE_IDS if tid != SEARCH_AI_SEARCH_TYPE_ID
)

SEARCH_TYPE_NAMES = {
    "search_ai_search": "Search/AI Search",
    "people_pets": "People and Pets",
    "places": "Places",
    "date_time": "Date & Time",
    "objects": "Objects",
    "events": "Events",
    "file_type": "File type",
    "albums": "Albums",
    "memories": "Memories",
    "other": "Other",
}

_SEARCH_TYPE_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "search_ai_search",
        re.compile(
            r"\b("
            r"search bar|search function|search feature|search option|search results|"
            r"ai search|ask photos|gemini"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        "people_pets",
        re.compile(
            r"\b("
            r"face(?:s| grouping| group| search| album)?|people search|people album|"
            r"pet(?:s)?|dog|cat|person|people|who is in|"
            r"label(?:ed)? faces|unrecognized people"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        "places",
        re.compile(
            r"\b("
            r"location|map view|places?|where (?:it|i|we) (?:took|was)|"
            r"custom radius|photos (?:i )?took at|search .{0,24}location|"
            r"by (?:their )?locations?"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        "date_time",
        re.compile(
            r"\b("
            r"date grouping|grouped by date|monthly sections|"
            r"year(?:s)? view|specific years?|chronological|"
            r"by date|creation date|wrong date|"
            r"last (?:year|month|week|autumn)|from 20\d{2}"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        "objects",
        re.compile(
            r"\b("
            r"objects?|colors?|what they contain|what the photo had|"
            r"text (?:in|on) (?:the )?photos?|ocr|bees|"
            r"screenshot of the photo|similar photos|more like this"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        "events",
        re.compile(
            r"\b("
            r"event(?:s)?|holiday|birthday|wedding|trip|vacation|"
            r"search .{0,20}event"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        "file_type",
        re.compile(
            r"\b("
            r"videos?|screenshots?|selfies?|live photos?|"
            r"filter to search only|search only for (?:photos?|videos?)"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        "albums",
        re.compile(
            r"\b("
            r"albums?|collections?|people album"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        "memories",
        re.compile(
            r"\b("
            r"memor(?:y|ies)|memories reels|on this day"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        "other",
        re.compile(
            r"\b("
            r"on device|on-device|camera folder|"
            r"photos on device vs|filename|file name|"
            r"recently added"
            r")\b",
            re.IGNORECASE,
        ),
    ),
]

_FORUM_SOLUTION = re.compile(
    r"("
    r"\b(?:try|have you tried|you can|you should|just go to|go to the|"
    r"workaround|good luck|doesn't sound|does not sound|"
    r"as others (?:have )?said|that should give you|"
    r"do one of these|i would recommend)\b|"
    r"\btry (?:to )?search\b"
    r")",
    re.IGNORECASE,
)
_OWN_PAIN = re.compile(
    r"\b("
    r"i (?:can't|cannot|couldn't|tried|hate|wish|need)|"
    r"my (?:photos?|search|app|library)|"
    r"search (?:doesn't|does not|won't|is broken)"
    r")\b",
    re.IGNORECASE,
)
_OVERALL_ONLY = re.compile(
    r"^\s*(?:i )?(?:can't|cannot|couldn't) (?:ever )?find my (?:pictures|photos)!?\s*$",
    re.IGNORECASE,
)
_SUGGESTION = re.compile(
    r"\b("
    r"please (?:add|bring|fix|restore)|should add|would (?:be nice|love if)|"
    r"feature request|bring back|at least give|"
    r"why (?:don't|isn't|is there no)|i wish|it would be great if|"
    r"update it like"
    r")\b",
    re.IGNORECASE,
)
_SEARCHISH = re.compile(
    r"\b(search|find (?:photos?|pictures?|videos?)|face|people album|date grouping)\b",
    re.IGNORECASE,
)
_QUESTION_ONLY = re.compile(
    r"^\s*(?:how (?:do|can|to)|is there a way|can you|where is|where's)\b",
    re.IGNORECASE,
)


def is_forum_reply(text: str, *, source: str, payload: dict[str, Any] | None = None) -> bool:
    raw = (payload or {}).get("raw_api_payload") or {}
    kind = str(raw.get("kind") or "")
    blob = text or ""
    if source == "reddit" and kind == "comment":
        if _FORUM_SOLUTION.search(blob) and not _OWN_PAIN.search(blob):
            return True
        if len(blob) < 160 and _QUESTION_ONLY.search(blob) and not _OWN_PAIN.search(blob):
            return True
    if source == "help_community" and kind == "reply":
        return True
    if _FORUM_SOLUTION.search(blob) and not _OWN_PAIN.search(blob) and source in ("reddit", "help_community"):
        return True
    return False


def exploration_signal(text: str, *, is_reply: bool) -> str:
    """Training Data.md — No signal vs Actionable Signal (used to tag pain points)."""
    if is_reply:
        return "no_signal"
    blob = (text or "").strip()
    if not blob:
        return "no_signal"
    if _OVERALL_ONLY.match(blob):
        return "no_signal"
    if _SUGGESTION.search(blob):
        return "actionable"
    if re.search(
        r"\b("
        r"can't find|cannot find|couldn't find|doesn't find|does not find|"
        r"doesn't work|does not work|not working|"
        r"wrong results|missing|gone|disappeared|nerf|ignored|"
        r"how (?:do|can|to) (?:i )?search|is there a way|"
        r"face (?:search|group|grouping)|people album|separate people|"
        r"inconsistent|won't acknowledge|unrecognized people|"
        r"date grouping|search bar|search button|search function|"
        r"filename|file name|metadata|wrong date|more like this|"
        r"didn't know|did not know|til\b|follow.?up query"
        r")",
        blob,
        re.IGNORECASE,
    ):
        return "actionable"
    return "no_signal"


def search_types_for_text(text: str, *, exclude: bool = False) -> list[str]:
    """Skip if no search type is mentioned. Exclude forum solution/question replies."""
    if exclude:
        return []
    blob = text or ""
    found: list[str] = []
    for type_id, pattern in _SEARCH_TYPE_RULES:
        if pattern.search(blob) and type_id not in found:
            found.append(type_id)
    return found


def is_suggestion(text: str) -> bool:
    blob = text or ""
    if not (_SUGGESTION.search(blob) and _SEARCHISH.search(blob)):
        return False
    if re.search(r"\b(backup|storage quota|widget control)\b", blob, re.IGNORECASE) and not re.search(
        r"\b(search bar|search function|search by|face grouping|date grouping)\b",
        blob,
        re.IGNORECASE,
    ):
        return False
    return True


def extract_engagement(source: str, payload: dict[str, Any] | None) -> dict[str, int]:
    raw = (payload or {}).get("raw_api_payload") or {}
    out = {"helpful_votes": 0, "reply_count": 0, "star_score": 0, "score": 0}
    if source == "app_store":
        entry = raw.get("entry") if isinstance(raw.get("entry"), dict) else {}
        out["helpful_votes"] = _nested_int(entry.get("im:voteCount"))
        out["star_score"] = _nested_int(entry.get("im:rating"))
    elif source == "play_store":
        out["star_score"] = _as_int(raw.get("score") or raw.get("thumbsUpCount"))
        out["helpful_votes"] = _as_int(raw.get("thumbsUpCount") or raw.get("thumbsUp"))
    elif source == "help_community":
        out["reply_count"] = _as_int(raw.get("reply_count"))
    elif source == "reddit":
        out["score"] = _as_int(raw.get("score") or raw.get("ups"))
    return out


def engagement_rank(engagement: dict[str, int]) -> int:
    return int(
        engagement.get("helpful_votes")
        or engagement.get("score")
        or engagement.get("reply_count")
        or 0
    )


def annotate_research_item(
    text: str,
    *,
    source: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reply = is_forum_reply(text, source=source, payload=payload)
    signal = exploration_signal(text, is_reply=reply)
    types = search_types_for_text(text, exclude=reply)
    return {
        "sentiment": classify_search_sentiment(text),
        "signal": signal,
        "search_types": types,
        "is_forum_reply": reply,
        "is_suggestion": is_suggestion(text),
        "engagement": extract_engagement(source, payload),
    }


def parse_payload_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        val = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return val if isinstance(val, dict) else {}


def _nested_int(value: Any) -> int:
    if isinstance(value, dict):
        return _as_int(value.get("label") or value.get("value"))
    return _as_int(value)


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
