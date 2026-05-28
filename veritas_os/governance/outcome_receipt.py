"""Local/offline deterministic Outcome Receipt artifact helpers.

Outcome Receipt v1 records post-execution outcome evidence for governed
execution attempts without introducing live integrations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from veritas_os.security.hash import sha256_of_canonical_json

PostconditionStatus = Literal["passed", "failed", "skipped", "indeterminate"]
_ALLOWED_POSTCONDITION_STATUS = {"passed", "failed", "skipped", "indeterminate"}
_COMMITTED_OUTCOMES = {"commit", "committed"}


@dataclass(frozen=True)
class OutcomeReceipt:
    """Deterministic local/offline post-execution outcome evidence artifact."""

    outcome_receipt_id: str
    decision_id: str
    execution_intent_id: str
    bind_receipt_id: str | None
    operation_id: str
    action_class: str
    target_system: str
    target_resource: str
    intended_action: str
    requested_scope: list[str]
    final_outcome: str
    committed: bool
    blocked: bool
    escalated: bool
    rolled_back: bool
    pre_state_fingerprint: str | None
    post_state_fingerprint: str | None
    postcondition_status: PostconditionStatus
    observed_effects: list[dict[str, Any]]
    failure_reasons: list[str]
    rollback_status: str | None
    evaluated_at: str
    outcome_hash: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return deterministic dictionary representation."""
        return {
            "outcome_receipt_id": self.outcome_receipt_id,
            "decision_id": self.decision_id,
            "execution_intent_id": self.execution_intent_id,
            "bind_receipt_id": self.bind_receipt_id,
            "operation_id": self.operation_id,
            "action_class": self.action_class,
            "target_system": self.target_system,
            "target_resource": self.target_resource,
            "intended_action": self.intended_action,
            "requested_scope": sorted(str(scope) for scope in self.requested_scope),
            "final_outcome": self.final_outcome,
            "committed": self.committed,
            "blocked": self.blocked,
            "escalated": self.escalated,
            "rolled_back": self.rolled_back,
            "pre_state_fingerprint": self.pre_state_fingerprint,
            "post_state_fingerprint": self.post_state_fingerprint,
            "postcondition_status": self.postcondition_status,
            "observed_effects": self.observed_effects,
            "failure_reasons": sorted(str(reason) for reason in self.failure_reasons),
            "rollback_status": self.rollback_status,
            "evaluated_at": self.evaluated_at,
            "outcome_hash": self.outcome_hash,
            "metadata": self.metadata,
        }

    def to_dict_for_hash(self) -> dict[str, Any]:
        """Return canonical hash payload excluding self-referential outcome hash."""
        payload = self.to_dict()
        payload.pop("outcome_hash", None)
        return payload

    def deterministic_digest(self) -> str:
        """Compute deterministic SHA-256 digest from canonical hash payload."""
        return sha256_of_canonical_json(self.to_dict_for_hash())


@dataclass(frozen=True)
class OutcomeReceiptValidationResult:
    """Fail-closed validation output for an outcome receipt."""

    is_valid: bool
    failure_reasons: list[str]


def with_outcome_hash(receipt: OutcomeReceipt) -> OutcomeReceipt:
    """Return a finalized copy with deterministic ``outcome_hash`` populated."""
    data = receipt.to_dict()
    data["outcome_hash"] = receipt.deterministic_digest()
    return OutcomeReceipt(**data)


def validate_outcome_receipt(receipt: OutcomeReceipt | None) -> OutcomeReceiptValidationResult:
    """Validate outcome receipt with deterministic fail-closed checks."""
    if receipt is None:
        return OutcomeReceiptValidationResult(False, ["outcome_receipt_missing"])

    failure_reasons: list[str] = []

    if not str(receipt.decision_id).strip():
        failure_reasons.append("outcome_receipt_decision_id_missing")
    if not str(receipt.execution_intent_id).strip():
        failure_reasons.append("outcome_receipt_execution_intent_id_missing")
    if not str(receipt.operation_id).strip():
        failure_reasons.append("outcome_receipt_operation_id_missing")
    if not str(receipt.target_system).strip():
        failure_reasons.append("outcome_receipt_target_system_missing")
    if not str(receipt.target_resource).strip():
        failure_reasons.append("outcome_receipt_target_resource_missing")
    if not str(receipt.intended_action).strip():
        failure_reasons.append("outcome_receipt_intended_action_missing")
    if not str(receipt.final_outcome).strip():
        failure_reasons.append("outcome_receipt_final_outcome_missing")

    if receipt.postcondition_status not in _ALLOWED_POSTCONDITION_STATUS:
        failure_reasons.append("outcome_receipt_invalid_postcondition_status")

    normalized_outcome = str(receipt.final_outcome).strip().lower()
    if receipt.committed and normalized_outcome not in _COMMITTED_OUTCOMES:
        failure_reasons.append("outcome_receipt_committed_outcome_mismatch")
    if receipt.blocked and receipt.committed:
        failure_reasons.append("outcome_receipt_committed_and_blocked_conflict")
    if receipt.rolled_back and not receipt.committed and not receipt.failure_reasons:
        failure_reasons.append("outcome_receipt_rollback_without_failure_reason")

    evaluated_at_raw = str(receipt.evaluated_at).strip()
    if not evaluated_at_raw:
        failure_reasons.append("outcome_receipt_evaluated_at_missing")
    elif _parse_iso_datetime(evaluated_at_raw) is None:
        failure_reasons.append("outcome_receipt_evaluated_at_unparseable")

    if not str(receipt.outcome_hash).strip():
        failure_reasons.append("outcome_receipt_hash_missing")

    return OutcomeReceiptValidationResult(not failure_reasons, sorted(set(failure_reasons)))


def build_outcome_receipt(
    *,
    decision_id: str,
    execution_intent_id: str,
    bind_receipt_id: str | None,
    operation_id: str,
    action_class: str,
    target_system: str,
    target_resource: str,
    intended_action: str,
    requested_scope: list[str],
    final_outcome: str,
    pre_state_fingerprint: str | None = None,
    post_state_fingerprint: str | None = None,
    postcondition_status: str = "skipped",
    observed_effects: list[dict[str, Any]] | None = None,
    failure_reasons: list[str] | None = None,
    rollback_status: str | None = None,
    evaluated_at: str = "",
    metadata: dict[str, Any] | None = None,
) -> OutcomeReceipt:
    """Build a deterministic local/offline finalized outcome receipt."""
    normalized_outcome = str(final_outcome).strip().lower()
    normalized_rollback = str(rollback_status or "").strip().lower()
    committed = normalized_outcome in _COMMITTED_OUTCOMES
    blocked = normalized_outcome in {"block", "blocked", "refuse", "refused"}
    escalated = normalized_outcome in {"escalate", "escalated"}
    rolled_back = normalized_rollback in {"performed", "rolled_back", "success", "completed"}

    receipt = OutcomeReceipt(
        outcome_receipt_id=f"outcome-{operation_id}",
        decision_id=decision_id,
        execution_intent_id=execution_intent_id,
        bind_receipt_id=bind_receipt_id,
        operation_id=operation_id,
        action_class=action_class,
        target_system=target_system,
        target_resource=target_resource,
        intended_action=intended_action,
        requested_scope=list(requested_scope),
        final_outcome=final_outcome,
        committed=committed,
        blocked=blocked,
        escalated=escalated,
        rolled_back=rolled_back,
        pre_state_fingerprint=pre_state_fingerprint,
        post_state_fingerprint=post_state_fingerprint,
        postcondition_status=postcondition_status,  # type: ignore[arg-type]
        observed_effects=list(observed_effects or []),
        failure_reasons=list(failure_reasons or []),
        rollback_status=rollback_status,
        evaluated_at=evaluated_at,
        outcome_hash="",
        metadata=dict(metadata or {}),
    )
    return with_outcome_hash(receipt)


def _parse_iso_datetime(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
