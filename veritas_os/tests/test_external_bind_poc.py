"""Integration coverage for the local external-bind evidence runner."""

from __future__ import annotations

import json
from pathlib import Path

from examples.external_bind_poc.poc import run_all


def test_poc_scenarios_and_external_effect_counts(tmp_path: Path) -> None:
    evidence = run_all(tmp_path)
    assert evidence["committed"]["final_outcome"] == "COMMITTED"
    assert evidence["committed"]["action_post_count"] == 1
    assert evidence["blocked"]["final_outcome"] == "BLOCKED"
    assert evidence["blocked"]["action_post_count"] == 0
    assert evidence["rolled-back"]["final_outcome"] == "ROLLED_BACK"
    assert evidence["rolled-back"]["action_post_count"] == 1
    assert evidence["rolled-back"]["compensation_post_count"] == 1
    assert evidence["rolled-back"]["verification_result"]["compensation_verified"]


def test_evidence_is_deterministic_and_contains_no_secret(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    run_all(first)
    run_all(second)
    first_files = {path.name: path.read_bytes() for path in first.iterdir()}
    second_files = {path.name: path.read_bytes() for path in second.iterdir()}
    assert first_files == second_files
    serialized = json.dumps(
        {name: value.decode("utf-8") for name, value in first_files.items()}
    )
    assert "test-only-external-bind-poc-secret" not in serialized
    assert "X-Veritas-Signature" not in serialized
    assert "api_key" not in serialized.lower()

