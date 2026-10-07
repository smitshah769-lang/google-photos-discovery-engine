from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from pipeline.db.connection import get_connection
from pipeline.handoff import handoff_payload
from pipeline.paths import db_path
from pipeline.serve import read as read_api
from pipeline.serve.auth import authorized_basic, bind_without_auth_warning, serving_credentials


class DiscoveryHTTPHandler(BaseHTTPRequestHandler):
    """Read-only Phase 4/5 API (architecture §8)."""

    run_spec: dict[str, Any]
    analysis_run_id: str

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        if args and str(args[0]).startswith("POST"):
            return
        super().log_message(format, *args)

    def _require_auth(self) -> bool:
        creds = serving_credentials(self.run_spec)
        if authorized_basic(self.headers.get("Authorization"), creds):
            return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="discovery-snapshot"')
        self.send_header("Content-Type", "application/json")
        self._cors()
        body = json.dumps({"error": "unauthorized"}).encode("utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return False

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if not self._require_auth():
            return
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        qs = read_api.parse_query(parsed.query)
        try:
            payload, code = self._dispatch_get(path, qs)
        except ValueError as exc:
            self._json_response(404, {"error": str(exc)})
            return
        self._json_response(code, payload)

    def do_POST(self) -> None:  # noqa: N802
        if not self._require_auth():
            return
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path != "/search":
            self._json_response(404, {"error": "not_found"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            body = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            self._json_response(400, {"error": "invalid_json"})
            return
        if not isinstance(body, dict):
            self._json_response(400, {"error": "invalid_json"})
            return
        try:
            db_file = db_path(self.run_spec)
            with get_connection(db_file) as conn:
                payload = read_api.search_payload(
                    conn, self.analysis_run_id, body, run_spec=self.run_spec
                )
        except Exception as exc:  # noqa: BLE001 — keep API JSON for unexpected search failures
            self._json_response(500, {"error": "search_failed", "detail": str(exc)})
            return
        self._json_response(200, payload)

    def _dispatch_get(self, path: str, qs: dict[str, str]) -> tuple[dict[str, Any], int]:
        db_file = db_path(self.run_spec)
        with get_connection(db_file) as conn:
            run_id = self.analysis_run_id
            if path in ("/insights",):
                return read_api.insights(conn, run_id), 200
            if path in ("/categories",):
                return read_api.categories(conn, run_id), 200
            if path in ("/methodology",):
                return read_api.methodology(conn, run_id), 200
            if path in ("/quality",):
                return read_api.quality(conn, run_id), 200
            if path in ("/handoff",):
                return handoff_payload(conn, run_id), 200
            if path in ("/chrome",):
                return read_api.chrome(conn, run_id), 200
            if path in ("/evidence",):
                return (
                    read_api.evidence(
                        conn,
                        run_id,
                        kind=qs.get("kind") or "",
                        taxonomy_node_id=qs.get("taxonomy_node_id") or None,
                        source=qs.get("source") or None,
                        overlay=qs.get("overlay") or None,
                        segment_key=qs.get("segment_key") or None,
                        segment_value=qs.get("segment_value") or None,
                        sentiment=qs.get("sentiment") or None,
                        signal=qs.get("signal") or None,
                        search_type=qs.get("search_type") or None,
                    ),
                    200,
                )
            if path.startswith("/items/"):
                item_id = path.split("/items/", 1)[-1]
                item = read_api.get_item(conn, run_id, item_id)
                if item is None:
                    return {"error": "not_found"}, 404
                return item, 200
        return {"error": "not_found"}, 404

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def _json_response(self, code: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self._cors()
        self.end_headers()
        self.wfile.write(data)


def serve_api(
    run_spec: dict[str, Any],
    analysis_run_id: str,
    *,
    host: str,
    port: int,
) -> None:
    creds = serving_credentials(run_spec)
    warning = bind_without_auth_warning(host, creds)
    if warning:
        print(warning, flush=True)
    auth_note = "basic auth on" if creds else "no auth (localhost-safe default)"
    handler = type(
        "BoundDiscoveryHTTPHandler",
        (DiscoveryHTTPHandler,),
        {"run_spec": run_spec, "analysis_run_id": analysis_run_id},
    )
    server = ThreadingHTTPServer((host, port), handler)
    print(
        f"Read-only API http://{host}:{port} "
        f"(run_id={analysis_run_id}; {auth_note}) "
        "GET /insights /categories /methodology /quality /handoff /items/:id POST /search",
        flush=True,
    )
    server.serve_forever()
