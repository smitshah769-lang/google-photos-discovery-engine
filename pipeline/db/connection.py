from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from pipeline.paths import SCHEMA_SQL
from pipeline.taxonomy import Taxonomy, taxonomy_nodes_for_db


def get_connection(db_file: Path) -> sqlite3.Connection:
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_file, timeout=60.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 60000")
    return conn


def init_database(
    db_file: Path,
    taxonomy: Taxonomy,
    methodology_template: dict[str, Any],
) -> None:
    schema = SCHEMA_SQL.read_text(encoding="utf-8")
    with get_connection(db_file) as conn:
        conn.executescript(schema)
        rows = taxonomy_nodes_for_db(taxonomy)
        if taxonomy.version != "research_v1":
            from pipeline.taxonomy import load_taxonomy as _load_tax

            rows = rows + taxonomy_nodes_for_db(_load_tax(version="research_v1"))
        conn.executemany(
            """
            INSERT OR REPLACE INTO taxonomy_node
              (id, taxonomy_version, name, definition, parent_id, examples_json)
            VALUES (:id, :taxonomy_version, :name, :definition, :parent_id, :examples_json)
            """,
            rows,
        )
        conn.commit()


def assert_not_frozen(conn: sqlite3.Connection, analysis_run_id: str) -> None:
    row = conn.execute(
        "SELECT status, frozen_at FROM analysis_run WHERE id = ?",
        (analysis_run_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Unknown analysis run: {analysis_run_id}")
    if row["status"] == "frozen" or row["frozen_at"]:
        raise RuntimeError(
            f"Analysis run {analysis_run_id} is frozen; start a new run_id instead."
        )


def json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)
