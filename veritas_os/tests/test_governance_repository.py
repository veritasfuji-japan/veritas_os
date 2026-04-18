"""Governance repository abstraction regression tests."""

from __future__ import annotations

import json
import threading

import pytest

from veritas_os.api import governance as gov
from veritas_os.governance.file_repository import FileGovernanceRepository


@pytest.fixture(autouse=True)
def _reset_repo_factory() -> None:
    gov.set_governance_repository_factory(None)
    yield
    gov.set_governance_repository_factory(None)


def test_file_repository_roundtrip(tmp_path):
    """File repository persists current policy and history with rollback records."""
    repo = FileGovernanceRepository(
        policy_path=tmp_path / "governance.json",
        history_path=tmp_path / "governance_history.jsonl",
        lock=threading.Lock(),
        policy_history_max=10,
    )

    default = repo.get_current_policy(
        default_factory=lambda: gov.GovernancePolicy().model_dump()
    )
    assert default["version"] == "governance_v1"

    updated = {**default, "version": "governance_v2", "updated_by": "alice"}
    repo.update_policy(
        previous=default,
        updated=updated,
        proposer="alice",
        approvers=["r1", "r2"],
        event_type="update",
    )
    assert repo.get_current_policy(default_factory=dict)["version"] == "governance_v2"

    restored = {**default, "version": "governance_v1_rollback", "updated_by": "bob"}
    repo.rollback_policy(
        previous=updated,
        restored=restored,
        proposer="bob",
        approvers=["r3", "r4"],
    )

    history = repo.list_policy_history(limit=10, max_records=500)
    assert len(history) == 2
    assert history[0]["event_type"] == "rollback"
    assert history[1]["event_type"] == "update"


class _InMemoryRepository:
    def __init__(self) -> None:
        self.policy = gov.GovernancePolicy().model_dump()
        self.history: list[dict] = []

    def get_current_policy(self, *, default_factory):
        return self.policy or default_factory()

    def save_policy(self, policy):
        self.policy = policy

    def append_policy_event(self, event):
        self.history.append(event.to_dict())

    def list_policy_history(self, *, limit, max_records):
        return list(reversed(self.history))[: max(1, min(limit, max_records))]

    def update_policy(
        self,
        *,
        previous,
        updated,
        proposer,
        approvers,
        event_type,
        approval_records=None,
        reason="",
    ):
        del approval_records, reason
        self.policy = updated
        self.history.append(
            {
                "previous_policy": previous,
                "new_policy": updated,
                "proposer": proposer,
                "approvers": approvers,
                "event_type": event_type,
            }
        )

    def rollback_policy(
        self,
        *,
        previous,
        restored,
        proposer,
        approvers,
        approval_records=None,
        reason="",
    ):
        del approval_records, reason
        self.policy = restored
        self.history.append(
            {
                "previous_policy": previous,
                "new_policy": restored,
                "proposer": proposer,
                "approvers": approvers,
                "event_type": "rollback",
            }
        )


def test_governance_api_uses_repository_interface(monkeypatch):
    """API-level operations should flow through repository interface methods."""
    repo = _InMemoryRepository()
    gov.set_governance_repository_factory(lambda: repo)
    monkeypatch.setenv("VERITAS_GOVERNANCE_REQUIRE_FOUR_EYES", "0")

    updated = gov.update_policy({"version": "governance_v2", "updated_by": "alice"})
    assert updated["version"] == "governance_v2"

    history = gov.get_policy_history(limit=5)
    assert history[0]["event_type"] == "update"

    rolled_back = gov.rollback_policy(
        {**repo.policy, "version": "governance_v1_restored"},
        rolled_back_by="bob",
        approvals=[
            {"reviewer": "r1", "signature": "s1"},
            {"reviewer": "r2", "signature": "s2"},
        ],
    )
    assert rolled_back["version"] == "governance_v1_restored"

    latest_history = gov.get_policy_history(limit=1)
    assert latest_history[0]["event_type"] == "rollback"


def test_file_mode_behavior_unchanged_for_load_save(tmp_path, monkeypatch):
    """Backward-compatible helpers still read/write JSON file based policy."""
    policy_path = tmp_path / "governance.json"
    history_path = tmp_path / "governance_history.jsonl"
    monkeypatch.setattr(gov, "_DEFAULT_POLICY_PATH", policy_path)
    monkeypatch.setattr(gov, "_POLICY_HISTORY_PATH", history_path)

    policy = gov.GovernancePolicy().model_dump()
    policy["version"] = "legacy-file-mode"
    gov._save(policy)

    loaded = gov._load()
    assert loaded["version"] == "legacy-file-mode"

    on_disk = json.loads(policy_path.read_text(encoding="utf-8"))
    assert on_disk["version"] == "legacy-file-mode"
