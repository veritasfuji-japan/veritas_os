"""Artifact-dependent checks: run only after the controlled E2E producer.

This file intentionally does not match default pytest discovery patterns.
The dedicated E2E workflow must invoke it explicitly. Missing artifacts
therefore FAIL that workflow, without breaking unrelated normal CI shards.
"""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from veritas_os.security.hash import sha256_of_canonical_json
from scripts.validation.verify_reviewer_proof_contract_v1 import (
    load_json, verify_report,
)

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "contracts/reviewer-proof-contract-v1.json"
PROOF_DIR = ROOT / "artifacts/real-decision-to-effect-e2e"

@pytest.fixture
def real_e2e():
    """Required controlled artifacts: fail, never skip, when evidence is absent."""
    report_path = PROOF_DIR / "report.json"
    evidence_path = PROOF_DIR / "evidence.json"
    missing = [
        path.name for path in (report_path, evidence_path) if not path.is_file()
    ]
    if missing:
        pytest.fail(
            "REQUIRED_CONTROLLED_E2E_EVIDENCE_MISSING: " + ", ".join(missing),
            pytrace=False,
        )
    return load_json(report_path), load_json(evidence_path)


def rehash(report, evidence):
    report["evidence_hash"] = sha256_of_canonical_json(evidence)
    report.pop("proof_manifest_hash", None)
    report["proof_manifest_hash"] = sha256_of_canonical_json(report)


def test_real_e2e_is_structurally_consistent(real_e2e):
    report, evidence = real_e2e
    verify_report(load_json(CONTRACT), report, evidence)


@pytest.mark.parametrize("tampering", (
    "remove_predicate", "overclaim", "wrong_consumption",
    "wrong_receipt", "wrong_reconciliation", "changed_effect_count",
))
def test_rehashed_tampering_of_real_e2e_is_rejected(real_e2e, tampering):
    report, evidence = copy.deepcopy(real_e2e)
    if tampering == "remove_predicate":
        report["proof_conjunction"].pop(next(iter(report["proof_conjunction"])))
    elif tampering == "overclaim":
        report["production_validation_proven"] = True
    elif tampering == "wrong_consumption":
        record = evidence["normal"]["consumption"]
        record["live_adapter_bind_authorization_id"] = "wrong"
        payload = {key: value for key, value in record.items()
                   if key not in {"consumption_id", "consumption_hash"}}
        record["consumption_hash"] = sha256_of_canonical_json(payload)
        record["consumption_id"] = "labac:v1:sha256:" + record["consumption_hash"]
        report["normal"]["consumption_id"] = record["consumption_id"]
    elif tampering == "wrong_receipt":
        bundle = evidence["normal"]["receipt_bundle"]
        bundle["bind_receipt"]["decision_id"] = "wrong"
        bundle["bundle_hash"] = sha256_of_canonical_json({
            key: bundle[key] for key in (
                "format_version", "bind_receipt", "outcome_receipt"
            )
        })
        report["normal"]["receipt_bundle_hash"] = bundle["bundle_hash"]
    elif tampering == "wrong_reconciliation":
        operation = evidence["fault"]["reconciliation_archive"]["operation"]
        operation["operation_id"] = "00000000-0000-4000-8000-000000000001"
        report["fault"]["external_operation_reference"] = operation["operation_id"]
    else:
        report["sandbox_rows_added"] = 3
    rehash(report, evidence)
    with pytest.raises((ValueError, KeyError)):
        verify_report(load_json(CONTRACT), report, evidence)
