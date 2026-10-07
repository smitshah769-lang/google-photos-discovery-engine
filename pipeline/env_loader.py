from __future__ import annotations

from pathlib import Path

from pipeline.paths import PROJECT_ROOT


def load_project_env() -> None:
    """Load .env from project root if python-dotenv is installed."""
    env_file = PROJECT_ROOT / ".env"
    if not env_file.is_file():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(env_file, override=False)
