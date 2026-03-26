# -*- coding: utf-8 -*-
"""Tests for evidence benchmark harness."""

from __future__ import annotations

import json
from pathlib import Path

from veritas_os.scripts.evidence_benchmark import run_benchmark


def test_run_benchmark_compares_veritas_and_generic(tmp_path: Path) -> None:
    """Benchmark should compute deterministic axis pass rates per system."""
    fixture_path = tmp_path / "cases.jsonl"
    fixture_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "case_id": "case-1",
                        "expected": {"fail_closed_on_uncertainty": True},
                        "systems": {
                            "veritas": {
                                "request_id": "r1",
                                "decision_id": "d1",
                                "timestamp": "2026-03-26T00:00:00Z",
                                "evidence_count": 3,
                                "decision_status": "hold",
                                "governance": {
                                    "policy_changed": True,
                                    "policy_version": "v1",
                                    "change_ticket_id": "G-1",
                                    "approval_count": 1,
                                },
                                "replay": {
                                    "executed": True,
                                    "diff": {
                                        "changed": False,
                                        "divergence_level": "no_divergence",
                                    },
                                },
                                "trust_log": {
                                    "sha256": "h1",
                                    "sha256_prev": "h0",
                                    "signature_valid": True,
                                },
                            },
                            "generic": {
                                "request_id": "gr1",
                                "decision_id": "gd1",
                                "timestamp": "2026-03-26T00:00:00Z",
                                "evidence_count": 1,
                                "decision_status": "allow",
                                "governance": {"policy_changed": False},
                                "replay": {"executed": False},
                                "trust_log": {"signature_valid": False},
                            },
                        },
                    }
                )
            ]
        ),
        encoding="utf-8",
    )

    report = run_benchmark(fixture_path)

    assert report["aggregate"]["veritas"]["fail_closed_safety"]["rate"] == 1.0
    assert report["aggregate"]["generic"]["fail_closed_safety"]["rate"] == 0.0
    assert report["aggregate"]["veritas"]["trust_log_integrity"]["rate"] == 1.0
    assert report["aggregate"]["generic"]["replay_divergence_visibility"]["rate"] == 0.0
