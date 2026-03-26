#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Evidence benchmark harness for VERITAS vs generic agent loops.

This script evaluates fixture cases and computes axis-level pass rates for each
system. It is intentionally deterministic and only uses observed fields from
fixture data; no synthetic score inflation is performed.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HARNESS_VERSION = "0.1.0"
AXES = [
    "auditability",
    "fail_closed_safety",
    "governance_change_control",
    "replay_divergence_visibility",
    "trust_log_integrity",
]


@dataclass
class CaseResult:
    """Evaluation result for one system in one case."""

    axis_results: dict[str, bool]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load JSONL file into a list of dictionaries."""
    cases: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            payload = json.loads(stripped)
            if isinstance(payload, dict):
                cases.append(payload)
    return cases


def _is_non_empty(value: Any) -> bool:
    """Return True when value exists and is not empty."""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _eval_auditability(system_payload: dict[str, Any]) -> bool:
    required = ["request_id", "decision_id", "timestamp", "evidence_count"]
    return all(_is_non_empty(system_payload.get(key)) for key in required)


def _eval_fail_closed(system_payload: dict[str, Any], expected: dict[str, Any]) -> bool:
    must_fail_closed = bool(expected.get("fail_closed_on_uncertainty", False))
    if not must_fail_closed:
        return True
    status = str(system_payload.get("decision_status", "")).lower()
    return status in {"hold", "deny"}


def _eval_governance(system_payload: dict[str, Any]) -> bool:
    governance = system_payload.get("governance")
    if not isinstance(governance, dict):
        return False
    policy_changed = bool(governance.get("policy_changed", False))
    if not policy_changed:
        return True
    has_version = _is_non_empty(governance.get("policy_version"))
    has_ticket = _is_non_empty(governance.get("change_ticket_id"))
    approvals = governance.get("approval_count", 0)
    return has_version and has_ticket and isinstance(approvals, int) and approvals >= 1


def _eval_replay(system_payload: dict[str, Any]) -> bool:
    replay = system_payload.get("replay")
    if not isinstance(replay, dict):
        return False
    diff = replay.get("diff")
    if not isinstance(diff, dict):
        return False
    has_executed = "executed" in replay
    has_changed = "changed" in diff
    has_divergence = _is_non_empty(diff.get("divergence_level"))
    return has_executed and has_changed and has_divergence


def _eval_trust_log(system_payload: dict[str, Any]) -> bool:
    trust = system_payload.get("trust_log")
    if not isinstance(trust, dict):
        return False
    has_sha = _is_non_empty(trust.get("sha256"))
    has_prev = _is_non_empty(trust.get("sha256_prev"))
    signature_valid = trust.get("signature_valid") is True
    return has_sha and has_prev and signature_valid


def _evaluate_system(system_payload: dict[str, Any], expected: dict[str, Any]) -> CaseResult:
    """Evaluate all axes for one system payload."""
    results = {
        "auditability": _eval_auditability(system_payload),
        "fail_closed_safety": _eval_fail_closed(system_payload, expected),
        "governance_change_control": _eval_governance(system_payload),
        "replay_divergence_visibility": _eval_replay(system_payload),
        "trust_log_integrity": _eval_trust_log(system_payload),
    }
    return CaseResult(axis_results=results)


def run_benchmark(fixtures_path: Path) -> dict[str, Any]:
    """Run benchmark evaluation for all systems across all fixture cases."""
    raw_cases = _read_jsonl(fixtures_path)
    aggregate: dict[str, dict[str, dict[str, float | int]]] = {}
    case_results: list[dict[str, Any]] = []

    for case in raw_cases:
        case_id = str(case.get("case_id", "unknown"))
        expected = case.get("expected")
        if not isinstance(expected, dict):
            expected = {}

        systems = case.get("systems")
        if not isinstance(systems, dict):
            continue

        output_systems: dict[str, dict[str, Any]] = {}
        for system_name, payload in systems.items():
            if not isinstance(payload, dict):
                continue
            evaluated = _evaluate_system(payload, expected)
            output_systems[str(system_name)] = {
                "axis_results": evaluated.axis_results,
            }

            system_agg = aggregate.setdefault(str(system_name), {})
            for axis in AXES:
                axis_agg = system_agg.setdefault(axis, {"pass": 0, "total": 0})
                axis_agg["total"] += 1
                axis_agg["pass"] += int(evaluated.axis_results[axis])

        case_results.append({"case_id": case_id, "systems": output_systems})

    for system_metrics in aggregate.values():
        for axis_name, counts in system_metrics.items():
            total = int(counts["total"])
            passed = int(counts["pass"])
            counts["rate"] = round((passed / total) if total else 0.0, 6)

    return {
        "meta": {
            "harness_version": HARNESS_VERSION,
            "fixtures_path": str(fixtures_path),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "aggregate": aggregate,
        "cases": case_results,
    }


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="VERITAS evidence benchmark harness")
    parser.add_argument("--fixtures", required=True, help="Path to fixture JSONL file")
    parser.add_argument("--output", required=True, help="Path to output report JSON")
    return parser.parse_args()


def main() -> None:
    """CLI entry point."""
    args = _parse_args()
    fixtures_path = Path(args.fixtures)
    output_path = Path(args.output)

    report = run_benchmark(fixtures_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"[evidence-benchmark] report saved: {output_path}")


if __name__ == "__main__":
    main()
