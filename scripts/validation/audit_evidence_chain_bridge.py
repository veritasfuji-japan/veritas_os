"""Read-only, local Audit Evidence Profile ↔ Evidence Chain Verifier bridge v0.1.

This module calls the existing verifier with supplied local artifacts; it never
accepts a serialized verifier result as proof. LINK_VERIFIED describes only
locally supplied, identity-bound evidence links, not actual effect, authentic
origin, independently established authority, external review or certification.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.validation.validate_audit_evidence_profile import verify as verify_profile
from veritas_os.governance.evidence_chain_manifest import (
    EvidenceChainManifest,
    validate_evidence_chain_manifest,
)
from veritas_os.governance.evidence_chain_verifier import (
    verify_evidence_chain_manifest,
)

BRIDGE_VERSION = "veritas.audit-evidence-chain-bridge/0.1"
SOURCE_VERIFIER = (
    "veritas_os.governance.evidence_chain_verifier.verify_evidence_chain_manifest"
)
CLAIM_LIMITATIONS = [
    "Local hashes and linked identifiers do not authenticate artifact origin.",
    "A locally verified chain is not proof of an actual effect or valid authority.",
    "The profile's case outcomes and reviewer/trust claims are not independently attested.",
    "Profile v0.1 does not include an operation_id or manifest_id binding field.",
    "This bridge does not modify runtime authorization, review or certification.",
]
_SOURCE_STATUSES = {
    "verified": "LINK_VERIFIED",
    "failed": "FAILED",
    "incomplete": "INCOMPLETE",
    "indeterminate": "INDETERMINATE",
}
_IDENTITY_FIELDS = (
    ("decision_id", "decision_id", True),
    ("intent_id", "execution_intent_id", True),
    ("authority_id", "authority_evidence_id", False),
    ("approval_id", "human_approval_receipt_id", False),
    ("bind_receipt_id", "bind_receipt_id", False),
    ("effect_receipt_id", "outcome_receipt_id", False),
)


def _blank_report(profile: Any, case_id: str) -> dict[str, Any]:
    return {
        "bridge_version": BRIDGE_VERSION,
        "status": "INDETERMINATE",
        "profile_packet_id": profile.get("packet_id") if isinstance(profile, dict) else None,
        "profile_case_id": case_id,
        "synthetic_example": profile.get("synthetic_example") if isinstance(profile, dict) else None,
        "source_verifier": SOURCE_VERIFIER,
        "source_verification_status": None,
        "chain_status": None,
        "manifest_id": None,
        "manifest_digest": None,
        "manifest_hash_matches": False,
        "identity_matches": {},
        "verified_links": [],
        "missing_links": [],
        "mismatched_links": [],
        "failure_reasons": [],
        "claim_limitations": list(CLAIM_LIMITATIONS),
    }


def _finish(report: dict[str, Any], status: str, *reasons: str) -> dict[str, Any]:
    report["status"] = status
    report["failure_reasons"] = sorted(
        set(report["failure_reasons"]).union(reason for reason in reasons if reason)
    )
    return report


def verify_audit_evidence_chain_bridge(
    *,
    profile: dict[str, Any],
    profile_path: Path,
    case_id: str,
    manifest: EvidenceChainManifest | None,
    verified_at: str,
    authority_evidence: Any | None = None,
    human_approval_receipt: Any | None = None,
    outcome_receipt: Any | None = None,
    verified_human_approval: Any | None = None,
    approval_required: bool = False,
    bind_coverage_operation_id: str | None = None,
    bind_receipt: Any | None = None,
) -> dict[str, Any]:
    """Validate the local profile and verify one explicitly matched chain.

    Only an in-process EvidenceChainManifest and supplied artifacts are allowed;
    caller-controlled serialized status JSON is not a verifier result. Returns
    a new report and does not change the profile, artifacts or manifest.
    """
    report = _blank_report(profile, case_id)

    if not isinstance(profile, dict) or not isinstance(case_id, str) or not case_id:
        return _finish(report, "FAILED", "INVALID_BRIDGE_INPUT")
    try:
        errors = verify_profile(profile, Path(profile_path))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return _finish(report, "FAILED", "PROFILE_VALIDATION_EXCEPTION")
    if errors:
        return _finish(report, "FAILED", "PROFILE_VALIDATION_FAILED", *sorted(errors))

    matching = [case for case in profile["cases"] if case["case_id"] == case_id]
    if len(matching) != 1:
        return _finish(report, "FAILED", "PROFILE_CASE_NOT_UNIQUE_OR_MISSING")
    case = matching[0]

    if manifest is None:
        return _finish(report, "FAILED", "CHAIN_MANIFEST_MISSING")
    if not isinstance(manifest, EvidenceChainManifest):
        return _finish(report, "FAILED", "UNTRUSTED_SERIALIZED_CHAIN_INPUT")

    report["manifest_id"] = manifest.manifest_id
    report["chain_status"] = manifest.chain_status
    try:
        report["manifest_digest"] = manifest.deterministic_digest()
        manifest_validation = validate_evidence_chain_manifest(manifest)
    except (AttributeError, KeyError, TypeError, ValueError):
        return _finish(report, "FAILED", "INVALID_CHAIN_MANIFEST")
    if not manifest_validation.is_valid:
        return _finish(
            report, "FAILED", "INVALID_CHAIN_MANIFEST",
            *manifest_validation.failure_reasons
        )

    missing_ids: list[str] = []
    mismatched_ids: list[str] = []
    for profile_key, manifest_key, required in _IDENTITY_FIELDS:
        expected = case.get(profile_key)
        actual = getattr(manifest, manifest_key)
        if not expected:
            report["identity_matches"][profile_key] = None
            if required:
                missing_ids.append(profile_key)
        elif not actual:
            report["identity_matches"][profile_key] = False
            missing_ids.append(profile_key)
        else:
            report["identity_matches"][profile_key] = expected == actual
            if expected != actual:
                mismatched_ids.append(profile_key)
    if mismatched_ids:
        return _finish(
            report, "FAILED", "CHAIN_IDENTITY_MISMATCH",
            *(f"MISMATCH_{key.upper()}" for key in mismatched_ids)
        )
    if missing_ids:
        return _finish(
            report, "INCOMPLETE", "CHAIN_IDENTITY_INCOMPLETE",
            *(f"MISSING_{key.upper()}" for key in missing_ids)
        )

    try:
        source = verify_evidence_chain_manifest(
            manifest=manifest,
            authority_evidence=authority_evidence,
            human_approval_receipt=human_approval_receipt,
            outcome_receipt=outcome_receipt,
            verified_human_approval=verified_human_approval,
            approval_required=approval_required,
            bind_coverage_operation_id=bind_coverage_operation_id,
            bind_receipt=bind_receipt,
            verified_at=verified_at,
        )
    except (AttributeError, KeyError, TypeError, ValueError):
        return _finish(report, "FAILED", "CHAIN_VERIFIER_EXCEPTION")

    report["source_verification_status"] = source.verification_status
    report["manifest_hash_matches"] = source.manifest_hash_matches
    report["verified_links"] = sorted(source.verified_links)
    report["missing_links"] = sorted(source.missing_links)
    report["mismatched_links"] = sorted(source.mismatched_links)
    report["failure_reasons"] = sorted(set(source.failure_reasons))

    mapped = _SOURCE_STATUSES.get(source.verification_status)
    if mapped is None or source.is_valid != (source.verification_status == "verified"):
        return _finish(report, "FAILED", "INCONSISTENT_SOURCE_VERIFIER_RESULT")
    if mapped != "LINK_VERIFIED":
        return _finish(report, mapped)

    # Existing verifier's 'verified' checks only the present local hash links.
    # A noncomplete chain, missing manifest links, or unobserved profile case
    # must not be promoted into an identity-bound positive profile report.
    if manifest.chain_status != "complete" or manifest.missing_links or source.missing_links:
        return _finish(report, "INCOMPLETE", "CHAIN_NOT_COMPLETE")
    if not profile["scope"]["execution_performed"]:
        return _finish(report, "INCOMPLETE", "PROFILE_SCOPE_NOT_EXECUTED")
    if not case["evidence_ids"]:
        return _finish(report, "INCOMPLETE", "CASE_HAS_NO_LOCAL_EVIDENCE")
    if case["observed"] not in ("PASS", "FAIL") or case["actual_effect"] in (
        "NOT_EXECUTED", "UNKNOWN"
    ):
        return _finish(report, "INCOMPLETE", "CASE_OUTCOME_UNOBSERVED")
    return _finish(report, "LINK_VERIFIED")


def serialize_bridge_report(report: dict[str, Any]) -> str:
    """Canonical, stable JSON report bytes (no timestamp or external calls)."""
    return json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
