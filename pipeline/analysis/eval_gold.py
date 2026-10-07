from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipeline.analysis.classify import ClassificationResult, classify_text
from pipeline.analysis.inference import CompletionClient
from pipeline.paths import CONFIG_DIR, PROJECT_ROOT
from pipeline.taxonomy import Taxonomy

DEFAULT_GOLD_SET = CONFIG_DIR / "gold_set.json"


def load_gold_set(path: Path | None = None) -> dict[str, Any]:
    target = path or DEFAULT_GOLD_SET
    if not target.is_absolute():
        target = PROJECT_ROOT / target
    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise ValueError(f"Invalid gold set at {target}")
    return data


def evaluate_gold_set(
    gold: dict[str, Any],
    taxonomy: Taxonomy,
    *,
    provider: str,
    client: CompletionClient | None,
    temperature: float,
    fallback_provider: str | None = None,
) -> dict[str, Any]:
    items = gold.get("items") or []
    per_item: list[dict[str, Any]] = []
    label_ids = sorted(taxonomy.ids())
    tp: dict[str, int] = {i: 0 for i in label_ids}
    fp: dict[str, int] = {i: 0 for i in label_ids}
    fn: dict[str, int] = {i: 0 for i in label_ids}
    exact = 0

    for item in items:
        expected = [lab for lab in item.get("labels") or [] if lab in taxonomy.ids()]
        result: ClassificationResult = classify_text(
            str(item.get("text") or ""),
            taxonomy,
            provider=provider,
            client=client,
            temperature=temperature,
            fallback_provider=fallback_provider,
        )
        predicted = result.labels
        if set(predicted) == set(expected):
            exact += 1
        exp_set, pred_set = set(expected), set(predicted)
        for lab in pred_set - exp_set:
            fp[lab] = fp.get(lab, 0) + 1
        for lab in exp_set - pred_set:
            fn[lab] = fn.get(lab, 0) + 1
        for lab in exp_set & pred_set:
            tp[lab] = tp.get(lab, 0) + 1
        per_item.append(
            {
                "id": item.get("id"),
                "case": item.get("case"),
                "expected": expected,
                "predicted": predicted,
                "unclassified": result.unclassified,
                "match": set(predicted) == set(expected),
            }
        )

    n = len(items) or 1
    per_label: dict[str, dict[str, float]] = {}
    for lab in label_ids:
        prec = tp[lab] / (tp[lab] + fp[lab]) if (tp[lab] + fp[lab]) else None
        rec = tp[lab] / (tp[lab] + fn[lab]) if (tp[lab] + fn[lab]) else None
        if prec is None and rec is None:
            continue
        per_label[lab] = {
            "precision": None if prec is None else round(prec, 4),
            "recall": None if rec is None else round(rec, 4),
            "tp": tp[lab],
            "fp": fp[lab],
            "fn": fn[lab],
        }

    return {
        "n": len(items),
        "exact_match_accuracy": round(exact / n, 4) if items else 0.0,
        "per_label": per_label,
        "confusion_notes": (
            "Multi-label eval: per-label precision/recall (one-vs-rest) plus exact-set "
            "match accuracy. Not a single exclusive-class confusion matrix."
        ),
        "gold_set_version": gold.get("version"),
        "cases_covered": sorted({str(i.get("case")) for i in items}),
        "items": per_item,
        "multi_label_counting_rule": gold.get("multi_label_counting_rule"),
    }
