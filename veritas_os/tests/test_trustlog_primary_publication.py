"""Unit tests for deterministic TrustLog primary publication identity."""

from __future__ import annotations

from veritas_os.storage.trustlog_primary_publication import (
    build_trustlog_publication_identity,
)


def test_publication_identity_is_deterministic_for_equivalent_payloads() -> None:
    first = build_trustlog_publication_identity(
        entry_type="outcome_receipt",
        entry_id="outcome-123",
        payload={"b": 2, "a": 1},
    )
    second = build_trustlog_publication_identity(
        entry_type="outcome_receipt",
        entry_id="outcome-123",
        payload={"a": 1, "b": 2},
    )

    assert first.logical_identity_key == second.logical_identity_key
    assert first.canonical_payload_hash == second.canonical_payload_hash
    assert first.publication_key == second.publication_key


def test_changed_payload_preserves_logical_identity_but_changes_publication_key() -> None:
    first = build_trustlog_publication_identity(
        entry_type="outcome_receipt",
        entry_id="outcome-123",
        payload={"status": "ok"},
    )
    changed = build_trustlog_publication_identity(
        entry_type="outcome_receipt",
        entry_id="outcome-123",
        payload={"status": "changed"},
    )

    assert first.logical_identity_key == changed.logical_identity_key
    assert first.canonical_payload_hash != changed.canonical_payload_hash
    assert first.publication_key != changed.publication_key


def test_logical_identity_changes_when_stable_entry_identity_changes() -> None:
    first = build_trustlog_publication_identity(
        entry_type="bind_receipt",
        entry_id="bind-1",
        payload={"status": "ok"},
    )
    second = build_trustlog_publication_identity(
        entry_type="bind_receipt",
        entry_id="bind-2",
        payload={"status": "ok"},
    )

    assert first.logical_identity_key != second.logical_identity_key
    assert first.publication_key != second.publication_key


def test_payload_is_redacted_before_hashing() -> None:
    first = build_trustlog_publication_identity(
        entry_type="review_packet",
        entry_id="packet-1",
        payload={"note": "password=secret-one", "result": "ok"},
    )
    second = build_trustlog_publication_identity(
        entry_type="review_packet",
        entry_id="packet-1",
        payload={"note": "password=secret-two", "result": "ok"},
    )

    assert first.redacted_payload["note"] != "password=secret-one"
    assert second.redacted_payload["note"] != "password=secret-two"
    assert first.canonical_payload_hash == second.canonical_payload_hash
    assert first.publication_key == second.publication_key
