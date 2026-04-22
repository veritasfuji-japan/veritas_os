"""Bind-controlled policy bundle promotion helpers.

This module provides a production-adjacent internal path that performs policy
bundle promotion through bind-boundary adjudication.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from veritas_os.policy.bind_artifacts import BindReceipt, ExecutionIntent
from veritas_os.policy.bind_boundary_adapters import PolicyBundlePromotionAdapter
from veritas_os.policy.bind_core import execute_bind_adjudication


def promote_policy_bundle_with_bind_boundary(
    *,
    decision_id: str,
    request_id: str,
    actor_identity: str,
    policy_snapshot_id: str,
    decision_hash: str,
    target_bundle_dir: str | Path,
    pointer_path: str | Path,
    allowed_root: str | Path,
    approval_context: dict[str, Any] | None = None,
    policy_lineage: dict[str, Any] | None = None,
    decision_ts: str | None = None,
    require_signature: bool = True,
    append_trustlog: bool = True,
    bind_ts: str | None = None,
    execution_intent_id: str | None = None,
    bind_receipt_id: str | None = None,
) -> BindReceipt:
    """Promote active policy bundle pointer via bind-boundary execution.

    The function builds an ``ExecutionIntent`` and routes promotion through
    ``execute_bind_adjudication`` using ``PolicyBundlePromotionAdapter``.
    """
    target_path = Path(target_bundle_dir).expanduser().resolve()
    adapter = PolicyBundlePromotionAdapter(
        pointer_path=Path(pointer_path).expanduser().resolve(),
        allowed_root=Path(allowed_root).expanduser().resolve(),
        require_signature=require_signature,
    )

    pre_snapshot = adapter.snapshot()
    expected_fingerprint = adapter.fingerprint_state(pre_snapshot)

    merged_approval_context: dict[str, Any] = dict(approval_context or {})
    merged_approval_context.setdefault("policy_bundle_promotion_approved", True)

    intent = ExecutionIntent(
        execution_intent_id=execution_intent_id or uuid4().hex,
        decision_id=decision_id,
        request_id=request_id,
        policy_snapshot_id=policy_snapshot_id,
        actor_identity=actor_identity,
        target_system="governance",
        target_resource=str(target_path),
        intended_action="promote_policy_bundle",
        decision_hash=decision_hash,
        decision_ts=decision_ts or _utc_now_iso8601(),
        expected_state_fingerprint=expected_fingerprint,
        approval_context=merged_approval_context,
        policy_lineage=dict(policy_lineage or {}),
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
