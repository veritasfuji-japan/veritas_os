"""Unit tests for WAT token canonicalization and signatures."""

from __future__ import annotations

from pathlib import Path

from veritas_os.security.signing import FileEd25519Signer
from veritas_os.security.wat_token import (
    WAT_VERSION_V1,
    build_wat_claims,
    canonicalize_wat_claims,
    compute_observable_digest,
    make_psid_display,
    sign_wat,
    verify_wat_signature,
)


def _make_signer(tmp_path: Path) -> FileEd25519Signer:
    signer = FileEd25519Signer(
        private_key_path=tmp_path / "keys" / "wat-private.key",
        public_key_path=tmp_path / "keys" / "wat-public.key",
    )
    signer.ensure_key_material()
    return signer


def test_canonicalization_is_deterministic_for_same_claims() -> None:
    claims = {"b": 2, "a": 1, "z": [3, 2, 1]}
    assert canonicalize_wat_claims(claims) == canonicalize_wat_claims(claims)


def test_canonicalization_same_claims_same_output() -> None:
    claims = {"k1": "value", "k2": {"x": 1, "y": 2}}
    first = canonicalize_wat_claims(claims)
    second = canonicalize_wat_claims(claims)
    assert first == second


def test_canonicalization_ignores_key_order() -> None:
    claims_a = {"a": 1, "b": 2, "c": {"x": 1, "y": 2}}
    claims_b = {"c": {"y": 2, "x": 1}, "b": 2, "a": 1}
    assert canonicalize_wat_claims(claims_a) == canonicalize_wat_claims(claims_b)


def test_psid_display_truncation_preserves_psid_full() -> None:
    full = "psid-prod-customer-00000123456789"
    signer_meta = {
        "signer_type": "file",
        "signer_key_id": "k1",
        "signer_key_version": "v1",
        "signature_algorithm": "ed25519",
    }
    claims = build_wat_claims(
        version=WAT_VERSION_V1,
        psid_full=full,
        action_payload={"action": "allow", "resource": "acct:123"},
        observable_refs=[{"trace_id": "t-1"}],
        issuance_ts=1_712_000_000,
        expiry_ts=1_712_000_600,
        session_id="sess-1",
        nonce="n-1",
        signer_metadata=signer_meta,
        psid_display_length=12,
    )
    assert claims["psid_full"] == full
    assert claims["psid_display"] == full[:12]
    assert make_psid_display(full, 12) == full[:12]


def test_sign_and_verify_wat_signature_success(tmp_path: Path) -> None:
    signer = _make_signer(tmp_path)
    claims = build_wat_claims(
        version=WAT_VERSION_V1,
        psid_full="psid-full-001",
        action_payload={"action": "allow", "resource": "r-1"},
        observable_refs=[{"obs": "A"}, {"obs": "B"}],
        issuance_ts=1_712_000_000,
        expiry_ts=1_712_000_600,
        session_id="s-1",
        nonce="n-1",
        signer_metadata={"source": "unit-test"},
    )
    signed = sign_wat(claims, signer)
    assert verify_wat_signature(claims, signed["signature"], signer)


def test_verify_wat_signature_fails_for_tampered_claim(tmp_path: Path) -> None:
    signer = _make_signer(tmp_path)
    claims = build_wat_claims(
        version=WAT_VERSION_V1,
        psid_full="psid-full-002",
        action_payload={"action": "allow"},
        observable_refs=[{"obs": "A"}],
        issuance_ts=1_712_000_000,
        expiry_ts=1_712_000_600,
        session_id="s-2",
        nonce="n-2",
        signer_metadata={"source": "unit-test"},
    )
    signed = sign_wat(claims, signer)

    tampered = dict(claims)
    tampered["nonce"] = "n-tampered"
    assert not verify_wat_signature(tampered, signed["signature"], signer)


def test_observable_digest_is_deterministic() -> None:
    observable_refs = [{"id": "1", "kind": "log"}, {"id": "2", "kind": "trace"}]
    first = compute_observable_digest(observable_refs)
    second = compute_observable_digest(observable_refs)
    assert first == second
