from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def spill_payload(data_dir: Path, source: str, source_native_id: str, payload: Any) -> Path:
    """Write large raw payloads under data/raw/ (edge case: SQLite row spill)."""
    raw_dir = data_dir / "raw" / source
    raw_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(source_native_id.encode()).hexdigest()[:16]
    path = raw_dir / f"{digest}.json"
    path.write_text(json.dumps(payload, default=str), encoding="utf-8")
    return path
