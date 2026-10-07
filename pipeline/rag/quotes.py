from __future__ import annotations

import re


def expand_to_sentence_boundary(text: str, snippet: str, max_chars: int = 600) -> str:
    """Expand a hit snippet to a sentence or item boundary for the evidence drawer."""
    if not text or not snippet:
        return snippet or ""
    idx = text.find(snippet)
    if idx < 0:
        return snippet[:max_chars]

    start = idx
    while start > 0 and text[start - 1] not in ".!?\n":
        start -= 1
        if idx - start > 200:
            start = max(0, idx - 120)
            break

    end = idx + len(snippet)
    while end < len(text) and text[end] not in ".!?\n":
        end += 1
        if end - (idx + len(snippet)) > 200:
            end = min(len(text), idx + len(snippet) + 120)
            break
    if end < len(text) and text[end] in ".!?\n":
        end += 1

    expanded = text[start:end].strip()
    if len(expanded) > max_chars:
        return expanded[: max_chars - 3].rstrip() + "..."
    return expanded
