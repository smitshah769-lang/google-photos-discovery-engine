from __future__ import annotations

from typing import Any

from pipeline.analysis.inference import CompletionClient, InferenceUnavailable
from pipeline.analysis.json_parse import parse_json_object
from pipeline.analysis.research_tags import SEARCH_TYPE_IDS
from pipeline.paths import PROJECT_ROOT
from pipeline.taxonomy import Taxonomy
from pipeline.taxonomy_aliases import resolve_taxonomy_label

PROMPT_PATH = PROJECT_ROOT / "config" / "prompts" / "research_llm_v0.txt"

OOS_REASONS = frozenset(
    {
        "backup_storage",
        "sharing",
        "privacy",
        "editing",
        "non_search_ui",
        "non_search_bug",
        "unrelated",
    }
)
SENTIMENTS = frozenset({"positive", "negative", "neutral"})
SIGNALS = frozenset({"actionable", "no_signal"})


def load_research_llm_prompt(*, source: str, text: str) -> str:
    template = PROMPT_PATH.read_text(encoding="utf-8")
    return template.replace("{{source}}", source).replace("{{text}}", text)


def _clamp_confidence(value: Any) -> float:
    try:
        c = float(value)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, c))


def normalize_llm_label(data: dict[str, Any], taxonomy: Taxonomy) -> dict[str, Any]:
    """Map raw LLM JSON to curated_labels-compatible dict."""
    valid_nodes = taxonomy.ids()
    in_scope = bool(data.get("in_scope"))
    oos = data.get("oos_reason")
    if in_scope:
        oos_reason = None
    else:
        oos_reason = str(oos) if oos in OOS_REASONS else "unrelated"
        in_scope = False

    sentiment = str(data.get("sentiment") or "neutral").lower()
    if sentiment not in SENTIMENTS:
        sentiment = "neutral"

    signal = str(data.get("signal") or "no_signal").lower()
    if signal not in SIGNALS:
        signal = "no_signal"

    is_forum_reply = bool(data.get("is_forum_reply"))
    if is_forum_reply:
        signal = "no_signal"

    pain_points: list[str] = []
    if in_scope and signal == "actionable":
        raw_pp = data.get("pain_points") or []
        if isinstance(raw_pp, list):
            for raw_id in raw_pp:
                node_id = resolve_taxonomy_label(str(raw_id))
                if node_id in valid_nodes and node_id not in pain_points:
                    pain_points.append(node_id)

    search_types: list[str] = []
    if in_scope and not is_forum_reply:
        raw_st = data.get("search_types") or []
        if isinstance(raw_st, list):
            for type_id in raw_st:
                tid = str(type_id)
                if tid in SEARCH_TYPE_IDS and tid not in search_types:
                    search_types.append(tid)

    is_suggestion = bool(data.get("is_suggestion")) and in_scope and not is_forum_reply

    return {
        "in_scope": in_scope,
        "oos_reason": oos_reason,
        "is_forum_reply": is_forum_reply,
        "signal": signal,
        "sentiment": sentiment,
        "pain_points": pain_points,
        "search_types": search_types,
        "is_suggestion": is_suggestion,
        "confidence": _clamp_confidence(data.get("confidence")),
        "rationale": str(data.get("rationale") or "").strip()[:500],
        "label_source": "ollama_second_pass",
    }


def classify_research_with_llm(
    text: str,
    *,
    source: str,
    taxonomy: Taxonomy,
    client: CompletionClient,
    temperature: float,
) -> tuple[dict[str, Any] | None, str]:
    """Returns (normalized label or None if invalid JSON after retry, last raw response)."""
    prompt = load_research_llm_prompt(source=source, text=text)
    last_raw = ""
    for _attempt in range(2):
        last_raw = client.complete(prompt, temperature=temperature)
        parsed = parse_json_object(last_raw)
        if parsed is not None:
            return normalize_llm_label(parsed, taxonomy), last_raw
    return None, last_raw


def resolve_ollama_model_id(models_cfg: dict[str, Any], *, purpose: str = "classification") -> str:
    block = (models_cfg or {}).get(purpose) or {}
    model_id = block.get("model_id")
    if model_id:
        return str(model_id)
    fallback = (models_cfg or {}).get("classification") or {}
    fb_id = fallback.get("model_id")
    if fb_id:
        return str(fb_id)
    raise InferenceUnavailable(
        f"Ollama requires models.{purpose}.model_id or models.classification.model_id in run.yaml."
    )
