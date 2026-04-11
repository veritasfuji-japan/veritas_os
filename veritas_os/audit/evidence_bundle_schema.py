"""Evidence Bundle schema definitions for external audit packaging.

This module defines the versioned schema for VERITAS evidence bundles.
Bundles are self-contained, deterministic archives that package all
cryptographic evidence needed for third-party verification of decisions,
incidents, or releases.

Schema version: 1.0.0
"""

from __future__ import annotations

BUNDLE_SCHEMA_VERSION = "1.0.0"

#: Required top-level manifest fields.
MANIFEST_REQUIRED_FIELDS = frozenset({
    "schema_version",
    "bundle_type",
    "bundle_id",
    "created_at",
    "created_by",
    "contents",
})

#: Valid bundle types.
BUNDLE_TYPES = frozenset({"decision", "incident", "release"})

#: File entries expected in each bundle type.
BUNDLE_TYPE_CONTENTS = {
    "decision": {
        "required": ["manifest.json", "witness_entries.jsonl"],
        "optional": [
            "artifacts/",
            "anchor_receipts/",
            "mirror_receipts/",
            "verification_report.json",
            "signer_metadata.json",
            "governance_identity.json",
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
        ],
    },
}
