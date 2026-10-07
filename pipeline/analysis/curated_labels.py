"""Human-reviewed labels (per source item) that take precedence over heuristic tagging.

File format: JSONL, one object per item keyed by ``"<source>:<native_id>"`` with fields
in_scope, oos_reason, is_forum_reply, signal, sentiment, pain_points, search_types, is_suggestion.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pipeline.analysis.snippets import fallback_snippet
from pipeline.paths import PROJECT_ROOT
from pipeline.taxonomy import Taxonomy
from pipeline.analysis.research_tags import search_types_for_text
from pipeline.taxonomy_aliases import resolve_taxonomy_label


def resolve_curated_path(run_spec: dict[str, Any] | None) -> Path | None:
    raw = ((run_spec or {}).get("analysis") or {}).get("curated_labels")
    if not raw:
        return None
    path = Path(str(raw))
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path if path.is_file() else None


@lru_cache(maxsize=4)
def _load(path_str: str, mtime: float) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for line in Path(path_str).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        out[str(row["key"])] = row
    return out


def load_curated_labels(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None or not path.is_file():
        return {}
    return _load(str(path), path.stat().st_mtime)


def item_key(source: str, payload: dict[str, Any] | None) -> str | None:
    native_id = (payload or {}).get("native_id")
    if not source or not native_id:
        return None
    return f"{source}:{native_id}"


def curated_relevance(label: dict[str, Any]) -> tuple[str, float]:
    return ("retrieval_related", 1.0) if label.get("in_scope") else ("unrelated", 1.0)


def apply_curated_label(result: Any, label: dict[str, Any], text: str, taxonomy: Taxonomy) -> None:
    """Overwrite a ClassificationResult in place with the reviewed label."""
    ids = taxonomy.ids()
    labels: list[str] = []
    if label.get("in_scope") and label.get("signal") == "actionable":
        for raw_id in label.get("pain_points") or []:
            node_id = resolve_taxonomy_label(str(raw_id))
            if node_id in ids and node_id not in labels:
                labels.append(node_id)
        for node_id in list(labels):
            parent = taxonomy.get(node_id).parent_id
            if parent and parent in ids and parent not in labels:
                labels.append(parent)
    reply = bool(label.get("is_forum_reply"))
    search_types = [] if reply else list(label.get("search_types") or [])
    if not reply:
        for type_id in search_types_for_text(text, exclude=False):
            if type_id == "search_ai_search" and type_id not in search_types:
                search_types.append(type_id)
    extra = dict(result.extra or {})
    extra.update(
        {
            "sentiment": label.get("sentiment") or "neutral",
            "signal": "no_signal" if reply else (label.get("signal") or "no_signal"),
            "search_types": search_types,
            "is_forum_reply": reply,
            "is_suggestion": bool(label.get("is_suggestion")) and not reply,
            "label_source": label.get("label_source") or "curated",
        }
    )
    result.labels = labels
    result.unclassified = not labels
    result.confidence = 1.0 if labels else 0.0
    result.rationale = "curated_review" if labels else "no_actionable_pain_point"
    result.snippets = fallback_snippet(text) if labels else []
    result.extra = extra
