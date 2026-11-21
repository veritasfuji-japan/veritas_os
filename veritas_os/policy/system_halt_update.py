"""Bind-controlled system halt helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Literal
from uuid import uuid4

from veritas_os.policy.bind_artifacts import BindReceipt, ExecutionIntent
from veritas_os.policy.bind_boundary_adapters import SystemHaltAdapter, SystemResumeAdapter
from veritas_os.policy.bind_core import execute_bind_adjudication
from veritas_os.policy.bind_core.core import BindAuditSink


_SYSTEM_CONTROL_INTENT_TTL_SECONDS = 30


def new_system_control_intent_window() -> tuple[str, datetime]:
    """Issue the timestamp and matching deadline for a bounded control intent."""
    issued_at = _utc_now_iso8601()
    return issued_at, datetime.fromisoformat(issued_at) + timedelta(seconds=_SYSTEM_CONTROL_INTENT_TTL_SECONDS)


def halt_system_with_bind_boundary(
    *,
    decision_id: str,
    request_id: str,
    actor_identity: str,
    policy_snapshot_id: str,
    decision_hash: str,
    reason: str,
    operator: str,
    status_reader: Callable[[], dict[str, Any]],
    halt_executor: Callable[..., dict[str, Any]],
    approval_context: dict[str, Any] | None = None,
    policy_lineage: dict[str, Any] | None = None,
    governance_policy: dict[str, Any] | None = None,
    decision_ts: str | None = None,
    bounded_intent: bool = False,
    append_trustlog: bool = True,
    bind_ts: str | None = None,
    execution_intent_id: str | None = None,
    bind_receipt_id: str | None = None,
) -> BindReceipt:
    """Execute operator emergency halt through bind-boundary adjudication."""
    adapter = SystemHaltAdapter(
        status_reader=status_reader,
        halt_executor=halt_executor,
        reason=reason,
        operator=operator,
    )
    issued_at = decision_ts or _utc_now_iso8601()
    pre_snapshot = adapter.snapshot()
    expected_fingerprint = adapter.fingerprint_state(pre_snapshot)

    merged_approval_context: dict[str, Any] = dict(approval_context or {})
    merged_approval_context.setdefault("system_halt_approved", True)
    if bounded_intent:
        merged_approval_context["approval_freshness_basis"] = "authenticated_emergency_halt"

    intent = ExecutionIntent(
        execution_intent_id=execution_intent_id or uuid4().hex,
        decision_id=decision_id,
        request_id=request_id,
        policy_snapshot_id=policy_snapshot_id,
        actor_identity=actor_identity,
        target_system="system",
        target_resource="system/halt",
        intended_action="halt_system",
        decision_hash=decision_hash,
        decision_ts=issued_at,
        ttl_seconds=_SYSTEM_CONTROL_INTENT_TTL_SECONDS if bounded_intent else None,
        expected_state_fingerprint=expected_fingerprint,
        approval_context=merged_approval_context,
        policy_lineage=_with_bind_policy_lineage(
            operation="halt",
            authenticated_halt=bounded_intent,
            lineage=policy_lineage,
            governance_policy=governance_policy,
        ),
    )

    return execute_bind_adjudication(
        execution_intent=intent,
        adapter=adapter,
        bind_ts=bind_ts,
        bind_receipt_id=bind_receipt_id,
        append_trustlog=append_trustlog,
    )


def resume_system_with_bind_boundary(
    *,
    decision_id: str,
    request_id: str,
    actor_identity: str,
    policy_snapshot_id: str,
    decision_hash: str,
    operator: str,
    comment: str,
    status_reader: Callable[[], dict[str, Any]],
    resume_executor: Callable[..., dict[str, Any] | None],
    approval_context: dict[str, Any] | None = None,
    policy_lineage: dict[str, Any] | None = None,
    governance_policy: dict[str, Any] | None = None,
    decision_ts: str | None = None,
    bounded_intent: bool = False,
    append_trustlog: bool | BindAuditSink = True,
    bind_ts: str | None = None,
    execution_intent_id: str | None = None,
    bind_receipt_id: str | None = None,
) -> BindReceipt:
    """Execute operator system resume through bind-boundary adjudication."""
    adapter = SystemResumeAdapter(
        status_reader=status_reader,
        resume_executor=resume_executor,
        operator=operator,
        comment=comment,
    )
    issued_at = decision_ts or _utc_now_iso8601()
    pre_snapshot = adapter.snapshot()
    expected_fingerprint = adapter.fingerprint_state(pre_snapshot)

    merged_approval_context: dict[str, Any] = dict(approval_context or {})
    merged_approval_context.setdefault("system_resume_approved", True)

    intent = ExecutionIntent(
        execution_intent_id=execution_intent_id or uuid4().hex,
        decision_id=decision_id,
        request_id=request_id,
        policy_snapshot_id=policy_snapshot_id,
        actor_identity=actor_identity,
        target_system="system",
        target_resource="system/resume",
        intended_action="resume_system",
        decision_hash=decision_hash,
        decision_ts=issued_at,
        ttl_seconds=_SYSTEM_CONTROL_INTENT_TTL_SECONDS if bounded_intent else None,
        expected_state_fingerprint=expected_fingerprint,
        approval_context=merged_approval_context,
        policy_lineage=_with_bind_policy_lineage(
            operation="resume",
            lineage=policy_lineage,
            governance_policy=governance_policy,
        ),
    )

    return execute_bind_adjudication(
        execution_intent=intent,
        adapter=adapter,
        bind_ts=bind_ts,
        bind_receipt_id=bind_receipt_id,
        append_trustlog=append_trustlog,
    )


def _utc_now_iso8601() -> str:
    """Return current UTC timestamp in canonical bind intent format."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _with_bind_policy_lineage(
    *,
    operation: Literal["halt", "resume"],
    authenticated_halt: bool = False,
    lineage: dict[str, Any] | None,
    governance_policy: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge governance bind policy surface into execution intent lineage."""
    merged: dict[str, Any] = dict(lineage or {})
    merged.setdefault("bind_target_metadata", {
        "target_path": f"/v1/system/{operation}",
        "target_type": f"system_{operation}",
        "target_path_type": f"system_{operation}",
        "target_label": "system emergency halt" if operation == "halt" else "system resume",
        "operator_surface": "compliance",
        "relevant_ui_href": "/system",
    })
    if isinstance(governance_policy, dict):
        bind_policy = governance_policy.get("bind_adjudication")
        if isinstance(bind_policy, dict):
            merged.setdefault("bind_adjudication", dict(bind_policy))

    if authenticated_halt:
        # Halting uses the authenticated operator's authority and request TTL.
        # A separate approval receipt is required to resume, not to stop.
        existing_policy = merged.get("bind_adjudication")
        halt_policy = dict(existing_policy) if isinstance(existing_policy, dict) else {}
        halt_policy["approval_freshness_required"] = False
        merged["bind_adjudication"] = halt_policy

    return merged
