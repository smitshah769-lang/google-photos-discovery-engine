from __future__ import annotations

def snippets_in_text(snippets: list[str], stored_text: str) -> list[str]:
    """Keep quotes that appear verbatim in stored text (edge §9 / RAG later)."""
    kept: list[str] = []
    haystack = stored_text or ""
    for raw in snippets:
        quote = (raw or "").strip()
        if not quote:
            continue
        if quote in haystack:
            kept.append(quote)
            continue
        # Allow whitespace-normalized match by locating original span.
        collapsed = " ".join(quote.split())
        collapsed_hay = " ".join(haystack.split())
        if collapsed and collapsed in collapsed_hay:
            idx = haystack.lower().find(quote[:12].lower()) if len(quote) >= 12 else -1
            if idx >= 0:
                kept.append(haystack[idx : idx + len(quote)])
            else:
                kept.append(quote)
    # Deduplicate while preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for s in kept:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def fallback_snippet(stored_text: str, max_len: int = 180) -> list[str]:
    text = (stored_text or "").strip()
    if not text:
        return []
    cut = text[:max_len].rsplit(" ", 1)[0] if len(text) > max_len else text
    return [cut]
