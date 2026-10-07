"""Optional HTTP basic auth and bind-host warnings (edge cases §13)."""

from __future__ import annotations

import base64
import os
from typing import Any


WILDCARD_HOSTS = frozenset({"0.0.0.0", "::", "[::]"})


def serving_credentials(run_spec: dict[str, Any] | None) -> tuple[str, str] | None:
    """Return (user, password) when basic auth is configured via env or run spec."""
    env_user = (os.environ.get("DISCOVERY_BASIC_USER") or "").strip()
    env_password = os.environ.get("DISCOVERY_BASIC_PASSWORD")
    if env_user and env_password is not None and env_password != "":
        return env_user, env_password

    serving = (run_spec or {}).get("serving") or {}
    auth = serving.get("auth")
    if not isinstance(auth, dict):
        return None
    if not auth.get("enabled"):
        return None
    user = str(auth.get("user") or "").strip()
    password = auth.get("password")
    if user and password is not None and str(password) != "":
        return user, str(password)
    return None


def bind_without_auth_warning(host: str, credentials: tuple[str, str] | None) -> str | None:
    if host in WILDCARD_HOSTS and not credentials:
        return (
            "Warning: binding 0.0.0.0 (or ::) without HTTP basic auth exposes the research "
            "API. Prefer 127.0.0.1, or set DISCOVERY_BASIC_USER / DISCOVERY_BASIC_PASSWORD."
        )
    return None


def authorized_basic(header: str | None, credentials: tuple[str, str] | None) -> bool:
    if credentials is None:
        return True
    if not header or not header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(header[6:].strip()).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return False
    user, sep, password = decoded.partition(":")
    if not sep:
        return False
    return user == credentials[0] and password == credentials[1]
