from __future__ import annotations

import re

from pipeline.analysis.classify import ClassificationResult
from pipeline.analysis.research_tags import annotate_research_item, exploration_signal, is_forum_reply
from pipeline.analysis.snippets import fallback_snippet
from pipeline.taxonomy import Taxonomy

# Multi-label rules from Training Data.md user pain points. Not mutually exclusive.
_RESEARCH_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "design_missing_search_control",
        re.compile(
            r"\b(?:where (?:is|did) (?:the )?|where's (?:the )?)"
            r"(?:search (?:button|bar|icon|tab|function)|more like this)\b|"
            r"\b(?:search (?:button|bar|icon|tab)|more like this)\b.{0,40}"
            r"\b(?:is gone|went away|missing|nowhere to be found|removed|moved|disappeared)\b|"
            r"\b(?:took|taken|removed|moved) (?:the |away the )?(?:old )?search (?:button|bar|icon|tab)\b|"
            r"\b(?:give|bring) back (?:the |my )?(?:old )?search (?:button|bar|icon|tab)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "design_date_grouping",
        re.compile(
            r"\b("
            r"date grouping|grouped by date|monthly sections|"
            r"photos being grouped by date|dates disappeared"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        "design_prefer_previous_ui",
        re.compile(
            r"\b("
            r"used to (?:be able|work)|like it used to|old (?:search|method|layout|ui)|"
            r"before (?:the )?(?:recent )?update|bring back the (?:old|previous)|"
            r"prefer (?:the )?(?:old|previous)|doesn't work like it used to"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        "design_ui_navigation",
        re.compile(
            r"\b("
            r"hard(?:er)? to (?:find|navigate|organise|organize|view)|"
            r"cluttered together|all mixed together|"
            r"where did it go|can't find it anywhere|"
            r"layout (?:update|change)|new layout"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        "system_face_grouping",
        re.compile(
            r"\b("
            r"face (?:search|group|grouping|album)|people album|"
            r"not detecting faces|won't acknowledge faces|"
            r"separate people into two|two different profiles|"
            r"unrecognized people|manually tag|"
            r"doesn't recognize (?:that )?there is one"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        "system_metadata_gaps",
        re.compile(
            r"\b("
            r"file name|filename|wrong date|creation date|metadata|"
            r"specific location|custom radius|place|date/time|"
            r"incorrect (?:date|time|location)|by their locations"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        "system_object_recognition",
        re.compile(
            r"\b("
            r"object recognition|search (?:for )?(?:objects?|colors?|words)|"
            r"text (?:search )?in photos|search text in|"
            r"what they contain|what the photo (?:had|contains)"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        "system_search_bugs",
        re.compile(
            r"\b("
            r"(?:search|app).{0,30}\b(crash|crashes|freeze|hangs|locks? up|glitch|bug)|"
            r"(?:crash|crashes|freeze|hangs|locks? up).{0,30}\bsearch"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        "system_other_failures",
        re.compile(
            r"\b("
            r"can't find|cannot find|couldn't find|doesn't find|does not find|will not find|"
            r"search (?:is )?(?:broken|broke|useless|doesn't work|does not work)|"
            r"similar photos|cropped one"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        "query_followup_ignored",
        re.compile(
            r"\b("
            r"follow.?up query|follow up query|ignores? the initial|"
            r"completely ignore the initial"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        "query_not_understood",
        re.compile(
            r"\b("
            r"nerf the search|can't find the search your looking|"
            r"doesn't understand|does not understand|"
            r"search (?:feature )?failing to understand|"
            r"ai has made this useless"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        "knowledge_unknown_capability",
        re.compile(
            r"\b("
            r"didn't know|did not know|til\b|i just happened to|"
            r"didn't realise|did not realize|had no idea|"
            r"can you search|is there a way to (?:search|find)|"
            r"hidden search|how (?:do|can) i search|"
            r"is there any ways? to do that"
            r")\b",
            re.IGNORECASE,
        ),
    ),
]

_PARENT_FALLBACK: list[tuple[str, str]] = [
    ("design_ui_navigation", "design_issues"),
    ("design_prefer_previous_ui", "design_issues"),
    ("design_missing_search_control", "design_issues"),
    ("design_date_grouping", "design_issues"),
    ("system_face_grouping", "system_issues"),
    ("system_metadata_gaps", "system_issues"),
    ("system_object_recognition", "system_issues"),
    ("system_other_failures", "system_issues"),
    ("system_search_bugs", "system_issues"),
    ("query_not_understood", "query_inference"),
    ("query_followup_ignored", "query_inference"),
    ("knowledge_unknown_capability", "knowledge_awareness_gaps"),
]


def _promote_parents(labels: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for lab in labels:
        if lab not in seen:
            seen.add(lab)
            out.append(lab)
    for child, parent in _PARENT_FALLBACK:
        if child in seen and parent not in seen:
            seen.add(parent)
            out.append(parent)
    return out


def classify_research_heuristic(
    text: str,
    taxonomy: Taxonomy,
    *,
    source: str = "",
    payload: dict | None = None,
) -> ClassificationResult:
    blob = text or ""
    reply = is_forum_reply(blob, source=source, payload=payload)
    signal = exploration_signal(blob, is_reply=reply)
    labels: list[str] = []
    # Pain points are tagged only on actionable signals (Training Data.md note).
    if signal == "actionable":
        for node_id, pattern in _RESEARCH_RULES:
            if node_id in taxonomy.ids() and pattern.search(blob):
                labels.append(node_id)
        labels = [lab for lab in _promote_parents(labels) if lab in taxonomy.ids()]
    extra = annotate_research_item(blob, source=source, payload=payload)
    snippets = fallback_snippet(blob) if labels else []
    return ClassificationResult(
        labels=labels,
        confidence=0.64 if labels else 0.0,
        rationale="research_heuristic_v2" if labels else "no_actionable_pain_point",
        snippets=snippets,
        unclassified=not labels,
        provider="heuristic",
        extra=extra,
    )
