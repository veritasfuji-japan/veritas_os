#!/usr/bin/env python3
"""Minimal HTTPS effect fixture for the secure real-bind PoC.

The fixture is intentionally a separate TLS socket/process. It requires a
Bearer token, records one POST effect in memory, and exposes a GET endpoint for
independent acknowledgement lookup. It is a local integration target, not a
mocked adapter call and not a public Internet service.
"""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import ssl
from threading import Lock
from urllib.parse import urlparse


class _State:
    def __init__(self, token: str) -> None:
        self.token = token
        self.lock = Lock()
        self.effects: dict[str, dict[str, object]] = {}


class _Handler(BaseHTTPRequestHandler):
    state: _State

    def _json(self, status: int, payload: dict[str, object]) -> None:
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _authorized(self) -> bool:
        return self.headers.get("Authorization", "") == f"Bearer {self.state.token}"

    def do_POST(self) -> None:  # noqa: N802
        if not self._authorized():
            self._json(401, {"error": "unauthorized"})
            return
        if self.path != "/v1/billing/effects":
            self._json(404, {"error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            external_operation_reference = str(payload["external_operation_reference"])
            authorization_id = str(payload["authorization_id"])
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            self._json(400, {"error": "invalid_payload"})
            return
        with self.state.lock:
            if external_operation_reference in self.state.effects:
                self._json(
                    409,
                    {
                        "error": "duplicate_operation",
                        "external_operation_reference": external_operation_reference,
                    },
                )
                return
            effect = {
                "external_operation_reference": external_operation_reference,
                "status": "committed",
                "source_identity": "api.example.invalid",
                "authorization_id": authorization_id,
            }
            self.state.effects[external_operation_reference] = effect
        self._json(201, effect)

    def do_GET(self) -> None:  # noqa: N802
        if not self._authorized():
            self._json(401, {"error": "unauthorized"})
            return
        parsed = urlparse(self.path)
        prefix = "/v1/billing/effects/"
        if not parsed.path.startswith(prefix):
            self._json(404, {"error": "not_found"})
            return
        external_operation_reference = parsed.path[len(prefix) :]
        with self.state.lock:
            effect = self.state.effects.get(external_operation_reference)
        if effect is None:
            self._json(
                404,
                {
                    "error": "effect_not_found",
                    "external_operation_reference": external_operation_reference,
                },
            )
            return
        self._json(200, effect)

    def log_message(self, format: str, *args: object) -> None:
        del format, args


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=443)
    parser.add_argument("--cert", required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("--token", required=True)
    args = parser.parse_args()

    _Handler.state = _State(args.token)
    server = ThreadingHTTPServer((args.host, args.port), _Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(args.cert, args.key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
