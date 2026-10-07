from __future__ import annotations

import html
import re

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

# Help Community pages include site chrome that mentions Search / Privacy Policy
# on every thread. Strip it before relevance or tagging.
_HELP_TITLE_SUFFIX = re.compile(r"\s*-\s*Google Photos Community\s*$", re.IGNORECASE)
_HELP_CHROME = re.compile(
    r"("
    r"Skip to main content|Google Photos Help|Sign in|Google Help|"
    r"Help Center(?: experience)?|Community Policy|Community Overview|"
    r"Privacy Policy|Terms of Service|Submit feedback|Send feedback(?: about our Help Center)?|"
    r"This help content & information|General Help Center experience|"
    r"Enable Dark Mode|Google apps|Main menu|Clear search|Close search|"
    r"Search Help Center|Can't find your photos\?|Notification|"
    r"Community Google Photos on(?:\.{2,}|…)|"
    r"Passkeys are the simplest and most secure way to sign in to your account\.[^.]*\.|"
    r"To sign in with just your fingerprint[^.]+\.|"
    r"©\s*20\d{2}\s*Google|false|true|"
    r"Close Next|Next Help Center Community"
    r")",
    re.IGNORECASE,
)
_HELP_NOISE_TOKEN = re.compile(r"\b(\d{6,}|(?:true|false))\b", re.IGNORECASE)
_HELP_NAV_SEARCH = re.compile(r"\bSearch\b(?:\s+\d+)?", re.IGNORECASE)


def strip_html_markdown(text: str) -> str:
    unescaped = html.unescape(text)
    no_tags = _TAG_RE.sub(" ", unescaped)
    no_tags = no_tags.replace("&nbsp;", " ")
    collapsed = _WS_RE.sub(" ", no_tags).strip()
    return collapsed


def help_community_title(title: str | None) -> str:
    if not title:
        return ""
    return _HELP_TITLE_SUFFIX.sub("", strip_html_markdown(str(title))).strip()


def strip_help_community_chrome(text: str, title: str | None = None) -> str:
    """Keep the user question; drop Help Center chrome that poisons keyword filters."""
    blob = strip_html_markdown(text or "")
    short_title = help_community_title(title)
    if short_title:
        idx = blob.lower().find(short_title.lower())
        if idx >= 0:
            blob = blob[idx:]
        blob = re.sub(
            re.escape(short_title) + r"\s*-?\s*Google Photos Community",
            short_title,
            blob,
            count=1,
            flags=re.IGNORECASE,
        )
    blob = _HELP_CHROME.sub(" ", blob)
    blob = _HELP_NAV_SEARCH.sub(" ", blob)
    blob = _HELP_NOISE_TOKEN.sub(" ", blob)
    blob = _WS_RE.sub(" ", blob).strip()
    if short_title and (not blob or len(blob) < len(short_title)):
        return short_title
    if short_title and short_title.lower() not in blob.lower():
        return f"{short_title} {blob}".strip()
    return blob
