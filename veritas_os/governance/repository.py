"""Repository interfaces for governance policy persistence."""

from __future__ import annotations

from typing import Any, Callable, Protocol

from veritas_os.governance.models import GovernancePolicyEventRecord


class GovernanceRepository(Protocol):
    """Persistence contract for governance policy and history operations."""

    def get_current_policy(
        self,
        *,
        default_factory: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        """Return current policy snapshot, falling back to default_factory."""

    def save_policy(self, policy: dict[str, Any]) -> None:
        """Persist full current policy atomically."""

    def append_policy_event(self, event: GovernancePolicyEventRecord) -> None:
        """Append one immutable policy-change event to history."""

    def list_policy_history(self, *, limit: int, max_records: int) -> list[dict[str, Any]]:
        """Return history events in newest-first order."""

    def update_policy(
        self,
        *,
        previous: dict[str, Any],
        updated: dict[str, Any],
        proposer: str,
        approvers: list[str],
        event_type: str,
    ) -> None:
        """Persist updated policy and record an update event."""

    def rollback_policy(
        self,
        *,
        previous: dict[str, Any],
        restored: dict[str, Any],
        proposer: str,
        approvers: list[str],
    ) -> None:
        """Persist restored policy and record a rollback event."""
