"""Read-only HTTP API for the frozen research snapshot."""

from __future__ import annotations

__all__ = ["DiscoveryHTTPHandler", "serve_api", "serve_search"]


def __getattr__(name: str):
    if name in {"DiscoveryHTTPHandler", "serve_api", "serve_search"}:
        from pipeline.serve.http import DiscoveryHTTPHandler, serve_api

        mapping = {
            "DiscoveryHTTPHandler": DiscoveryHTTPHandler,
            "serve_api": serve_api,
            "serve_search": serve_api,
        }
        return mapping[name]
    raise AttributeError(name)
