"""Tests for PostgreSQL governance repository.

These tests run against an in-memory SQL dispatcher (no live DB) and validate:
- current policy retrieval
- transactional update (policy + event + approvals)
- rollback event persistence
- deterministic history ordering
- duplicate approval validation
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

import pytest

from veritas_os.governance.postgresql_repository import PostgresGovernanceRepository


class _MockCursor:
    def __init__(self, state: dict[str, Any]) -> None:
        self._state = state
        self._rows: list[tuple[Any, ...]] = []

    def execute(self, query: str, params: tuple[Any, ...] | None = None) -> None:
        sql = " ".join(query.strip().split()).lower()
        params = params or tuple()

        if sql.startswith("select policy_payload from governance_policies"):
            current = [p for p in self._state["policies"] if p["is_current"]]
            if not current:
                self._rows = []
            else:
                self._rows = [(current[-1]["policy_payload"],)]
            return

        if sql.startswith("select id from governance_policies"):
            current = [p for p in self._state["policies"] if p["is_current"]]
            self._rows = [(current[-1]["id"],)] if current else []
            return

        if sql.startswith("update governance_policies set is_current = false"):
            policy_id = params[0]
            for policy in self._state["policies"]:
                if policy["id"] == policy_id:
                    policy["is_current"] = False
            self._rows = []
            return

        if sql.startswith("insert into governance_policies"):
            self._state["policy_seq"] += 1
            policy_id = self._state["policy_seq"]
            self._state["policies"].append(
                {
                    "id": policy_id,
                    "policy_version": params[0],
                    "policy_payload": params[1],
                    "digest": params[2],
                    "updated_at": params[3],
                    "updated_by": params[4],
                    "is_current": True,
                }
            )
            self._rows = [(policy_id,)]
            return

        if sql.startswith("insert into governance_policy_events"):
            self._state["event_seq"] += 1
            event_id = self._state["event_seq"]
            self._state["events"].append(
                {
                    "id": event_id,
                    "event_order": event_id,
                    "event_type": params[0],
                    "previous_policy_id": params[1],
                    "new_policy_id": params[2],
                    "previous_digest": params[3],
                    "new_digest": params[4],
                    "proposer": params[5],
                    "changed_by": params[6],
                    "changed_at": params[7],
                    "reason": params[8],
                }
            )
            self._rows = [(event_id,)]
            return

        if sql.startswith("insert into governance_approvals"):
            event_id, reviewer, signature, _metadata = params
            for existing in self._state["approvals"]:
                if existing["event_id"] == event_id and existing["reviewer"] == reviewer:
                    raise ValueError("duplicate reviewer")
                if (
                    signature
                    and existing["event_id"] == event_id
                    and existing["signature"] == signature
                ):
                    raise ValueError("duplicate signature")
            self._state["approvals"].append(
                {
                    "event_id": event_id,
                    "reviewer": reviewer,
                    "signature": signature,
                }
            )
            self._rows = []
            return

        if sql.startswith("select e.id,"):
            ordered = sorted(
                self._state["events"],
                key=lambda item: item["event_order"],
                reverse=True,
            )
            limit = params[0]
            selected = ordered[:limit]
            rows: list[tuple[Any, ...]] = []
            for event in selected:
                previous_policy = {}
                new_policy = {}
                if event["previous_policy_id"]:
                    previous_policy = next(
                        p["policy_payload"]
                        for p in self._state["policies"]
                        if p["id"] == event["previous_policy_id"]
                    )
                if event["new_policy_id"]:
                    new_policy = next(
                        p["policy_payload"]
                        for p in self._state["policies"]
                        if p["id"] == event["new_policy_id"]
                    )
                rows.append(
                    (
                        event["id"],
                        event["event_type"],
                        event["previous_digest"],
                        event["new_digest"],
                        event["proposer"],
                        event["changed_by"],
                        event["changed_at"],
                        event["reason"],
                        previous_policy,
                        new_policy,
                    )
                )
            self._rows = rows
            return

        if sql.startswith("select event_id, reviewer, signature"):
            event_ids = set(params[0])
            rows = [
                (a["event_id"], a["reviewer"], a["signature"])
                for a in self._state["approvals"]
                if a["event_id"] in event_ids
            ]
            rows.sort(key=lambda row: (row[0], row[1]))
            self._rows = rows
            return

        raise ValueError(f"Unhandled SQL: {query}")

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[tuple[Any, ...]]:
        return list(self._rows)


class _MockConn:
    def __init__(self, state: dict[str, Any]) -> None:
        self._state = state

    @contextmanager
    def cursor(self):
        yield _MockCursor(self._state)

    def commit(self) -> None:
        self._state["committed"] += 1

    def rollback(self) -> None:
        self._state["rolled_back"] += 1

    def close(self) -> None:
        return


@pytest.fixture()
def repository() -> tuple[PostgresGovernanceRepository, dict[str, Any]]:
    state = {
        "policies": [],
        "events": [],
        "approvals": [],
        "policy_seq": 0,
        "event_seq": 0,
        "committed": 0,
        "rolled_back": 0,
    }
    repo = PostgresGovernanceRepository(database_url="postgresql://unused")

    @contextmanager
    def _mock_connect():
        yield _MockConn(state)

    repo._connect = _mock_connect  # type: ignore[assignment]
    return repo, state


def _policy(version: str, updated_by: str) -> dict[str, Any]:
    return {
        "version": version,
        "updated_by": updated_by,
        "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "fuji_rules": {"pii_check": True},
        "risk_thresholds": {"allow_upper": 0.5},
        "rollout_controls": {"strategy": "immediate", "canary_percent": 0},
        "log_retention": {"days": 30, "encrypted": True},
        "auto_stop": {"max_risk_score": 0.9, "halt_on_missing_evidence": True},
    }


def test_get_current_policy_works(repository) -> None:
    repo, _state = repository
    fallback = repo.get_current_policy(default_factory=lambda: {"version": "default"})
    assert fallback["version"] == "default"

    updated = _policy("governance_v2", "alice")
    repo.update_policy(
        previous={},
        updated=updated,
        proposer="alice",
        approvers=["r1", "r2"],
        event_type="update",
        approval_records=[
            {"reviewer": "r1", "signature": "sig1"},
            {"reviewer": "r2", "signature": "sig2"},
        ],
    )

    current = repo.get_current_policy(default_factory=dict)
    assert current["version"] == "governance_v2"


def test_update_creates_policy_event_and_approvals(repository) -> None:
    repo, state = repository
    previous = _policy("governance_v1", "seed")
    updated = _policy("governance_v2", "alice")

    repo.update_policy(
        previous=previous,
        updated=updated,
        proposer="alice",
        approvers=["r1", "r2"],
        event_type="update",
        approval_records=[
            {"reviewer": "r1", "signature": "sig1"},
            {"reviewer": "r2", "signature": "sig2"},
        ],
    )

    assert len(state["policies"]) == 1
    assert len(state["events"]) == 1
    assert len(state["approvals"]) == 2
    assert state["events"][0]["event_type"] == "update"
    assert state["committed"] == 1


def test_rollback_creates_rollback_event(repository) -> None:
    repo, state = repository
    v1 = _policy("governance_v1", "seed")
    v2 = _policy("governance_v2", "alice")
    rollback_target = _policy("governance_v1_restored", "bob")

    repo.update_policy(
        previous=v1,
        updated=v2,
        proposer="alice",
        approvers=["r1", "r2"],
        event_type="update",
    )
    repo.rollback_policy(
        previous=v2,
        restored=rollback_target,
        proposer="bob",
        approvers=["r3", "r4"],
        approval_records=[
            {"reviewer": "r3", "signature": "sig3"},
            {"reviewer": "r4", "signature": "sig4"},
        ],
        reason="manual rollback",
    )

    assert len(state["events"]) == 2
    assert state["events"][1]["event_type"] == "rollback"
    assert state["events"][1]["reason"] == "manual rollback"


def test_list_policy_history_ordering_desc(repository) -> None:
    repo, _state = repository

    repo.update_policy(
        previous=_policy("v1", "seed"),
        updated=_policy("v2", "alice"),
        proposer="alice",
        approvers=["r1", "r2"],
        event_type="update",
    )
    repo.rollback_policy(
        previous=_policy("v2", "alice"),
        restored=_policy("v1-restored", "bob"),
        proposer="bob",
        approvers=["r3", "r4"],
    )

    history = repo.list_policy_history(limit=10, max_records=500)
    assert len(history) == 2
    assert history[0]["event_type"] == "rollback"
    assert history[1]["event_type"] == "update"


def test_duplicate_approval_reviewer_rejected(repository) -> None:
    repo, _state = repository
    with pytest.raises(ValueError):
        repo.update_policy(
            previous=_policy("v1", "seed"),
            updated=_policy("v2", "alice"),
            proposer="alice",
            approvers=["r1", "r1"],
            event_type="update",
            approval_records=[
                {"reviewer": "r1", "signature": "sig1"},
                {"reviewer": "r1", "signature": "sig2"},
            ],
        )
