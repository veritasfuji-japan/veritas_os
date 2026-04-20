"""Bind-boundary governance artifact contracts.

This module introduces schema-first, runtime-neutral artifact contracts for
VERITAS bind-boundary governance.

Artifacts
---------
- ``ExecutionIntent``: a decision-linked descriptor of an execution attempt.
- ``BindReceipt``: a bind-time governance artifact recording bind checks,
  admissibility, and final outcome.

Design constraints
------------------
- Extends existing VERITAS governance lineage (decision_id, policy lineage,
  governance identity, TrustLog hash references).
- Reuses canonical JSON + SHA-256 primitives from ``veritas_os.security.hash``.
- Does not perform external side effects or orchestration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from veritas_os.security.hash import canonical_json_dumps, sha256_of_canonical_json


class FinalOutcome(str, Enum):
    """Canonical terminal outcome labels for bind-boundary adjudication."""

    COMMITTED = "COMMITTED"
    BLOCKED = "BLOCKED"
    ESCALATED = "ESCALATED"
    ROLLED_BACK = "ROLLED_BACK"
    APPLY_FAILED = "APPLY_FAILED"
    SNAPSHOT_FAILED = "SNAPSHOT_FAILED"
    PRECONDITION_FAILED = "PRECONDITION_FAILED"



def _utc_now_iso8601() -> str:
    """Return a UTC timestamp in ISO-8601 format with trailing ``Z``."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class ExecutionIntent:
    """Decision-linked execution attempt descriptor.

    This is a schema contract only. Runtime orchestration is intentionally
    deferred to later PRs.
    """

    execution_intent_id: str = field(default_factory=lambda: uuid4().hex)
    decision_id: str = ""
    request_id: str = ""
    policy_snapshot_id: str = ""
    actor_identity: str = ""
    target_system: str = ""
    target_resource: str = ""
    intended_action: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    decision_hash: str = ""
    decision_ts: str = ""
    ttl_seconds: int | None = None
    expected_state_fingerprint: str | None = None
    approval_context: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "execution_intent_id": self.execution_intent_id,
            "decision_id": self.decision_id,
            "request_id": self.request_id,
            "policy_snapshot_id": self.policy_snapshot_id,
            "actor_identity": self.actor_identity,
            "target_system": self.target_system,
            "target_resource": self.target_resource,
            "intended_action": self.intended_action,
            "evidence_refs": list(self.evidence_refs),
            "decision_hash": self.decision_hash,
            "decision_ts": self.decision_ts,
            "ttl_seconds": self.ttl_seconds,
            "expected_state_fingerprint": self.expected_state_fingerprint,
            "approval_context": self.approval_context,
        }


@dataclass(frozen=True)
class BindReceipt:
    """Bind-time governance artifact linked to decision and execution intent."""

    bind_receipt_id: str = field(default_factory=lambda: uuid4().hex)
    execution_intent_id: str = ""
    decision_id: str = ""
    bind_ts: str = field(default_factory=_utc_now_iso8601)
    live_state_fingerprint_before: str = ""
    live_state_fingerprint_after: str = ""
    authority_check_result: dict[str, Any] = field(default_factory=dict)
    constraint_check_result: dict[str, Any] = field(default_factory=dict)
    drift_check_result: dict[str, Any] = field(default_factory=dict)
    risk_check_result: dict[str, Any] = field(default_factory=dict)
    admissibility_result: dict[str, Any] = field(default_factory=dict)
    final_outcome: FinalOutcome = FinalOutcome.BLOCKED
    rollback_reason: str | None = None
    escalation_reason: str | None = None
    trustlog_hash: str = ""
    prev_bind_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "bind_receipt_id": self.bind_receipt_id,
            "execution_intent_id": self.execution_intent_id,
            "decision_id": self.decision_id,
            "bind_ts": self.bind_ts,
            "live_state_fingerprint_before": self.live_state_fingerprint_before,
            "live_state_fingerprint_after": self.live_state_fingerprint_after,
            "authority_check_result": dict(self.authority_check_result),
            "constraint_check_result": dict(self.constraint_check_result),
            "drift_check_result": dict(self.drift_check_result),
            "risk_check_result": dict(self.risk_check_result),
            "admissibility_result": dict(self.admissibility_result),
            "final_outcome": self.final_outcome.value,
            "rollback_reason": self.rollback_reason,
            "escalation_reason": self.escalation_reason,
            "trustlog_hash": self.trustlog_hash,
            "prev_bind_hash": self.prev_bind_hash,
        }



def canonical_execution_intent_json(intent: ExecutionIntent) -> str:
    """Serialize ``ExecutionIntent`` with canonical deterministic JSON ordering."""
    return canonical_json_dumps(intent.to_dict())



def canonical_bind_receipt_json(receipt: BindReceipt) -> str:
    """Serialize ``BindReceipt`` with canonical deterministic JSON ordering."""
    return canonical_json_dumps(receipt.to_dict())



def hash_execution_intent(intent: ExecutionIntent) -> str:
    """Compute SHA-256 over canonical ``ExecutionIntent`` payload."""
    return sha256_of_canonical_json(intent.to_dict())



def hash_bind_receipt(receipt: BindReceipt) -> str:
    """Compute SHA-256 over canonical ``BindReceipt`` payload."""
    return sha256_of_canonical_json(receipt.to_dict())
