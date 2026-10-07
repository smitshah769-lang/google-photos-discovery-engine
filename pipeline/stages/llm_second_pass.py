from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from pipeline.analysis.classify import ClassificationResult
from pipeline.analysis.curated_labels import apply_curated_label, item_key
from pipeline.analysis.inference import InferenceUnavailable, OllamaClient
from pipeline.analysis.research_llm import classify_research_with_llm, resolve_ollama_model_id
from pipeline.analysis.research_tags import annotate_research_item, parse_payload_json
from pipeline.db.connection import assert_not_frozen, json_dumps
from pipeline.db.repository import load_run_spec
from pipeline.model_run import log_model_run
from pipeline.paths import PROJECT_ROOT
from pipeline.run_context import complete_stage_receipt
from pipeline.taxonomy import load_taxonomy


def _default_output_path(analysis_run_id: str) -> Path:
    return PROJECT_ROOT / "data" / f"llm_second_pass_{analysis_run_id}.jsonl"


def _load_completed_keys(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    done: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        key = row.get("key")
        if key and row.get("status") == "ok":
            done.add(str(key))
    return done


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def run_llm_second_pass(
    conn: sqlite3.Connection,
    analysis_run_id: str,
    *,
    output_path: Path | None = None,
    limit: int | None = None,
    resume: bool = True,
    reaggregate: bool = False,
) -> dict[str, Any]:
    assert_not_frozen(conn, analysis_run_id)
    run_spec = load_run_spec(conn, analysis_run_id)
    analysis_cfg = run_spec.get("analysis") or {}
    tax_version = str(analysis_cfg.get("taxonomy_version") or "research_v1")
    taxonomy = load_taxonomy(version=tax_version)
    if taxonomy.version != "research_v1":
        raise ValueError("llm-second-pass requires taxonomy_version research_v1")

    models = run_spec.get("models") or {}
    rel_cfg = models.get("relevance") or {}
    temperature = float(rel_cfg.get("temperature") if rel_cfg.get("temperature") is not None else 0.0)
    prompt_version = str(rel_cfg.get("prompt_version") or "research_llm_v0")
    model_id = resolve_ollama_model_id(models, purpose="relevance")
    client = OllamaClient(model_id)

    out_path = output_path or _default_output_path(analysis_run_id)
    completed = _load_completed_keys(out_path) if resume else set()

    rows = conn.execute(
        """
        SELECT f.id, f.source, f.text, f.relevance_label, rr.payload_json
        FROM feedback_item f
        LEFT JOIN raw_record rr ON rr.id = f.raw_record_id
        WHERE f.analysis_run_id = ? AND f.relevance_label = 'retrieval_related'
        ORDER BY f.id
        """,
        (analysis_run_id,),
    ).fetchall()

    stats: dict[str, Any] = {
        "stage": "llm_second_pass",
        "analysis_run_id": analysis_run_id,
        "model_id": model_id,
        "prompt_version": prompt_version,
        "input_retrieval_related": len(rows),
        "processed": 0,
        "skipped_resume": 0,
        "invalid_json": 0,
        "moved_out_of_scope": 0,
        "kept_in_scope": 0,
        "classified_pain_points": 0,
        "output_path": str(out_path),
    }

    try:
        for row in rows:
            if limit is not None and stats["processed"] >= limit:
                break
            payload = parse_payload_json(row["payload_json"] if "payload_json" in row.keys() else None)
            key = item_key(row["source"] or "", payload)
            if key and key in completed:
                stats["skipped_resume"] += 1
                continue

            text = row["text"] or ""
            source = row["source"] or ""
            label, last_raw = classify_research_with_llm(
                text,
                source=source,
                taxonomy=taxonomy,
                client=client,
                temperature=temperature,
            )
            stats["processed"] += 1

            if label is None:
                stats["invalid_json"] += 1
                _append_jsonl(
                    out_path,
                    {
                        "key": key,
                        "feedback_item_id": row["id"],
                        "status": "invalid_json",
                        "raw_tail": (last_raw or "")[-400:],
                    },
                )
                if stats["processed"] % 10 == 0:
                    conn.commit()
                continue

            if label.get("in_scope"):
                stats["kept_in_scope"] += 1
                rel_label = "retrieval_related"
                rel_conf = float(label.get("confidence") or 0.75)
            else:
                stats["moved_out_of_scope"] += 1
                rel_label = "unrelated"
                rel_conf = float(label.get("confidence") or 0.75)

            conn.execute(
                """
                UPDATE feedback_item
                SET relevance_label = ?, relevance_confidence = ?
                WHERE id = ?
                """,
                (rel_label, rel_conf, row["id"]),
            )

            conn.execute(
                "DELETE FROM classification WHERE feedback_item_id = ?",
                (row["id"],),
            )

            result = ClassificationResult(
                labels=[],
                confidence=0.0,
                rationale="",
                snippets=[],
                unclassified=True,
                provider="ollama",
            )
            result.extra = annotate_research_item(text, source=source, payload=payload)
            apply_curated_label(result, label, text, taxonomy)
            if result.extra:
                result.extra["label_source"] = "ollama_second_pass"
                result.extra["llm_rationale"] = label.get("rationale") or ""

            segments = dict(result.extra or {})
            conn.execute(
                "UPDATE feedback_item SET segments_json = ? WHERE id = ?",
                (json_dumps(segments), row["id"]),
            )

            if not result.unclassified:
                stats["classified_pain_points"] += 1
                model_run_id = log_model_run(
                    conn,
                    analysis_run_id,
                    purpose="llm_second_pass",
                    model_id=model_id,
                    prompt_version=prompt_version,
                    temperature=temperature,
                    payload_for_hash={"item_id": row["id"], "key": key, "prompt_version": prompt_version},
                    output_summary=json_dumps(
                        {
                            "in_scope": label.get("in_scope"),
                            "pain_points": result.labels,
                            "signal": segments.get("signal"),
                        }
                    ),
                )
                snippets_json = json_dumps(result.snippets)
                for node_id in result.labels:
                    conn.execute(
                        """
                        INSERT INTO classification
                          (id, feedback_item_id, taxonomy_node_id, taxonomy_version,
                           confidence, rationale, model_run_id, snippets_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(uuid.uuid4()),
                            row["id"],
                            node_id,
                            taxonomy.version,
                            result.confidence,
                            result.rationale or label.get("rationale") or "ollama_second_pass",
                            model_run_id,
                            snippets_json,
                        ),
                    )

            _append_jsonl(
                out_path,
                {
                    "key": key,
                    "feedback_item_id": row["id"],
                    "status": "ok",
                    **{k: label[k] for k in label if k != "label_source"},
                    "taxonomy_labels": result.labels,
                },
            )

            if stats["processed"] % 10 == 0:
                conn.commit()
    except InferenceUnavailable as exc:
        conn.commit()
        complete_stage_receipt(
            conn,
            analysis_run_id,
            "llm_second_pass",
            status="failed",
            item_count=stats["processed"],
            notes=str(exc),
        )
        conn.commit()
        stats["status"] = "failed"
        stats["error"] = str(exc)
        return stats

    conn.commit()

    notes = (
        f"LLM second pass: processed={stats['processed']} kept_in_scope={stats['kept_in_scope']} "
        f"out_of_scope={stats['moved_out_of_scope']} invalid_json={stats['invalid_json']}"
    )
    complete_stage_receipt(
        conn,
        analysis_run_id,
        "llm_second_pass",
        status="success",
        item_count=stats["processed"],
        notes=notes,
    )
    conn.commit()
    stats["status"] = "success"

    if reaggregate:
        from pipeline.stages.aggregate import run_aggregate

        agg = run_aggregate(conn, analysis_run_id)
        stats["aggregate"] = agg
        conn.commit()

    return stats
