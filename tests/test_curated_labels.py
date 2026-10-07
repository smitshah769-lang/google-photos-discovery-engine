from pipeline.analysis.classify import ClassificationResult
from pipeline.analysis.curated_labels import apply_curated_label, curated_relevance, item_key
from pipeline.analysis.research_heuristics import classify_research_heuristic
from pipeline.normalize.feedback_builder import build_feedback_from_raw
from pipeline.taxonomy import load_taxonomy


def _result() -> ClassificationResult:
    return ClassificationResult(
        labels=["design_missing_search_control", "design_issues"],
        confidence=0.64,
        rationale="research_heuristic_v2",
        snippets=[],
        unclassified=False,
        provider="heuristic",
        extra={"sentiment": "negative", "signal": "actionable", "engagement": {"score": 3}},
    )


def test_curated_label_replaces_heuristic_tags_and_adds_parents():
    taxonomy = load_taxonomy(version="research_v1")
    result = _result()
    apply_curated_label(
        result,
        {
            "in_scope": True,
            "is_forum_reply": False,
            "signal": "actionable",
            "sentiment": "negative",
            "pain_points": ["system_face_grouping"],
            "search_types": ["people_pets"],
            "is_suggestion": False,
        },
        "I accidentally turned off face grouping and now I can't see it in my search bar",
        taxonomy,
    )
    assert result.labels == ["system_face_grouping", "system_issues"]
    assert result.extra["search_types"] == ["people_pets"]
    assert result.extra["engagement"] == {"score": 3}
    assert result.extra["label_source"] == "curated"


def test_curated_forum_reply_gets_no_pain_points_or_types():
    taxonomy = load_taxonomy(version="research_v1")
    result = _result()
    apply_curated_label(
        result,
        {
            "in_scope": True,
            "is_forum_reply": True,
            "signal": "no_signal",
            "sentiment": "neutral",
            "pain_points": [],
            "search_types": ["other"],
            "is_suggestion": False,
        },
        "Go to the search bar and type Recently added",
        taxonomy,
    )
    assert result.labels == []
    assert result.unclassified
    assert result.extra["search_types"] == []
    assert result.extra["signal"] == "no_signal"


def test_curated_relevance_overrides_rule_based_filter():
    payload = {
        "source": "help_community",
        "native_id": "123",
        "title": "Can't find video stabilization feature on Pixel 3",
        "text": "Whenever I tap the Edit button for a video, I can't find stabilization in search.",
    }
    assert item_key("help_community", payload) == "help_community:123"
    curated = {"help_community:123": {"in_scope": False, "oos_reason": "editing"}}
    built = build_feedback_from_raw(payload, curated)
    assert built is not None
    assert (built["relevance_label"], built["relevance_confidence"]) == curated_relevance({"in_scope": False})


def test_heuristic_does_not_tag_search_bar_tips_as_missing_control():
    taxonomy = load_taxonomy(version="research_v1")
    tip = classify_research_heuristic(
        "Did Google change search? If I type Recently added in the search bar it no longer works",
        taxonomy,
    )
    assert "design_missing_search_control" not in tip.labels
    gone = classify_research_heuristic(
        "where is the search button? it's missing after update, the ask button is useless",
        taxonomy,
    )
    assert "design_missing_search_control" in gone.labels
