"""Fail-closed intake binding for one real NeoMundi RGC v0.2 PoC packet.

The intake manifest binds the exact partner-supplied RGC artifact, JWKS, and
Trusted Public Key Provenance Receipt before any provider verification or replay
state is consumed.  It is correlation metadata only: it does not establish
cryptographic trust, freshness, authority, approval, or execution permission.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from veritas_os.security.hash import sha256_of_canonical_json

INTAKE_MANIFEST_VERSION = "1.0"
INTAKE_PROVIDER_ID = "neomundi"
INTAKE_ARTIFACT_TYPE = "neomundi_rgc"
INTAKE_ARTIFACT_VERSION = "0.2.0"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED_KEYS = {
    "manifest_version",
    "manifest_id",
    "provider_id",
    "artifact_type",
    "artifact_version",
    "artifact_id",
    "expected_key_id",
    "expected_signer_identity",
    "artifact_file_sha256",
    "trusted_jwks_file_sha256",
    "trusted_key_provenance_receipt_file_sha256",
    "handoff_reference",
    "received_at",
}


@dataclass(frozen=True)
class NeoMundiRealObservationIntakeBinding:
    """Reviewer-safe correlation result for a validated intake manifest."""

    manifest_id: str
    manifest_canonical_sha256: str
    provider_id: str
    artifact_type: str
    artifact_version: str
    artifact_id: str
    expected_key_id: str
    expected_signer_identity: str
    artifact_file_sha256: str
    trusted_jwks_file_sha256: str
    trusted_key_provenance_receipt_file_sha256: str
    handoff_reference: str
    received_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_id": self.manifest_id,
            "manifest_canonical_sha256": self.manifest_canonical_sha256,
            "provider_id": self.provider_id,
            "artifact_type": self.artifact_type,
            "artifact_version": self.artifact_version,
            "artifact_id": self.artifact_id,
            "expected_key_id": self.expected_key_id,
            "expected_signer_identity": self.expected_signer_identity,
            "artifact_file_sha256": self.artifact_file_sha256,
            "trusted_jwks_file_sha256": self.trusted_jwks_file_sha256,
            "trusted_key_provenance_receipt_file_sha256": (
                self.trusted_key_provenance_receipt_file_sha256
            ),
            "handoff_reference": self.handoff_reference,
            "received_at": self.received_at,
            "packet_correlation_only": True,
            "trust_established_by_intake_manifest": False,
            "freshness_established_by_received_at": False,
            "execution_permission_created": False,
        }


def _nonempty_string(value: Any, reason: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(reason)
    return value


def _sha256(value: Any, reason: str) -> str:
    text = _nonempty_string(value, reason)
    if _SHA256_RE.fullmatch(text) is None:
        raise ValueError(reason)
    return text


def _timezone_aware_timestamp(value: Any) -> str:
    text = _nonempty_string(value, "neomundi_poc_intake_received_at_invalid")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("neomundi_poc_intake_received_at_invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("neomundi_poc_intake_received_at_timezone_required")
    return text


def bind_neomundi_real_observation_intake(
    manifest: dict[str, Any],
    *,
    artifact: dict[str, Any],
    artifact_file_sha256: str,
    trusted_jwks_file_sha256: str,
    trusted_key_provenance_receipt_file_sha256: str,
) -> NeoMundiRealObservationIntakeBinding:
    """Bind one intake manifest to the exact local packet and artifact identity."""

    if not isinstance(manifest, dict):
        raise ValueError("neomundi_poc_intake_manifest_invalid")
    if set(manifest) != _REQUIRED_KEYS:
        raise ValueError("neomundi_poc_intake_manifest_fields_invalid")

    if manifest.get("manifest_version") != INTAKE_MANIFEST_VERSION:
        raise ValueError("neomundi_poc_intake_manifest_version_unsupported")
    if manifest.get("provider_id") != INTAKE_PROVIDER_ID:
        raise ValueError("neomundi_poc_intake_provider_mismatch")
    if manifest.get("artifact_type") != INTAKE_ARTIFACT_TYPE:
        raise ValueError("neomundi_poc_intake_artifact_type_mismatch")
    if manifest.get("artifact_version") != INTAKE_ARTIFACT_VERSION:
        raise ValueError("neomundi_poc_intake_artifact_version_mismatch")

    manifest_id = _nonempty_string(
        manifest.get("manifest_id"), "neomundi_poc_intake_manifest_id_invalid"
    )
    artifact_id = _nonempty_string(
        manifest.get("artifact_id"), "neomundi_poc_intake_artifact_id_invalid"
    )
    expected_key_id = _nonempty_string(
        manifest.get("expected_key_id"), "neomundi_poc_intake_key_id_invalid"
    )
    expected_signer_identity = _nonempty_string(
        manifest.get("expected_signer_identity"),
        "neomundi_poc_intake_signer_identity_invalid",
    )
    handoff_reference = _nonempty_string(
        manifest.get("handoff_reference"),
        "neomundi_poc_intake_handoff_reference_invalid",
    )
    received_at = _timezone_aware_timestamp(manifest.get("received_at"))

    declared_artifact_hash = _sha256(
        manifest.get("artifact_file_sha256"),
        "neomundi_poc_intake_artifact_hash_invalid",
    )
    declared_jwks_hash = _sha256(
        manifest.get("trusted_jwks_file_sha256"),
        "neomundi_poc_intake_jwks_hash_invalid",
    )
    declared_receipt_hash = _sha256(
        manifest.get("trusted_key_provenance_receipt_file_sha256"),
        "neomundi_poc_intake_provenance_hash_invalid",
    )

    actual_artifact_hash = _sha256(
        artifact_file_sha256, "neomundi_poc_intake_actual_artifact_hash_invalid"
    )
    actual_jwks_hash = _sha256(
        trusted_jwks_file_sha256, "neomundi_poc_intake_actual_jwks_hash_invalid"
    )
    actual_receipt_hash = _sha256(
        trusted_key_provenance_receipt_file_sha256,
        "neomundi_poc_intake_actual_provenance_hash_invalid",
    )

    if declared_artifact_hash != actual_artifact_hash:
        raise ValueError("neomundi_poc_intake_artifact_hash_mismatch")
    if declared_jwks_hash != actual_jwks_hash:
        raise ValueError("neomundi_poc_intake_jwks_hash_mismatch")
    if declared_receipt_hash != actual_receipt_hash:
        raise ValueError("neomundi_poc_intake_provenance_hash_mismatch")

    if not isinstance(artifact, dict):
        raise ValueError("neomundi_poc_intake_artifact_invalid")
    identity = artifact.get("identity")
    integrity = artifact.get("integrity")
    if not isinstance(identity, dict) or not isinstance(integrity, dict):
        raise ValueError("neomundi_poc_intake_artifact_invalid")

    if identity.get("schema_version") != INTAKE_ARTIFACT_VERSION:
        raise ValueError("neomundi_poc_intake_artifact_version_mismatch")
    if identity.get("request_id") != artifact_id:
        raise ValueError("neomundi_poc_intake_artifact_id_mismatch")
    if integrity.get("key_id") != expected_key_id:
        raise ValueError("neomundi_poc_intake_key_id_mismatch")
    if integrity.get("signer_identity") != expected_signer_identity:
        raise ValueError("neomundi_poc_intake_signer_identity_mismatch")

    return NeoMundiRealObservationIntakeBinding(
        manifest_id=manifest_id,
        manifest_canonical_sha256=sha256_of_canonical_json(manifest),
        provider_id=INTAKE_PROVIDER_ID,
        artifact_type=INTAKE_ARTIFACT_TYPE,
        artifact_version=INTAKE_ARTIFACT_VERSION,
        artifact_id=artifact_id,
        expected_key_id=expected_key_id,
        expected_signer_identity=expected_signer_identity,
        artifact_file_sha256=actual_artifact_hash,
        trusted_jwks_file_sha256=actual_jwks_hash,
        trusted_key_provenance_receipt_file_sha256=actual_receipt_hash,
        handoff_reference=handoff_reference,
        received_at=received_at,
    )
