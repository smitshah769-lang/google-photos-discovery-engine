from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from pipeline.paths import DEFAULT_RUN_SPEC, METHODOLOGY_TEMPLATE


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}")
    return data


def load_run_spec(path: Path | None = None) -> dict[str, Any]:
    return load_yaml(path or DEFAULT_RUN_SPEC)


def run_spec_as_json(run_spec: dict[str, Any]) -> str:
    return json.dumps(run_spec, sort_keys=True)


def load_methodology_template() -> dict[str, Any]:
    return load_yaml(METHODOLOGY_TEMPLATE)
