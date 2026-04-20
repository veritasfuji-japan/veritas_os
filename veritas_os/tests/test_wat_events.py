"""Unit tests for WAT event-lane revocation state derivation."""

from __future__ import annotations

from pathlib import Path

from veritas_os.audit.wat_events import (
    derive_latest_revocation_state,
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
