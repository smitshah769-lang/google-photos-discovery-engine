from pipeline.analysis.research_heuristics import classify_research_heuristic
from pipeline.analysis.research_tags import (
    SEARCH_AI_SEARCH_TYPE_ID,
    SEARCH_TYPE_IDS,
    SEARCH_TYPE_IDS_FOR_THEME_CHARTS,
    annotate_research_item,
    is_forum_reply,
)
from pipeline.analysis.sentiment import classify_search_sentiment
from pipeline.normalize.relevance import classify_relevance
from pipeline.normalize.text_clean import strip_help_community_chrome
from pipeline.taxonomy import load_taxonomy


def test_out_of_scope_examples_from_training_data():
    cases = [
        (
            "app_store",
            "the edit button is at the bottom for pictures in unshared albums but it is not available on photos in albums I have shared",
        ),
        (
            "app_store",
            "The export frame for video is now hard to find and it doesn't even work correctly",
        ),
        (
            "help_community",
            "There is a bug in the Creations Module, I've edited a highlight which is getting processed from yesterday (it's stuck). My wifi and internet connection is stable.",
        ),
        ("help_community", "Accidently shared photos. How can I undo this?"),
        ("help_community", "I want to get back my permanently deleted data from recycle bin"),
        ("help_community", "Can't Find the Photos Google Deleted"),
        ("help_community", "Is there a way to rename my downloaded files? I can't find it in the three dot menu."),
        (
            "app_store",
            "Getting Worse They have update and taken away the useful editing tools! I want to keep all my photos on my device!",
        ),
        (
            "app_store",
            "Privacy invasive I wanted this for specific features, but did not want to give Google access to every photo on my device.",
        ),
        ("play_store", "why did you have to screw up the magic eraser?"),
        (
            "app_store",
            "recently, there is an animated shimmer over the subject of a photo when you open it. i cannot find a way to turn this off.",
        ),
    ]
    for source, text in cases:
        label, _ = classify_relevance(text, source)
        assert label != "retrieval_related", text


def test_in_scope_search_examples_from_training_data():
    cases = [
        "Great app! I can find photos of specific people, specific years, or documents! its great!",
        "it's horrible. I can't find half the photos I want to send to people.",
        "How to search for group photos? Searching for group photos did not filter out the results I wanted.",
        "The more like this search function on individual photos is nowhere to be found. Where did it go?",
        "where is the search button after the recent update ? I can't find it anywhere",
        "Date grouping disappeared! an update removed the photos being grouped by date.",
        "Face search categories are inconsistent, app will separate people into two different profiles",
        "did you guys nerf the search function. now it says we can't find the search your looking for",
        "Can you search for photos just by their locations",
        "TIL. You can search your images for what they contain",
    ]
    for text in cases:
        label, _ = classify_relevance(text, "reddit")
        assert label == "retrieval_related", text


def test_help_community_chrome_is_not_search_signal():
    chrome = (
        "Stop back up videos - Google Photos Community Skip to main content "
        "Google Photos Help Sign in Privacy Policy Search Help Center Clear search "
        "Can't find your photos? Close search Search 105394"
    )
    cleaned = strip_help_community_chrome(chrome, "Stop back up videos - Google Photos Community")
    assert "search" not in cleaned.lower()
    label, _ = classify_relevance(chrome, "help_community", title="Stop back up videos - Google Photos Community")
    assert label == "unrelated"


def test_sentiment_uses_training_data_rules():
    assert classify_search_sentiment(
        "Great app! I can find photos of specific people, specific years, or documents! its great!"
    ) == "positive"
    assert classify_search_sentiment(
        "it's horrible. I can't find half the photos I want to send to people."
    ) == "negative"
    assert classify_search_sentiment(
        "Helpful hack: How I manually tag unrecognized people in my photos Google Photos does not currently allow manually tagging faces"
    ) == "neutral"


def test_forum_reply_is_no_signal_and_excluded_from_search_types():
    text = (
        "Doesn't sound particularly serious after reading your subsequent posts. "
        "Find them and put them in an album called pictures of myself. Good luck."
    )
    payload = {"raw_api_payload": {"kind": "comment"}}
    assert is_forum_reply(text, source="reddit", payload=payload)
    tags = annotate_research_item(text, source="reddit", payload=payload)
    assert tags["signal"] == "no_signal"
    assert tags["search_types"] == []


def test_pain_points_only_on_actionable_signals():
    taxonomy = load_taxonomy(version="research_v1")
    actionable = classify_research_heuristic(
        "Face search categories are inconsistent, app will separate people into two different profiles",
        taxonomy,
        source="reddit",
    )
    assert "system_face_grouping" in actionable.labels
    assert "system_issues" in actionable.labels

    opinion = classify_research_heuristic("I can't ever find my pictures!", taxonomy, source="play_store")
    assert opinion.labels == []

    reply = classify_research_heuristic(
        "Try to search by 'lenovo' or model number. That should give you all photos taken using the phone.",
        taxonomy,
        source="reddit",
        payload={"raw_api_payload": {"kind": "comment"}},
    )
    assert reply.labels == []
    assert reply.extra["signal"] == "no_signal"


def test_search_types_multi_label():
    tags = annotate_research_item(
        "I can no longer search my photos for people, colors, objects or words. The option to search using name or event is no longer available.",
        source="app_store",
    )
    assert "people_pets" in tags["search_types"]
    assert "objects" in tags["search_types"]
    assert "events" in tags["search_types"]


def test_theme_charts_exclude_search_ai_search_type():
    assert SEARCH_AI_SEARCH_TYPE_ID in SEARCH_TYPE_IDS
    assert SEARCH_AI_SEARCH_TYPE_ID not in SEARCH_TYPE_IDS_FOR_THEME_CHARTS
    assert len(SEARCH_TYPE_IDS_FOR_THEME_CHARTS) == len(SEARCH_TYPE_IDS) - 1


def test_search_ai_search_type_keywords_only():
    tags = annotate_research_item(
        "Lost the search bar; Gemini pop-up blocks the screen and search results never load.",
        source="app_store",
    )
    assert "search_ai_search" in tags["search_types"]
    without = annotate_research_item(
        "Face grouping is broken and I can't find albums.",
        source="app_store",
    )
    assert "search_ai_search" not in without["search_types"]
    assert "albums" in without["search_types"]
