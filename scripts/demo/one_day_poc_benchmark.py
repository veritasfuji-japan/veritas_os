#!/usr/bin/env python3
"""Lightweight local benchmark for one-day VERITAS PoC checks."""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from scripts.demo import one_day_poc_smoke

SCHEMA_VERSION = "one_day_poc_benchmark.v1"
PACKET_TYPE = "performance_benchmark"
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_TIMEOUT_SECONDS = 10.0


def _emit_status(message: str, *, json_output: bool, error: bool = False) -> None:
    stream = sys.stderr if json_output or error else sys.stdout
    print(message, file=stream)


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(
        len(ordered) - 1,
        max(0, math.ceil((percentile / 100.0) * len(ordered)) - 1),
    )
    return ordered[idx]


def _summarize_timings(values: list[float], success_count: int, failure_count: int) -> dict[str, float | int]:
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


def _redact_message(exc: Exception) -> str:
    return str(exc).replace(os.getenv("VERITAS_API_KEY", ""), "[REDACTED]")


def _run_target(runs: int, warmup: int, target: Callable[[], None]) -> tuple[dict[str, float | int], list[dict[str, str]]]:
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
        except Exception as exc:  # pragma: no cover - defensive branch
            failures.append({"type": exc.__class__.__name__, "message": _redact_message(exc)[:200]})
    return _summarize_timings(timings, success, runs - success), failures


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="One-day VERITAS PoC benchmark")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--base-url", default=os.getenv("VERITAS_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--scenario", default="one_day_poc", choices=["one_day_poc"])
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--out-json")
    parser.add_argument("--out-md")
    return parser


def _build_markdown(packet: dict[str, Any]) -> str:
    b = packet["benchmarks"]
    lines = [
        "# One-Day PoC Performance Benchmark",
        "",
        "## Summary",
        "Local benchmark for lightweight PoC latency checks.",
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
    for name in ["observability_capabilities", "governance_policy_read", "smoke_equivalent_end_to_end"]:
        row = b[name]
        lines.append(
            f"| {name} | {packet['runs']} | {row['success_count']} | {row['failure_count']} | "
            f"{row['p50_ms']:.2f} | {row['p95_ms']:.2f} | {row['p99_ms']:.2f} | {row['mean_ms']:.2f} | {row['max_ms']:.2f} |"
        )
    lines.extend([
        "",
        "## Methodology",
        "- Repeats endpoint checks and a smoke-equivalent flow for configured runs.",
        "- Uses local wall-clock latency from Python runtime.",
        "",
        "## Limitations",
        "- Local benchmark only; not a production SLA.",
        "- Network, model provider latency, and deployment topology may change results.",
        "- This benchmark does not certify EU AI Act compliance.",
        "",
        "## What this does not prove",
        "- Not throughput testing.",
        "- Not legal certification.",
        "",
        "## Recommended next measurements",
        "- Controlled staging environment measurements.",
        "- Load, concurrency, and tail-latency analysis.",
    ])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if not 1 <= args.runs <= 50:
        _emit_status("--runs must be between 1 and 50", json_output=args.json, error=True)
        return 2
    if not 0 <= args.warmup <= 10:
        _emit_status("--warmup must be between 0 and 10", json_output=args.json, error=True)
        return 2

    api_key = os.getenv("VERITAS_API_KEY", "").strip()
    if not api_key:
        _emit_status("missing required API credentials: set VERITAS_API_KEY", json_output=args.json, error=True)
        return 2

    def _obs() -> None:
        one_day_poc_smoke._http_get_json(args.base_url, "/v1/observability/capabilities", api_key)

    def _policy() -> None:
        one_day_poc_smoke._http_get_json(args.base_url, "/v1/governance/policy", api_key)

    def _smoke_equivalent() -> None:
        status, obs_payload = one_day_poc_smoke._http_get_json(args.base_url, "/v1/observability/capabilities", api_key)
        one_day_poc_smoke._extract_observability_summary(obs_payload)
        policy_status, _ = one_day_poc_smoke._http_get_json(args.base_url, "/v1/governance/policy", api_key)
        one_day_poc_smoke._build_evidence_packet(status, obs_payload, policy_status)

    obs, obs_failures = _run_target(args.runs, args.warmup, _obs)
    policy, policy_failures = _run_target(args.runs, args.warmup, _policy)
    e2e, e2e_failures = _run_target(args.runs, args.warmup, _smoke_equivalent)
    measured_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    packet: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "packet_type": PACKET_TYPE,
        "scenario": args.scenario,
        "measured_at": measured_at,
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
            "Network, model provider latency, and deployment topology may change results.",
            "This benchmark does not certify EU AI Act compliance.",
        ],
    }

    if args.out_json:
        Path(args.out_json).write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")
        _emit_status(f"Wrote sanitized benchmark JSON: {args.out_json}", json_output=args.json)
    if args.out_md:
        Path(args.out_md).write_text(_build_markdown(packet), encoding="utf-8")
        _emit_status(f"Wrote sanitized benchmark Markdown: {args.out_md}", json_output=args.json)

    if args.json:
        print(json.dumps(packet, indent=2))
    else:
        print(_build_markdown(packet))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
