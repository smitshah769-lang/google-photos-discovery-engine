"""Backward-compatible alias for Phase 3 serve-search."""

from pipeline.serve.http import DiscoveryHTTPHandler, serve_api

SearchHTTPHandler = DiscoveryHTTPHandler
serve_search = serve_api
