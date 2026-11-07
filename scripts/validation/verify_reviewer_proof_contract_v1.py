#!/usr/bin/env python3
"""Validate existing controlled E2E evidence without granting execution authority.

A bounded consistency check, NOT independent execution, authenticity or
production assurance. Reuses VERITAS provenance and canonical hash primitives.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

from veritas_os.policy.live_adapter_bind_authorization_consumption_store import (
    AuthorizationConsumptionRecord,
)
from veritas_os.policy.sandbox_receipt_outcome import SandboxReceiptBundle
from veritas_os.policy.sandbox_reconciliation_archive import SandboxReconciliationArchive
from veritas_os.security.hash import sha256_of_canonical_json
from veritas_os.tests.helpers.proof_provenance import (
    REPO_ROOT,
    verify_proof_provenance,
)

# Contract changes must be explicit, reviewed code changes. This in-repo pin is
# NOT an independent trust root; external reviewers need an out-of-band anchor.
CONTRACT_DIGEST = "7bf329ae8077510b99c387811382196693bc4f5257e3c563be652661dbf43a52"


class ProofError(ValueError):
    """A required controlled proof invariant was not observed."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise ProofError(code)


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, "DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _constant(_: str) -> None:
    raise ProofError("NON_FINITE_JSON")


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_object,
            parse_constant=_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProofError("INVALID_JSON") from exc
    require(isinstance(value, dict), "NON_OBJECT_JSON")
    return value


def verify_contract(contract: dict[str, Any]) -> None:
    # One source of expected values: the pinned contract JSON. No second
    # hand-maintained Python list of all scenario conditions or predicates.
    require(contract.get("format_version") == "veritas-reviewer-proof-contract/v1",
            "WRONG_CONTRACT_VERSION")
    require(sha256_of_canonical_json(contract) == CONTRACT_DIGEST,
            "CONTRACT_DRIFT_OR_WEAKENING")


def _value(value: dict[str, Any], *path: str) -> Any:
    item: Any = value
    for key in path:
        require(type(item) is dict and key in item, "MISSING_EVIDENCE_FIELD")
        item = item[key]
    return item


def _same(a: Any, b: Any, code: str) -> None:
    require(type(a) is type(b) and a == b, code)


def verify_report(
    contract: dict[str, Any],
    report: dict[str, Any],
    evidence: dict[str, Any],
) -> None:
    """Check pinned expectations, hashes and report/evidence linkage."""
    verify_contract(contract)
    _same(report.get("format_version"), contract["report_format"], "REPORT_FORMAT")
    _same(evidence.get("format_version"), contract["evidence_format"], "EVIDENCE_FORMAT")
    _same(report.get("proof"), contract["proof"], "PROOF_SCOPE")
    _same(report.get("result"), "PASS", "PROOF_FAILED")
    for name in ("decision_capture_mode", "external_effect_scope"):
        _same(report.get(name), contract[name], "PROOF_SCOPE")
    for name in contract["required_true_claims"]:
        require(report.get(name) is True, "MISSING_CONTROLLED_CLAIM")
    for name in contract["required_false_claims"]:
        require(report.get(name) is False, "UNSUPPORTED_PRODUCTION_CLAIM")
    require(type(report.get("proof_non_claims")) is list
            and set(report["proof_non_claims"]) == set(contract["required_non_claims"])
            and len(report["proof_non_claims"]) == len(contract["required_non_claims"]),
            "MISSING_NONCLAIMS")
    conjunction = report.get("proof_conjunction")
    require(type(conjunction) is dict
            and set(conjunction) == set(contract["required_conjunction"])
            and len(conjunction) == len(contract["required_conjunction"]),
            "INCOMPLETE_PROOF_CONJUNCTION")
    require(all(state is True for state in conjunction.values()),
            "UNPROVEN_PREDICATE")
    _same(report.get("sandbox_rows_added"),
          contract["expected_sandbox_rows_added"], "EFFECT_COUNT")
    require(type(report.get("sandbox_rows_added")) is int, "EFFECT_COUNT_TYPE")

    require(sha256_of_canonical_json(evidence) == report.get("evidence_hash"),
            "EVIDENCE_HASH")
    report_body = {key: val for key, val in report.items()
                   if key != "proof_manifest_hash"}
    require(sha256_of_canonical_json(report_body) ==
            report.get("proof_manifest_hash"), "REPORT_HASH")

    for case in contract["scenario_keys"]:
        current, detail = _value(report, case), _value(evidence, case)
        require(type(current) is dict and type(detail) is dict, "MISSING_CASE")
        for key, expected in contract["scenarios"][case].items():
            if key == "min_governance_rechecks":
                observed = current.get("governance_recheck_calls")
                require(type(observed) is int and observed >= expected,
                        "GOVERNANCE_RECHECKS")
            else:
                _same(current.get(key), expected, "CASE_RESULT_" + case)

        # Reuse VERITAS's native artifact shapes rather than inventing a
        # second authorization/receipt/reconciliation serialization contract.
        consumption = AuthorizationConsumptionRecord.model_validate(
            detail["consumption"],
        )
        archive = SandboxReconciliationArchive.model_validate(
            detail["reconciliation_archive"],
        )
        receipt = SandboxReceiptBundle.model_validate(detail["receipt_bundle"])
        consumed = consumption.model_dump(mode="json")
        digest = sha256_of_canonical_json({
            key: val for key, val in consumed.items()
            if key not in {"consumption_id", "consumption_hash"}
        })
        _same(consumption.consumption_hash, digest, "CONSUMPTION_HASH")
        _same(consumption.consumption_id,
              "labac:v1:sha256:" + digest, "CONSUMPTION_ID")
        _same(receipt.bundle_hash, sha256_of_canonical_json({
            "format_version": receipt.format_version,
            "bind_receipt": receipt.bind_receipt,
            "outcome_receipt": receipt.outcome_receipt,
        }), "RECEIPT_BUNDLE_HASH")

        cda = _value(detail, "canonical_decision_artifact")
        promotion = _value(detail, "promotion_packet")
        authorization = _value(detail, "native_authorization")
        for key, object_key in (
            ("decision_id", cda), ("decision_hash", cda),
            ("promotion_hash", promotion), ("authorization_id", authorization),
            ("consumption_id", consumed),
        ):
            _same(current.get(key), object_key[key], "CASE_LINK_" + key)
        _same(current.get("external_operation_reference"),
              archive.operation.operation_id, "EXTERNAL_OPERATION_LINK")
        _same(current.get("receipt_bundle_hash"), receipt.bundle_hash,
              "RECEIPT_LINK")
        _same(current.get("reconciliation_evidence_hash"),
              archive.proof.deterministic_digest(), "RECONCILIATION_DIGEST")
        _same(consumption.live_adapter_bind_authorization_id,
              authorization["authorization_id"], "AUTHORIZATION_CONSUMPTION_LINK")
        _same(consumption.live_adapter_bind_authorization_hash,
              authorization["authorization_hash"], "AUTHORIZATION_HASH_LINK")
        _same(archive.original_record.consumption_id,
              consumption.consumption_id, "ARCHIVE_CONSUMPTION_LINK")
        _same(archive.original_record.authorization_id,
              authorization["authorization_id"], "ARCHIVE_AUTHORIZATION_LINK")
        _same(archive.proof.evidence.external_operation_reference,
              archive.operation.operation_id, "ARCHIVE_OPERATION_LINK")
        bind = receipt.bind_receipt
        outcome = receipt.outcome_receipt
        _same(bind.get("decision_id"), cda["decision_id"], "BIND_DECISION_LINK")
        _same(bind.get("decision_hash"), cda["decision_hash"], "BIND_DECISION_HASH")
        _same(bind.get("execution_intent_id"),
              promotion["execution_intent_id"], "BIND_INTENT_LINK")
        _same(bind.get("execution_intent_hash"),
              promotion["execution_intent_hash"], "BIND_INTENT_HASH")
        _same(outcome.get("decision_id"), cda["decision_id"],
              "OUTCOME_DECISION_LINK")
        _same(outcome.get("execution_intent_id"),
              promotion["execution_intent_id"], "OUTCOME_INTENT_LINK")
        _same(outcome.get("bind_receipt_id"), bind.get("bind_receipt_id"),
              "OUTCOME_RECEIPT_LINK")
    _same(report["normal"]["consumption_id"] ==
          report["fault"]["consumption_id"], False, "CASES_NOT_DISTINCT")


def verify(
    contract: dict[str, Any], report: dict[str, Any], evidence: dict[str, Any],
    *, source_sha: str, base_sha: str, expected_tested_sha: str,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    # The original shared helper already validates real Git HEAD and all
    # three identities independently for both artifacts.
    verify_proof_provenance(
        report, evidence, source_sha=source_sha, base_sha=base_sha,
        expected_tested_sha=expected_tested_sha, repo_root=repo_root,
    )
    verify_report(contract, report, evidence)
    return {
        "format_version": "veritas-reviewer-proof-verification/v1",
        "result": "PASS_BOUNDED_CONSISTENCY_ONLY",
        "proof": contract["proof"], "tested_sha": expected_tested_sha,
        "source_sha": source_sha, "base_sha": base_sha,
        "contract_digest": CONTRACT_DIGEST,
        "verified_scenarios": contract["scenario_keys"],
        # The producer supplies these PASS flags. Presence and truthiness are
        # checked, but all predicates are NOT independently reconstructed.
        "producer_reported_pass_predicate_count": len(contract["required_conjunction"]),
        "all_producer_predicates_independently_recomputed": False,
        "independent_effect_observed": False,
        "independent_custody_proven": False,
        "production_proven": False, "third_party_certified": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("contract", "report", "evidence"):
        parser.add_argument("--" + field, required=True, type=Path)
    for field in ("tested-sha", "source-sha", "base-sha"):
        parser.add_argument("--" + field, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = verify(
            load_json(args.contract), load_json(args.report),
            load_json(args.evidence), source_sha=args.source_sha,
            base_sha=args.base_sha, expected_tested_sha=args.tested_sha,
        )
        result["contract_file_sha256"] = hashlib.sha256(
            args.contract.read_bytes(),
        ).hexdigest()
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2, sort_keys=True)
                                   + "\n", encoding="utf-8")
    except (ValueError, OSError, KeyError) as exc:
        print("REVIEWER_PROOF_CONTRACT_V1 FAIL: " + str(exc), file=sys.stderr)
        return 1
    print("REVIEWER_PROOF_CONTRACT_V1 PASS_BOUNDED_CONSISTENCY_ONLY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
