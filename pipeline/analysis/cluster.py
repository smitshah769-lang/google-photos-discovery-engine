from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from pipeline.analysis.embeddings import cosine


@dataclass
class ClusterResult:
    member_indices: list[int]
    cohesion: float
    label: str
    ranked_opportunity: bool
    needs_human_review: bool
    reason: str


def _avg_pairwise(vectors: list[list[float]], members: list[int]) -> float:
    if len(members) < 2:
        return 1.0
    total = 0.0
    n = 0
    for i, a in enumerate(members):
        for b in members[i + 1 :]:
            total += cosine(vectors[a], vectors[b])
            n += 1
    return total / n if n else 0.0


def cluster_items(
    vectors: list[list[float]],
    label_sets: list[list[str]],
    *,
    threshold: float,
) -> list[ClusterResult]:
    n = len(vectors)
    if n == 0:
        return []
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(n):
        for j in range(i + 1, n):
            if cosine(vectors[i], vectors[j]) >= threshold:
                union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)

    results: list[ClusterResult] = []
    for members in groups.values():
        cohesion = _avg_pairwise(vectors, members)
        label = _cluster_label(label_sets, members)
        size = len(members)
        tiny = size <= 2
        giant_other = label == "other" or (
            size >= max(8, int(0.4 * n)) and cohesion < 0.25
        )
        if giant_other:
            label = "other"
        ranked = not tiny and not giant_other
        reason = ""
        if tiny:
            reason = "n=1-2; not a new taxonomy root without human review"
        elif giant_other:
            reason = "giant catch-all / other; not a ranked opportunity"
        results.append(
            ClusterResult(
                member_indices=sorted(members),
                cohesion=round(cohesion, 4),
                label=label,
                ranked_opportunity=ranked,
                needs_human_review=tiny,
                reason=reason,
            )
        )
    results.sort(key=lambda c: (-len(c.member_indices), -c.cohesion))
    return results


def _cluster_label(label_sets: Sequence[Sequence[str]], members: list[int]) -> str:
    counts: dict[str, int] = {}
    for idx in members:
        for lab in label_sets[idx]:
            counts[lab] = counts.get(lab, 0) + 1
    if not counts:
        return "other"
    top = max(counts, key=lambda k: counts[k])
    # If the plurality is weak, call it mixed/other rather than a fake theme.
    if counts[top] < max(1, len(members) // 2):
        return "other"
    return top
