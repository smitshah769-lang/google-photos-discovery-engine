import json
from pathlib import Path

from pipeline.adapters.app_store import parse_feed_json

FIXTURES = Path(__file__).parent / "fixtures"


def test_single_entry_object():
    data = {
        "feed": {
            "entry": {
                "id": {"label": "solo-1"},
                "im:rating": {"label": "3"},
                "title": {"label": "Find photos"},
                "content": {"label": "Search does not work for old pics"},
                "updated": {"label": "2024-01-01T00:00:00-07:00"},
            }
        }
    }
    items = parse_feed_json(data, "us")
    assert len(items) == 1
    assert items[0].native_id == "solo-1"


def test_skips_metadata_first_entry():
    data = json.loads((FIXTURES / "app_store_us_page1.json").read_text())
    items = parse_feed_json(data, "us")
    ids = [i.native_id for i in items]
    assert "app-metadata" not in ids
    assert "review-1001" in ids
    assert any("Goa" in i.text for i in items)
