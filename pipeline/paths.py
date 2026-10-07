from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
DEFAULT_RUN_SPEC = CONFIG_DIR / "run.yaml"
DEFAULT_TAXONOMY = CONFIG_DIR / "taxonomy_v0.yaml"
METHODOLOGY_TEMPLATE = CONFIG_DIR / "methodology_template.yaml"
SCHEMA_SQL = Path(__file__).resolve().parent / "db" / "schema.sql"


def taxonomy_path_for_version(version: str) -> Path:
    version = (version or "v0").strip()
    candidate = CONFIG_DIR / f"taxonomy_{version}.yaml"
    if candidate.is_file():
        return candidate
    return DEFAULT_TAXONOMY


def resolve_data_dir(run_spec: dict) -> Path:
    paths = run_spec.get("paths") or {}
    rel = paths.get("data_dir", "data")
    path = Path(rel)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path(run_spec: dict) -> Path:
    paths = run_spec.get("paths") or {}
    data_dir = resolve_data_dir(run_spec)
    return data_dir / paths.get("db_filename", "snapshot.db")
