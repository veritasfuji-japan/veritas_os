"""Evidence Bundle schema definitions for external audit packaging.

This module defines the versioned schema for VERITAS evidence bundles.
Bundles are self-contained, deterministic archives that package all
cryptographic evidence needed for third-party verification of decisions,
incidents, or releases.

Schema version: 1.1.0
"""

from __future__ import annotations

BUNDLE_SCHEMA_VERSION = "1.1.0"

#: Required top-level manifest fields.
MANIFEST_REQUIRED_FIELDS = frozenset({
    "schema_version",
    "bundle_type",
    "bundle_id",
    "created_at",
    "created_by",
    "contents",
    "file_hashes",
    "entry_count",
})

#: Required keys for the decision snapshot payload minimum contract.
DECISION_SNAPSHOT_MINIMUM_REQUIRED_FIELDS = frozenset({
    "decision_payload",
    "gate_decision",
    "business_decision",
    "next_action",
    "trustlog_references",
    "verification",
    "provenance",
})

#: Required keys for the decision snapshot full contract.
DECISION_SNAPSHOT_FULL_REQUIRED_FIELDS = frozenset({
    "decision_payload",
    "gate_decision",
    "business_decision",
    "next_action",
    "required_evidence",
    "human_review_required",
    "trustlog_references",
    "verification",
    "provenance",
    "runtime_context",
})

#: Backwards-compatible alias for the strict/full requirement set.
DECISION_SNAPSHOT_REQUIRED_FIELDS = DECISION_SNAPSHOT_FULL_REQUIRED_FIELDS

DECISION_RECORD_PROFILES = frozenset({"minimum", "full"})

#: Valid bundle types.
BUNDLE_TYPES = frozenset({"decision", "incident", "release"})

#: File entries expected in each bundle type.
BUNDLE_TYPE_CONTENTS = {
    "decision": {
        "required": ["manifest.json", "witness_entries.jsonl", "decision_record.json"],
        "optional": [
            "artifacts/",
            "anchor_receipts/",
            "mirror_receipts/",
            "verification_report.json",
            "signer_metadata.json",
            "governance_identity.json",
            "acceptance_checklist.json",
            "README.txt",
            "ui_delivery_hook.json",
        ],
    },
    "incident": {
        "required": ["manifest.json", "witness_entries.jsonl"],
        "optional": [
            "artifacts/",
            "anchor_receipts/",
            "mirror_receipts/",
            "verification_report.json",
            "signer_metadata.json",
            "governance_identity.json",
            "incident_metadata.json",
            "acceptance_checklist.json",
            "README.txt",
            "ui_delivery_hook.json",
        ],
    },
    "release": {
        "required": ["manifest.json", "witness_entries.jsonl"],
        "optional": [
            "artifacts/",
            "anchor_receipts/",
            "mirror_receipts/",
            "verification_report.json",
            "signer_metadata.json",
            "governance_identity.json",
            "release_provenance.json",
            "acceptance_checklist.json",
            "README.txt",
            "ui_delivery_hook.json",
        ],
    },
}


def validate_decision_snapshot_shape(payload: dict, profile: str = "minimum") -> list[str]:
    """Validate required fields for ``decision_record.json``.

    Returns a list of human-readable validation errors.
    """
    errors: list[str] = []
    if profile not in DECISION_RECORD_PROFILES:
        errors.append(f"decision_record profile must be one of {sorted(DECISION_RECORD_PROFILES)}")
        return errors

    required_fields = (
        DECISION_SNAPSHOT_MINIMUM_REQUIRED_FIELDS
        if profile == "minimum"
        else DECISION_SNAPSHOT_FULL_REQUIRED_FIELDS
    )
    missing = required_fields - set(payload.keys())
    if missing:
        errors.append(f"decision_record missing fields ({profile}): {sorted(missing)}")

    if "required_evidence" in payload and not isinstance(payload.get("required_evidence"), list):
        errors.append("decision_record.required_evidence must be a list")

    if "human_review_required" in payload and not isinstance(
        payload.get("human_review_required"), bool
    ):
        errors.append("decision_record.human_review_required must be a boolean")

    references = payload.get("trustlog_references")
    if references is not None and not isinstance(references, dict):
        errors.append("decision_record.trustlog_references must be an object")

    verification = payload.get("verification")
    if verification is not None and not isinstance(verification, dict):
        errors.append("decision_record.verification must be an object")

    decision_payload = payload.get("decision_payload")
    if decision_payload is not None and not isinstance(decision_payload, dict):
        errors.append("decision_record.decision_payload must be an object")

    return errors
