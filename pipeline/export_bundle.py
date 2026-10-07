"""Versioned freeze export, including redaction for sharing outside the research team."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from pipeline.db.connection import get_connection, json_dumps
from pipeline.db.repository import load_run_spec
from pipeline.handoff import handoff_payload, write_handoff_files
from pipeline.paths import PROJECT_ROOT, db_path, resolve_data_dir
from pipeline.rag.store import index_path_for_run
from pipeline.serve.read import methodology, quality


AUTHOR_KEYS = {
    "author",
    "author_name",
    "authorname",
    "username",
    "user",
    "display_name",
    "displayname",
    "author_handle",
    "authorhandle",
    "im:name",
    "reviewer",
}


def redact_obj(value: Any) -> Any:
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k.lower() in AUTHOR_KEYS:
                out[k] = "[redacted]"
            else:
                out[k] = redact_obj(v)
        return out
    if isinstance(value, list):
        return [redact_obj(v) for v in value]
    return value


def overlay_export_run_spec(run_spec: dict[str, Any], export_dir: Path) -> dict[str, Any]:
    spec = dict(run_spec)
    paths = dict(spec.get("paths") or {})
    paths["data_dir"] = str(export_dir)
    paths["db_filename"] = "snapshot.db"
    spec["paths"] = paths
    return spec


def _copy_prompts(dest: Path) -> None:
    src = PROJECT_ROOT / "config" / "prompts"
    if src.is_dir():
        shutil.copytree(src, dest / "prompts", dirs_exist_ok=True)


def _copy_config_files(dest: Path) -> None:
    for name in ("run.yaml", "taxonomy_v0.yaml", "gold_set.json", "methodology_template.yaml"):
        src = PROJECT_ROOT / "config" / name
        if src.is_file():
            shutil.copy2(src, dest / name)


def _redact_thread_context(raw: str | None) -> str | None:
    if not raw:
        return raw
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    return json_dumps(redact_obj(parsed))


def redact_export_db(dest_db: Path) -> None:
    with get_connection(dest_db) as conn:
        conn.execute("UPDATE feedback_item SET redaction_flag = 1")
        for row in conn.execute("SELECT id, thread_context FROM feedback_item").fetchall():
            redacted = _redact_thread_context(row["thread_context"])
            if redacted != row["thread_context"]:
                conn.execute(
                    "UPDATE feedback_item SET thread_context = ? WHERE id = ?",
                    (redacted, row["id"]),
                )
        for raw in conn.execute("SELECT id, payload_json FROM raw_record").fetchall():
            if not raw["payload_json"]:
                continue
            try:
                payload = json.loads(raw["payload_json"])
            except json.JSONDecodeError:
                continue
            conn.execute(
                "UPDATE raw_record SET payload_json = ? WHERE id = ?",
                (json_dumps(redact_obj(payload)), raw["id"]),
            )
        conn.commit()


def _copy_spilled_payloads(dest_db: Path, export_dir: Path, *, redact: bool) -> None:
    raw_dest = export_dir / "raw"
    with get_connection(dest_db) as conn:
        rows = conn.execute("SELECT id, payload_path FROM raw_record").fetchall()
        for row in rows:
            path_val = row["payload_path"]
            if not path_val:
                continue
            src = Path(path_val)
            if not src.is_file():
                continue
            raw_dest.mkdir(parents=True, exist_ok=True)
            dest = raw_dest / src.name
            try:
                payload = json.loads(src.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                shutil.copy2(src, dest)
            else:
                if redact:
                    payload = redact_obj(payload)
                dest.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
            conn.execute(
                "UPDATE raw_record SET payload_path = ? WHERE id = ?",
                (str(dest), row["id"]),
            )
        conn.commit()


def write_export_bundle(
    conn,
    analysis_run_id: str,
    *,
    redact: bool = False,
    frozen_at: str | None = None,
) -> dict[str, Any]:
    spec = load_run_spec(conn, analysis_run_id)
    data_dir = resolve_data_dir(spec)
    export_dir = data_dir / "exports" / analysis_run_id
    export_dir.mkdir(parents=True, exist_ok=True)

    src_db = db_path(spec)
    dest_db = export_dir / "snapshot.db"
    shutil.copy2(src_db, dest_db)
    _copy_spilled_payloads(dest_db, export_dir, redact=redact)
    if redact:
        redact_export_db(dest_db)

    index_src = index_path_for_run(data_dir, analysis_run_id)
    if index_src.is_file():
        rag_dest = export_dir / "rag"
        rag_dest.mkdir(exist_ok=True)
        shutil.copy2(index_src, rag_dest / index_src.name)

    _copy_prompts(export_dir)
    _copy_config_files(export_dir)

    method = methodology(conn, analysis_run_id)
    quality_payload = quality(conn, analysis_run_id)
    (export_dir / "receipts.json").write_text(
        json.dumps(
            {
                "source_runs": method["source_receipts"],
                "quality": quality_payload,
                "frozen_at": frozen_at,
                "redacted": redact,
            },
            indent=2,
            default=str,
        )
    )
    (export_dir / "methodology.json").write_text(json.dumps(method, indent=2, default=str))
    (export_dir / "FREEZE.json").write_text(
        json.dumps(
            {
                "run_id": analysis_run_id,
                "frozen_at": frozen_at,
                "redacted": redact,
                "immutable": True,
            },
            indent=2,
        )
    )
    write_handoff_files(export_dir, handoff_payload(conn, analysis_run_id))
    return {
        "export_dir": str(export_dir),
        "redacted": redact,
        "frozen_at": frozen_at,
        "run_id": analysis_run_id,
    }
