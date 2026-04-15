"""Tests for evidence bundle CLI and financial sample fixture."""

from __future__ import annotations

import json
from pathlib import Path

from veritas_os.audit import trustlog_signed


def test_evidence_bundle_cli_generate_and_verify(tmp_path, monkeypatch) -> None:
    """CLI can generate and verify a decision evidence bundle."""
    log_path = tmp_path / "trustlog.jsonl"
    private_key = tmp_path / "keys" / "priv.key"
    public_key = tmp_path / "keys" / "pub.key"

    monkeypatch.setattr(trustlog_signed, "SIGNED_TRUSTLOG_JSONL", log_path)
    monkeypatch.setattr(trustlog_signed, "PRIVATE_KEY_PATH", private_key)
    monkeypatch.setattr(trustlog_signed, "PUBLIC_KEY_PATH", public_key)

    trustlog_signed.append_signed_decision(
        {
            "request_id": "fin-wire-2026-0001",
            "gate_decision": "human_review_required",
            "business_decision": "REVIEW_REQUIRED",
            "next_action": "ROUTE_TO_HUMAN_REVIEW",
            "required_evidence": [
                "kyc_verification",
                "source_of_funds_attestation",
                "aml_screening_receipt",
            ],
            "human_review_required": True,
        }
    )

    from veritas_os.cli.evidence_bundle import main

    out_dir = tmp_path / "bundles"
    exit_code = main(
        [
            "generate",
            "--bundle-type",
            "decision",
            "--witness-ledger",
            str(log_path),
            "--output-dir",
            str(out_dir),
            "--request-id",
            "fin-wire-2026-0001",
            "--json",
        ]
    )
    assert exit_code == 0

    generated_dirs = list(out_dir.glob("veritas_bundle_decision_*"))
    assert generated_dirs
    bundle_dir = generated_dirs[0]

    verify_exit = main(["verify", "--bundle-dir", str(bundle_dir), "--json"])
    assert verify_exit == 0


def test_financial_bundle_sample_fixture_exists() -> None:
    """Repository includes a representative financial decision bundle sample."""
    fixture_path = Path(
        "veritas_os/benchmarks/evidence/fixtures/financial_template_bundle_sample.json"
    )
    assert fixture_path.exists()

    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.1.0"
    decision_record = payload["decision_record"]
    assert decision_record["decision_payload"]["gate_decision"] == "human_review_required"
    assert decision_record["decision_payload"]["business_decision"] == "REVIEW_REQUIRED"
    assert decision_record["decision_payload"]["human_review_required"] is True
