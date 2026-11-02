"""Negative cryptographic and trust-pin tests for offline custody receipts."""
from __future__ import annotations

from copy import deepcopy

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
import pytest

from scripts.validation.audit_checkpoint_signed_custody_v0_1 import (
    check_registry_against_signed_reference,
    sign_checkpoint,
    verify_signed_reference,
)
from scripts.validation.audit_checkpoint_signed_custody_cli_v0_1 import (
    _read_restricted_raw_key,
    _write_exclusive_json,
)
from scripts.validation.audit_registry_checkpoint_v0_1 import _digest

ZERO = "0" * 64


def fixture():
    roster = [{"packet_id": "packet-A", "packet_hash": "a" * 64, "case_count": 1}]
    root = {
        "format_version": "veritas.audit-registry-checkpoint/0.1",
        "packet_count": 1,
        "case_count": 1,
        "packets": roster,
    }
    value = {
        **root,
        "scope": "LOCAL_UNAUTHENTICATED_AUDIT_INVENTORY",
        "origin_authentication": "NOT_PERFORMED",
        "external_anchor": "NOT_EMBEDDED",
        "snapshot_root": _digest(root),
    }
    value["checkpoint_hash"] = _digest(value)
    private = Ed25519PrivateKey.generate()
    raw = private.private_bytes_raw()
    pub = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    receipt = sign_checkpoint(
        value, private_key_raw=raw,
        sequence=1, previous_receipt_sha256=ZERO,
    )
    return value, raw, pub, receipt


def check(ref, receipt, pub, head):
    return verify_signed_reference(
        reference=ref, receipt=receipt,
        trusted_public_key_hex=pub,
        expected_head_sha256=head,
    )


def test_correctly_pinned_baseline_signature():
    ref, _, pub, receipt = fixture()
    assert check(ref, receipt, pub, _digest(receipt)) == "SIGNED_LOCAL_BASELINE_VERIFIED"
    assert receipt["checkpoint_hash"] == _digest(ref)
    assert receipt["checkpoint_snapshot_root"] == ref["snapshot_root"]
    assert receipt["scope"] == "LOCAL_OBSERVATION_CONTINUITY_ONLY"


def test_key_and_head_are_required_and_not_self_trusted():
    ref, _, pub, receipt = fixture()
    head = _digest(receipt)
    assert check(ref, receipt, "", head) == "EXTERNAL_PINS_REQUIRED"
    assert check(ref, receipt, pub, "") == "EXTERNAL_PINS_REQUIRED"
    assert check(ref, receipt, "x" * 64, head) == "EXTERNAL_PINS_REQUIRED"
    assert check(ref, receipt, pub, "f" * 64) == "CUSTODY_HEAD_MISMATCH"


def test_forged_signed_message_and_changed_checkpoint_fail():
    ref, _, pub, original = fixture()
    attacker = deepcopy(original)
    attacker["checkpoint_hash"] = "f" * 64
    attacker["receipt_hash"] = _digest({
        k: v for k, v in attacker.items() if k != "receipt_hash"
    })
    # Even if the attacker could substitute the independent head pin, they
    # still cannot produce a valid signature under the trusted signer key.
    assert check(ref, attacker, pub, _digest(attacker)) == "SIGNATURE_INVALID"
    changed = deepcopy(ref)
    changed["packets"][0]["packet_hash"] = "b" * 64
    changed["snapshot_root"] = _digest({
        k: changed[k] for k in (
            "format_version", "packet_count", "case_count", "packets",
        )
    })
    changed["checkpoint_hash"] = _digest({
        k: v for k, v in changed.items() if k != "checkpoint_hash"
    })
    assert check(changed, original, pub, _digest(original)) == "SIGNED_BASELINE_MISMATCH"


def test_wrong_key_cannot_be_used_even_with_valid_self_signature():
    ref, _, pub, receipt = fixture()
    another_pub = Ed25519PrivateKey.generate().public_key().public_bytes(
        Encoding.Raw, PublicFormat.Raw,
    ).hex()
    assert another_pub != pub
    assert check(ref, receipt, another_pub, _digest(receipt)) == "SIGNER_PIN_MISMATCH"


def test_old_valid_signed_receipt_cannot_replace_latest_head():
    ref, private, pub, old = fixture()
    newer = sign_checkpoint(
        ref, private_key_raw=private,
        sequence=2, previous_receipt_sha256=_digest(old),
    )
    assert check(ref, old, pub, _digest(newer)) == "CUSTODY_HEAD_MISMATCH"
    assert check(ref, newer, pub, _digest(newer)) == "SIGNED_LOCAL_BASELINE_VERIFIED"


@pytest.mark.parametrize("sequence,previous", [
    (True, ZERO), (0, ZERO), (2, ZERO), (1, "1" * 64), (2, ""),
])
def test_missing_or_invalid_predecessor_rejected(sequence, previous):
    ref, private, _, _ = fixture()
    with pytest.raises(ValueError):
        sign_checkpoint(
            ref, private_key_raw=private,
            sequence=sequence, previous_receipt_sha256=previous,
        )


def test_restricted_signing_key_rejects_symlink_and_world_readable(tmp_path):
    _, private, _, _ = fixture()
    key = tmp_path / "restricted.key"
    key.write_bytes(private)
    key.chmod(0o600)
    assert _read_restricted_raw_key(key) == private
    key.chmod(0o644)
    with pytest.raises(PermissionError):
        _read_restricted_raw_key(key)
    key.chmod(0o600)
    link = tmp_path / "alias.key"
    link.symlink_to(key)
    with pytest.raises(OSError):
        _read_restricted_raw_key(link)
    bad = tmp_path / "wrong.key"
    bad.write_bytes(b"A" * 33)
    bad.chmod(0o600)
    with pytest.raises(ValueError):
        _read_restricted_raw_key(bad)


def test_no_overwrite_of_published_receipt(tmp_path):
    _, _, _, receipt = fixture()
    target = tmp_path / "immutable-on-create.json"
    _write_exclusive_json(target, receipt)
    original = target.read_bytes()
    with pytest.raises(FileExistsError):
        _write_exclusive_json(target, receipt)
    assert target.read_bytes() == original


@pytest.mark.asyncio
async def test_bad_pins_prevent_all_database_access(monkeypatch):
    ref, _, pub, receipt = fixture()
    called = {"count": 0}
    async def unreachable(**kwargs):
        called["count"] += 1
        raise AssertionError("untrusted proof reached database")
    monkeypatch.setattr(
        "scripts.validation.audit_checkpoint_signed_custody_v0_1.check_registry_against_pin",
        unreachable,
    )
    result = await check_registry_against_signed_reference(
        reference=ref, receipt=receipt,
        trusted_public_key_hex=pub, expected_head_sha256="f" * 64,
    )
    assert result == "CUSTODY_HEAD_MISMATCH"
    assert called["count"] == 0


@pytest.mark.asyncio
async def test_verified_reference_delegates_to_existing_readback_gate(monkeypatch):
    ref, _, pub, receipt = fixture()
    seen = []
    async def reader(**kwargs):
        seen.append(kwargs)
        return "HISTORY_DIVERGED"
    monkeypatch.setattr(
        "scripts.validation.audit_checkpoint_signed_custody_v0_1.check_registry_against_pin",
        reader,
    )
    assert (await check_registry_against_signed_reference(
        reference=ref, receipt=receipt,
        trusted_public_key_hex=pub, expected_head_sha256=_digest(receipt),
    )) == "HISTORY_DIVERGED"
    assert seen == [{
        "reference": ref, "pinned_reference_sha256": _digest(ref),
    }]
