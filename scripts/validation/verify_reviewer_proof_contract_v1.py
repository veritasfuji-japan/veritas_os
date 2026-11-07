#!/usr/bin/env python3
"""Offline, fail-closed consistency verifier for the controlled E2E only.

Not an independent executor, real customer effect, or third-party attestation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SHA40 = re.compile(r"[0-9a-f]{40}")
SHA256 = re.compile(r"[0-9a-f]{64}")
REQUIRED = frozenset((
    "current_head_source_recorded", "tested_checkout_sha_verified",
    "real_decide_route_exercised", "canonical_decisions_verified",
    "selected_action_bindings_verified", "decision_lineage_proven",
    "execution_intent_lineage_proven", "native_v2_authorizations_verified",
    "real_postgresql_consumption", "current_governance_rechecks_exercised",
    "real_certificate_validated_tls_post", "dedicated_postgresql_effect_persistence",
    "read_only_reconciliation_confirmed", "bind_receipt_decision_lineage_verified",
    "outcome_decision_lineage_verified", "fault_unknown_preserved",
    "no_blind_redispatch", "repeat_recovery_avoids_lookup",
))
FALSE_CLAIMS = frozenset((
    "production_claim", "production_decision_to_effect_e2e_proven",
    "trustlog_exactly_once_proven", "production_validation_proven",
))
NONCLAIMS = frozenset((
    "production readiness", "real customer credentials", "real customer endpoint",
    "independent production infrastructure", "external UTC clock trust",
    "TrustLog exactly-once publication", "regulatory approval or certification",
))
LINKS = (
    ("decision_id", ("canonical_decision_artifact", "decision_id")),
    ("decision_hash", ("canonical_decision_artifact", "decision_hash")),
    ("promotion_hash", ("promotion_packet", "promotion_hash")),
    ("authorization_id", ("native_authorization", "authorization_id")),
    ("consumption_id", ("consumption", "consumption_id")),
    ("receipt_bundle_hash", ("receipt_bundle", "bundle_hash")),
    ("external_operation_reference", ("reconciliation_archive", "operation", "operation_id")),
)

class ContractError(ValueError):
    """A review contract assertion failed."""


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ContractError(message)


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def invalid_constant(value: str) -> None:
    raise ContractError("invalid JSON constant: " + value)


def load_json(path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"),
                         object_pairs_hook=strict_object, parse_constant=invalid_constant)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError("invalid or unavailable JSON: " + path.name) from exc
    require(isinstance(obj, dict), "JSON root must be object")
    return obj


def nested(obj: dict[str, Any], path: tuple[str, ...]) -> Any:
    value: Any = obj
    for key in path:
        require(isinstance(value, dict) and key in value, "missing evidence: " + ".".join(path))
        value = value[key]
    return value


def validate(
    contract: dict[str, Any],
    report: dict[str, Any],
    evidence: dict[str, Any],
    *, tested_sha: str, source_sha: str, base_sha: str, checkout_sha: str,
) -> dict[str, Any]:
    """Check a frozen self-produced proof; no independent authenticity inferred."""
    require(contract.get("format_version") == "veritas-reviewer-proof-contract/v1",
            "wrong contract version")
    require(contract.get("proof") == "CONTROLLED_CURRENT_HEAD_DECISION_TO_EFFECT_E2E",
            "wrong proof")
    require(contract.get("report_format") == "controlled-decision-to-effect-e2e/v1"
            and contract.get("evidence_format") == "controlled-decision-to-effect-evidence/v1",
            "wrong proof artifact versions")
    require(contract.get("scope") == "CONTROLLED_SYNTHETIC_TLS_POSTGRESQL_E2E_ONLY"
            and contract.get("decision_capture_mode") ==
            "REAL_POST_V1_DECIDE_WITH_CONTROLLED_MODEL_OUTPUT"
            and contract.get("external_effect_scope") ==
            "SYNTHETIC_SANDBOX_EVENT_PERSISTENCE", "unexpected claim scope")
    require(contract.get("scenario_keys") == ["normal", "fault"], "missing proof case")
    predicates = contract.get("required_conjunction")
    require(isinstance(predicates, list) and len(predicates) == len(REQUIRED)
            and set(predicates) == REQUIRED, "required predicates weakened")
    require(contract.get("required_true_claims") ==
            ["controlled_decision_to_effect_e2e_proven"], "positive claim weakened")
    false_claims = contract.get("required_false_claims")
    require(isinstance(false_claims, list) and len(false_claims) == len(FALSE_CLAIMS)
            and set(false_claims) == FALSE_CLAIMS, "false claims weakened")
    nonclaims = contract.get("required_non_claims")
    require(isinstance(nonclaims, list) and len(nonclaims) == len(NONCLAIMS)
            and set(nonclaims) == NONCLAIMS, "nonclaims weakened")
    require(type(contract.get("expected_sandbox_rows_added")) is int
            and contract["expected_sandbox_rows_added"] == 2, "effect-count scope weakened")
    for label, value in (("tested", tested_sha), ("source", source_sha),
                         ("base", base_sha), ("checkout", checkout_sha)):
        require(isinstance(value, str) and SHA40.fullmatch(value) is not None,
                "malformed SHA: " + label)
    require(tested_sha == checkout_sha, "checked-out HEAD differs from event SHA")
    for label, artifact in (("report", report), ("evidence", evidence)):
        for name, expected in (("tested_sha", tested_sha),
                               ("source_sha", source_sha), ("base_sha", base_sha)):
            require(artifact.get(name) == expected,
                    "provenance mismatch: " + label + "." + name)

    require(report.get("format_version") == contract["report_format"]
            and evidence.get("format_version") == contract["evidence_format"],
            "artifact format mismatch")
    require(report.get("result") == "PASS" and report.get("proof") == contract["proof"],
            "controlled proof is not PASS")
    require(report.get("decision_capture_mode") == contract["decision_capture_mode"]
            and report.get("external_effect_scope") == contract["external_effect_scope"],
            "report scope mismatch")
    for field in false_claims:
        require(report.get(field) is False, "unsupported production claim: " + field)
    require(report.get("controlled_decision_to_effect_e2e_proven") is True,
            "controlled proof not claimed")
    declared_nonclaims = report.get("proof_non_claims")
    require(isinstance(declared_nonclaims, list)
            and len(declared_nonclaims) == len(NONCLAIMS)
            and set(declared_nonclaims) == NONCLAIMS, "missing proof nonclaim")
    conjunction = report.get("proof_conjunction")
    require(isinstance(conjunction, dict) and set(conjunction) == REQUIRED,
            "incomplete or extended proof conjunction")
    for field, state in conjunction.items():
        require(state is True, "unproven predicate: " + field)
    require(type(report.get("sandbox_rows_added")) is int
            and report["sandbox_rows_added"] == 2, "unexpected sandbox event count")
    require(isinstance(report.get("alembic_head"), str) and bool(report["alembic_head"]),
            "missing migration provenance")

    scenarios = contract.get("scenarios")
    require(isinstance(scenarios, dict) and set(scenarios) == {"normal", "fault"},
            "scenario set changed")
    for case in ("normal", "fault"):
        expected = scenarios[case]
        current, detail = report.get(case), evidence.get(case)
        require(isinstance(expected, dict) and isinstance(current, dict)
                and isinstance(detail, dict), "missing scenario: " + case)
        require(expected.get("min_governance_rechecks") == 3
                and type(expected["min_governance_rechecks"]) is int,
                "recheck threshold weakened")
        for key, value in expected.items():
            if key == "min_governance_rechecks":
                current_value = current.get("governance_recheck_calls")
                require(type(current_value) is int and current_value >= value,
                        "too few governance checks: " + case)
            else:
                require(current.get(key) == value
                        and type(current[key]) is type(value),
                        "case expectation mismatch: " + case + "." + key)
        for report_key, evidence_path in LINKS:
            observed = current.get(report_key)
            require(isinstance(observed, str) and bool(observed)
                    and observed == nested(detail, evidence_path),
                    "case identity mismatch: " + case + "." + report_key)
    require(report["normal"]["decision_id"] != report["fault"]["decision_id"]
            and report["normal"]["consumption_id"] != report["fault"]["consumption_id"],
            "cases are not independent")

    evidence_digest = report.get("evidence_hash")
    require(isinstance(evidence_digest, str)
            and SHA256.fullmatch(evidence_digest) is not None
            and evidence_digest == canonical_hash(evidence), "evidence hash mismatch")
    manifest_digest = report.get("proof_manifest_hash")
    body = dict(report)
    body.pop("proof_manifest_hash", None)
    require(isinstance(manifest_digest, str)
            and SHA256.fullmatch(manifest_digest) is not None
            and manifest_digest == canonical_hash(body), "proof manifest hash mismatch")
    return {
        "format_version": "veritas-reviewer-proof-verification/v1",
        "result": "PASS_BOUNDED_CONSISTENCY_ONLY",
        "proof": contract["proof"], "scope": contract["scope"],
        "tested_sha": tested_sha, "source_sha": source_sha, "base_sha": base_sha,
        "verified_scenarios": ["normal", "fault"],
        "verified_predicate_count": len(REQUIRED),
        "evidence_hash": evidence_digest, "proof_manifest_hash": manifest_digest,
        "independent_custody_proven": False, "independent_effect_observed": False,
        "production_proven": False, "third_party_certified": False,
    }


def git_checkout_head() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise ContractError("git checkout HEAD unavailable") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("contract", "report", "evidence"):
        parser.add_argument("--" + name, required=True, type=Path)
    for name in ("tested-sha", "source-sha", "base-sha"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = validate(
            load_json(args.contract), load_json(args.report), load_json(args.evidence),
            tested_sha=args.tested_sha, source_sha=args.source_sha,
            base_sha=args.base_sha, checkout_sha=git_checkout_head(),
        )
        result["contract_sha256"] = hashlib.sha256(args.contract.read_bytes()).hexdigest()
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8",
            )
    except (ContractError, OSError, UnicodeError) as exc:
        print("REVIEWER_PROOF_CONTRACT_V1 FAIL: " + str(exc), file=sys.stderr)
        return 1
    print("REVIEWER_PROOF_CONTRACT_V1 PASS_BOUNDED_CONSISTENCY_ONLY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
