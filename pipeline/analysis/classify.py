from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from pipeline.analysis.inference import (
    CompletionClient,
    InferenceUnavailable,
    OllamaClient,
    huggingface_zero_shot,
)
from pipeline.analysis.json_parse import parse_json_object
from pipeline.analysis.snippets import fallback_snippet, snippets_in_text
from pipeline.paths import PROJECT_ROOT
from pipeline.taxonomy import Taxonomy

PROMPT_PATH = PROJECT_ROOT / "config" / "prompts" / "classify_v0.txt"

# Heuristic patterns map to taxonomy ids. Used only when provider=heuristic.
# Invalid LLM JSON must NOT fall through here (edge §9).
_HEURISTIC_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "deleted_locked_partner_sharing",
        re.compile(
            r"\b(in trash|were deleted|locked folder|partner sharing|shared library|locked album)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "backup_sync_storage",
        re.compile(
            r"\b(backup|sync|storage quota|upload|switched phones|device change)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "query_failure_complete_info",
        re.compile(
            r"\b(exact date|exact day|searched the exact|right album name)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "workarounds_succeeded",
        re.compile(
            r"\b(years view|workaround (actually )?worked|partner'?s phone|found it by browsing)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "search_abandonment",
        re.compile(
            r"\b(gave up|two or three times|tried search three times|abandon)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "metadata_gaps",
        re.compile(r"\b(dates? (are|is) (all )?wrong|people tags?|metadata)\b", re.IGNORECASE),
    ),
    (
        "library_scale_recency",
        re.compile(r"\b(thousands of photos|3000|3,000|old pictures from years)\b", re.IGNORECASE),
    ),
    (
        "incomplete_memory_object_time",
        re.compile(
            r"\b(screenshot|warranty card|last autumn|months ago|medicine)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "incomplete_memory_person_occasion",
        re.compile(r"\b(cousin|brother|sister|which summer|which holiday)\b", re.IGNORECASE),
    ),
    (
        "incomplete_memory_place_event",
        re.compile(
            r"\b(night market|city walk|without remembering the date|lakeside cabin)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "query_formulation_mismatch",
        re.compile(r"\b(wrong keyword|keyword mismatch)\b", re.IGNORECASE),
    ),
]


@dataclass
class ClassificationResult:
    labels: list[str]
    confidence: float
    rationale: str
    snippets: list[str]
    unclassified: bool
    provider: str
    raw_response: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def load_classify_prompt(taxonomy: Taxonomy, text: str) -> str:
    template = PROMPT_PATH.read_text(encoding="utf-8")
    block = "\n".join(f"- {n.id}: {n.definition}" for n in taxonomy.nodes)
    return template.replace("{{taxonomy_block}}", block).replace("{{text}}", text)


def _normalize_result(
    data: dict[str, Any],
    text: str,
    taxonomy: Taxonomy,
    *,
    provider: str,
    raw: str | None,
) -> ClassificationResult:
    valid_ids = taxonomy.ids()
    raw_labels = data.get("labels") or []
    if not isinstance(raw_labels, list):
        raw_labels = []
    labels = [str(x) for x in raw_labels if str(x) in valid_ids]
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    rationale = str(data.get("rationale") or "").strip()
    if confidence >= 0.8 and not rationale:
        confidence = min(confidence, 0.4)
        rationale = "high_confidence_empty_rationale"
    raw_snips = data.get("snippets") or []
    if not isinstance(raw_snips, list):
        raw_snips = []
    snippets = snippets_in_text([str(s) for s in raw_snips], text)
    if labels and not snippets:
        snippets = fallback_snippet(text)
    unclassified = len(labels) == 0
    return ClassificationResult(
        labels=labels,
        confidence=confidence,
        rationale=rationale,
        snippets=snippets,
        unclassified=unclassified,
        provider=provider,
        raw_response=raw,
    )


def classify_heuristic(
    text: str,
    taxonomy: Taxonomy,
    *,
    source: str = "",
    payload: dict[str, Any] | None = None,
) -> ClassificationResult:
    if taxonomy.version == "research_v1":
        from pipeline.analysis.research_heuristics import classify_research_heuristic

        return classify_research_heuristic(text, taxonomy, source=source, payload=payload)
    labels: list[str] = []
    for node_id, pattern in _HEURISTIC_RULES:
        if node_id in taxonomy.ids() and pattern.search(text or ""):
            labels.append(node_id)
    # Keep unique order.
    seen: set[str] = set()
    uniq: list[str] = []
    for lab in labels:
        if lab not in seen:
            seen.add(lab)
            uniq.append(lab)
    snippets = fallback_snippet(text)
    return ClassificationResult(
        labels=uniq,
        confidence=0.55 if uniq else 0.0,
        rationale="heuristic_v0" if uniq else "unclassified",
        snippets=snippets if uniq else [],
        unclassified=not uniq,
        provider="heuristic",
    )


def classify_with_llm(
    text: str,
    taxonomy: Taxonomy,
    client: CompletionClient,
    *,
    temperature: float,
) -> ClassificationResult:
    prompt = load_classify_prompt(taxonomy, text)
    last_raw = ""
    for _attempt in range(2):
        last_raw = client.complete(prompt, temperature=temperature)
        parsed = parse_json_object(last_raw)
        if parsed is not None:
            return _normalize_result(
                parsed, text, taxonomy, provider="ollama", raw=last_raw
            )
    # Invalid JSON after one retry: unclassified. Do not regex-guess labels.
    return ClassificationResult(
        labels=[],
        confidence=0.0,
        rationale="invalid_llm_json",
        snippets=[],
        unclassified=True,
        provider="ollama",
        raw_response=last_raw,
    )


def classify_huggingface(text: str, taxonomy: Taxonomy, *, threshold: float = 0.45) -> ClassificationResult:
    labels_all = [n.id for n in taxonomy.nodes]
    scores = huggingface_zero_shot(text, labels_all)
    labels = [lab for lab, score in scores.items() if score >= threshold and lab in taxonomy.ids()]
    conf = max((scores.get(lab, 0.0) for lab in labels), default=0.0)
    snippets = fallback_snippet(text) if labels else []
    return ClassificationResult(
        labels=labels,
        confidence=conf,
        rationale="huggingface_zero_shot",
        snippets=snippets,
        unclassified=not labels,
        provider="huggingface",
        extra={"scores": scores},
    )


def build_classifier(models_cfg: dict[str, Any]) -> tuple[str, CompletionClient | None]:
    clf = (models_cfg or {}).get("classification") or {}
    provider = str(clf.get("provider") or "ollama").lower()
    if provider == "heuristic":
        return provider, None
    if provider == "huggingface":
        return provider, None
    if provider == "ollama":
        model_id = clf.get("model_id")
        return provider, OllamaClient(str(model_id) if model_id else "")
    raise InferenceUnavailable(
        f"Unknown classification provider {provider!r}. Use ollama, huggingface, or heuristic."
    )


def classify_text(
    text: str,
    taxonomy: Taxonomy,
    *,
    provider: str,
    client: CompletionClient | None,
    temperature: float,
    fallback_provider: str | None = None,
    source: str = "",
    payload: dict[str, Any] | None = None,
) -> ClassificationResult:
    try:
        if provider == "heuristic":
            return classify_heuristic(text, taxonomy, source=source, payload=payload)
        if provider == "huggingface":
            return classify_huggingface(text, taxonomy)
        if provider == "ollama":
            if client is None:
                raise InferenceUnavailable("Ollama client missing.")
            return classify_with_llm(text, taxonomy, client, temperature=temperature)
        raise InferenceUnavailable(f"Unknown provider {provider}")
    except InferenceUnavailable:
        if fallback_provider and fallback_provider != provider:
            return classify_text(
                text,
                taxonomy,
                provider=fallback_provider,
                client=None,
                temperature=temperature,
                fallback_provider=None,
                source=source,
                payload=payload,
            )
        raise
