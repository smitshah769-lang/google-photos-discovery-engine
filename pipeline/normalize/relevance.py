from __future__ import annotations

import re

from pipeline.normalize.text_clean import help_community_title, strip_help_community_chrome

# In-scope: talking about searching or finding photos already in the library.
SEARCH_SIGNAL = re.compile(
    r"("
    r"\bsearch(?:es|ing|ed)?\b|"
    r"\bsearch (?:bar|box|button|function|result|filter|page)\b|"
    r"\b(?:face|people|keyword|text|video|photo|image) search\b|"
    r"\b(?:can't|cannot|couldn't|could not|won't|will not|doesn't|does not) find\b|"
    r"\bfind(?:ing)? (?:my |the )?(?:photos?|pictures?|videos?|images?|screenshots?|albums?)\b|"
    r"\b(?:look(?:ing)?|looked) for (?:a |my |the )?(?:photos?|pictures?|videos?|images?)\b|"
    r"\bmore like this\b|"
    r"\bgrouped by date\b|\bdate grouping\b|"
    r"\bface group(?:ing)?\b|\bpeople album\b|"
    r"\brecogni[sz]e\b|\bobject recognition\b"
    r")",
    re.IGNORECASE,
)

# Training Data.md — Out of Scope / Filter Out (only those topics).
EDITING_ONLY = re.compile(
    r"\b("
    r"magic eraser|photo editor|editing tools|edit(?:ing)? tools|"
    r"crop photos|export frame|highlight which is getting processed|"
    r"creations module|saving after editing"
    r")\b",
    re.IGNORECASE,
)
PRIVACY_ONLY = re.compile(
    r"\b("
    r"privacy invasive|without my consent|full access to every photo|"
    r"give (?:google )?access to every photo|photo.?access permission|"
    r"animated [\"']?shimmer[\"']?|"
    r"scanning my photos without"
    r")\b",
    re.IGNORECASE,
)
SHARING_ONLY = re.compile(
    r"\b("
    r"accidentally shared|undo this\b.*\bshar|"
    r"partner sharing|shared library|shared albums?|"
    r"share (?:a )?link|contribute to album|"
    r"choose from (?:fb|facebook|whatsapp)|"
    r"can't find the edited ones"
    r")\b",
    re.IGNORECASE,
)
BACKUP_ONLY = re.compile(
    r"\b("
    r"backup|back up|sync(?:ing)?|storage quota|upload only|"
    r"recycle bin|permanently deleted|restore deleted|"
    r"recover (?:my )?(?:deleted|permanently)|"
    r"from (?:the )?trash|from (?:the )?bin|"
    r"switched (?:to a )?new phone|device (?:change|migration)|"
    r"move photos from my google photos|not syncing|"
    r"storage full|keep all my photos on my device"
    r")\b",
    re.IGNORECASE,
)
NON_SEARCH_UI = re.compile(
    r"\b("
    r"edit button is at the bottom|custom ordering in albums|"
    r"ordering of photos in albums|print photos|chromecast|"
    r"download the photo is broken|menu to share or download"
    r")\b",
    re.IGNORECASE,
)
NON_SEARCH_BUG = re.compile(
    r"\b("
    r"creations module|stuck processing|wifi and internet connection is stable|"
    r"audio destination from videos"
    r")\b",
    re.IGNORECASE,
)

# Deleted / trash restore is out of scope unless the user is searching the library.
DELETED_RESTORE = re.compile(
    r"\b("
    r"restore|recover|recycle bin|permanently deleted|"
    r"deleted (?:photos?|data|videos?)|"
    r"(?:photos?|videos?|data)(?:\s+\w+){0,3}\s+deleted|"
    r"photos? in trash|from (?:the )?trash|from (?:the )?bin|locked folder"
    r")\b",
    re.IGNORECASE,
)

AMBIGUOUS = re.compile(
    r"\b(search settings|people to share|share with)\b",
    re.IGNORECASE,
)


def prepare_relevance_text(text: str, source: str, title: str | None = None) -> str:
    if source == "help_community":
        return strip_help_community_chrome(text or "", title)
    return (text or "").strip()


def _out_of_scope_only(blob: str) -> bool:
    """True when the item is about an excluded theme and not about photo search."""
    has_search = bool(SEARCH_SIGNAL.search(blob))
    if EDITING_ONLY.search(blob) and not has_search:
        return True
    if PRIVACY_ONLY.search(blob) and not has_search:
        return True
    if SHARING_ONLY.search(blob) and not has_search:
        return True
    if BACKUP_ONLY.search(blob) and not has_search:
        return True
    if NON_SEARCH_UI.search(blob) and not has_search:
        return True
    if NON_SEARCH_BUG.search(blob) and not has_search:
        return True
    if DELETED_RESTORE.search(blob) and not has_search:
        return True
    # Restore/trash/locked-folder complaints are out of scope even with "can't find"
    # unless the user is talking about the search feature itself.
    if DELETED_RESTORE.search(blob) and not re.search(r"\bsearch\b", blob, re.IGNORECASE):
        return True
    if re.search(r"can't find it in the (?:three dot|menu)|find the edit button", blob, re.IGNORECASE):
        return True
    # Editing / privacy / sharing / backup as the main complaint even if a weak "find" slipped in.
    if PRIVACY_ONLY.search(blob) and not re.search(
        r"\bsearch\b|\bfind (?:my |the )?(?:photos?|pictures?)\b", blob, re.IGNORECASE
    ):
        return True
    if EDITING_ONLY.search(blob) and not re.search(r"\bsearch\b", blob, re.IGNORECASE):
        return True
    if BACKUP_ONLY.search(blob) and not re.search(
        r"\bsearch\b|\bface (?:search|group)|can't find (?:my )?(?:photos?|pictures?)",
        blob,
        re.IGNORECASE,
    ):
        return True
    return False


def classify_relevance(text: str, source: str, *, title: str | None = None) -> tuple[str, float]:
    """
    Rule-based relevance aligned with Training Data.md.
    Labels: retrieval_related | unrelated | ambiguous
    """
    if not text or not text.strip():
        return "unrelated", 0.9

    blob = prepare_relevance_text(text, source, title)
    if source == "help_community":
        titled = help_community_title(title)
        if titled:
            # Title is the user question; leftover chrome must not create a search hit.
            blob = f"{titled} {blob}".strip() if blob and titled.lower() not in blob.lower() else (blob or titled)
            if _out_of_scope_only(titled) and not SEARCH_SIGNAL.search(titled):
                return "unrelated", 0.9

    if not blob:
        return "unrelated", 0.9

    if AMBIGUOUS.search(blob) and not SEARCH_SIGNAL.search(blob):
        return "ambiguous", 0.55

    if _out_of_scope_only(blob):
        return "unrelated", 0.86

    if SEARCH_SIGNAL.search(blob):
        return "retrieval_related", 0.88

    return "unrelated", 0.72
