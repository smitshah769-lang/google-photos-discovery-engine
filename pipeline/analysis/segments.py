from __future__ import annotations

import re
from typing import Any

# Do not map place names from problem-statement examples to countries (edge §8).
_GOA_LEAK = re.compile(r"\bgoa\b", re.IGNORECASE)

_LARGE_LIB = re.compile(
    r"\b(3000\+?|3,000|thousands? of photos|huge library|tens of thousands|large library)\b",
    re.IGNORECASE,
)
_YEARS_OLD = re.compile(
    r"\b(years? ago|last year|old photos?|old pictures?|decade|from 20\d{2})\b",
    re.IGNORECASE,
)
_RECENT = re.compile(r"\b(yesterday|last week|last month|this week|recent(ly)?)\b", re.IGNORECASE)
_DEVICE = re.compile(
    r"\b(iphone|ipad|ios|android|pixel|samsung|oneplus|xiaomi|huawei|mac|windows phone)\b",
    re.IGNORECASE,
)
# User-stated geo only: country-like tokens, not inferred from café/Goa examples in prompts.
_GEO = re.compile(
    r"\b("
    r"united states|usa|uk|united kingdom|canada|australia|germany|france|india|"
    r"japan|brazil|mexico|spain|italy|netherlands|sweden|ireland|new zealand|"
    r"singapore|indonesia|philippines"
    r")\b",
    re.IGNORECASE,
)


def tag_segments(text: str) -> dict[str, Any]:
    blob = text or ""
    library_size = "large" if _LARGE_LIB.search(blob) else "unknown"
    if _YEARS_OLD.search(blob):
        photo_age = "years_old"
    elif _RECENT.search(blob):
        photo_age = "recent"
    else:
        photo_age = "unknown"
    device_match = _DEVICE.search(blob)
    if device_match:
        token = device_match.group(0).lower()
        if token in ("iphone", "ipad", "ios", "mac"):
            device = "ios"
        elif token in ("android", "pixel", "samsung", "oneplus", "xiaomi", "huawei"):
            device = "android"
        else:
            device = "unknown"
    else:
        device = "unknown"
    geo_match = _GEO.search(blob)
    if geo_match:
        geo = geo_match.group(0)
    else:
        geo = "unknown"
    # If the only place cue is Goa (prompt-example leak risk), still record the
    # user-stated token but never promote it to India.
    if geo == "unknown" and _GOA_LEAK.search(blob):
        geo = "unknown"
    return {
        "library_size": library_size,
        "photo_age": photo_age,
        "geo": geo,
        "device": device,
    }


def unknown_rates(segment_rows: list[dict[str, Any]]) -> dict[str, float]:
    keys = ("library_size", "photo_age", "geo", "device")
    if not segment_rows:
        return {k: 1.0 for k in keys}
    n = len(segment_rows)
    rates: dict[str, float] = {}
    for key in keys:
        unknown = sum(1 for row in segment_rows if (row.get(key) or "unknown") == "unknown")
        rates[key] = round(unknown / n, 4)
    return rates
