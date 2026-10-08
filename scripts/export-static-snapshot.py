#!/usr/bin/env python3
"""Write the frozen read-API JSON the Next.js app serves without the Python API."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from pipeline.db.connection import get_connection
from pipeline.handoff import handoff_payload
from pipeline.rag.quotes import expand_to_sentence_boundary
from pipeline.serve.read import (
    _json_obj,
    _relevant_items,
    categories,
    chrome,
    get_item,
    insights,
    methodology,
    quality,
)

RUN_ID = "4ad39133-1e6c-4146-99a0-7d68dfe72020"
ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "snapshot.db"
INDEX = ROOT / "data" / "rag" / f"{RUN_ID}.json"
OUT = ROOT / "app" / "snapshot"


def dump(name: str, payload: object) -> None:
    path = OUT / name
    path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    print(f"{name} {path.stat().st_size}")


def main() -> None:
    if not DB.is_file():
        raise SystemExit(f"Missing database: {DB}")
    if not INDEX.is_file():
        raise SystemExit(f"Missing vector index: {INDEX}")
    OUT.mkdir(parents=True, exist_ok=True)
    conn = get_connection(DB)
    try:
        dump("chrome.json", chrome(conn, RUN_ID))
        dump("insights.json", insights(conn, RUN_ID))
        dump("categories.json", categories(conn, RUN_ID))
        dump("methodology.json", methodology(conn, RUN_ID))
        dump("quality.json", quality(conn, RUN_ID))
        dump("handoff.json", handoff_payload(conn, RUN_ID))
        items: dict[str, object] = {}
        corpus: list[dict[str, object]] = []
        for row in _relevant_items(conn, RUN_ID):
            item = get_item(conn, RUN_ID, row["id"])
            if item is None:
                continue
            items[row["id"]] = item
            text = row["text"] or ""
            corpus.append(
                {
                    "id": row["id"],
                    "source": row["source"],
                    "source_url": row["source_url"],
                    "authored_at": row["authored_at"],
                    "snippet": expand_to_sentence_boundary(text, text[:160]),
                    "segments": _json_obj(row["segments_json"]),
                    "taxonomy_node_ids": [
                        c["taxonomy_node_id"] for c in item.get("classifications") or []
                    ],
                }
            )
        dump("items.json", items)
        dump("corpus.json", corpus)
    finally:
        conn.close()
    dest = OUT / "index.json"
    shutil.copyfile(INDEX, dest)
    print(f"index.json {dest.stat().st_size}")


if __name__ == "__main__":
    main()
