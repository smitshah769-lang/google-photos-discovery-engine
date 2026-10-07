from pipeline.analysis.research_llm import normalize_llm_label
from pipeline.taxonomy import load_taxonomy


def test_normalize_llm_label_maps_enums():
    taxonomy = load_taxonomy(version="research_v1")
    label = normalize_llm_label(
        {
            "in_scope": True,
            "signal": "actionable",
            "sentiment": "negative",
            "pain_points": ["system_face_grouping", "bogus_id"],
            "search_types": ["people_pets", "not_a_type"],
            "is_forum_reply": False,
            "is_suggestion": False,
            "confidence": 1.5,
        },
        taxonomy,
    )
    assert label["in_scope"] is True
    assert label["pain_points"] == ["system_face_grouping"]
    assert label["search_types"] == ["people_pets"]
    assert label["confidence"] == 1.0


def test_normalize_llm_label_out_of_scope():
    taxonomy = load_taxonomy(version="research_v1")
    label = normalize_llm_label(
        {"in_scope": False, "oos_reason": "backup_storage", "signal": "actionable"},
        taxonomy,
    )
    assert label["in_scope"] is False
    assert label["oos_reason"] == "backup_storage"
    assert label["pain_points"] == []
