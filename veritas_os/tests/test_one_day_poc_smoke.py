"""Tests for one-day VERITAS PoC smoke script."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPT_PATH = Path("scripts/demo/one_day_poc_smoke.py")


def _run_script(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    run_env = os.environ.copy()
    run_env.update(env)
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        check=False,
        env=run_env,
    )


@pytest.fixture()
def api_server(monkeypatch: pytest.MonkeyPatch) -> Any:
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading

    state = {"mutation_called": False}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/v1/observability/capabilities":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                payload = {
                    "ok": True,
                    "observability": {
                        "structured_logging": {
                            "available": True,
                            "format": "json",
                            "trace_id_supported": True,
                        },
                        "tracing": {
                            "helper_available": True,
                            "opentelemetry_importable": True,
                            "exporter_configured": False,
                            "no_op_fallback": True,
                            "governance_span_chain": True,
                            "rbac_denial_events": True,
                            "rbac_denial_audit_append_visibility": True,
                        },
                        "docs": {
                            "governance_trace_span_chain_en": (
                                "docs/en/operations/governance-trace-span-chain.md"
                            ),
                            "governance_trace_span_chain_ja": (
                                "docs/ja/operations/governance-trace-span-chain.md"
                            ),
                        },
                    },
                }
                self.wfile.write(json.dumps(payload).encode("utf-8"))
                return
            if self.path == "/v1/governance/policy":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b"{}")
                return
            if self.path.startswith("/v1/governance/policy/update"):
                state["mutation_called"] = True
                self.send_response(405)
                self.end_headers()
                return
            self.send_response(404)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    try:
        yield url, state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_missing_api_key_fails_clearly() -> None:
    result = _run_script({"VERITAS_API_KEY": ""})

    assert result.returncode != 0
    assert "missing required API credentials" in result.stderr


def test_uses_x_api_key_header_only(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("one_day_poc_smoke", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    captured_headers: dict[str, str] = {}

    class DummyResponse:
        def __enter__(self) -> "DummyResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def getcode(self) -> int:
            return 200

        def read(self) -> bytes:
            return b"{}"

    def _fake_urlopen(req: Any, timeout: float) -> DummyResponse:
        del timeout
        captured_headers.update(dict(req.header_items()))
        return DummyResponse()

    monkeypatch.setattr(module.request, "urlopen", _fake_urlopen)

    status, _payload = module._http_get_json(
        "http://127.0.0.1:8000",
        "/v1/observability/capabilities",
        "key-for-test",
    )

    assert status == 200
    lowered = {k.lower(): v for k, v in captured_headers.items()}
    assert lowered.get("x-api-key") == "key-for-test"
    assert "authorization" not in lowered


def test_script_does_not_print_api_key(api_server: Any) -> None:
    base_url, _ = api_server
    result = _run_script(
        {"VERITAS_API_KEY": "super-secret-key", "VERITAS_BASE_URL": base_url},
        "--json",
    )

    assert result.returncode == 0
    assert "super-secret-key" not in result.stdout
    assert "super-secret-key" not in result.stderr


def test_capabilities_response_is_summarized(api_server: Any) -> None:
    base_url, _ = api_server
    result = _run_script(
        {"VERITAS_API_KEY": "test-key", "VERITAS_BASE_URL": base_url},
        "--json",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["capabilities_ok"] is True
    assert payload["observability"]["structured_logging_format"] == "json"
    assert payload["observability"]["opentelemetry_importable"] is True
    assert payload["observability"]["exporter_configured"] is False
    assert payload["observability"]["governance_span_chain"] is True
    assert payload["observability"]["rbac_denial_audit_append_visibility"] is True


def test_unexpected_exporter_endpoint_raw_value_is_not_printed(api_server: Any) -> None:
    base_url, _ = api_server
    result = _run_script(
        {"VERITAS_API_KEY": "test-key", "VERITAS_BASE_URL": base_url},
        "--json",
    )

    assert result.returncode == 0
    assert "secret-exporter" not in result.stdout


def test_fixture_does_not_expose_exporter_endpoint_field(api_server: Any) -> None:
    base_url, _ = api_server
    result = _run_script(
        {"VERITAS_API_KEY": "test-key", "VERITAS_BASE_URL": base_url},
        "--json",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert "exporter_endpoint" not in payload["observability"]


def test_non_200_capabilities_fails_nonzero() -> None:
    result = _run_script(
        {
            "VERITAS_API_KEY": "test-key",
            "VERITAS_BASE_URL": "http://127.0.0.1:9",
        },
        "--json",
    )

    assert result.returncode != 0


def test_default_mode_does_not_call_mutation_endpoints(api_server: Any) -> None:
    base_url, state = api_server
    result = _run_script(
        {"VERITAS_API_KEY": "test-key", "VERITAS_BASE_URL": base_url},
        "--json",
    )

    assert result.returncode == 0
    assert state["mutation_called"] is False
