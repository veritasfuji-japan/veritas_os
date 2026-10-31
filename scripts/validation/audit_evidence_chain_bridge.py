"""Read-only, local Audit Evidence Profile ↔ Evidence Chain Verifier bridge v0.1.

This module calls the existing verifier with supplied local artifacts; it never
accepts a serialized verifier result as proof. LINK_VERIFIED describes only
locally supplied, identity-bound evidence links, not actual effect, authentic
origin, independently established authority, external review or certification.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
from typing import Any

from scripts.validation.validate_audit_evidence_profile import (
    V02_PROFILE_VERSION,
    verify as verify_profile,
)
from veritas_os.governance.evidence_chain_manifest import (
    EvidenceChainManifest,
    validate_evidence_chain_manifest,
)
from veritas_os.governance.evidence_chain_verifier import (
    verify_evidence_chain_manifest,
)
from veritas_os.security.hash import canonical_json_dumps, sha256_hex

BRIDGE_VERSION = "veritas.audit-evidence-chain-bridge/0.1"
BRIDGE_VERSION_V02 = "veritas.audit-evidence-chain-bridge/0.2"
SOURCE_VERIFIER = (
    "veritas_os.governance.evidence_chain_verifier.verify_evidence_chain_manifest"
)
CLAIM_LIMITATIONS = [
    "Local hashes and linked identifiers do not authenticate artifact origin.",
    "A locally verified chain is not proof of an actual effect or valid authority.",
    "The profile's case outcomes and reviewer/trust claims are not independently attested.",
    "Profile v0.1 does not include an operation_id or manifest_id binding field.",
    "The manifest is bound to a local evidence file by canonical JSON bytes, not by an external signature.",
    "This bridge does not modify runtime authorization, review or certification.",
]
_SOURCE_STATUSES = {
    "verified": "LINK_VERIFIED",
    "failed": "FAILED",
    "incomplete": "INCOMPLETE",
    "indeterminate": "INDETERMINATE",
}
_REQUIRED_HASH_FOR_ID = {
    "authority_id": "authority_evidence_hash",
    "approval_id": "human_approval_receipt_hash",
    "bind_receipt_id": "bind_receipt_hash",
    "effect_receipt_id": "outcome_receipt_hash",
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
        "manifest_evidence_id": None,
        "manifest_evidence_sha256": None,
        "manifest_hash_matches": False,
        "identity_matches": {},
        "verified_links": [],
        "missing_links": [],
        "mismatched_links": [],
        "failure_reasons": [],
        "claim_limitations": list(CLAIM_LIMITATIONS),
    }


MAX_PROFILE_BYTES = 16 * 1024 * 1024


def _read_local_profile(profile_path: Path) -> Any:
    """Read a bounded regular JSON profile, refusing a final symlink."""
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
    if not hasattr(os, "O_NOFOLLOW"):
        raise OSError("platform cannot safely open an untrusted profile file")
    fd = os.open(profile_path, flags | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_PROFILE_BYTES:
            raise ValueError("profile is not a bounded regular file")
        raw = bytearray()
        while len(raw) <= MAX_PROFILE_BYTES:
            chunk = os.read(fd, min(65536, MAX_PROFILE_BYTES + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        if len(raw) > MAX_PROFILE_BYTES:
            raise ValueError("profile exceeds size limit")
        after = os.fstat(fd)
        if (len(raw) != before.st_size or before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns
                or before.st_ctime_ns != after.st_ctime_ns):
            raise ValueError("profile changed during read")
        return json.loads(raw)
    finally:
        os.close(fd)


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
    manifest_evidence_id: str,
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
    is_v02 = isinstance(profile, dict) and profile.get("profile_version") == V02_PROFILE_VERSION
    if is_v02:
        report["bridge_version"] = BRIDGE_VERSION_V02
        report["profile_version"] = V02_PROFILE_VERSION
        report["case_operation_id"] = None
        report["case_manifest_id"] = None
        report["case_manifest_evidence_id"] = None
        report["claim_limitations"] = [
            limitation for limitation in CLAIM_LIMITATIONS
            if not limitation.startswith("Profile v0.1 does not include")
        ] + [
            "Operation, manifest and local evidence IDs are not independently attested."
        ]

    if not isinstance(profile, dict) or not isinstance(case_id, str) or not case_id:
        return _finish(report, "FAILED", "INVALID_BRIDGE_INPUT")
    # Bind the caller's in-memory profile to the actual local profile file;
    # profile_path must not be merely a convenient evidence-directory hint.
    try:
        on_disk_profile = _read_local_profile(Path(profile_path))
    except (OSError, ValueError, TypeError):
        return _finish(report, "FAILED", "PROFILE_FILE_UNREADABLE_OR_UNSAFE")
    if on_disk_profile != profile:
        return _finish(report, "FAILED", "PROFILE_FILE_CONTENT_MISMATCH")
    try:
        errors = verify_profile(profile, Path(profile_path))
    except (OSError, ValueError, TypeError, KeyError):
        return _finish(report, "FAILED", "PROFILE_VALIDATION_EXCEPTION")
    if errors:
        return _finish(report, "FAILED", "PROFILE_VALIDATION_FAILED", *sorted(errors))

    matching = [case for case in profile["cases"] if case["case_id"] == case_id]
    if len(matching) != 1:
        return _finish(report, "FAILED", "PROFILE_CASE_NOT_UNIQUE_OR_MISSING")
    case = matching[0]
    if not case["evidence_ids"]:
        return _finish(report, "INCOMPLETE", "CASE_HAS_NO_LOCAL_EVIDENCE")

    # Two distinct profile cases cannot claim the same decision+intent pair.
    if case.get("decision_id") and case.get("intent_id") and any(
        other["case_id"] != case_id
        and other.get("decision_id") == case["decision_id"]
        and other.get("intent_id") == case["intent_id"]
        for other in profile["cases"]
    ):
        return _finish(report, "FAILED", "AMBIGUOUS_CASE_CHAIN_BINDING")

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
    # The source manifest validator does not enforce that every declared
    # complete chain has a commit-family final_outcome. Never attach a
    # positive local-link verdict to a blocked/refused/unknown outcome.
    if manifest.chain_status == "complete" and manifest.final_outcome.strip().lower() not in (
        "commit", "committed", "commit_eligible"
    ):
        return _finish(report, "FAILED", "CHAIN_OUTCOME_STATUS_CONTRADICTION")

    if is_v02:
        # v0.2 operation-level binding MUST be taken from the on-disk
        # profile case, never inferred from a caller's chosen manifest.
        operation_id = case["operation_id"]
        declared_manifest_id = case["manifest_id"]
        declared_evidence_id = case["manifest_evidence_id"]
        report["case_operation_id"] = operation_id
        report["case_manifest_id"] = declared_manifest_id
        report["case_manifest_evidence_id"] = declared_evidence_id
        if not operation_id or not declared_manifest_id or not declared_evidence_id:
            return _finish(report, "INCOMPLETE", "CASE_OPERATION_BINDING_INCOMPLETE")
        report["identity_matches"]["operation_id"] = (
            operation_id == manifest.operation_id
        )
        report["identity_matches"]["manifest_id"] = (
            declared_manifest_id == manifest.manifest_id
        )
        report["identity_matches"]["manifest_evidence_id"] = (
            declared_evidence_id == manifest_evidence_id
        )
        if operation_id != manifest.operation_id:
            return _finish(report, "FAILED", "CASE_OPERATION_ID_MISMATCH")
        if declared_manifest_id != manifest.manifest_id:
            return _finish(report, "FAILED", "CASE_MANIFEST_ID_MISMATCH")
        if declared_evidence_id != manifest_evidence_id:
            return _finish(report, "FAILED", "CASE_MANIFEST_EVIDENCE_ID_MISMATCH")

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

    # A caller must bind the supplied manifest to a concrete local file that
    # was hashed by verify_profile. Requiring canonical JSON *bytes* prevents
    # substituting an unrelated in-memory manifest for the cited evidence.
    report["manifest_evidence_id"] = manifest_evidence_id if isinstance(manifest_evidence_id, str) else None
    if not isinstance(manifest_evidence_id, str) or not manifest_evidence_id:
        return _finish(report, "INCOMPLETE", "MANIFEST_EVIDENCE_ID_REQUIRED")
    evidence_by_id = {item["id"]: item for item in profile["evidence"]}
    if manifest_evidence_id not in case["evidence_ids"]:
        return _finish(report, "FAILED", "MANIFEST_EVIDENCE_NOT_REFERENCED_BY_CASE")
    if manifest_evidence_id not in evidence_by_id:
        return _finish(report, "FAILED", "MANIFEST_EVIDENCE_ID_NOT_FOUND")
    try:
        canonical_bytes = canonical_json_dumps(manifest.to_dict()).encode("utf-8")
        expected_sha256 = sha256_hex(canonical_bytes)
    except (AttributeError, TypeError, ValueError):
        return _finish(report, "FAILED", "MANIFEST_CANONICALIZATION_FAILED")
    report["manifest_evidence_sha256"] = expected_sha256
    if evidence_by_id[manifest_evidence_id]["sha256"] != expected_sha256:
        return _finish(report, "FAILED", "MANIFEST_EVIDENCE_DIGEST_MISMATCH")

    # A case naming a particular authority/approval/bind/outcome artifact
    # also requires a manifest hash field for that named link.
    absent_hashes = [
        field for field, hash_field in _REQUIRED_HASH_FOR_ID.items()
        if case.get(field) and not getattr(manifest, hash_field)
    ]
    if absent_hashes:
        return _finish(report, "INCOMPLETE", "NAMED_LINK_HASH_MISSING",
                       *(f"MISSING_{field.upper()}_HASH" for field in absent_hashes))

    try:
        source = verify_evidence_chain_manifest(
            manifest=manifest,
            authority_evidence=authority_evidence,
            human_approval_receipt=human_approval_receipt,
            outcome_receipt=outcome_receipt,
            verified_human_approval=verified_human_approval,
            # A caller cannot suppress manifest-declared required approval.
            approval_required=bool(approval_required or manifest.human_approval_required),
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
    # This consistency check is *not* an independent effect attestation.
    if manifest.final_outcome.strip().lower() in (
        "commit", "committed", "commit_eligible"
    ) and case["actual_effect"] == "DENIED":
        return _finish(report, "FAILED", "DECLARED_OUTCOME_CONTRADICTION")
    return _finish(report, "LINK_VERIFIED")


def verify_audit_evidence_chain_bridge_v02(
    *, profile: dict[str, Any], **kwargs: Any
) -> dict[str, Any]:
    """Version-pinned operation-binding entrypoint.

    Use this entrypoint when operation-level binding is mandatory. A caller
    cannot submit a legacy v0.1 profile to bypass v0.2's required IDs.
    """
    if not isinstance(profile, dict) or profile.get("profile_version") != V02_PROFILE_VERSION:
        report = _blank_report(profile, kwargs.get("case_id"))
        report["bridge_version"] = BRIDGE_VERSION_V02
        report["profile_version"] = V02_PROFILE_VERSION
        return _finish(report, "FAILED", "V02_PROFILE_REQUIRED")
    return verify_audit_evidence_chain_bridge(profile=profile, **kwargs)


def serialize_bridge_report(report: dict[str, Any]) -> str:
    """Canonical, stable JSON report bytes (no timestamp or external calls)."""
    return json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
