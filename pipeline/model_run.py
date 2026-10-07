from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from typing import Any

from pipeline.run_context import utc_now_iso


def input_hash(payload: Any) -> str:
    normalized = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(normalized.encode()).hexdigest()


def log_model_run(
    conn: sqlite3.Connection,
    analysis_run_id: str,
    *,
    purpose: str,
    model_id: str,
    prompt_version: str | None,
    temperature: float | None,
    payload_for_hash: Any,
    output_summary: str | None = None,
) -> str:
    run_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO model_run
          (id, analysis_run_id, purpose, prompt_version, model_id, temperature,
           input_hash, created_at, output_summary)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            analysis_run_id,
            purpose,
            prompt_version,
            model_id,
            temperature,
            input_hash(payload_for_hash),
            utc_now_iso(),
            output_summary,
        ),
    )
    return run_id
