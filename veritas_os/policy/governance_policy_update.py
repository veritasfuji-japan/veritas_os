"""Bind-controlled governance policy update helpers.

This module wires the existing governance policy update path through
bind-boundary adjudication without altering legacy policy repository behavior.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from veritas_os.policy.bind_artifacts import BindReceipt, ExecutionIntent
from veritas_os.policy.bind_boundary_adapters import GovernancePolicyUpdateAdapter
from veritas_os.policy.bind_core import execute_bind_adjudication


def update_governance_policy_with_bind_boundary(
    *,
    decision_id: str,
    request_id: str,
    actor_identity: str,
    policy_snapshot_id: str,
    decision_hash: str,
    policy_patch: dict[str, Any],
    policy_reader: Callable[[], dict[str, Any]],
    policy_updater: Callable[[dict[str, Any]], dict[str, Any]],
    policy_rollback: Callable[..., dict[str, Any]] | None = None,
    approval_context: dict[str, Any] | None = None,
    policy_lineage: dict[str, Any] | None = None,
    approval_records: list[dict[str, Any]] | None = None,
    decision_ts: str | None = None,
    governance_policy: dict[str, Any] | None = None,
    append_trustlog: bool = True,
    bind_ts: str | None = None,
    execution_intent_id: str | None = None,
    bind_receipt_id: str | None = None,
) -> BindReceipt:
    """Apply governance policy patch through bind-boundary adjudication."""
    adapter = GovernancePolicyUpdateAdapter(
        policy_reader=policy_reader,
        policy_updater=policy_updater,
        policy_patch=dict(policy_patch),
        policy_rollback=policy_rollback,
        approval_records=approval_records,
    )

    pre_snapshot = adapter.snapshot()
    expected_fingerprint = adapter.fingerprint_state(pre_snapshot)

    merged_approval_context: dict[str, Any] = dict(approval_context or {})
    merged_approval_context.setdefault("governance_policy_update_approved", True)

    intent = ExecutionIntent(
        execution_intent_id=execution_intent_id or uuid4().hex,
        decision_id=decision_id,
        request_id=request_id,
        policy_snapshot_id=policy_snapshot_id,
        actor_identity=actor_identity,
        target_system="governance",
        target_resource="governance/policy",
        intended_action="update_governance_policy",
        decision_hash=decision_hash,
        decision_ts=decision_ts or _utc_now_iso8601(),
        expected_state_fingerprint=expected_fingerprint,
        approval_context=merged_approval_context,
        policy_lineage=_with_bind_policy_lineage(
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
    lineage: dict[str, Any] | None,
    governance_policy: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge governance bind policy surface into execution intent lineage."""
    merged: dict[str, Any] = dict(lineage or {})
    merged.setdefault(
        "bind_target_metadata",
        {
            "target_path": "/v1/governance/policy",
            "target_type": "governance_policy",
            "target_path_type": "governance_policy_update",
            "target_label": "governance policy update",
            "operator_surface": "governance",
            "relevant_ui_href": "/governance",
        },
    )
    if not isinstance(governance_policy, dict):
        return merged
    bind_policy = governance_policy.get("bind_adjudication")
    if isinstance(bind_policy, dict):
        merged.setdefault("bind_adjudication", dict(bind_policy))
    return merged
