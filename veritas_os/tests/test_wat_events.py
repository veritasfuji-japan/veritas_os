"""Unit tests for WAT event-lane revocation state derivation."""

from __future__ import annotations

from pathlib import Path

import pytest

from veritas_os.audit.wat_events import (
    derive_latest_revocation_state,
    persist_wat_validation_event,
    persist_wat_issuance_event,
    persist_wat_revocation_event,
)


def test_derive_latest_revocation_state_defaults_active(tmp_path: Path) -> None:
    state = derive_latest_revocation_state("missing-wat", path=tmp_path / "wat_events.jsonl")
    assert state["status"] == "active"
    assert state["source"] == "wat_events"


def test_derive_latest_revocation_state_pending(tmp_path: Path) -> None:
    path = tmp_path / "wat_events.jsonl"
    persist_wat_issuance_event(wat_id="wat-1", actor="test", path=path)
    persist_wat_revocation_event(wat_id="wat-1", actor="test", confirmed=False, path=path)
    state = derive_latest_revocation_state("wat-1", path=path)
    assert state["status"] == "revoked_pending"
    assert state["source"] == "wat_events"


def test_derive_latest_revocation_state_confirmed(tmp_path: Path) -> None:
    path = tmp_path / "wat_events.jsonl"
    persist_wat_issuance_event(wat_id="wat-2", actor="test", path=path)
    persist_wat_revocation_event(wat_id="wat-2", actor="test", confirmed=False, path=path)
    persist_wat_revocation_event(wat_id="wat-2", actor="test", confirmed=True, path=path)
    state = derive_latest_revocation_state("wat-2", path=path)
    assert state["status"] == "revoked_confirmed"
    assert state["source"] == "wat_events"


def test_primary_audit_path_stores_metadata_and_pointers_only(tmp_path: Path) -> None:
    path = tmp_path / "wat_events.jsonl"
    event = persist_wat_issuance_event(
        wat_id="wat-boundary-1",
        actor="test",
        details={
            "psid": "psid-1",
            "metadata": {"request_id": "rid-1"},
            "observable_digest_ref": "separate_store://digests/wat-boundary-1",
            "observable_digest_payload": {"raw": "must-not-persist"},
        },
        path=path,
    )

    details = event["details"]
    assert "metadata" in details
    assert "event_pointers" in details
    assert (
        details["event_pointers"]["observable_digest_ref"]
        == "separate_store://digests/wat-boundary-1"
    )
    assert "observable_digest_payload" not in details


def test_observable_digest_payload_not_accepted_as_ref(tmp_path: Path) -> None:
    path = tmp_path / "wat_events.jsonl"
    event = persist_wat_issuance_event(
        wat_id="wat-boundary-legacy-1",
        actor="test",
        details={
            "observable_digest": "sha256:deadbeef",
        },
        path=path,
    )

    assertion = event["details"]["retention_boundary_assertion"]
    assert assertion["outcome"] == "failed"
    assert "observable_digest_payload_not_accepted_as_ref" in assertion["failed_reasons"]


def test_legacy_locator_fallback_is_transitional_and_flagged(tmp_path: Path) -> None:
    path = tmp_path / "wat_events.jsonl"
    event = persist_wat_issuance_event(
        wat_id="wat-boundary-legacy-2",
        actor="test",
        details={
            "observable_digest": "separate_store://digests/wat-boundary-legacy-2",
        },
        path=path,
    )

    assertion = event["details"]["retention_boundary_assertion"]
    assert event["details"]["event_pointers"]["observable_digest_ref"].startswith(
        "separate_store://digests/"
    )
    assert assertion["outcome"] == "failed"
    assert "legacy_observable_digest_ref_fallback_used" in assertion["failed_reasons"]


def test_retention_policy_version_immutable_after_enforcement(tmp_path: Path) -> None:
    path = tmp_path / "wat_events.jsonl"
    persist_wat_issuance_event(
        wat_id="wat-boundary-2",
        actor="test",
        details={
            "retention_policy_version": "wat_retention_v1",
            "retention_enforced_at_write": True,
        },
        path=path,
    )

    with pytest.raises(ValueError, match="immutable"):
        persist_wat_validation_event(
            wat_id="wat-boundary-2",
            actor="test",
            details={
                "retention_policy_version": "wat_retention_v2",
                "retention_enforced_at_write": True,
            },
            path=path,
        )


def test_warning_events_include_traceability_context_and_correlation(tmp_path: Path) -> None:
    path = tmp_path / "wat_events.jsonl"
    event = persist_wat_validation_event(
        wat_id="wat-warning-1",
        actor="test",
        event_type="wat_validation_failed",
        status="warning",
        details={"reason": "revocation_pending"},
        path=path,
    )
    metadata = event["details"]["metadata"]
    assert metadata["warning_context"] == "wat_shadow_warning"
    assert metadata["warning_correlation_id"]
