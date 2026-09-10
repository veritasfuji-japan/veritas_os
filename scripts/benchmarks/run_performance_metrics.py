"""Deterministic local performance metrics harness.

This script measures a lightweight local code path without external API calls
and writes a stable JSON report for reproducible benchmarking workflows.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import shlex
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from veritas_os.security.hash import canonical_json_dumps, sha256_hex
from veritas_os.security.wat_verifier import (
    DriftVector,
    VerifierResult,
    build_operator_message,
    score_drift,
)

_COMMIT_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_DEFAULT_SCENARIO = "local_deterministic_smoke"
_HARNESS_PATH = "scripts/benchmarks/run_performance_metrics.py"


def _positive_int(value: str) -> int:
    """Parse CLI integer argument that must be >= 1."""
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return parsed


def _non_negative_int(value: str) -> int:
    """Parse CLI integer argument that must be >= 0."""
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return parsed


def _normalize_commit_sha(value: str | None) -> str | None:
    """Return a normalized full commit SHA or ``None`` when invalid."""
    if value is None:
        return None
    candidate = value.strip()
    if not _COMMIT_SHA_RE.fullmatch(candidate):
        return None
    return candidate.lower()


def _resolve_source_commit(explicit: str | None = None) -> str:
    """Resolve the exact Git commit measured by this benchmark.

    Resolution deliberately prefers an explicit override and then the checked
    out Git tree. ``GITHUB_SHA`` is only a final fallback because pull-request
    events can otherwise point at a synthetic merge commit rather than the
    checked-out benchmark source.
    """
    for candidate in (explicit, os.getenv("VERITAS_BENCHMARK_SOURCE_COMMIT")):
        normalized = _normalize_commit_sha(candidate)
        if candidate is not None and normalized is None:
            raise ValueError("source commit must be a full 40-character Git SHA")
        if normalized is not None:
            return normalized

    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT_DIR,
            text=True,
            capture_output=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        completed = None

    if completed is not None and completed.returncode == 0:
        normalized = _normalize_commit_sha(completed.stdout)
        if normalized is not None:
            return normalized

    github_sha = _normalize_commit_sha(os.getenv("GITHUB_SHA"))
    if github_sha is not None:
        return github_sha

    raise RuntimeError(
        "unable to resolve measured source commit; run from a Git checkout or "
        "pass --source-commit"
    )


def _percentile(sorted_values: list[float], percentile: float) -> float:
    """Return nearest-rank percentile for a pre-sorted non-empty list.

    Args:
        sorted_values: Pre-sorted values in ascending order.
        percentile: Ratio in the inclusive range [0.0, 1.0].
    """
    if not sorted_values:
        raise ValueError("sorted_values must not be empty")
    if percentile < 0.0 or percentile > 1.0:
        raise ValueError("percentile must be between 0.0 and 1.0")
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = math.ceil(percentile * len(sorted_values))
    index = min(max(rank - 1, 0), len(sorted_values) - 1)
    return sorted_values[index]


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
            "Not a customer environment measurement.",
        ],
    }
    return report


def _build_exact_command(args: argparse.Namespace) -> str:
    """Build the canonical, copyable command represented by parsed arguments."""
    command = [
        "python",
        _HARNESS_PATH,
        "--iterations",
        str(args.iterations),
        "--warmup",
        str(args.warmup),
    ]
    if args.output is not None:
        command.extend(["--output", args.output.as_posix()])
    if args.scenario != _DEFAULT_SCENARIO:
        command.extend(["--scenario", args.scenario])
    if args.source_commit is not None:
        command.extend(["--source-commit", args.source_commit])
    return shlex.join(command)


def _attach_provenance(
    report: dict[str, Any],
    *,
    args: argparse.Namespace,
    source_commit_sha: str,
) -> None:
    """Attach Phase B provenance without changing measured runtime behavior."""
    exact_command = _build_exact_command(args)
    harness_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    metrics = dict(report["metrics"])
    counters = dict(report["counters"])

    report.update(
        {
            "source_commit_sha": source_commit_sha,
            "run_timestamp": report["generated_at"],
            "exact_command": exact_command,
            "iterations_or_run_count": args.iterations,
            "warmup_when_relevant": args.warmup,
            "failure_count": counters["failure"],
            "harness_identity": {
                "path": _HARNESS_PATH,
                "sha256": harness_sha256,
            },
            "input_identity": {
                "type": "embedded_deterministic_fixture",
                "location": f"{_HARNESS_PATH}::_run_iteration",
                "scenario": args.scenario,
            },
            "raw_machine_readable_result": {
                "metrics": metrics,
                "counters": counters,
            },
            "summary": {
                "scenario": args.scenario,
                "mean_ms": metrics["mean_ms"],
                "p95_ms": metrics["p95_ms"],
                "p99_ms": metrics["p99_ms"],
                "success_count": counters["success"],
                "failure_count": counters["failure"],
            },
            "claim_boundary": {
                "scope": "lightweight deterministic local function-path timing only",
                "external_network_required": False,
                "external_llm_or_api_allowed": False,
                "non_claims": [
                    "production latency",
                    "production SLA",
                    "customer-environment performance",
                    "real customer endpoint performance",
                    "external provider latency",
                    "third-party certification",
                    "regulatory approval",
                    "superiority over named vendors",
                ],
            },
            "reproducibility_instructions": {
                "checkout": f"git checkout {source_commit_sha}",
                "command": exact_command,
                "canonical_python_minor": "3.12",
                "platform_class": "Linux x86_64",
            },
        }
    )


def main() -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=_positive_int, default=100)
    parser.add_argument("--warmup", type=_non_negative_int, default=10)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--scenario", default=_DEFAULT_SCENARIO)
    parser.add_argument(
        "--source-commit",
        help="Optional full Git SHA override for source-bound benchmark provenance.",
    )
    args = parser.parse_args()

    source_commit_sha = _resolve_source_commit(args.source_commit)
    report = collect_metrics(args.iterations, args.warmup, args.scenario)
    _attach_provenance(report, args=args, source_commit_sha=source_commit_sha)
    rendered = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2)

    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
