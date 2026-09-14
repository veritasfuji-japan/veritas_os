"""Tests for the deterministic external UTC clock reviewer proof fixture."""

from __future__ import annotations

import json

from veritas_os.governance.external_clock_fixture_proof import (
    FIXTURE_ID,
    PROOF_ID,
    build_external_clock_fixture_proof,
    write_external_clock_fixture_artifacts,
)


def test_fixture_proof_preserves_non_authoritative_claim_boundary() -> None:
    bundle = build_external_clock_fixture_proof(
        challenge_id="external-clock-fixture-test-challenge-001"
    )

    manifest = bundle["manifest"]
    summary = bundle["summary"]
    negative = bundle["negative_test_report"]

    assert manifest["proof_id"] == PROOF_ID
    assert manifest["fixture_id"] == FIXTURE_ID
    assert manifest["monotonic_rtt_ms"] == 125.0
    assert len(manifest["evidence_hash"]) == 64
    assert len(manifest["verification_proof_hash"]) == 64
    assert len(manifest["proof_payload_hash"]) == 64

    assert summary["valid_proof"] is True
    assert summary["validation_failures"] == []
    assert summary["tamper_checks_passed"] is True
    assert summary["live_external_effects"] is False
    assert summary["live_clock_provider"] is False
    assert summary["runtime_clock_replacement"] is False
    assert summary["execution_authority"] is False
    assert summary["production_claim"] is False

    assert negative["passed"] is True
    assert negative["expected_failure"] in negative["observed_failures"]


def test_fixture_writer_emits_only_expected_reviewer_json(tmp_path) -> None:
    write_external_clock_fixture_artifacts(tmp_path)

    names = sorted(path.name for path in tmp_path.iterdir())
    assert names == [
        "manifest.json",
        "negative_test_report.json",
        "proof.json",
        "summary.json",
    ]

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    proof = json.loads((tmp_path / "proof.json").read_text(encoding="utf-8"))

    assert manifest["proof_id"] == PROOF_ID
    assert proof["runtime_trust_portable"] is False
    assert proof["execution_authority"] is False
