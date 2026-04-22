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

from dataclasses import dataclass, field, replace
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
    policy_lineage: dict[str, Any] | None = None

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
            "policy_lineage": self.policy_lineage,
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
    bind_receipt_hash: str = ""
    execution_intent_hash: str = ""
    policy_snapshot_id: str = ""
    actor_identity: str = ""
    decision_hash: str = ""
    governance_identity: dict[str, Any] | None = None
    revalidation_context: dict[str, Any] = field(default_factory=dict)
    bind_reason_code: str | None = None
    bind_failure_reason: str | None = None
    idempotency_key: str | None = None
    idempotency_status: str | None = None
    retry_safety: str | None = None
    rollback_status: str | None = None
    failure_category: str | None = None
    target_path: str = ""
    target_type: str = ""
    target_path_type: str = "other"
    target_label: str = "other"
    operator_surface: str = "audit"
    relevant_ui_href: str = "/audit"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        final_outcome = (
            self.final_outcome.value
            if isinstance(self.final_outcome, FinalOutcome)
            else str(self.final_outcome)
        )
        target_path = str(self.target_path).strip() if isinstance(self.target_path, str) else ""
        target_type = str(self.target_type).strip() if isinstance(self.target_type, str) else ""
        target_path_type = str(self.target_path_type or "").strip() or "other"
        target_label = str(self.target_label or "").strip() or "other"
        operator_surface = str(self.operator_surface or "").strip() or "audit"
        relevant_ui_href = str(self.relevant_ui_href or "").strip() or "/audit"
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
            "final_outcome": final_outcome,
            "rollback_reason": self.rollback_reason,
            "escalation_reason": self.escalation_reason,
            "trustlog_hash": self.trustlog_hash,
            "prev_bind_hash": self.prev_bind_hash,
            "bind_receipt_hash": self.bind_receipt_hash,
            "execution_intent_hash": self.execution_intent_hash,
            "policy_snapshot_id": self.policy_snapshot_id,
            "actor_identity": self.actor_identity,
            "decision_hash": self.decision_hash,
            "governance_identity": self.governance_identity,
            "revalidation_context": dict(self.revalidation_context),
            "bind_reason_code": self.bind_reason_code,
            "bind_failure_reason": self.bind_failure_reason,
            "idempotency_key": self.idempotency_key,
            "idempotency_status": self.idempotency_status,
            "retry_safety": self.retry_safety,
            "rollback_status": self.rollback_status,
            "failure_category": self.failure_category,
            "target_path": target_path,
            "target_type": target_type,
            "target_path_type": target_path_type,
            "target_label": target_label,
            "operator_surface": operator_surface,
            "relevant_ui_href": relevant_ui_href,
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
    payload = receipt.to_dict()
    # Keep hash semantics stable/non-recursive even when receipt stores its own hash.
    payload["bind_receipt_hash"] = ""
    return sha256_of_canonical_json(payload)


def build_execution_intent_trustlog_entry(intent: ExecutionIntent) -> dict[str, Any]:
    """Build a native TrustLog entry payload for ``ExecutionIntent`` lineage."""
    return {
        "kind": "governance.execution_intent",
        "request_id": intent.request_id or intent.decision_id,
        "decision_id": intent.decision_id,
        "execution_intent_id": intent.execution_intent_id,
        "policy_snapshot_id": intent.policy_snapshot_id,
        "actor_identity": intent.actor_identity,
        "decision_hash": intent.decision_hash,
        "execution_intent_hash": hash_execution_intent(intent),
        "execution_intent": intent.to_dict(),
    }


def _extract_bind_receipt(entry: dict[str, Any]) -> BindReceipt | None:
    """Return ``BindReceipt`` when entry is a bind-receipt trustlog record."""
    if entry.get("kind") != "governance.bind_receipt":
        return None
    payload = entry.get("bind_receipt")
    if not isinstance(payload, dict):
        return None
    try:
        return BindReceipt(
            bind_receipt_id=str(payload.get("bind_receipt_id") or ""),
            execution_intent_id=str(payload.get("execution_intent_id") or ""),
            decision_id=str(payload.get("decision_id") or ""),
            bind_ts=str(payload.get("bind_ts") or ""),
            live_state_fingerprint_before=str(payload.get("live_state_fingerprint_before") or ""),
            live_state_fingerprint_after=str(payload.get("live_state_fingerprint_after") or ""),
            authority_check_result=dict(payload.get("authority_check_result") or {}),
            constraint_check_result=dict(payload.get("constraint_check_result") or {}),
            drift_check_result=dict(payload.get("drift_check_result") or {}),
            risk_check_result=dict(payload.get("risk_check_result") or {}),
            admissibility_result=dict(payload.get("admissibility_result") or {}),
            final_outcome=FinalOutcome(str(payload.get("final_outcome") or FinalOutcome.BLOCKED.value)),
            rollback_reason=payload.get("rollback_reason"),
            escalation_reason=payload.get("escalation_reason"),
            trustlog_hash=str(payload.get("trustlog_hash") or ""),
            prev_bind_hash=payload.get("prev_bind_hash"),
            bind_receipt_hash=str(payload.get("bind_receipt_hash") or ""),
            execution_intent_hash=str(payload.get("execution_intent_hash") or ""),
            policy_snapshot_id=str(payload.get("policy_snapshot_id") or ""),
            actor_identity=str(payload.get("actor_identity") or ""),
            decision_hash=str(payload.get("decision_hash") or ""),
            governance_identity=(
                dict(payload.get("governance_identity"))
                if isinstance(payload.get("governance_identity"), dict)
                else None
            ),
            revalidation_context=dict(payload.get("revalidation_context") or {}),
            bind_reason_code=(
                str(payload.get("bind_reason_code"))
                if payload.get("bind_reason_code")
                else None
            ),
            bind_failure_reason=(
                str(payload.get("bind_failure_reason"))
                if payload.get("bind_failure_reason")
                else None
            ),
            idempotency_key=(
                str(payload.get("idempotency_key"))
                if payload.get("idempotency_key")
                else None
            ),
            idempotency_status=(
                str(payload.get("idempotency_status"))
                if payload.get("idempotency_status")
                else None
            ),
            retry_safety=(
                str(payload.get("retry_safety")) if payload.get("retry_safety") else None
            ),
            rollback_status=(
                str(payload.get("rollback_status")) if payload.get("rollback_status") else None
            ),
            failure_category=(
                str(payload.get("failure_category"))
                if payload.get("failure_category")
                else None
            ),
            target_path=str(payload.get("target_path") or ""),
            target_type=str(payload.get("target_type") or ""),
            target_path_type=str(payload.get("target_path_type") or "other"),
            target_label=str(payload.get("target_label") or "other"),
            operator_surface=str(payload.get("operator_surface") or "audit"),
            relevant_ui_href=str(payload.get("relevant_ui_href") or "/audit"),
        )
    except (TypeError, ValueError):
        return None


def get_previous_bind_hash(*, decision_id: str = "", execution_intent_id: str = "") -> str | None:
    """Find the latest bind hash for lineage chaining using native TrustLog."""
    from veritas_os.logging.trust_log import iter_trust_log

    for entry in iter_trust_log(reverse=True):
        if entry.get("kind") != "governance.bind_receipt":
            continue
        if decision_id and entry.get("decision_id") != decision_id:
            continue
        if execution_intent_id and entry.get("execution_intent_id") != execution_intent_id:
            continue
        value = entry.get("bind_receipt_hash")
        if isinstance(value, str) and value:
            return value
    return None


def append_execution_intent_trustlog(intent: ExecutionIntent) -> dict[str, Any]:
    """Append ``ExecutionIntent`` to TrustLog using existing hash-chain/sign path."""
    from veritas_os.logging.trust_log import append_trust_log

    return append_trust_log(build_execution_intent_trustlog_entry(intent))


def append_bind_receipt_trustlog(receipt: BindReceipt) -> BindReceipt:
    """Append ``BindReceipt`` via native TrustLog and return linked receipt."""
    from veritas_os.logging.trust_log import append_trust_log

    prev_bind_hash = receipt.prev_bind_hash or get_previous_bind_hash(
        decision_id=receipt.decision_id,
        execution_intent_id=receipt.execution_intent_id,
    )
    candidate = replace(receipt, prev_bind_hash=prev_bind_hash)
    bind_receipt_hash = hash_bind_receipt(candidate)
    candidate = replace(candidate, bind_receipt_hash=bind_receipt_hash)

    entry = append_trust_log(
        {
            "kind": "governance.bind_receipt",
            "request_id": candidate.decision_id,
            "decision_id": candidate.decision_id,
            "execution_intent_id": candidate.execution_intent_id,
            "bind_receipt_id": candidate.bind_receipt_id,
            "bind_ts": candidate.bind_ts,
            "final_outcome": (
                candidate.final_outcome.value
                if isinstance(candidate.final_outcome, FinalOutcome)
                else str(candidate.final_outcome)
            ),
            "prev_bind_hash": candidate.prev_bind_hash,
            "bind_receipt_hash": bind_receipt_hash,
            "bind_receipt": candidate.to_dict(),
        }
    )
    trustlog_hash = str(entry.get("sha256") or "")
    return replace(candidate, trustlog_hash=trustlog_hash)


def find_bind_receipts(
    *,
    bind_receipt_id: str | None = None,
    execution_intent_id: str | None = None,
    decision_id: str | None = None,
) -> list[BindReceipt]:
    """Retrieve bind receipts from TrustLog filtered by lineage identifiers."""
    from veritas_os.logging.trust_log import iter_trust_log

    matched: list[BindReceipt] = []
    for entry in iter_trust_log(reverse=False):
        if entry.get("kind") != "governance.bind_receipt":
            continue
        if bind_receipt_id and entry.get("bind_receipt_id") != bind_receipt_id:
            continue
        if execution_intent_id and entry.get("execution_intent_id") != execution_intent_id:
            continue
        if decision_id and entry.get("decision_id") != decision_id:
            continue
        receipt = _extract_bind_receipt(entry)
        if receipt is not None:
            matched.append(receipt)
    return matched
