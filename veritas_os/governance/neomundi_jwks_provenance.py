"""Bind a NeoMundi trusted JWKS key to an operator/reviewer provenance receipt.

This module does not establish an out-of-band trust channel by itself. It only
proves that the Ed25519 public key selected by the RGC ``integrity.key_id`` is
byte-for-byte the key whose SHA-256 fingerprint was recorded in a separately
supplied Trusted Public Key Provenance Receipt.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from veritas_os.security.hash import sha256_of_canonical_json

TRUSTED_PUBLIC_KEY_PROVENANCE_RECEIPT_TYPE = "trusted_public_key_provenance"
TRUSTED_PUBLIC_KEY_PROVENANCE_ALGORITHM = "Ed25519"
TRUSTED_PUBLIC_KEY_PROVENANCE_CHANNELS = {
    "operator_handoff",
    "reviewer_vault",
    "signed_release",
    "kms_or_certificate_process",
    "offline_key_ceremony",
    "other",
}

_REQUIRED_RECEIPT_FIELDS = {
    "receipt_type",
    "algorithm",
    "public_key_fingerprint_sha256",
    "trust_channel",
    "received_at",
    "approved_by",
    "approval_reference",
    "notes",
    "bundle_internal_key_used",
}
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_B64URL_RE = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass(frozen=True)
class NeoMundiTrustedJwksProvenanceBinding:
    """Validated correlation between one JWKS key and one provenance receipt."""

    key_id: str
    public_key_fingerprint_sha256: str
    receipt_canonical_sha256: str
    trust_channel: str
    received_at: str

    def to_dict(self) -> dict[str, Any]:
        """Return reviewer-safe binding metadata without approval notes/identity."""
        return {
            "key_id": self.key_id,
            "algorithm": TRUSTED_PUBLIC_KEY_PROVENANCE_ALGORITHM,
            "public_key_fingerprint_sha256": self.public_key_fingerprint_sha256,
            "receipt_canonical_sha256": self.receipt_canonical_sha256,
            "trust_channel": self.trust_channel,
            "received_at": self.received_at,
            "out_of_band_trust_established_by_veritas": False,
        }


def _require_nonempty_string(
    payload: dict[str, Any], key: str, reason: str
) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(reason)
    return value


def _decode_public_x(value: Any) -> bytes:
    if not isinstance(value, str) or not value or not _B64URL_RE.fullmatch(value):
        raise ValueError("neomundi_poc_provenance_jwk_x_invalid")
    try:
        decoded = base64.b64decode(
            value + "=" * (-len(value) % 4),
            altchars=b"-_",
            validate=True,
        )
    except (binascii.Error, ValueError) as exc:
        raise ValueError("neomundi_poc_provenance_jwk_x_invalid") from exc
    if len(decoded) != 32:
        raise ValueError("neomundi_poc_provenance_jwk_x_invalid")
    return decoded


def _validate_receipt(receipt: dict[str, Any]) -> None:
    if not isinstance(receipt, dict):
        raise ValueError("neomundi_poc_provenance_receipt_invalid")
    if set(receipt) != _REQUIRED_RECEIPT_FIELDS:
        raise ValueError("neomundi_poc_provenance_receipt_invalid")
    if receipt.get("receipt_type") != TRUSTED_PUBLIC_KEY_PROVENANCE_RECEIPT_TYPE:
        raise ValueError("neomundi_poc_provenance_receipt_type_invalid")
    if receipt.get("algorithm") != TRUSTED_PUBLIC_KEY_PROVENANCE_ALGORITHM:
        raise ValueError("neomundi_poc_provenance_algorithm_invalid")

    fingerprint = receipt.get("public_key_fingerprint_sha256")
    if not isinstance(fingerprint, str) or not _HEX64_RE.fullmatch(fingerprint):
        raise ValueError("neomundi_poc_provenance_fingerprint_invalid")

    trust_channel = receipt.get("trust_channel")
    if trust_channel not in TRUSTED_PUBLIC_KEY_PROVENANCE_CHANNELS:
        raise ValueError("neomundi_poc_provenance_trust_channel_invalid")

    received_at = _require_nonempty_string(
        receipt, "received_at", "neomundi_poc_provenance_received_at_invalid"
    )
    try:
        parsed = datetime.fromisoformat(received_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("neomundi_poc_provenance_received_at_invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("neomundi_poc_provenance_received_at_timezone_required")

    _require_nonempty_string(
        receipt, "approved_by", "neomundi_poc_provenance_approved_by_invalid"
    )
    _require_nonempty_string(
        receipt,
        "approval_reference",
        "neomundi_poc_provenance_approval_reference_invalid",
    )
    _require_nonempty_string(
        receipt, "notes", "neomundi_poc_provenance_notes_invalid"
    )
    if receipt.get("bundle_internal_key_used") is not False:
        raise ValueError("neomundi_poc_provenance_bundle_internal_key_forbidden")


def bind_neomundi_trusted_jwks_provenance(
    artifact: dict[str, Any],
    *,
    trusted_jwks: dict[str, Any],
    provenance_receipt: dict[str, Any],
) -> NeoMundiTrustedJwksProvenanceBinding:
    """Fail closed unless the selected JWKS key matches the provenance receipt."""
    _validate_receipt(provenance_receipt)

    if not isinstance(artifact, dict):
        raise ValueError("neomundi_poc_provenance_artifact_invalid")
    integrity = artifact.get("integrity")
    if not isinstance(integrity, dict):
        raise ValueError("neomundi_poc_provenance_key_id_missing")
    key_id = _require_nonempty_string(
        integrity, "key_id", "neomundi_poc_provenance_key_id_missing"
    )

    if not isinstance(trusted_jwks, dict) or not isinstance(
        trusted_jwks.get("keys"), list
    ):
        raise ValueError("neomundi_poc_provenance_jwks_invalid")

    matches: list[dict[str, Any]] = []
    for item in trusted_jwks["keys"]:
        if not isinstance(item, dict):
            raise ValueError("neomundi_poc_provenance_jwks_invalid")
        if item.get("kid") == key_id:
            matches.append(item)

    if len(matches) != 1:
        raise ValueError("neomundi_poc_provenance_key_binding_invalid")

    selected = matches[0]
    if "d" in selected:
        raise ValueError("neomundi_poc_provenance_private_jwk_forbidden")
    if selected.get("kty") != "OKP" or selected.get("crv") != "Ed25519":
        raise ValueError("neomundi_poc_provenance_jwk_invalid")

    raw_public_key = _decode_public_x(selected.get("x"))
    actual_fingerprint = hashlib.sha256(raw_public_key).hexdigest()
    expected_fingerprint = provenance_receipt["public_key_fingerprint_sha256"]
    if not hmac.compare_digest(actual_fingerprint, expected_fingerprint):
        raise ValueError("neomundi_poc_provenance_fingerprint_mismatch")

    return NeoMundiTrustedJwksProvenanceBinding(
        key_id=key_id,
        public_key_fingerprint_sha256=actual_fingerprint,
        receipt_canonical_sha256=sha256_of_canonical_json(provenance_receipt),
        trust_channel=provenance_receipt["trust_channel"],
        received_at=provenance_receipt["received_at"],
    )
