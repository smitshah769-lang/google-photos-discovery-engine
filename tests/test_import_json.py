import json
from pathlib import Path

import yaml

from pipeline.db.connection import get_connection, init_database
from pipeline.import_json import import_raw_json, load_export
from pipeline.run_context import create_analysis_run
from pipeline.taxonomy import load_taxonomy

PROJECT = Path(__file__).resolve().parent.parent
def _write_sample_export(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema": "photos-discovery-raw-v1",
                "collection_date": "2026-01-01T00:00:00Z",
                "receipts": {
                    "app_store": {"status": "success", "notes": "test"},
                    "play_store": {"status": "success", "notes": "test"},
                    "reddit": {"status": "gap", "notes": "test"},
                    "help_community": {"status": "partial", "notes": "test"},
                },
                "raw": {
                    "app_store": [
                        {
                            "native_id": "r1",
                            "text": "cannot find old photos",
                            "title": "Search",
                            "storefront": "us",
                            "authored_at": "2024-01-01",
                            "source_url": "https://example.com/r1",
                        }
                    ],
                    "play_store": [
                        {
                            "native_id": "p1",
                            "text": "search broken",
                            "authored_at": None,
                            "source_url": "https://play.google.com/",
                        }
                    ],
                    "reddit": [],
                    "help_community": [
                        {
                            "native_id": "t1",
                            "text": "how do I find screenshots",
                            "title": "Help",
                            "source_url": "https://support.google.com/photos/thread/t1/x",
                        }
                    ],
                },
            }
        )
    )


def test_import_into_sqlite(tmp_path: Path):
    json_file = tmp_path / "export.json"
    _write_sample_export(json_file)
    export = load_export(json_file)
    db = tmp_path / "import.db"
    init_database(db, load_taxonomy(), {"limitations_seed": [], "open_decisions": {}})
    run_spec = yaml.safe_load((PROJECT / "config" / "run.yaml").read_text())

    with get_connection(db) as conn:
        run_id = create_analysis_run(conn, run_spec)
        summary = import_raw_json(conn, run_id, export)
        conn.commit()
        raw_count = conn.execute("SELECT COUNT(*) FROM raw_record").fetchone()[0]

    assert summary["total"] == 3
    assert raw_count == 3
