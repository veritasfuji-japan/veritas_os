"""Data records used by governance persistence repositories."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class GovernancePolicyRecord:
    """Current policy snapshot persisted by repository implementations."""

    policy: dict[str, Any]


@dataclass(frozen=True)
class GovernancePolicyEventRecord:
    """Append-only audit event for governance policy mutations."""

    changed_at: str
    changed_by: str
    proposer: str
    approvers: list[str] = field(default_factory=list)
    event_type: str = "update"
    previous_version: str | None = None
    new_version: str | None = None
    previous_digest: str = ""
    new_digest: str = ""
    previous_policy: dict[str, Any] = field(default_factory=dict)
    new_policy: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "changed_at": self.changed_at,
            "changed_by": self.changed_by,
            "proposer": self.proposer,
            "approvers": self.approvers,
            "event_type": self.event_type,
            "previous_version": self.previous_version,
            "new_version": self.new_version,
            "previous_digest": self.previous_digest,
            "new_digest": self.new_digest,
            "previous_policy": self.previous_policy,
            "new_policy": self.new_policy,
        }
