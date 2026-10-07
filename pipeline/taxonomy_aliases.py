"""Map retired taxonomy node ids to their replacements for counts and evidence."""

from __future__ import annotations

TAXONOMY_LABEL_ALIASES: dict[str, str] = {
    "knowledge_hidden_features": "knowledge_unknown_capability",
}


def resolve_taxonomy_label(node_id: str) -> str:
    return TAXONOMY_LABEL_ALIASES.get(node_id, node_id)


def classification_node_ids_for_query(node_id: str) -> tuple[str, ...]:
    """DB rows may still reference retired ids until the next analyze pass."""
    canonical = resolve_taxonomy_label(node_id)
    if canonical == "knowledge_unknown_capability":
        return ("knowledge_unknown_capability", "knowledge_hidden_features")
    return (node_id,)
