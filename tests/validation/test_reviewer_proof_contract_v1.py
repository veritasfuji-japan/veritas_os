"""Bounded contract pin and adversarial evidence tests; never run a provider."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from veritas_os.security.hash import sha256_of_canonical_json
from scripts.validation.verify_reviewer_proof_contract_v1 import (
    ProofError, load_json, verify_contract, verify_report,
)

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "contracts/reviewer-proof-contract-v1.json"
PROOF_DIR = ROOT / "artifacts/real-decision-to-effect-e2e"


def test_exact_contract_is_pinned():
    verify_contract(load_json(CONTRACT))


@pytest.mark.parametrize("change", (
    "remove_predicate", "relax_dispatch", "drop_nonclaim",
    "erase_out_of_scope", "remove_fault", "remove_false_claim",
))
def test_contract_cannot_be_silently_weakened(change):
    value = copy.deepcopy(load_json(CONTRACT))
    if change == "remove_predicate":
        value["required_conjunction"].pop()
    elif change == "relax_dispatch":
        del value["scenarios"]["normal"]["dispatch_reason"]
    elif change == "drop_nonclaim":
        value["required_non_claims"].pop()
    elif change == "erase_out_of_scope":
        value["out_of_scope"] = []
    elif change == "remove_fault":
        del value["scenarios"]["fault"]
    else:
        value["required_false_claims"].pop()
    with pytest.raises(ProofError, match="CONTRACT_DRIFT"):
        verify_contract(value)


@pytest.mark.parametrize("raw", (
    '{"a":1,"a":2}', '{"a":NaN}', '[]',
))
def test_json_loader_rejects_ambiguous_artifacts(tmp_path, raw):
    path = tmp_path / "report.json"
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(ProofError):
        load_json(path)


@pytest.fixture
def real_e2e():
    """Only run artifact mutation checks once the existing E2E has generated it."""
    report_path = PROOF_DIR / "report.json"
    evidence_path = PROOF_DIR / "evidence.json"
    if not report_path.is_file() or not evidence_path.is_file():
        pytest.skip("controlled E2E artifacts not generated in this environment")
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
