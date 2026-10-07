from __future__ import annotations

INCOMPLETE_MEMORY_NODES = frozenset(
    {
        "incomplete_memory",
        "incomplete_memory_place_event",
        "incomplete_memory_person_occasion",
        "incomplete_memory_object_time",
        "query_inference",
        "query_not_understood",
        "query_followup_ignored",
        "knowledge_awareness_gaps",
        "knowledge_unknown_capability",
    }
)

# Search is not the incomplete-memory problem (upload/delete/complete-info failure).
CONTRADICT_NODES = frozenset(
    {
        "backup_sync_storage",
        "deleted_locked_partner_sharing",
        "query_failure_complete_info",
        "system_issues",
        "system_face_grouping",
        "system_metadata_gaps",
        "system_object_recognition",
        "system_other_failures",
        "system_search_bugs",
    }
)


def overlay_for_labels(labels: list[str]) -> str:
    """Per-item overlay: support | contradict | insufficient."""
    lab = set(labels)
    has_memory = bool(lab & INCOMPLETE_MEMORY_NODES)
    has_contradict = bool(lab & CONTRADICT_NODES)
    if has_memory:
        return "support"
    if has_contradict:
        return "contradict"
    return "insufficient"


def summarize_overlays(values: list[str]) -> dict:
    counts = {"support": 0, "contradict": 0, "insufficient": 0}
    for value in values:
        if value in counts:
            counts[value] += 1
        else:
            counts["insufficient"] += 1
    # Overall is the plurality; zeros stay visible so the UI is not support-only.
    overall = max(counts, key=lambda k: counts[k]) if any(counts.values()) else "insufficient"
    return {
        "counts": counts,
        "overall": overall,
        "values_supported": ["support", "contradict", "insufficient"],
    }
