from __future__ import annotations

from typing import Any

from pipeline.analysis.cloud_llm import build_synthesis_client
from pipeline.analysis.inference import InferenceUnavailable
from pipeline.analysis.json_parse import parse_json_object
from pipeline.analysis.snippets import snippets_in_text


def _build_prompt(query: str, hits: list[dict[str, Any]]) -> str:
    lines = [
        "You summarize user feedback about Google Photos photo search/retrieval.",
        "Use ONLY the evidence below. Every quote MUST appear verbatim in the item text.",
        "Write 2–4 sentences. Cite at most 2 items.",
        'Return JSON only: {"summary": "...", "citations": [{"item_id": "...", "quote": "..."}]}',
        "citations must have at most 2 entries.",
        f"Question: {query}",
        "",
        "Evidence:",
    ]
    for h in hits[:8]:
        lines.append(f"- item_id={h['item_id']}: {h.get('text', '')[:800]}")
    return "\n".join(lines)


def synthesize_cited_summary(
    query: str,
    hits: list[dict[str, Any]],
    *,
    provider: str,
    model_id: str,
    temperature: float = 0.1,
) -> dict[str, Any] | None:
    if not hits or not model_id:
        return None
    try:
        client = build_synthesis_client(provider, model_id)
        raw = client.complete(_build_prompt(query, hits), temperature=temperature)
    except InferenceUnavailable:
        return None

    data = parse_json_object(raw)
    if not data:
        return None

    summary = str(data.get("summary") or "").strip()
    citations_raw = data.get("citations") or []
    if not summary:
        return None

    validated: list[dict[str, str]] = []
    text_by_id = {h["item_id"]: h.get("stored_text") or h.get("text") or "" for h in hits}
    for entry in citations_raw:
        if not isinstance(entry, dict):
            continue
        item_id = str(entry.get("item_id") or "")
        quote = str(entry.get("quote") or "")
        if not item_id or not quote:
            continue
        stored = text_by_id.get(item_id)
        if not stored:
            continue
        kept = snippets_in_text([quote], stored)
        if not kept:
            continue
        validated.append({"item_id": item_id, "quote": kept[0]})
        if len(validated) >= 2:
            break

    if not validated:
        return None

    return {"summary": summary, "citations": validated[:2]}
