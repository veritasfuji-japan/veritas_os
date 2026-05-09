#!/usr/bin/env python3
"""Lightweight local benchmark for one-day VERITAS PoC checks."""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import socket
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib import error, request

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.demo import one_day_poc_shared

SCHEMA_VERSION = "one_day_poc_benchmark.v1"
PACKET_TYPE = "performance_benchmark"
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_TIMEOUT_SECONDS = 10.0


class BenchmarkRequestError(RuntimeError):
    """Raised when a benchmark request does not satisfy target constraints."""


def _emit_status(message: str, *, json_output: bool = False, error_output: bool = False) -> None:
    del json_output, error_output
    print(message, file=sys.stderr)


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(
        len(ordered) - 1,
        max(0, math.ceil((percentile / 100.0) * len(ordered)) - 1),
    )
    return ordered[idx]


def _summarize_timings(
    values: list[float], success_count: int, failure_count: int
) -> dict[str, float | int]:
    if not values:
        return {
            "success_count": success_count,
            "failure_count": failure_count,
            "min_ms": 0.0,
            "p50_ms": 0.0,
            "p95_ms": 0.0,
            "p99_ms": 0.0,
            "max_ms": 0.0,
            "mean_ms": 0.0,
            "stdev_ms": 0.0,
        }
    return {
        "success_count": success_count,
        "failure_count": failure_count,
        "min_ms": min(values),
        "p50_ms": _percentile(values, 50),
        "p95_ms": _percentile(values, 95),
        "p99_ms": _percentile(values, 99),
        "max_ms": max(values),
        "mean_ms": statistics.mean(values),
        "stdev_ms": statistics.stdev(values) if len(values) > 1 else 0.0,
    }


def _redact_message(message: str) -> str:
    api_key = os.getenv("VERITAS_API_KEY", "")
    if api_key:
        return message.replace(api_key, "[REDACTED]")
    return message


def _http_get_json_with_timeout(
    base_url: str,
    path: str,
    api_key: str,
    *,
    timeout: float,
) -> tuple[int, dict[str, Any]]:
    """Perform a GET request with timeout and sanitized error payloads."""
    url = f"{base_url.rstrip('/')}{path}"
    req = request.Request(url=url, method="GET")
    req.add_header("X-API-Key", api_key)
    req.add_header("Accept", "application/json")

    try:
        with request.urlopen(req, timeout=timeout) as response:
            status = response.getcode()
            body = response.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        return exc.code, {"error": "http_error"}
    except TimeoutError:
        return 0, {"error": "timeout"}
    except socket.timeout:
        return 0, {"error": "timeout"}
    except error.URLError as exc:
        reason = getattr(exc, "reason", None)
        if isinstance(reason, (TimeoutError, socket.timeout)):
            return 0, {"error": "timeout"}
        if "timed out" in str(reason).lower():
            return 0, {"error": "timeout"}
        return 0, {"error": "url_error"}

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return status, {"error": "invalid_json"}

    if not isinstance(payload, dict):
        return status, {"error": "non_object_json"}
    return status, payload


def _checked_http_get_json(
    base_url: str,
    path: str,
    api_key: str,
    *,
    timeout: float,
    allowed_statuses: set[int] | None = None,
    require_ok: bool = False,
) -> tuple[int, dict[str, Any]]:
    """Get JSON with target-specific status/body validation."""
    status, payload = _http_get_json_with_timeout(
        base_url,
        path,
        api_key,
        timeout=timeout,
    )
    allowed = allowed_statuses or {200}
    if status not in allowed:
        raise BenchmarkRequestError(f"{path} returned status {status}")
    if not isinstance(payload, dict):
        raise BenchmarkRequestError(f"{path} returned non-object JSON")
    if require_ok and payload.get("ok") is not True:
        raise BenchmarkRequestError(f"{path} returned ok!=true")
    if status == 0 and payload.get("error"):
        raise BenchmarkRequestError(f"{path} request failed")
    if payload.get("error") in {"invalid_json", "non_object_json"}:
        raise BenchmarkRequestError(f"{path} returned invalid JSON payload")
    return status, payload


def _run_target(
    runs: int,
    warmup: int,
    target: Callable[[], None],
) -> tuple[dict[str, float | int], list[dict[str, str]]]:
    for _ in range(warmup):
        try:
            target()
        except Exception:
            pass

    timings: list[float] = []
    failures: list[dict[str, str]] = []
    success = 0
    for _ in range(runs):
        started = time.perf_counter()
        try:
            target()
            timings.append((time.perf_counter() - started) * 1000.0)
            success += 1
        except Exception as exc:
            failures.append(
                {
                    "type": exc.__class__.__name__,
                    "message": _redact_message(str(exc))[:200],
                }
            )
    return _summarize_timings(timings, success, runs - success), failures


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="One-day VERITAS PoC benchmark")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument(
        "--base-url", default=os.getenv("VERITAS_BASE_URL", DEFAULT_BASE_URL)
    )
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--scenario", default="one_day_poc", choices=["one_day_poc"])
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--out-json")
    parser.add_argument("--out-md")
    return parser


def _build_markdown(packet: dict[str, Any]) -> str:
    benchmarks = packet["benchmarks"]
    lines = [
        "# One-Day PoC Performance Benchmark",
        "",
        "## Summary",
        "Local benchmark for lightweight PoC latency checks.",
        "Packet generation succeeds with exit code 0 even when request failures are recorded.",
        "",
        "## Environment",
        f"- Measured at: {packet['measured_at']}",
        f"- Python: {packet['environment']['python_version']}",
        f"- Platform: {packet['environment']['platform']}",
        f"- Base URL: {packet['environment']['base_url']}",
        "",
        "## Benchmark Results",
        "| Target | Runs | Success | Failure | p50 ms | p95 ms | p99 ms | Mean ms | Max ms |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in [
        "observability_capabilities",
        "governance_policy_read",
        "smoke_equivalent_end_to_end",
    ]:
        row = benchmarks[name]
        lines.append(
            f"| {name} | {packet['runs']} | {row['success_count']} | "
            f"{row['failure_count']} | {row['p50_ms']:.2f} | {row['p95_ms']:.2f} | "
            f"{row['p99_ms']:.2f} | {row['mean_ms']:.2f} | {row['max_ms']:.2f} |"
        )
    lines.extend(
        [
            "",
            "## Methodology",
            "- Repeats endpoint checks and a smoke-equivalent flow.",
            "- Uses request timeout from `--timeout` for each HTTP call.",
            "",
            "## Limitations",
            "- Local benchmark only; not a production SLA.",
            "- Not a customer environment measurement.",
            "- Not third-party certified.",
            "- Network, model provider latency, and deployment topology may change results.",
            "- Does not measure external LLM/provider latency unless the configured local server explicitly invokes such providers.",
            "- This benchmark does not certify EU AI Act compliance.",
            "",
            "## What this does not prove",
            "- Not throughput testing.",
            "- Not legal certification.",
            "",
            "## Recommended next measurements",
            "- Controlled staging environment measurements.",
            "- Load, concurrency, and tail-latency analysis.",
        ]
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if not 1 <= args.runs <= 50:
        _emit_status("--runs must be between 1 and 50")
        return 2
    if not 0 <= args.warmup <= 10:
        _emit_status("--warmup must be between 0 and 10")
        return 2
    if not 0 < args.timeout <= 120:
        _emit_status("--timeout must be greater than 0 and at most 120")
        return 2

    api_key = os.getenv("VERITAS_API_KEY", "").strip()
    if not api_key:
        _emit_status("missing required API credentials: set VERITAS_API_KEY")
        return 2

    def _obs() -> None:
        _checked_http_get_json(
            args.base_url,
            "/v1/observability/capabilities",
            api_key,
            timeout=args.timeout,
            require_ok=True,
        )

    def _policy() -> None:
        _checked_http_get_json(
            args.base_url,
            "/v1/governance/policy",
            api_key,
            timeout=args.timeout,
            allowed_statuses={200, 401, 403},
        )

    def _smoke_equivalent() -> None:
        status, obs_payload = _checked_http_get_json(
            args.base_url,
            "/v1/observability/capabilities",
            api_key,
            timeout=args.timeout,
            require_ok=True,
        )
        observability_summary = one_day_poc_shared.extract_observability_summary(obs_payload)
        policy_status, _policy_payload = _checked_http_get_json(
            args.base_url,
            "/v1/governance/policy",
            api_key,
            timeout=args.timeout,
            allowed_statuses={200, 401, 403},
        )
        capabilities_ok = status == 200 and bool(obs_payload.get("ok", True))
        warnings: list[str] = []
        one_day_poc_shared.build_evidence_packet(
            observability=observability_summary,
            capabilities_status=status,
            capabilities_ok=capabilities_ok,
            policy_status=policy_status,
            warnings=warnings,
        )

    obs, obs_failures = _run_target(args.runs, args.warmup, _obs)
    policy, policy_failures = _run_target(args.runs, args.warmup, _policy)
    e2e, e2e_failures = _run_target(args.runs, args.warmup, _smoke_equivalent)

    packet: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "packet_type": PACKET_TYPE,
        "scenario": args.scenario,
        "measured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "runs": args.runs,
        "warmup": args.warmup,
        "timeout_seconds": args.timeout,
        "environment": {
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "base_url": "redacted-local-or-configured",
        },
        "benchmarks": {
            "observability_capabilities": obs,
            "governance_policy_read": policy,
            "smoke_equivalent_end_to_end": e2e,
        },
        "failures": {
            "observability_capabilities": obs_failures,
            "governance_policy_read": policy_failures,
            "smoke_equivalent_end_to_end": e2e_failures,
        },
        "limitations": [
            "Local benchmark only; not a production SLA.",
            "Not a customer environment measurement.",
            "Not third-party certified.",
            "Network, model provider latency, and deployment topology may change results.",
            "Does not measure external LLM/provider latency unless the configured local server explicitly invokes such providers.",
            "This benchmark does not certify EU AI Act compliance.",
        ],
    }

    if args.out_json:
        try:
            Path(args.out_json).write_text(
                json.dumps(packet, indent=2) + "\n", encoding="utf-8"
            )
        except OSError as exc:
            _emit_status(
                f"ERROR: failed to write benchmark JSON: {_redact_message(str(exc))}"
            )
            return 3
        _emit_status(f"Wrote sanitized benchmark JSON: {args.out_json}")

    if args.out_md:
        try:
            Path(args.out_md).write_text(_build_markdown(packet), encoding="utf-8")
        except OSError as exc:
            _emit_status(
                f"ERROR: failed to write benchmark Markdown: {_redact_message(str(exc))}"
            )
            return 3
        _emit_status(f"Wrote sanitized benchmark Markdown: {args.out_md}")

    if args.json:
        print(json.dumps(packet, indent=2))
    else:
        print(_build_markdown(packet))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
