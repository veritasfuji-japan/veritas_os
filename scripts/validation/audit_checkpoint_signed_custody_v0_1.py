"""Opt-in signed, *externally pinned* custody receipts for local audit snapshots.

A signature authenticates the holder of the explicitly pinned Ed25519 key,
not the provenance, completeness, timestamps or external effects of the data.
Neither the signer nor the database decides which receipt is the trusted head.
"""
from __future__ import annotations

import hmac
import re
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from scripts.validation.audit_registry_checkpoint_v0_1 import (
    _digest,
    check_registry_against_pin,
    validate_checkpoint,
)
from veritas_os.security.hash import canonical_json_dumps, sha256_hex

FORMAT = "veritas.audit-checkpoint-custody-receipt/0.1"
_SCOPE = "LOCAL_OBSERVATION_CONTINUITY_ONLY"
_DOMAIN = b"VERITAS_AUDIT_CHECKPOINT_CUSTODY_V0_1\x00"
_ZERO = "0" * 64
_SHA = re.compile(r"^[0-9a-f]{64}$")
_KEYS = {
    "format_version", "scope", "signer_key_id",
    "checkpoint_hash", "checkpoint_snapshot_root",
    "sequence", "previous_receipt_sha256", "signature_ed25519",
    "receipt_hash",
}
_SIGNED_KEYS = _KEYS - {"signature_ed25519", "receipt_hash"}


def _message(payload: dict[str, Any]) -> bytes:
    return _DOMAIN + canonical_json_dumps(payload).encode("utf-8")


def _format_receipt(receipt: Any) -> bool:
    if not isinstance(receipt, dict) or set(receipt) != _KEYS:
        return False
    if (
        receipt["format_version"] != FORMAT
        or receipt["scope"] != _SCOPE
        or type(receipt["sequence"]) is not int
        or not 1 <= receipt["sequence"] <= 1_000_000_000
    ):
        return False
    if any(
        not isinstance(receipt[key], str) or not _SHA.fullmatch(receipt[key])
        for key in (
            "signer_key_id", "checkpoint_hash", "checkpoint_snapshot_root",
            "previous_receipt_sha256", "receipt_hash",
        )
    ):
        return False
    if (
        receipt["sequence"] == 1
        and receipt["previous_receipt_sha256"] != _ZERO
    ) or (
        receipt["sequence"] > 1
        and receipt["previous_receipt_sha256"] == _ZERO
    ):
        return False
    sig = receipt["signature_ed25519"]
    if not isinstance(sig, str) or not re.fullmatch(r"[0-9a-f]{128}", sig):
        return False
    return hmac.compare_digest(
        receipt["receipt_hash"],
        _digest({key: value for key, value in receipt.items() if key != "receipt_hash"}),
    )


def sign_checkpoint(
    reference: Any,
    *,
    private_key_raw: bytes,
    sequence: int,
    previous_receipt_sha256: str,
) -> dict[str, Any]:
    """Sign a self-consistent, *untrusted* local snapshot using a custodian key.

    Key provisioning and custody are operator responsibilities. This function
    accepts no caller-provided PASS or authorization claims.
    """
    if not validate_checkpoint(reference):
        raise ValueError("REFERENCE_INVALID")
    if not isinstance(private_key_raw, bytes) or len(private_key_raw) != 32:
        raise ValueError("PRIVATE_KEY_INVALID")
    if type(sequence) is not int or not 1 <= sequence <= 1_000_000_000:
        raise ValueError("SEQUENCE_INVALID")
    if (
        not isinstance(previous_receipt_sha256, str)
        or not _SHA.fullmatch(previous_receipt_sha256)
        or (sequence == 1) != (previous_receipt_sha256 == _ZERO)
    ):
        raise ValueError("PREDECESSOR_INVALID")
    private = Ed25519PrivateKey.from_private_bytes(private_key_raw)
    pub = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    statement = {
        "format_version": FORMAT,
        "scope": _SCOPE,
        "signer_key_id": sha256_hex(pub),
        "checkpoint_hash": _digest(reference),
        "checkpoint_snapshot_root": reference["snapshot_root"],
        "sequence": sequence,
        "previous_receipt_sha256": previous_receipt_sha256,
    }
    receipt = {
        **statement,
        "signature_ed25519": private.sign(_message(statement)).hex(),
    }
    receipt["receipt_hash"] = _digest(receipt)
    return receipt


def verify_signed_reference(
    *,
    reference: Any,
    receipt: Any,
    trusted_public_key_hex: str,
    expected_head_sha256: str,
) -> str:
    """Verify strictly pinned key + strictly pinned signed receipt.

    An old but valid signature MUST NOT be accepted unless its full receipt
    digest matches the independently held expected head.
    """
    if (
        not isinstance(trusted_public_key_hex, str)
        or not _SHA.fullmatch(trusted_public_key_hex)
        or not isinstance(expected_head_sha256, str)
        or not _SHA.fullmatch(expected_head_sha256)
    ):
        return "EXTERNAL_PINS_REQUIRED"
    if not _format_receipt(receipt):
        return "RECEIPT_INVALID"
    if not hmac.compare_digest(_digest(receipt), expected_head_sha256):
        return "CUSTODY_HEAD_MISMATCH"
    if not hmac.compare_digest(
        receipt["signer_key_id"], sha256_hex(bytes.fromhex(trusted_public_key_hex))
    ):
        return "SIGNER_PIN_MISMATCH"
    try:
        statement = {k: receipt[k] for k in _SIGNED_KEYS}
        Ed25519PublicKey.from_public_bytes(
            bytes.fromhex(trusted_public_key_hex)
        ).verify(bytes.fromhex(receipt["signature_ed25519"]), _message(statement))
    except (InvalidSignature, ValueError, TypeError):
        return "SIGNATURE_INVALID"
    if not validate_checkpoint(reference):
        return "REFERENCE_INVALID"
    if (
        not hmac.compare_digest(receipt["checkpoint_hash"], _digest(reference))
        or not hmac.compare_digest(
            receipt["checkpoint_snapshot_root"], reference["snapshot_root"],
        )
    ):
        return "SIGNED_BASELINE_MISMATCH"
    return "SIGNED_LOCAL_BASELINE_VERIFIED"


async def check_registry_against_signed_reference(
    *, reference: Any, receipt: Any,
    trusted_public_key_hex: str, expected_head_sha256: str,
) -> str:
    """Check current DB only after validating independent head + public key."""
    result = verify_signed_reference(
        reference=reference, receipt=receipt,
        trusted_public_key_hex=trusted_public_key_hex,
        expected_head_sha256=expected_head_sha256,
    )
    if result != "SIGNED_LOCAL_BASELINE_VERIFIED":
        return result
    return await check_registry_against_pin(
        reference=reference, pinned_reference_sha256=_digest(reference),
    )
