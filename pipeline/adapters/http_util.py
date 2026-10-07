from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.request
from typing import Any

import certifi


class HttpError(RuntimeError):
    pass


def fetch_text(
    url: str,
    *,
    method: str = "GET",
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
    max_retries: int = 3,
) -> str:
    hdrs = {"User-Agent": "PhotosDiscoveryEngine/0.1 (research; public data only)"}
    if headers:
        hdrs.update(headers)
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
            ctx = ssl.create_default_context(cafile=certifi.where())
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                charset = resp.headers.get_content_charset() or "utf-8"
                return resp.read().decode(charset, errors="replace")
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code == 429 and attempt < max_retries - 1:
                time.sleep(2 ** (attempt + 1))
                continue
            raise HttpError(f"HTTP {exc.code} for {url}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            if attempt < max_retries - 1:
                time.sleep(1 + attempt)
                continue
            raise HttpError(f"Request failed for {url}: {exc}") from exc
    raise HttpError(f"Request failed for {url}: {last_error}")


def fetch_json(url: str, **kwargs: Any) -> Any:
    return json.loads(fetch_text(url, **kwargs))
