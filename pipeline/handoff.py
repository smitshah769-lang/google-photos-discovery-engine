"""Phase 5 handoff pack: non-claims, known gaps, rebuild copy, out-of-repo scope."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from pipeline.serve.methodology_copy import NON_CLAIMS, OUT_OF_REPO_SCOPE, RANKING_COPY
from pipeline.serve.read import SOURCES, chrome, methodology, quality


GAP_STATUSES = frozenset({"failed", "gap", "skipped", "pending"})


def known_gaps(
    receipts: list[dict[str, Any]],
    *,
    relevant_count: int | None,
    corpus_target: int,
    index_exists: bool = True,
) -> list[dict[str, str]]:
    gaps: list[dict[str, str]] = []
    for receipt in receipts:
        status = str(receipt.get("status") or "")
        notes = str(receipt.get("notes") or "").strip()
        source = str(receipt.get("source") or "")
        if status in GAP_STATUSES or status == "partial":
            gaps.append(
                {
                    "kind": "adapter",
                    "source": source,
                    "status": status,
                    "detail": notes or f"Source {source} is {status} — not a silent skip.",
                }
            )
        lowered = notes.lower()
        if "quota" in lowered or "cse" in lowered:
            gaps.append(
                {
                    "kind": "cse_quota",
                    "source": source or "help_community",
                    "status": status,
                    "detail": notes,
                }
            )
        if "arctic" in lowered or "outage" in lowered:
            gaps.append(
                {
                    "kind": "arctic_shift",
                    "source": source or "reddit",
                    "status": status,
                    "detail": notes,
                }
            )
    if relevant_count is not None and relevant_count < corpus_target:
        gaps.append(
            {
                "kind": "corpus_target",
                "source": "all",
                "status": "miss",
                "detail": (
                    f"Relevant items {relevant_count} vs success bar {corpus_target}. "
                    "Widening keywords or storefronts requires a new run_id."
                ),
            }
        )
    if not index_exists:
        gaps.append(
            {
                "kind": "vector_index",
                "source": "rag",
                "status": "missing",
                "detail": "Vector index file is missing; dashboard aggregates can still load.",
            }
        )
    # Deduplicate identical details
    seen: set[tuple[str, str, str]] = set()
    unique: list[dict[str, str]] = []
    for gap in gaps:
        key = (gap["kind"], gap["source"], gap["detail"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(gap)
    return unique


def rebuild_instructions(analysis_run_id: str) -> list[str]:
    return [
        "Serving the frozen artifact does not require collect/analyze jobs: "
        f"`python -m pipeline serve {analysis_run_id}` plus `./scripts/serve-artifact.sh {analysis_run_id}`.",
        "To rebuild aggregates from stored raw + the run spec (does not re-fetch the web): "
        f"`python -m pipeline rebuild {analysis_run_id}`. This is refused if the run is frozen — "
        "create a new run_id and copy raw, or use rebuild-from-export.",
        "To rebuild from a freeze export directory: "
        "`python -m pipeline rebuild-from-export data/exports/<run-id>` "
        "(new run_id; copies raw + receipts, then normalize → analyze → index → aggregate).",
        "Same `config/run.yaml` (or the `run.yaml` inside the export) plus stored `raw_record` "
        "rows is the reproducibility contract (architecture §15). Do not collect again unless "
        "you intend a new snapshot.",
    ]


def handoff_payload(conn: sqlite3.Connection, analysis_run_id: str) -> dict[str, Any]:
    method = methodology(conn, analysis_run_id)
    quality_payload = quality(conn, analysis_run_id)
    meta = chrome(conn, analysis_run_id)
    coverage = method.get("coverage") or {}
    relevant = coverage.get("relevant_count")
    if relevant is None:
        relevant = quality_payload.get("classified_count")
    gaps = known_gaps(
        method.get("source_receipts") or [],
        relevant_count=int(relevant) if relevant is not None else None,
        corpus_target=int(meta["corpus_target_relevant"]),
        index_exists=bool((quality_payload.get("index") or {}).get("exists")),
    )
    return {
        **meta,
        "non_claims": list(NON_CLAIMS),
        "known_gaps": gaps,
        "out_of_repo_scope": list(OUT_OF_REPO_SCOPE),
        "rebuild_instructions": rebuild_instructions(analysis_run_id),
        "ranking_copy": RANKING_COPY,
        "required_limitations": method.get("required_limitations") or [],
        "source_receipts": method.get("source_receipts") or [],
        "pipeline_required_for_serving": False,
        "serving_note": (
            "Dashboard and RAG read the frozen SQLite + vector index only. "
            "Do not run collect/analyze while reviewing this snapshot."
        ),
        "sources": list(SOURCES),
    }


def handoff_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Handoff pack — Google Photos retrieval snapshot",
        "",
        f"- run_id: `{payload.get('run_id')}`",
        f"- freeze: `{payload.get('frozen_at') or 'not frozen'}`",
        f"- status: `{payload.get('status')}`",
        "",
        payload.get("serving_note") or "",
        "",
        "## Non-claims",
        "",
    ]
    for claim in payload.get("non_claims") or []:
        lines.append(f"- {claim}")
    lines.extend(["", "## Known gaps (from receipts)", ""])
    gaps = payload.get("known_gaps") or []
    if not gaps:
        lines.append("- No adapter gaps recorded; still not a census of all Photos users.")
    else:
        for gap in gaps:
            lines.append(
                f"- **{gap.get('kind')}** ({gap.get('source')}, {gap.get('status')}): {gap.get('detail')}"
            )
    lines.extend(["", "## Rebuild from raw + run spec", ""])
    for step in payload.get("rebuild_instructions") or []:
        lines.append(f"- {step}")
    lines.extend(["", "## Out of this repository", ""])
    for item in payload.get("out_of_repo_scope") or []:
        lines.append(f"- {item}")
    lines.extend(["", "## Ranking", "", payload.get("ranking_copy") or "", ""])
    return "\n".join(lines)


def write_handoff_files(dest: Any, payload: dict[str, Any]) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "HANDOFF.json").write_text(json.dumps(payload, indent=2, default=str))
    (dest / "HANDOFF.md").write_text(handoff_markdown(payload))
    (dest / "REBUILD.md").write_text(
        "\n".join(
            ["# Rebuild from stored raw + run spec", ""]
            + [f"- {s}" for s in payload.get("rebuild_instructions") or []]
            + [""]
        )
    )
