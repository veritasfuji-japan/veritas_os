"""Offline positive/negative tests for the bounded reviewer proof contract."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.validation.verify_reviewer_proof_contract_v1 import (
    ContractError, NONCLAIMS, REQUIRED, canonical_hash, load_json, validate,
)

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = json.loads(
    (ROOT / "contracts/reviewer-proof-contract-v1.json").read_text(encoding="utf-8")
)
TESTED, SOURCE, BASE = "a" * 40, "b" * 40, "c" * 40


def samples():
    evidence = {
        "format_version": CONTRACT["evidence_format"],
        "tested_sha": TESTED, "source_sha": SOURCE, "base_sha": BASE,
    }
    report = {
        "format_version": CONTRACT["report_format"],
        "result": "PASS", "proof": CONTRACT["proof"],
        "tested_sha": TESTED, "source_sha": SOURCE, "base_sha": BASE,
        "decision_capture_mode": CONTRACT["decision_capture_mode"],
        "external_effect_scope": CONTRACT["external_effect_scope"],
        "production_claim": False,
        "controlled_decision_to_effect_e2e_proven": True,
        "production_decision_to_effect_e2e_proven": False,
        "trustlog_exactly_once_proven": False,
        "production_validation_proven": False,
        "proof_non_claims": list(CONTRACT["required_non_claims"]),
        "proof_conjunction": dict.fromkeys(CONTRACT["required_conjunction"], True),
        "alembic_head": "0012", "sandbox_rows_added": 2,
    }
    for case in ("normal", "fault"):
        key = case.upper()
        evidence[case] = {
            "canonical_decision_artifact": {
                "decision_id": key + "-decision", "decision_hash": key + "-hash",
            },
            "promotion_packet": {"promotion_hash": key + "-promotion"},
            "native_authorization": {"authorization_id": key + "-authorization"},
            "consumption": {"consumption_id": key + "-consumption"},
            "reconciliation_archive": {
                "operation": {"operation_id": key + "-operation"},
            },
            "receipt_bundle": {"bundle_hash": key + "-receipt"},
        }
        report[case] = {
            "decision_id": key + "-decision",
            "decision_hash": key + "-hash",
            "promotion_hash": key + "-promotion",
            "authorization_id": key + "-authorization",
            "consumption_id": key + "-consumption",
            "external_operation_reference": key + "-operation",
            "receipt_bundle_hash": key + "-receipt",
            "governance_recheck_calls": 3,
            **{
                k: v for k, v in CONTRACT["scenarios"][case].items()
                if k != "min_governance_rechecks"
            },
        }
    resign(report, evidence)
    return report, evidence


def resign(report, evidence):
    report["evidence_hash"] = canonical_hash(evidence)
    report.pop("proof_manifest_hash", None)
    report["proof_manifest_hash"] = canonical_hash(report)


def check(report, evidence, contract=CONTRACT, **overrides):
    return validate(
        contract, report, evidence,
        tested_sha=overrides.get("tested_sha", TESTED),
        source_sha=overrides.get("source_sha", SOURCE),
        base_sha=overrides.get("base_sha", BASE),
        checkout_sha=overrides.get("checkout_sha", TESTED),
    )


def test_bounded_valid_fixture_passes_without_certification():
    report, evidence = samples()
    result = check(report, evidence)
    assert result["result"] == "PASS_BOUNDED_CONSISTENCY_ONLY"
    assert result["production_proven"] is False
    assert result["third_party_certified"] is False
    assert result["verified_predicate_count"] == len(REQUIRED)
    assert set(CONTRACT["required_non_claims"]) == NONCLAIMS


@pytest.mark.parametrize("predicate", sorted(REQUIRED))
def test_dropped_conjunction_predicate_is_rejected_even_if_rehashed(predicate):
    report, evidence = samples()
    del report["proof_conjunction"][predicate]
    resign(report, evidence)
    with pytest.raises(ContractError, match="conjunction"):
        check(report, evidence)


@pytest.mark.parametrize("claim", [
    "production_claim", "production_decision_to_effect_e2e_proven",
    "trustlog_exactly_once_proven", "production_validation_proven",
])
def test_false_claim_cannot_be_raised(claim):
    report, evidence = samples()
    report[claim] = True
    resign(report, evidence)
    with pytest.raises(ContractError, match="unsupported production"):
        check(report, evidence)


@pytest.mark.parametrize("sha_field", ["tested_sha", "source_sha", "base_sha"])
def test_both_artifacts_forged_provenance_is_rejected(sha_field):
    report, evidence = samples()
    report[sha_field] = evidence[sha_field] = "d" * 40
    resign(report, evidence)
    with pytest.raises(ContractError, match="provenance"):
        check(report, evidence)


def test_wrong_checkout_is_rejected():
    report, evidence = samples()
    with pytest.raises(ContractError, match="checked-out"):
        check(report, evidence, checkout_sha="f" * 40)


def test_rehashed_bad_lineage_is_rejected():
    report, evidence = samples()
    evidence["normal"]["consumption"]["consumption_id"] = "changed"
    resign(report, evidence)
    with pytest.raises(ContractError, match="identity"):
        check(report, evidence)


def test_unchanged_hash_detects_evidence_mutation():
    report, evidence = samples()
    evidence["normal"]["receipt_bundle"]["bundle_hash"] = "changed"
    with pytest.raises(ContractError):
        check(report, evidence)


@pytest.mark.parametrize("field,value", [
    ("sandbox_rows_added", 3), ("sandbox_rows_added", True), ("result", "FAIL"),
])
def test_wrong_effect_or_success_statement_rejected(field, value):
    report, evidence = samples()
    report[field] = value
    resign(report, evidence)
    with pytest.raises(ContractError):
        check(report, evidence)


def test_omitted_production_nonclaim_rejected():
    report, evidence = samples()
    report["proof_non_claims"].remove("production readiness")
    resign(report, evidence)
    with pytest.raises(ContractError, match="nonclaim"):
        check(report, evidence)


def test_weakened_contract_is_rejected():
    report, evidence = samples()
    weaker = copy.deepcopy(CONTRACT)
    weaker["required_conjunction"].pop()
    with pytest.raises(ContractError, match="predicates"):
        check(report, evidence, weaker)


def test_missing_fault_evidence_rejected():
    report, evidence = samples()
    del evidence["fault"]
    resign(report, evidence)
    with pytest.raises(ContractError, match="missing scenario"):
        check(report, evidence)


def test_json_duplicate_keys_fail_closed(tmp_path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"status":"FAIL","status":"PASS"}', encoding="utf-8")
    with pytest.raises(ContractError, match="duplicate"):
        load_json(path)


def test_nonstandard_nan_rejected(tmp_path):
    path = tmp_path / "nan.json"
    path.write_text('{"status":NaN}', encoding="utf-8")
    with pytest.raises(ContractError, match="invalid JSON"):
        load_json(path)
