"""Tests for governance backend selection and API backend wiring."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from veritas_os.api import governance as gov
from veritas_os.governance import factory as governance_factory
from veritas_os.governance.config import validate_governance_backend
from veritas_os.governance.file_repository import FileGovernanceRepository


class _InMemoryGovernanceRepository:
    """Simple in-memory repository used to emulate PostgreSQL backend in tests."""

    def __init__(self) -> None:
        self.policy = gov.GovernancePolicy().model_dump()
        self.history: list[dict[str, Any]] = []

    def get_current_policy(self, *, default_factory):
        return self.policy or default_factory()

    def save_policy(self, policy: dict[str, Any]) -> None:
        self.policy = policy

    def append_policy_event(self, event) -> None:
        self.history.append(event.to_dict())

    def list_policy_history(self, *, limit: int, max_records: int) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(limit, max_records))
        return list(reversed(self.history))[:bounded_limit]

    def update_policy(
        self,
        *,
        previous: dict[str, Any],
        updated: dict[str, Any],
        proposer: str,
        approvers: list[str],
        event_type: str,
        approval_records: list[dict[str, str]] | None = None,
        reason: str = "",
    ) -> None:
        self.policy = updated
        self.history.append(
            {
                "changed_at": updated.get(
                    "updated_at",
                    datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                ),
                "changed_by": updated.get("updated_by", proposer),
                "proposer": proposer,
                "approvers": approvers,
                "approvals": approval_records or [],
                "event_type": event_type,
                "previous_policy": previous,
                "new_policy": updated,
                "reason": reason,
            }
        )

    def rollback_policy(
        self,
        *,
        previous: dict[str, Any],
        restored: dict[str, Any],
        proposer: str,
        approvers: list[str],
        approval_records: list[dict[str, str]] | None = None,
        reason: str = "",
    ) -> None:
        self.update_policy(
            previous=previous,
            updated=restored,
            proposer=proposer,
            approvers=approvers,
            event_type="rollback",
            approval_records=approval_records,
            reason=reason,
        )


@pytest.fixture(autouse=True)
def _reset_governance_repo_factory() -> None:
    gov.set_governance_repository_factory(None)
    yield
    gov.set_governance_repository_factory(None)


def test_governance_backend_file_path_works(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """File backend selection keeps legacy file persistence behavior."""
    monkeypatch.setenv("VERITAS_GOVERNANCE_BACKEND", "file")
    repo = governance_factory.create_governance_repository(
        policy_path=tmp_path / "governance.json",
        history_path=tmp_path / "governance_history.jsonl",
        lock=threading.Lock(),
        policy_history_max=50,
        has_atomic_io=False,
    )
    assert isinstance(repo, FileGovernanceRepository)


def test_governance_backend_postgresql_path_works(monkeypatch: pytest.MonkeyPatch) -> None:
    """PostgreSQL backend selection returns PostgreSQL repository class."""
    monkeypatch.setenv("VERITAS_GOVERNANCE_BACKEND", "postgresql")
    monkeypatch.setenv("VERITAS_DATABASE_URL", "postgresql://user:pass@localhost:5432/veritas")

    class _StubPostgresRepo:
        def health_check(self) -> None:
            return

    monkeypatch.setattr(governance_factory, "PostgresGovernanceRepository", _StubPostgresRepo)

    repo = governance_factory.create_governance_repository(
        policy_path=Path("unused-policy.json"),
        history_path=Path("unused-history.jsonl"),
        lock=threading.Lock(),
        policy_history_max=50,
        has_atomic_io=False,
    )
    assert isinstance(repo, _StubPostgresRepo)


def test_governance_backend_invalid_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unknown governance backend should fail fast during validation."""
    monkeypatch.setenv("VERITAS_GOVERNANCE_BACKEND", "invalid")
    with pytest.raises(ValueError, match="Unknown VERITAS_GOVERNANCE_BACKEND"):
        validate_governance_backend()


def test_configure_governance_repository_fails_fast_for_invalid_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Startup configuration should fail fast for unknown backend values."""
    monkeypatch.setenv("VERITAS_GOVERNANCE_BACKEND", "unknown-backend")
    with pytest.raises(ValueError, match="Unknown VERITAS_GOVERNANCE_BACKEND"):
        gov.configure_governance_repository_from_env()


def test_governance_api_history_rollback_approval_flow_postgresql_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """API workflow works with PostgreSQL backend selection via DI factory."""
    monkeypatch.setenv("VERITAS_GOVERNANCE_BACKEND", "postgresql")
    monkeypatch.setenv("VERITAS_DATABASE_URL", "postgresql://user:pass@localhost:5432/veritas")

    in_memory_repo = _InMemoryGovernanceRepository()

    def _fake_create_repo(**_kwargs):
        return in_memory_repo

    monkeypatch.setattr(gov, "create_governance_repository", _fake_create_repo)
    gov.configure_governance_repository_from_env()

    approvals = [
        {"reviewer": "alice", "signature": "sig-1"},
        {"reviewer": "bob", "signature": "sig-2"},
    ]

    gov.enforce_four_eyes_approval({"approvals": approvals})
    updated = gov.update_policy(
        {
            "version": "governance_v2",
            "updated_by": "alice",
            "approvals": approvals,
        }
    )
    assert updated["version"] == "governance_v2"

    rolled_back = gov.rollback_policy(
        {**updated, "version": "governance_v1_restored"},
        rolled_back_by="bob",
        approvals=approvals,
        reason="postgresql test rollback",
    )
    assert rolled_back["version"] == "governance_v1_restored"

    history = gov.get_policy_history(limit=10)
    assert len(history) == 2
    assert history[0]["event_type"] == "rollback"
    assert history[1]["event_type"] == "update"
