"""Custody SQLite CAS, offline signer boundary, corruption and concurrency tests."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3

from scripts.validation.audit_checkpoint_signed_custody_v0_1 import sign_checkpoint
from scripts.validation.audit_custody_head_store_v0_1 import (
    create_store, publish, read_head,
)
from scripts.validation.audit_registry_checkpoint_v0_1 import _digest
from test_audit_checkpoint_signed_custody_v0_1 import fixture


def seed(tmp_path):
    ref, private, pub, first = fixture()
    db = tmp_path / "custody.sqlite"
    assert create_store(db, signer_public_key_hex=pub) == "STORE_CREATED"
    assert db.exists()
    assert create_store(db, signer_public_key_hex=pub) == "STORE_ALREADY_EXISTS"
    assert publish(db, reference=ref, receipt=first) == "NEW_HEAD_PUBLISHED"
    return db, ref, private, pub, first


def second_receipt(reference, private, first):
    return sign_checkpoint(
        reference, private_key_raw=private,
        sequence=2, previous_receipt_sha256=_digest(first),
    )


def test_initialization_requires_exclusive_store_and_trusted_key(tmp_path):
    db = tmp_path / "custody.sqlite"
    assert create_store(db, signer_public_key_hex="invalid") == "INPUT_INVALID"
    assert not db.exists()
    assert create_store(db, signer_public_key_hex="f" * 64) == "STORE_CREATED"
    assert read_head(db) == ("HEAD_UNAVAILABLE", None)
    assert create_store(db, signer_public_key_hex="e" * 64) == "STORE_ALREADY_EXISTS"


def test_publish_readback_and_process_reopen(tmp_path):
    db, ref, private, pub, first = seed(tmp_path)
    state, head = read_head(db)
    assert state == "HEAD_OBSERVED"
    assert head == {
        "format_version": "veritas.audit-custody-remote-head/0.1",
        "scope": "LOCAL_AUDIT_OBSERVATION_ONLY",
        "signer_public_key_hex": pub,
        "latest_receipt_sha256": _digest(first),
        "sequence": 1,
    }
    assert publish(db, reference=ref, receipt=first) == "ALREADY_PUBLISHED"
    second = second_receipt(ref, private, first)
    assert publish(db, reference=ref, receipt=second) == "NEW_HEAD_PUBLISHED"
    assert read_head(db)[1]["latest_receipt_sha256"] == _digest(second)
    assert read_head(db)[1]["sequence"] == 2
    assert publish(db, reference=ref, receipt=first) == "HEAD_CONFLICT_OR_ROLLBACK"


def test_invalid_signer_or_unknown_reference_rejected(tmp_path):
    db, ref, private, pub, first = seed(tmp_path)
    other_ref, other_private, _, _ = fixture()
    untrusted = second_receipt(other_ref, other_private, first)
    assert publish(db, reference=other_ref, receipt=untrusted) == "UNTRUSTED_CUSTODY_RECEIPT"
    changed = dict(first, signature_ed25519="0" * 128)
    changed["receipt_hash"] = _digest({
        key: value for key, value in changed.items() if key != "receipt_hash"
    })
    assert publish(db, reference=ref, receipt=changed) == "UNTRUSTED_CUSTODY_RECEIPT"
    assert read_head(db)[1]["sequence"] == 1


def test_concurrent_same_head_has_exactly_one_commit(tmp_path):
    db, ref, private, pub, first = seed(tmp_path)
    second = second_receipt(ref, private, first)
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(
            lambda _: publish(db, reference=ref, receipt=second),
            range(12),
        ))
    assert results.count("NEW_HEAD_PUBLISHED") == 1, results
    assert results.count("ALREADY_PUBLISHED") == 11, results
    assert read_head(db)[1]["sequence"] == 2


def test_fork_at_same_sequence_is_rejected(tmp_path):
    db, ref, private, pub, first = seed(tmp_path)
    second = second_receipt(ref, private, first)
    assert publish(db, reference=ref, receipt=second) == "NEW_HEAD_PUBLISHED"
    modified = json.loads(json.dumps(ref))
    modified["packets"][0]["packet_hash"] = "b" * 64
    content = {key: modified[key] for key in (
        "format_version", "packet_count", "case_count", "packets"
    )}
    modified["snapshot_root"] = _digest(content)
    modified["checkpoint_hash"] = _digest({
        key: value for key, value in modified.items() if key != "checkpoint_hash"
    })
    fork = second_receipt(modified, private, first)
    assert publish(db, reference=modified, receipt=fork) == "HEAD_CONFLICT_OR_ROLLBACK"
    assert read_head(db)[1]["latest_receipt_sha256"] == _digest(second)


def test_sqlite_api_triggers_block_mutations_and_history_corruption_detected(tmp_path):
    db, ref, private, pub, first = seed(tmp_path)
    second = second_receipt(ref, private, first)
    assert publish(db, reference=ref, receipt=second) == "NEW_HEAD_PUBLISHED"
    with sqlite3.connect(db) as conn:
        for sql in (
            "DELETE FROM receipts WHERE sequence = 2",
            "UPDATE receipts SET receipt_hash = '0' WHERE sequence = 2",
            "UPDATE config SET public_key_hex = '0'",
        ):
            try:
                conn.execute(sql)
            except sqlite3.IntegrityError:
                pass
            else:
                raise AssertionError("SQL mutation trigger did not reject " + sql)
        # A database owner can remove triggers. This attack is deliberately
        # outside the 'immutable' assurance; an external verifier must retain
        # its last accepted floor to detect the missing head.
        conn.execute("DROP TRIGGER immutable_receipts_update")
        conn.execute("UPDATE receipts SET receipt_json = '{}' WHERE sequence = 2")
    assert read_head(db) == ("HISTORY_INCOMPLETE", None)
    assert publish(db, reference=ref, receipt=second) == "HISTORY_INCOMPLETE"


def test_privileged_tail_deletion_requires_independent_sequence_floor(tmp_path):
    db, ref, private, pub, first = seed(tmp_path)
    second = second_receipt(ref, private, first)
    assert publish(db, reference=ref, receipt=second) == "NEW_HEAD_PUBLISHED"
    with sqlite3.connect(db) as conn:
        conn.execute("DROP TRIGGER immutable_receipts_delete")
        conn.execute("DELETE FROM receipts WHERE sequence = 2")
    status, head = read_head(db)
    assert status == "HEAD_OBSERVED"
    assert head["sequence"] == 1
    assert head["latest_receipt_sha256"] == _digest(first)
    # The #2451 verifier, supplied an independently pinned minimum of 2,
    # rejects this signed-but-rolled-back remote head.


def test_read_only_store_handle_cannot_modify_database(tmp_path):
    db, _, _, _, _ = seed(tmp_path)
    from scripts.validation.audit_custody_head_store_v0_1 import _open
    with _open(db, readonly=True) as conn:
        try:
            conn.execute("DELETE FROM receipts")
        except sqlite3.OperationalError:
            pass
        else:
            raise AssertionError("read-only server handle performed write")
    assert read_head(db)[1]["sequence"] == 1


def test_unavailable_or_nonregular_storage_is_not_a_success(tmp_path):
    assert read_head(tmp_path / "absent.db")[0] == "STORAGE_UNAVAILABLE"
    assert publish(
        tmp_path / "absent.db", reference={}, receipt={},
    ) == "STORAGE_UNAVAILABLE"
    link = tmp_path / "link.db"
    link.symlink_to(tmp_path / "missing.db")
    assert read_head(link)[0] == "STORAGE_UNAVAILABLE"
