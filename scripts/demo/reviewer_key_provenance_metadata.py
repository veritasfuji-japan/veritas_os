"""Fixed key provenance artifact metadata for Reviewer Evidence Packets."""

from __future__ import annotations

import copy
from typing import Any

KEY_PROVENANCE_ARTIFACTS = {
    "trusted_public_key_provenance_receipt": {
        "artifact_name": "trusted-public-key-provenance.json",
        "schema_id": (
            "https://veritas-os.example/schemas/"
            "trusted_public_key_provenance_receipt.schema.json"
        ),
        "required_for_strict_signature_review": True,
    },
    "key_provenance_validation_report": {
        "artifact_name": "key-provenance-validation.json",
        "schema_id": (
            "https://veritas-os.example/schemas/"
            "trusted_public_key_provenance_validation_report.schema.json"
        ),
    },
    "key_provenance_result_validation_report": {
        "artifact_name": "key-provenance-result-validation.json",
        "schema_id": (
            "https://veritas-os.example/schemas/"
            "trusted_public_key_provenance_result_validation_report.schema.json"
        ),
    },
}


def key_provenance_metadata() -> dict[str, Any]:
    """Return fixed key provenance artifact references for reviewer metadata.

    The metadata intentionally includes only stable artifact names and schema
    identifiers. It does not copy public key fingerprints, local paths,
    exception text, validator messages, or externally supplied JSON values into
    Reviewer Evidence Packets.
    """
    return copy.deepcopy(KEY_PROVENANCE_ARTIFACTS)
