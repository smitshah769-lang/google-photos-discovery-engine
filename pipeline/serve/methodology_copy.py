"""Required How-the-Engine-Works copy (edge cases §11)."""

from __future__ import annotations

RANKING_COPY = (
    "Ranking is within this snapshot, not user-base incidence. "
    "Public-feedback volume is not prevalence among Google Photos users."
)

TREND_SUBTITLE = (
    "Trend counts use authored_at inside the collection window only. "
    "This is not a live post-analysis trend."
)

REQUIRED_LIMITATIONS = [
    "App Store RSS is recency-biased: roughly 500 most-recent written reviews per storefront; older complaints may be invisible.",
    "Play Store collection uses an undocumented batchexecute RPC; parsers can break and coverage is not an official census.",
    "Reddit is subreddit- and keyword-scoped via Arctic Shift; an outage is recorded as a gap rather than switching to a paid API.",
    "Help Community discovery uses Custom Search ranking and/or public browse HTML, which is recency- and recovery-biased — not a forum-wide census.",
    "English, public complainers, and store-review extremes are over-weighted.",
    "Social media is excluded (four sources only: Play Store, App Store, Reddit, Help Community).",
    "There is no Google Photos product telemetry or private library access.",
    "Human review is required when classification confidence is low, items are ambiguous, or a category would drive a roadmap bet.",
    "This snapshot is not a census of Google Photos users.",
    "Findings are not causal claims about all Photos users; public complainers and store extremes are biased samples.",
    "Findings evolve only with future research — a new collect is a new run_id, not a live update of this freeze.",
]

BIAS_NOTES = (
    "Public reviews and forum posts over-represent English speakers, people who post publicly, "
    "and extreme store ratings. Channel mix is shown on aggregates so volume is not treated as prevalence."
)

COLLECTION_METHODS = {
    "app_store": "Public Apple customer-reviews RSS/JSON (no API key).",
    "play_store": "Play Store UI batchexecute RPC (UsvDTd) for com.google.android.apps.photos.",
    "reddit": "Arctic Shift research API, subreddit-scoped keyword search.",
    "help_community": "Programmable Search (site:support.google.com/photos/thread) and/or public browse HTML, then public thread parse.",
}

NON_CLAIMS = [
    "This snapshot is not a census of Google Photos users.",
    "Findings are not causal claims about all Photos users; public complainers and store extremes are biased samples.",
    "Findings evolve only with future research — a new collect is a new run_id, not a live update of this freeze.",
]

OUT_OF_REPO_SCOPE = [
    "Problem-statement Phase 2 (product-team review and opportunity prioritization) is out of this repository.",
    "Problem-statement Phase 3 (in-product Photos retrieval features and the product roadmap) is out of this repository.",
    "Joining public handles to Google accounts is forbidden.",
    "Continuous collectors, live post-freeze trends, paid model APIs, and a fifth channel are out of architecture.",
]
