"""Deterministic local performance metrics harness.

This script measures a lightweight local code path without external API calls
and writes a stable JSON report for reproducible benchmarking workflows.
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
from datetime import datetime, timezone
from typing import Any

from veritas_os.security.hash import canonical_json_dumps, sha256_hex
from veritas_os.security.wat_verifier import (
    DriftVector,
    VerifierResult,
    build_operator_message,
    score_drift,
)


def _percentile(sorted_values: list[float], percentile: float) -> float:
    """Return percentile value for a pre-sorted non-empty list."""
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = int((len(sorted_values) - 1) * percentile)
    return sorted_values[rank]


def _run_iteration() -> bool:
    """Run one deterministic local benchmark iteration."""
    payload = {
        "action": "local_deterministic_smoke",
        "amount": 42,
        "currency": "JPY",
        "meta": {"path": "bench", "version": 1},
    }
    canonical = canonical_json_dumps(payload)
    digest = sha256_hex(canonical)
    drift_vector = DriftVector(
        policy_drift=0.1,
        signature_drift=0.0,
        observable_drift=0.0,
        temporal_drift=0.0,
    )
    drift_score = score_drift(drift_vector)
    result = VerifierResult(
        validation_status="valid",
        admissibility_state="admissible",
        failure_type=None,
        drift_vector=drift_vector,
        audit_event_ref=f"audit::{digest[:12]}",
        mission_control_event_name="performance_metrics_harness",
        operator_message="",
        warning_context="local-benchmark",
        warning_correlation_id=digest[:16],
    )
    message = build_operator_message(result)
    return bool(canonical and digest and drift_score.classification and message)


def collect_metrics(iterations: int, warmup: int, scenario: str) -> dict[str, Any]:
    """Collect deterministic benchmark metrics and return report payload."""
    if iterations < 1:
        raise ValueError("iterations must be >= 1")
    if warmup < 0:
        raise ValueError("warmup must be >= 0")

    for _ in range(warmup):
        _run_iteration()

    durations_ms: list[float] = []
    success = 0
    failure = 0

    for _ in range(iterations):
        start_ns = time.perf_counter_ns()
        ok = _run_iteration()
        end_ns = time.perf_counter_ns()
        durations_ms.append((end_ns - start_ns) / 1_000_000.0)
        if ok:
            success += 1
        else:
            failure += 1

    sorted_durations = sorted(durations_ms)
    report = {
        "schema_version": "performance_metrics.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scenario": scenario,
        "environment": {
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "processor": platform.processor(),
            "implementation": platform.python_implementation().lower(),
        },
        "iterations": iterations,
        "warmup": warmup,
        "metrics": {
            "total_wall_ms": round(sum(durations_ms), 6),
            "mean_ms": round(statistics.fmean(durations_ms), 6),
            "median_ms": round(statistics.median(durations_ms), 6),
            "p95_ms": round(_percentile(sorted_durations, 0.95), 6),
            "p99_ms": round(_percentile(sorted_durations, 0.99), 6),
            "min_ms": round(sorted_durations[0], 6),
            "max_ms": round(sorted_durations[-1], 6),
        },
        "counters": {
            "success": success,
            "failure": failure,
        },
        "notes": [
            "Deterministic local benchmark only.",
            "No external LLM/API calls.",
            "Not a production SLA.",
            "Not third-party certified.",
        ],
    }
    return report


def main() -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument("--warmup", type=int, default=10)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--scenario", default="local_deterministic_smoke")
    args = parser.parse_args()

    report = collect_metrics(args.iterations, args.warmup, args.scenario)
    rendered = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2)

    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
