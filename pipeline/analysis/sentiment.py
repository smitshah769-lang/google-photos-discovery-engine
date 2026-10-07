from __future__ import annotations

import re

# Training Data.md — Overall Sentiment analysis for search function.
_FOUND_PHOTO = re.compile(
    r"\b("
    r"(?:can|could|able to|always) find|"
    r"found (?:the |my |those )?(?:photo|picture|image|it)|"
    r"find photos of specific|"
    r"surfaces? photos|"
    r"search (?:is )?(?:unbeatable|excellent|incredible|perfect|amazing)"
    r")\b",
    re.IGNORECASE,
)
_RELEVANT_RESULTS = re.compile(
    r"\b("
    r"(?:relevant|accurate) results|"
    r"improvements? you did to search|"
    r"search mostly (?:works|returns)|"
    r"now you surface"
    r")\b",
    re.IGNORECASE,
)
_EASY_SEARCH = re.compile(
    r"\b("
    r"search (?:is |was )?(?:intuitive|fast|easy|simple)|"
    r"easy to find|"
    r"search your photos with an ease|"
    r"love the (?:search|memories)"
    r")\b",
    re.IGNORECASE,
)
_CANT_FIND = re.compile(
    r"\b("
    r"(?:can't|cannot|couldn't|could not|won't) find|"
    r"unable to find|"
    r"doesn't find|does not find|never finds|"
    r"search (?:is )?(?:broken|broke|useless|horrible|awful)|"
    r"search (?:often |still )?(?:doesn't|does not|won't|will not) work|"
    r"search no longer works|search function gone"
    r")\b",
    re.IGNORECASE,
)
_BAD_RESULTS = re.compile(
    r"\b("
    r"(?:wrong|irrelevant|inaccurate|nonsensical|incomplete) results|"
    r"search (?:w/ |with )?wrong results|"
    r"hundreds of images to scroll|"
    r"random photo from my library"
    r")\b",
    re.IGNORECASE,
)
_HARD_SEARCH = re.compile(
    r"\b("
    r"(?:unintuitive|slow|difficult|hard|impossible) to (?:find|search|use)|"
    r"photos are so hard to find|"
    r"much harder to (?:organise|organize|view|find)|"
    r"practically impossible|"
    r"requir(?:es|ing) excessive effort"
    r")\b",
    re.IGNORECASE,
)
_POSITIVE_TONE = re.compile(
    r"\b(love|great|awesome|excellent|amazing|fantastic|perfect|impressed|thankful)\b",
    re.IGNORECASE,
)
_NEGATIVE_TONE = re.compile(
    r"\b("
    r"hate|terrible|awful|horrible|useless|worst|broken|frustrat|"
    r"disappoint|garbage|sucks|ridiculous"
    r")\b",
    re.IGNORECASE,
)


def classify_search_sentiment(text: str) -> str:
    """Return positive | negative | neutral using Training Data.md evidence rules."""
    blob = text or ""
    pos_hits = 0
    neg_hits = 0
    if _FOUND_PHOTO.search(blob):
        pos_hits += 2
    if _RELEVANT_RESULTS.search(blob):
        pos_hits += 2
    if _EASY_SEARCH.search(blob):
        pos_hits += 2
    if _CANT_FIND.search(blob):
        neg_hits += 2
    if _BAD_RESULTS.search(blob):
        neg_hits += 2
    if _HARD_SEARCH.search(blob):
        neg_hits += 2
    if pos_hits and not neg_hits:
        return "positive"
    if neg_hits and not pos_hits:
        return "negative"
    if pos_hits > neg_hits:
        return "positive"
    if neg_hits > pos_hits:
        return "negative"
    # Weak tone only when no explicit search-outcome evidence.
    pos_tone = bool(_POSITIVE_TONE.search(blob))
    neg_tone = bool(_NEGATIVE_TONE.search(blob))
    if pos_tone and not neg_tone:
        return "positive"
    if neg_tone and not pos_tone:
        return "negative"
    return "neutral"


def score_text_sentiment(text: str) -> float:
    """Legacy 0–100 helper kept for older callers; maps the three-way label."""
    label = classify_search_sentiment(text)
    if label == "positive":
        return 78.0
    if label == "negative":
        return 22.0
    return 50.0


def sentiment_label(score: float) -> str:
    if score >= 62:
        return "positive"
    if score <= 38:
        return "negative"
    return "neutral"
