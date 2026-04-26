"""Predicate result model for deterministic runtime governance checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

PredicateStatus = Literal["pass", "fail", "stale", "missing", "indeterminate"]
PredicateType = Literal[
    "action_contract_present",
    "action_contract_valid",
    "authority_present",
    "authority_valid",
    "authority_not_expired",
    "scope_allowed",
    "prohibited_scope_absent",
    "evidence_present",
    "evidence_fresh",
    "policy_snapshot_resolved",
    "human_approval_present",
    "irreversibility_boundary_defined",
    "actor_identity_resolved",
    "bind_context_valid",
]
PredicateSeverity = Literal["low", "medium", "high", "critical"]


@dataclass(frozen=True)
class PredicateResult:
    """Structured result for one deterministic admissibility predicate."""

    predicate_id: str
    predicate_type: PredicateType
    status: PredicateStatus
    reason: str
    evidence_ref: str | None = None
    severity: PredicateSeverity = "critical"
    evaluated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)
