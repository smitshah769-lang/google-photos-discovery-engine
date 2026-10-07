from __future__ import annotations

import re
from typing import Any, Iterable

FRUSTRATION = re.compile(
    r"\b("
    r"can't find|cannot find|couldn't find|useless|hate|frustrated|give up|gave up|"
    r"impossible|never (finds|works)|broken|worst|terrible|angry"
    r")\b",
    re.IGNORECASE,
)

EMOTIONAL_VALUE = re.compile(
    r"\b("
    r"family|wedding|travel|memory|memories|sick|medicine|baby|funeral|"
    r"anniversary|holiday|cousin|brother|sister|child"
    r")\b",
    re.IGNORECASE,
)

MULTI_LABEL_COUNTING_RULE = (
    "An item may increment frequency for every taxonomy node it is labeled with. "
    "Headline category frequency is the count of distinct retrieval_related items "
    "with that node. Ambiguous relevance items are excluded until a human accepts them."
)


def item_impact_features(text: str) -> dict[str, float]:
    blob = text or ""
    return {
        "frustration": 1.0 if FRUSTRATION.search(blob) else 0.0,
        "emotional_value": 1.0 if EMOTIONAL_VALUE.search(blob) else 0.0,
    }


def score_categories(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    items: dicts with keys id, source, text, labels[], confidence, segments
    Returns per-node aggregates. Severity is ordinal within this snapshot only.
    """
    by_node: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        for lab in item.get("labels") or []:
            by_node.setdefault(lab, []).append(item)

    raw_rows: list[dict[str, Any]] = []
    for node_id, members in by_node.items():
        sources = {m["source"] for m in members if m.get("source")}
        freqs = len({m["id"] for m in members})
        confs = [float(m.get("confidence") or 0.0) for m in members]
        avg_conf = sum(confs) / len(confs) if confs else 0.0
        frust = sum(item_impact_features(m.get("text") or "")["frustration"] for m in members)
        emo = sum(item_impact_features(m.get("text") or "")["emotional_value"] for m in members)
        diversity = len(sources)
        # Star ratings are not used. Frequency + frustration + diversity + emotional markers.
        raw_severity = (
            freqs * 1.0
            + frust * 1.5
            + diversity * 2.0
            + emo * 1.0
        )
        source_mix = {src: sum(1 for m in members if m.get("source") == src) for src in sorted(sources)}
        segs = [m.get("segments") or {} for m in members]
        unknown = _unknown_rates(segs)
        workarounds = [m["id"] for m in members if "workarounds_succeeded" in (m.get("labels") or [])]
        raw_rows.append(
            {
                "taxonomy_node_id": node_id,
                "frequency": freqs,
                "raw_severity": raw_severity,
                "avg_confidence": round(avg_conf, 4),
                "source_mix": source_mix,
                "consistent_across_sources": diversity >= 2,
                "segment_unknown_rates": unknown,
                "workaround_ids": workarounds,
                "ranked_opportunity": node_id != "other",
            }
        )

    if not raw_rows:
        return []
    max_sev = max(r["raw_severity"] for r in raw_rows) or 1.0
    min_sev = min(r["raw_severity"] for r in raw_rows)
    span = max_sev - min_sev or 1.0
    for row in raw_rows:
        # Ordinal 0–1 within this snapshot, not prevalence.
        row["severity"] = round((row["raw_severity"] - min_sev) / span, 4)
    raw_rows.sort(key=lambda r: (-r["severity"], -r["frequency"]))
    return raw_rows


def _unknown_rates(segs: Iterable[dict[str, Any]]) -> dict[str, float]:
    rows = list(segs)
    keys = ("library_size", "photo_age", "geo", "device")
    if not rows:
        return {k: 1.0 for k in keys}
    n = len(rows)
    return {
        k: round(sum(1 for s in rows if (s.get(k) or "unknown") == "unknown") / n, 4)
        for k in keys
    }
