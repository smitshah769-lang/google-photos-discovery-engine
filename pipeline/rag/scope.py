from __future__ import annotations

import re

# Hard out-of-scope: never vector-search (edge §10 blocker).
OUT_OF_SCOPE = re.compile(
    r"\b("
    r"train(?:ing)?\s+(?:the\s+)?model|fine[- ]?tune|"
    r"write\s+(?:a\s+)?python|python\s+scraper|scrape\s+(?:the\s+)?play\s+store|"
    r"what\s+is\s+rag\b|how\s+does\s+(?:this|the)\s+(?:discovery|research)\s+engine\s+work|"
    r"discovery\s+engine\s+work|"
    r"capital\s+of\s+france|who\s+won\s+the\s+world\s+cup|"
    r"openai|chatgpt|gemini\s+api"
    r")\b",
    re.IGNORECASE,
)

GOOGLE_PHOTOS = re.compile(
    r"\b(google\s+photos|gphotos|photos\s+app)\b",
    re.IGNORECASE,
)

RETRIEVAL_QUERY = re.compile(
    r"\b("
    r"find|search|locate|look(?:ing)?\s+for|can't\s+find|cannot\s+find|couldn't\s+find|"
    r"old\s+pictures?|old\s+photos?|screenshot|metadata|people|face|album|"
    r"remember\s+when|incomplete\s+memory|workaround|"
    r"date|location|place|years?\s+ago|abandon|gave\s+up|scroll"
    r")\b",
    re.IGNORECASE,
)

BACKUP_BILLING_ONLY = re.compile(
    r"\b(backup|sync|storage|quota|billing|subscription|payment|upload)\b",
    re.IGNORECASE,
)

FINDING_CONTEXT = re.compile(
    r"\b(find|search|locate|missing\s+photo|can't\s+find|cannot\s+find)\b",
    re.IGNORECASE,
)

# Reviewer-style questions about the frozen snapshot (still retrieval-related).
REVIEWER_QUERY = re.compile(
    r"\b("
    r"pain\s+points?|sentiment|themes?|frustrations?|complaints?|key\s+findings?|"
    r"what\s+are|how\s+(?:is|are|do)\s+users?|overall|search\s+experience|"
    r"user\s+feedback|evidence"
    r")\b",
    re.IGNORECASE,
)

SNAPSHOT_CONTEXT = re.compile(
    r"\b(search|photos?|retrieval|feedback|google\s+photos|users?|ask\s+photos|ai\s+search)\b",
    re.IGNORECASE,
)

OUT_OF_SCOPE_MESSAGE = (
    "This search only covers Google Photos photo search and retrieval in the collected "
    "feedback snapshot (finding photos, incomplete memory, metadata, abandonment, workarounds). "
    "Your query is outside that scope."
)

EMPTY_QUERY_MESSAGE = "Enter a question about Google Photos photo search or retrieval."

NO_MATCH_MESSAGE = (
    "No matching feedback in this snapshot for that query. Try different wording or relax filters."
)

FILTER_EMPTY_MESSAGE = "0 items match filters."


def classify_query_scope(query: str) -> tuple[bool, str | None]:
    """
    Returns (in_scope, explanation_if_out_of_scope).
    Out-of-scope queries must not reach vector search.
    """
    text = (query or "").strip()
    if not text:
        return False, EMPTY_QUERY_MESSAGE

    if OUT_OF_SCOPE.search(text):
        return False, OUT_OF_SCOPE_MESSAGE

    has_retrieval = bool(RETRIEVAL_QUERY.search(text))
    has_photos = bool(GOOGLE_PHOTOS.search(text))
    reviewer = bool(REVIEWER_QUERY.search(text) and SNAPSHOT_CONTEXT.search(text))

    if not has_retrieval and not has_photos and not reviewer:
        return False, OUT_OF_SCOPE_MESSAGE

    if BACKUP_BILLING_ONLY.search(text) and not FINDING_CONTEXT.search(text):
        return False, OUT_OF_SCOPE_MESSAGE

    return True, None
