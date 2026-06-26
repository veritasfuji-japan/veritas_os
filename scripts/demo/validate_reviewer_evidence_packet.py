#!/usr/bin/env python3
"""Build a deterministic local/offline validation report for reviewer packets."""

from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.demo.verifier_lifecycle import (  # noqa: E402
    validate_human_approval_verifier_lifecycle_snapshot,
)
from scripts.demo.export_reviewer_evidence_packet import (  # noqa: E402
    BOUNDARY_NOTE,
    PACKET_ID,
    PACKET_VERSION,
    build_reviewer_evidence_packet,
    compute_reviewer_packet_hash,
)

REPORT_ID = "reviewer-evidence-packet-validation-report-v1"
REPORT_VERSION = "v1"
FIXTURE_PATH = (
    REPO_ROOT
    / "docs/en/demo/fixtures/reviewer-evidence-packet-saas-permission-change-v1.json"
)
SCHEMA_PATH = REPO_ROOT / "docs/en/demo/schemas/reviewer-evidence-packet-v1.schema.json"
SHA256_HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_TOP_LEVEL_FIELDS = [
    "packet_id",
    "packet_version",
    "demo_id",
    "generated_at",
    "title",
    "summary",
    "boundary_note",
    "local_offline_only",
    "cases",
    "aggregate_summary",
    "reviewer_notes",
    "packet_hash",
]
REQUIRED_CASE_FIELDS = [
    "case_id",
    "expected_outcome",
    "actual_outcome",
    "passed",
    "requested_scope",
    "target_system",
    "target_resource",
    "authority_validation_status",
    "runtime_recommended_outcome",
    "human_approval_summary",
    "verifier_lifecycle_summary",
    "refusal_basis",
    "failure_reasons",
    "outcome_receipt_summary",
    "evidence_chain_manifest_summary",
    "evidence_chain_verification_summary",
    "reviewer_interpretation",
    "boundary_note",
]
REQUIRED_FALLBACK_CASE_SUMMARIES = [
    "outcome_receipt_summary",
    "evidence_chain_manifest_summary",
    "evidence_chain_verification_summary",
]
CASE_EXPECTED_OUTCOMES = {
    "missing_authority": "block",
    "missing_human_approval": "block",
    "expired_human_approval": "block",
    "scope_mismatch": "block",
}
VALID_COMMIT_OUTCOMES = {"commit", "commit_eligible"}
VALID_CASE_ID = "valid_authority_and_approval"
REVIEWER_NOTES = [
    "This report validates a local/offline Reviewer Evidence Packet fixture.",
    (
        "It checks generated packet equality, packet hash recomputation, "
        "schema or fallback structural validation, case expectations, and "
        "evidence-chain verification summaries."
    ),
    (
        "It does not connect to live SaaS, IAM, IdP, SSO, customer "
        "directories, banks, sanctions systems, production approval workflows, "
        "or live audit stores."
    ),
    (
        "It is not legal advice, regulatory approval, third-party "
        "certification, production audit certification, or proof of live "
        "deployment."
    ),
]
FAILURE_REASON_BY_CHECK = {
    "golden_fixture_exists": "golden_fixture_missing",
    "golden_fixture_json_parseable": "golden_fixture_json_unparseable",
    "generated_packet_matches_golden_fixture": "generated_packet_mismatch",
    "packet_hash_present": "packet_hash_missing",
    "packet_hash_length_valid": "packet_hash_length_invalid",
    "packet_hash_recomputes": "packet_hash_recompute_mismatch",
    "schema_file_exists": "schema_file_missing",
    "schema_json_parseable": "schema_json_unparseable",
    "schema_validation_status": "schema_validation_failed",
    "required_top_level_fields_present": "required_top_level_fields_missing",
    "required_case_fields_present": "required_case_fields_missing",
    "case_expectations_passed": "case_expectations_failed",
    "blocked_cases_have_refusal_basis": "blocked_case_refusal_basis_missing",
    "blocked_cases_have_outcome_failure_reasons": (
        "blocked_case_outcome_failure_reasons_missing"
    ),
    "evidence_chain_verification_present": "evidence_chain_verification_missing",
    "valid_case_chain_verified": "valid_case_chain_not_verified",
    "no_mismatched_links_in_demo": "demo_mismatched_links_present",
    "approval_proof_continuity_valid": (
        "reviewer_packet_human_approval_proof_continuity_invalid"
    ),
    "verifier_lifecycle_valid": (
        "reviewer_packet_verifier_lifecycle_invalid"
    ),
    "local_offline_boundary_present": "local_offline_boundary_missing",
}


def _load_json_file(path: Path) -> tuple[dict[str, Any] | None, bool, bool]:
    """Load a local JSON object and return object, exists, and parse status."""
    exists = path.is_file()
    if not exists:
        return None, False, False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, True, False
    if not isinstance(payload, dict):
        return None, True, False
    return payload, True, True


def _jsonschema_module() -> Any | None:
    """Return the optional jsonschema module when it is locally available."""
    try:
        import jsonschema
    except ImportError:
        return None
    return jsonschema


def _has_required_fields(payload: dict[str, Any], required: list[str]) -> bool:
    """Return whether all required keys are present in a mapping."""
    return all(field in payload for field in required)


def _required_case_fields_present(packet: dict[str, Any]) -> bool:
    """Return whether every packet case has required reviewer-facing fields."""
    cases = packet.get("cases")
    if not isinstance(cases, list) or not cases:
        return False
    return all(
        isinstance(case, dict) and _has_required_fields(case, REQUIRED_CASE_FIELDS)
        for case in cases
    )


def _fallback_structural_validation(packet: dict[str, Any]) -> bool:
    """Run deterministic local structural checks when jsonschema is unavailable."""
    if not _has_required_fields(packet, REQUIRED_TOP_LEVEL_FIELDS):
        return False
    if packet.get("packet_id") != PACKET_ID:
        return False
    if packet.get("packet_version") != PACKET_VERSION:
        return False
    if packet.get("local_offline_only") is not True:
        return False
    if not SHA256_HEX_PATTERN.fullmatch(str(packet.get("packet_hash", ""))):
        return False
    cases = packet.get("cases")
    if not isinstance(cases, list) or not cases:
        return False
    if not isinstance(packet.get("aggregate_summary"), dict):
        return False
    for case in cases:
        if not isinstance(case, dict):
            return False
        if not all(field in case for field in REQUIRED_FALLBACK_CASE_SUMMARIES):
            return False
    return True


def _schema_validation_status(
    generated_packet: dict[str, Any],
    golden_packet: dict[str, Any] | None,
    schema: dict[str, Any] | None,
) -> tuple[str, str]:
    """Validate packets with jsonschema or deterministic fallback checks."""
    jsonschema = _jsonschema_module()
    if jsonschema is None:
        generated_valid = _fallback_structural_validation(generated_packet)
        golden_valid = golden_packet is not None and _fallback_structural_validation(
            golden_packet
        )
        if generated_valid and golden_valid:
            return "skipped", "fallback"
        return "fail", "fallback"
    if schema is None or golden_packet is None:
        return "fail", "jsonschema"
    try:
        validator = jsonschema.Draft202012Validator(schema)
        validator.validate(generated_packet)
        validator.validate(golden_packet)
    except jsonschema.ValidationError:
        return "fail", "jsonschema"
    except jsonschema.SchemaError:
        return "fail", "jsonschema"
    return "pass", "jsonschema"


def _case_expectations_passed(packet: dict[str, Any]) -> bool:
    """Return whether deterministic demo case outcomes still hold."""
    cases = packet.get("cases")
    if not isinstance(cases, list):
        return False
    if len(cases) != 5:
        return False
    cases_by_id = {
        case.get("case_id"): case for case in cases if isinstance(case, dict)
    }
    for case_id, expected_outcome in CASE_EXPECTED_OUTCOMES.items():
        if cases_by_id.get(case_id, {}).get("actual_outcome") != expected_outcome:
            return False
    valid_case = cases_by_id.get(VALID_CASE_ID, {})
    if valid_case.get("actual_outcome") not in VALID_COMMIT_OUTCOMES:
        return False
    return all(case.get("passed") is True for case in cases)


def _blocked_cases_have_refusal_basis(packet: dict[str, Any]) -> bool:
    """Return whether blocked demo cases include top-level refusal bases."""
    cases = packet.get("cases")
    if not isinstance(cases, list):
        return False
    blocked_cases = [case for case in cases if case.get("actual_outcome") == "block"]
    if not blocked_cases:
        return False
    return all(bool(case.get("refusal_basis")) for case in blocked_cases)


def _blocked_cases_have_outcome_failure_reasons(packet: dict[str, Any]) -> bool:
    """Return whether blocked cases include outcome receipt failure reasons."""
    cases = packet.get("cases")
    if not isinstance(cases, list):
        return False
    blocked_cases = [case for case in cases if case.get("actual_outcome") == "block"]
    if not blocked_cases:
        return False
    return all(
        bool(case.get("outcome_receipt_summary", {}).get("failure_reasons"))
        for case in blocked_cases
    )


def _evidence_chain_verification_present(packet: dict[str, Any]) -> bool:
    """Return whether every case includes evidence-chain verification summary."""
    cases = packet.get("cases")
    if not isinstance(cases, list) or not cases:
        return False
    return all(
        isinstance(case, dict)
        and isinstance(case.get("evidence_chain_verification_summary"), dict)
        for case in cases
    )


def _valid_case_chain_verified(packet: dict[str, Any]) -> bool:
    """Return whether the valid authority case has a verified evidence chain."""
    cases = packet.get("cases")
    if not isinstance(cases, list):
        return False
    for case in cases:
        if case.get("case_id") != VALID_CASE_ID:
            continue
        summary = case.get("evidence_chain_verification_summary", {})
        return (
            summary.get("verification_status") == "verified"
            and summary.get("is_valid") is True
        )
    return False


def _no_mismatched_links_in_demo(packet: dict[str, Any]) -> bool:
    """Return whether no demo case has mismatched evidence-chain links."""
    cases = packet.get("cases")
    if not isinstance(cases, list) or not cases:
        return False
    return all(
        not case.get("evidence_chain_verification_summary", {}).get(
            "mismatched_links"
        )
        for case in cases
    )


def _case_approval_proof_continuity_reasons(case: dict[str, Any]) -> list[str]:
    """Return reviewer-facing approval proof continuity validation reasons.

    Reviewer packets must prove that approval-required cases bind the same
    verified human approval proof hash in the EvidenceChainManifest, the
    OutcomeReceipt metadata, and verified evidence-chain links.
    """
    reasons: list[str] = []
    manifest = case.get("evidence_chain_manifest_summary", {})
    outcome = case.get("outcome_receipt_summary", {})
    verification = case.get("evidence_chain_verification_summary")
    if not isinstance(manifest, dict):
        manifest = {}
    if not isinstance(outcome, dict):
        outcome = {}

    committed = outcome.get("committed") is True
    has_proof_binding = bool(
        manifest.get("verified_human_approval_proof_hash")
        or (
            isinstance(outcome.get("metadata", {}), dict)
            and outcome.get("metadata", {}).get(
                "verified_human_approval_proof_hash"
            )
        )
    )
    approval_required = manifest.get("human_approval_required") is True
    if not approval_required or (not committed and not has_proof_binding):
        return reasons

    manifest_hash = str(
        manifest.get("verified_human_approval_proof_hash") or ""
    ).strip()
    metadata = outcome.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    outcome_hash = str(
        metadata.get("verified_human_approval_proof_hash") or ""
    ).strip()

    if not manifest_hash:
        reasons.append("reviewer_packet_human_approval_proof_hash_missing")
    if not outcome_hash:
        reasons.append("reviewer_packet_outcome_human_approval_proof_hash_missing")
    if manifest_hash and outcome_hash and manifest_hash != outcome_hash:
        reasons.append("reviewer_packet_human_approval_proof_hash_mismatch")

    summary = case.get("human_approval_summary", {})
    if not isinstance(summary, dict):
        summary = {}
    if not str(summary.get("verifier_id") or "").strip():
        reasons.append("reviewer_packet_verifier_id_missing")
    if not str(summary.get("verifier_policy_id") or "").strip():
        reasons.append("reviewer_packet_verifier_policy_id_missing")
    proof_policy_hash = str(summary.get("verifier_policy_hash") or "").strip()
    manifest_policy_hash = str(
        manifest.get("human_approval_verifier_policy_hash") or ""
    ).strip()
    outcome_policy_hash = str(
        metadata.get("human_approval_verifier_policy_hash") or ""
    ).strip()
    if not proof_policy_hash or not manifest_policy_hash or not outcome_policy_hash:
        reasons.append("reviewer_packet_verifier_policy_hash_missing")
    if (
        proof_policy_hash
        and manifest_policy_hash
        and proof_policy_hash != manifest_policy_hash
    ):
        reasons.append("reviewer_packet_verifier_policy_hash_mismatch")
    if (
        outcome_policy_hash
        and manifest_policy_hash
        and outcome_policy_hash != manifest_policy_hash
    ):
        reasons.append("reviewer_packet_verifier_policy_hash_mismatch")

    if isinstance(verification, dict):
        status = verification.get("verification_status")
        verified_links = verification.get("verified_links", [])
        if not isinstance(verified_links, list):
            verified_links = []
        failure_reasons = verification.get("failure_reasons", [])
        if not isinstance(failure_reasons, list):
            failure_reasons = []
        continuity_failure_reasons = {
            "human_approval_proof_hash_missing",
            "outcome_human_approval_proof_hash_mismatch",
            "manifest_human_approval_proof_hash_mismatch",
            "human_approval_proof_hash_mismatch",
        }
        if (
            status == "verified"
            and "verified_human_approval_proof_hash" not in verified_links
        ):
            reasons.append("reviewer_packet_human_approval_proof_link_not_verified")
        if status in {"failed", "incomplete"} and (
            "verified_human_approval_proof_hash"
            in verification.get("missing_links", [])
            or "outcome_verified_human_approval_proof_hash" in verification.get(
                "missing_links", []
            )
            or "verified_human_approval_proof_hash" in verification.get(
                "mismatched_links", []
            )
            or "outcome_verified_human_approval_proof_hash" in verification.get(
                "mismatched_links", []
            )
        ):
            if not any(
                reason in continuity_failure_reasons for reason in failure_reasons
            ):
                reasons.append(
                    "reviewer_packet_human_approval_proof_link_not_verified"
                )
    return reasons


def _approval_proof_continuity_reasons(packet: dict[str, Any]) -> list[str]:
    """Return deterministic approval proof continuity reasons for all cases."""
    cases = packet.get("cases")
    if not isinstance(cases, list):
        return ["required_case_fields_missing"]
    reasons: list[str] = []
    for case in cases:
        if not isinstance(case, dict):
            reasons.append("required_case_fields_missing")
            continue
        for reason in _case_approval_proof_continuity_reasons(case):
            if reason not in reasons:
                reasons.append(reason)
    return reasons


def _approval_proof_continuity_valid(packet: dict[str, Any]) -> bool:
    """Return whether all cases preserve reviewer approval proof continuity."""
    return not _approval_proof_continuity_reasons(packet)


def _verifier_lifecycle_reasons(packet: dict[str, Any]) -> list[str]:
    """Return deterministic verifier lifecycle validation reasons."""
    cases = packet.get("cases")
    if not isinstance(cases, list):
        return ["required_case_fields_missing"]
    reasons: list[str] = []
    for case in cases:
        if not isinstance(case, dict):
            continue
        human_approval = case.get("human_approval_summary", {})
        if not isinstance(human_approval, dict):
            continue
        case_reasons = validate_human_approval_verifier_lifecycle_snapshot(
            human_approval_summary=human_approval,
            lifecycle_snapshot=case.get("verifier_lifecycle_summary"),
            proof_verified_at=human_approval.get("verified_at"),
        )
        for reason in case_reasons:
            if reason not in reasons:
                reasons.append(reason)
    return reasons


def _verifier_lifecycle_valid(packet: dict[str, Any]) -> bool:
    """Return whether approval proofs carry valid verifier lifecycle evidence."""
    return not _verifier_lifecycle_reasons(packet)


def _local_offline_boundary_present(packet: dict[str, Any]) -> bool:
    """Return whether packet-level local/offline boundary markers are present."""
    boundary_note = packet.get("boundary_note")
    return (
        packet.get("local_offline_only") is True
        and isinstance(boundary_note, str)
        and bool(boundary_note)
    )


def _build_checks(
    generated_packet: dict[str, Any],
    golden_packet: dict[str, Any] | None,
    schema: dict[str, Any] | None,
    fixture_exists: bool,
    fixture_parseable: bool,
    schema_exists: bool,
    schema_parseable: bool,
) -> dict[str, Any]:
    """Build deterministic validation check statuses for the report."""
    schema_status, schema_mode = _schema_validation_status(
        generated_packet, golden_packet, schema
    )
    packet_hash = generated_packet.get("packet_hash")
    return {
        "golden_fixture_exists": fixture_exists,
        "golden_fixture_json_parseable": fixture_parseable,
        "generated_packet_matches_golden_fixture": generated_packet == golden_packet,
        "packet_hash_present": bool(packet_hash),
        "packet_hash_length_valid": isinstance(packet_hash, str)
        and bool(SHA256_HEX_PATTERN.fullmatch(packet_hash)),
        "packet_hash_recomputes": packet_hash
        == compute_reviewer_packet_hash(generated_packet),
        "schema_file_exists": schema_exists,
        "schema_json_parseable": schema_parseable,
        "schema_validation_status": schema_status,
        "schema_validation_mode": schema_mode,
        "required_top_level_fields_present": _has_required_fields(
            generated_packet, REQUIRED_TOP_LEVEL_FIELDS
        ),
        "required_case_fields_present": _required_case_fields_present(generated_packet),
        "case_expectations_passed": _case_expectations_passed(generated_packet),
        "blocked_cases_have_refusal_basis": _blocked_cases_have_refusal_basis(
            generated_packet
        ),
        "blocked_cases_have_outcome_failure_reasons": (
            _blocked_cases_have_outcome_failure_reasons(generated_packet)
        ),
        "evidence_chain_verification_present": _evidence_chain_verification_present(
            generated_packet
        ),
        "valid_case_chain_verified": _valid_case_chain_verified(generated_packet),
        "no_mismatched_links_in_demo": _no_mismatched_links_in_demo(generated_packet),
        "approval_proof_continuity_valid": _approval_proof_continuity_valid(
            generated_packet
        ),
        "verifier_lifecycle_valid": _verifier_lifecycle_valid(generated_packet),
        "verifier_lifecycle_reasons": _verifier_lifecycle_reasons(generated_packet),
        "local_offline_boundary_present": _local_offline_boundary_present(
            generated_packet
        ),
    }


def _failure_reasons(checks: dict[str, Any]) -> list[str]:
    """Return stable failure reason codes for failed required checks."""
    reasons: list[str] = []
    for check_name, reason in FAILURE_REASON_BY_CHECK.items():
        value = checks[check_name]
        failed = value is False or (
            check_name == "schema_validation_status" and value == "fail"
        )
        if failed:
            reasons.append(reason)
    for reason in checks.get("approval_proof_continuity_reasons", []):
        if reason not in reasons:
            reasons.append(reason)
    for reason in checks.get("verifier_lifecycle_reasons", []):
        if reason not in reasons:
            reasons.append(reason)
    return reasons


def _aggregate_summary(packet: dict[str, Any]) -> dict[str, Any]:
    """Return aggregate summary values copied from the generated packet."""
    source = packet.get("aggregate_summary", {})
    return {
        "total_cases": source.get("total_cases", 0),
        "passed_cases": source.get("passed_cases", 0),
        "blocked_cases": source.get("blocked_cases", 0),
        "committed_cases": source.get("committed_cases", 0),
        "verified_chains": source.get("verified_chains", 0),
        "failed_chains": source.get("failed_chains", 0),
        "incomplete_chains": source.get("incomplete_chains", 0),
        "indeterminate_chains": source.get("indeterminate_chains", 0),
        "local_offline_only": bool(source.get("local_offline_only", False)),
    }


def _build_report_for_packet(
    generated_packet: dict[str, Any],
    golden_packet: dict[str, Any] | None,
    schema: dict[str, Any] | None,
    fixture_exists: bool,
    fixture_parseable: bool,
    schema_exists: bool,
    schema_parseable: bool,
) -> dict[str, Any]:
    """Build a validation report from already loaded local artifacts."""
    packet = copy.deepcopy(generated_packet)
    checks = _build_checks(
        packet,
        copy.deepcopy(golden_packet),
        copy.deepcopy(schema),
        fixture_exists,
        fixture_parseable,
        schema_exists,
        schema_parseable,
    )
    checks["approval_proof_continuity_reasons"] = (
        _approval_proof_continuity_reasons(packet)
    )
    failure_reasons = _failure_reasons(checks)
    return {
        "report_id": REPORT_ID,
        "report_version": REPORT_VERSION,
        "generated_at": packet.get("generated_at"),
        "packet_id": packet.get("packet_id"),
        "packet_version": packet.get("packet_version"),
        "status": "pass" if not failure_reasons else "fail",
        "local_offline_only": True,
        "checks": checks,
        "aggregate_summary": _aggregate_summary(packet),
        "failure_reasons": failure_reasons,
        "reviewer_notes": list(REVIEWER_NOTES),
        "boundary_note": packet.get("boundary_note", BOUNDARY_NOTE),
    }


def build_reviewer_evidence_packet_validation_report() -> dict[str, Any]:
    """Build the deterministic local/offline reviewer validation report.

    The report uses only checked-in local files and deterministic packet builders.
    It performs no network calls and does not require credentials.
    """
    generated_packet = build_reviewer_evidence_packet()
    golden_packet, fixture_exists, fixture_parseable = _load_json_file(FIXTURE_PATH)
    schema, schema_exists, schema_parseable = _load_json_file(SCHEMA_PATH)
    return _build_report_for_packet(
        generated_packet,
        golden_packet,
        schema,
        fixture_exists,
        fixture_parseable,
        schema_exists,
        schema_parseable,
    )


def main() -> int:
    """Print deterministic validation report JSON and return status code."""
    report = build_reviewer_evidence_packet_validation_report()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
