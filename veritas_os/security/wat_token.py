"""WAT token claim construction, canonicalization, and signature helpers.

This module is intentionally narrow: it provides deterministic WAT claim
construction/canonicalization and crypto sign/verify primitives only.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence
from uuid import uuid4

from veritas_os.security.hash import canonical_json_dumps, sha256_hex
from veritas_os.security.signing import Signer

WAT_VERSION_V1 = "1"
ALLOWED_OBSERVABLE_DIGEST_ACCESS_CLASSES: frozenset[str] = frozenset({
    "restricted",
    "privileged",
})


def canonicalize_wat_claims(claims: Mapping[str, Any]) -> bytes:
    """Return deterministic canonical bytes for WAT claims."""
    return canonical_json_dumps(claims).encode("utf-8")


def make_psid_display(psid_full: str, display_length: int = 12) -> str:
    """Create a display-only PSID preview.

    Security:
        ``psid_display`` is for UI/log display only and MUST NOT be used for
        enforcement decisions. Always use ``psid_full`` for enforcement.
    """
    if display_length <= 0:
        raise ValueError("display_length must be > 0")
    return psid_full[:display_length]


def compute_action_digest(action_payload: Mapping[str, Any]) -> str:
    """Compute deterministic digest for action payload."""
    return sha256_hex(canonical_json_dumps(action_payload))


def compute_observable_digests(observable_refs: Sequence[object]) -> list[str]:
    """Compute deterministic digest per observable reference."""
    return [sha256_hex(canonical_json_dumps(ref)) for ref in observable_refs]


def compute_observable_digest(observable_refs: Sequence[object]) -> str:
    """Compute deterministic aggregate digest for observable references."""
    per_ref_digests = compute_observable_digests(observable_refs)
    return sha256_hex(canonical_json_dumps(per_ref_digests))


def _build_signer_metadata(signer: Signer) -> dict[str, Any]:
    return {
        "signer_type": signer.signer_type,
        "signer_key_id": signer.signer_key_id(),
        "signer_key_version": signer.signer_key_version(),
        "signature_algorithm": signer.signature_algorithm(),
        "public_key_fingerprint": signer.public_key_fingerprint(),
    }


def build_wat_claims(
    *,
    version: str,
    psid_full: str,
    action_payload: Mapping[str, Any],
    observable_refs: Sequence[object],
    issuance_ts: int,
    expiry_ts: int,
    session_id: str,
    nonce: str,
    signer_metadata: Mapping[str, Any],
    wat_id: str | None = None,
    decision_reason: str | None = None,
    action_summary: str | None = None,
    resource_summary: str | None = None,
    psid_display_length: int = 12,
    observable_digest_ref: str | None = None,
    observable_digest_access_class: str = "restricted",
    retention_policy_version: str = "wat_retention_v1",
    retention_enforced_at_write: bool = True,
) -> dict[str, Any]:
    """Build immutable WAT claims with required fields for v1."""
    normalized_access_class = str(observable_digest_access_class).strip().lower()
    if normalized_access_class not in ALLOWED_OBSERVABLE_DIGEST_ACCESS_CLASSES:
        raise ValueError(
            f"invalid_observable_digest_access_class: {observable_digest_access_class}"
        )
    observable_digest_list = compute_observable_digests(observable_refs)
    claims: dict[str, Any] = {
        "wat_id": wat_id or str(uuid4()),
        "version": version,
        "psid_full": psid_full,
        "psid_display": make_psid_display(psid_full, psid_display_length),
        "action_digest": compute_action_digest(action_payload),
        "observable_refs": list(observable_refs),
        "observable_digest_list": observable_digest_list,
        "observable_digest": sha256_hex(canonical_json_dumps(observable_digest_list)),
        "issuance_ts": issuance_ts,
        "expiry_ts": expiry_ts,
        "session_id": session_id,
        "nonce": nonce,
        "signer": dict(signer_metadata),
        "observable_digest_ref": str(observable_digest_ref or "").strip(),
        "observable_digest_access_class": normalized_access_class,
        "retention_policy_version": str(retention_policy_version).strip()
        or "wat_retention_v1",
        "retention_enforced_at_write": bool(retention_enforced_at_write),
    }

    if decision_reason is not None:
        claims["decision_reason"] = decision_reason
    if action_summary is not None:
        claims["action_summary"] = action_summary
    if resource_summary is not None:
        claims["resource_summary"] = resource_summary
    return claims


def sign_wat(claims: Mapping[str, Any], signer: Signer) -> dict[str, Any]:
    """Sign canonicalized WAT claims using existing signer abstraction."""
    canonical = canonicalize_wat_claims(claims)
    payload_hash = sha256_hex(canonical)
    signature = signer.sign_payload_hash(payload_hash)
    return {
        "claims": dict(claims),
        "payload_hash": payload_hash,
        "signature": signature,
        "signer": _build_signer_metadata(signer),
    }


def verify_wat_signature(
    claims: Mapping[str, Any],
    signature_b64: str,
    signer: Signer,
) -> bool:
    """Verify WAT claim signature using canonicalized claim hash."""
    canonical = canonicalize_wat_claims(claims)
    payload_hash = sha256_hex(canonical)
    return signer.verify_payload_signature(payload_hash, signature_b64)
