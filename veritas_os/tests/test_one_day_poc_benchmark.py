"""Tests for one-day VERITAS PoC benchmark script."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPT_PATH = Path("scripts/demo/one_day_poc_benchmark.py")


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
def api_server() -> Any:
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading

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
                            "opentelemetry_importable": True,
                            "exporter_configured": False,
                            "governance_span_chain": True,
                            "rbac_denial_audit_append_visibility": True,
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
            self.send_response(404)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    try:
        yield url
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_percentile_helper() -> None:
    from scripts.demo import one_day_poc_benchmark as target

    assert target._percentile([], 95) == 0.0
    assert target._percentile([42.0], 50) == 42.0
    assert target._percentile([1.0, 2.0, 3.0, 4.0, 5.0], 50) == 3.0
    assert target._percentile([1.0, 2.0, 3.0, 4.0, 5.0], 95) == 5.0
    assert target._percentile([1.0, 2.0, 3.0, 4.0, 5.0], 99) == 5.0


def test_summarize_timings() -> None:
    from scripts.demo import one_day_poc_benchmark as target

    summary = target._summarize_timings([10.0, 20.0, 30.0], success_count=3, failure_count=0)
    assert summary["min_ms"] == 10.0
    assert summary["p50_ms"] == 20.0
    assert summary["p95_ms"] == 30.0
    assert summary["p99_ms"] == 30.0
    assert summary["max_ms"] == 30.0
    assert summary["mean_ms"] == pytest.approx(20.0)
    assert summary["stdev_ms"] > 0.0


def test_json_output_parseable_and_status_in_stderr(api_server: Any, tmp_path: Path) -> None:
    output_path = tmp_path / "bench.json"
    result = _run_script(
        {"VERITAS_API_KEY": "test-key", "VERITAS_BASE_URL": api_server},
        "--json",
        "--out-json",
        str(output_path),
    )
    assert result.returncode == 0
    json.loads(result.stdout)
    assert "Wrote sanitized benchmark JSON" in result.stderr


def test_smoke_equivalent_success(api_server: Any) -> None:
    result = _run_script(
        {"VERITAS_API_KEY": "test-key", "VERITAS_BASE_URL": api_server},
        "--json",
        "--runs",
        "1",
        "--warmup",
        "0",
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    row = payload["benchmarks"]["smoke_equivalent_end_to_end"]
    assert row["success_count"] == 1
    assert row["failure_count"] == 0


def test_unreachable_counts_as_failure() -> None:
    result = _run_script(
        {"VERITAS_API_KEY": "test-key", "VERITAS_BASE_URL": "http://127.0.0.1:9"},
        "--json",
        "--runs",
        "1",
        "--warmup",
        "0",
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    row = payload["benchmarks"]["observability_capabilities"]
    assert row["failure_count"] > 0
    assert row["success_count"] == 0


def test_secret_safety(api_server: Any, tmp_path: Path) -> None:
    out_json = tmp_path / "bench.json"
    out_md = tmp_path / "bench.md"
    secret = "super-secret-key"
    result = _run_script(
        {"VERITAS_API_KEY": secret, "VERITAS_BASE_URL": api_server},
        "--json",
        "--out-json",
        str(out_json),
        "--out-md",
        str(out_md),
    )
    assert result.returncode == 0
    for body in [
        result.stdout,
        result.stderr,
        out_json.read_text("utf-8"),
        out_md.read_text("utf-8"),
    ]:
        assert secret not in body


def test_out_json_sanitized_packet(api_server: Any, tmp_path: Path) -> None:
    out_json = tmp_path / "bench.json"
    result = _run_script(
        {"VERITAS_API_KEY": "test-key", "VERITAS_BASE_URL": api_server},
        "--json",
        "--out-json",
        str(out_json),
    )
    assert result.returncode == 0
    payload = json.loads(out_json.read_text("utf-8"))
    assert payload["schema_version"] == "one_day_poc_benchmark.v1"
    assert "test-key" not in out_json.read_text("utf-8")


def test_out_md_written(api_server: Any, tmp_path: Path) -> None:
    out_md = tmp_path / "bench.md"
    result = _run_script(
        {"VERITAS_API_KEY": "test-key", "VERITAS_BASE_URL": api_server},
        "--out-md",
        str(out_md),
    )
    assert result.returncode == 0
    body = out_md.read_text("utf-8")
    assert "One-Day PoC Performance Benchmark" in body
    assert "test-key" not in body


def test_write_failure_is_sanitized_nonzero(api_server: Any, tmp_path: Path) -> None:
    out_json = tmp_path / "missing" / "bench.json"
    result = _run_script(
        {"VERITAS_API_KEY": "test-key", "VERITAS_BASE_URL": api_server},
        "--json",
        "--out-json",
        str(out_json),
    )
    assert result.returncode != 0
    assert "ERROR: failed to write benchmark JSON" in result.stderr
    assert "Traceback" not in result.stderr


def test_status_lines_always_stderr(api_server: Any, tmp_path: Path) -> None:
    out_json = tmp_path / "bench.json"
    out_md = tmp_path / "bench.md"
    result = _run_script(
        {"VERITAS_API_KEY": "test-key", "VERITAS_BASE_URL": api_server},
        "--out-json",
        str(out_json),
        "--out-md",
        str(out_md),
    )
    assert result.returncode == 0
    assert result.stdout.startswith("# One-Day PoC Performance Benchmark")
    assert "Wrote sanitized benchmark" not in result.stdout
    assert "Wrote sanitized benchmark" in result.stderr


def test_timeout_argument_applied(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.demo import one_day_poc_benchmark as target

    captured: dict[str, float] = {}

    def _fake_urlopen(req: Any, timeout: float) -> Any:
        captured["timeout"] = timeout
        raise TimeoutError

    monkeypatch.setattr(target.request, "urlopen", _fake_urlopen)
    status, payload = target._http_get_json_with_timeout(
        "http://127.0.0.1:8000", "/v1/observability/capabilities", "key", timeout=0.25
    )
    assert status == 0
    assert payload == {"error": "timeout"}
    assert captured["timeout"] == 0.25


@pytest.mark.parametrize(
    "args",
    [("--runs", "0"), ("--runs", "51"), ("--warmup", "-1"), ("--warmup", "11")],
)
def test_runs_validation(args: tuple[str, str]) -> None:
    result = _run_script({"VERITAS_API_KEY": "test-key"}, *args)
    assert result.returncode != 0
