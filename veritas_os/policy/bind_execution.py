"""Minimal native bind-boundary execution contract.

This module adds a small, adapter-based bind execution substrate that sits
between decision artifacts and concrete execution side effects. It is designed
for deterministic orchestration tests and does not alter FUJI or continuation
runtime semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from veritas_os.core.continuation_runtime.bind_admissibility import (
    AdmissibilityOutcome,
    BindAdmissibilityInput,
    CheckStatus,
    evaluate_bind_admissibility,
)
from veritas_os.policy.bind_artifacts import (
    BindReceipt,
    ExecutionIntent,
    FinalOutcome,
    append_bind_receipt_trustlog,
    append_execution_intent_trustlog,
)
from veritas_os.security.hash import canonical_json_dumps, sha256_of_canonical_json


@dataclass(frozen=True)
class BindExecutionCheckResult:
    """Structured check result for adapter-driven signals."""

    status: str
    reason_code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        """Return JSON-serializable check payload."""
        return {
            "status": self.status,
            "reason_code": self.reason_code,
            "message": self.message,
        }


class BindBoundaryAdapter(Protocol):
    """Narrow bind-boundary execution adapter contract."""

    def snapshot(self) -> Any:
        """Capture current target state before bind execution."""

    def fingerprint_state(self, snapshot: Any) -> str:
        """Return deterministic fingerprint of a state snapshot."""

    def validate_authority(self, intent: ExecutionIntent, snapshot: Any) -> bool | None:
        """Return bind-time authority validity (None means missing signal)."""

    def validate_constraints(
        self,
        intent: ExecutionIntent,
        snapshot: Any,
    ) -> dict[str, bool] | None:
        """Return bind-time constraint status map (None means missing signal)."""

    def assess_runtime_risk(self, intent: ExecutionIntent, snapshot: Any) -> bool | None:
        """Return runtime risk admissibility (None means missing signal)."""

    def apply(self, intent: ExecutionIntent, snapshot: Any) -> bool:
        """Apply staged change to target. Return ``True`` on success."""

    def verify_postconditions(self, intent: ExecutionIntent, snapshot: Any) -> bool:
        """Verify postconditions after apply."""

    def revert(self, intent: ExecutionIntent, snapshot: Any) -> bool:
        """Revert or compensate using pre-apply snapshot."""

    def describe_target(self) -> str:
        """Return a short human-readable target description."""


@dataclass
class ReferenceBindAdapter:
    """Deterministic in-memory reference adapter for orchestration tests."""

    state: dict[str, Any]
    pending_changes: dict[str, Any] = field(default_factory=dict)
    authority_signal: bool | None = True
    constraint_signals: dict[str, bool] | None = field(
        default_factory=lambda: {"default_constraint": True}
    )
    runtime_risk_signal: bool | None = True
    snapshot_success: bool = True
    apply_success: bool = True
    postcondition_success: bool = True
    revert_success: bool = True
    target_description: str = "reference/in-memory"

    def snapshot(self) -> dict[str, Any]:
        """Return a deep-copied snapshot for deterministic rollback paths."""
        if not self.snapshot_success:
            raise RuntimeError("BIND_SNAPSHOT_READ_ERROR")
        return _deep_copy_mapping(self.state)

    def fingerprint_state(self, snapshot: Any) -> str:
        """Compute deterministic SHA-256 over canonical snapshot JSON."""
        if not isinstance(snapshot, dict):
            raise ValueError("BIND_STATE_SNAPSHOT_INVALID")
        return sha256_of_canonical_json(snapshot)

    def validate_authority(self, intent: ExecutionIntent, snapshot: Any) -> bool | None:
        """Return configured authority signal."""
        return self.authority_signal

    def validate_constraints(
        self,
        intent: ExecutionIntent,
        snapshot: Any,
    ) -> dict[str, bool] | None:
        """Return configured constraint signal mapping."""
        if self.constraint_signals is None:
            return None
        return dict(self.constraint_signals)

    def assess_runtime_risk(self, intent: ExecutionIntent, snapshot: Any) -> bool | None:
        """Return configured runtime risk signal."""
        return self.runtime_risk_signal

    def apply(self, intent: ExecutionIntent, snapshot: Any) -> bool:
        """Apply deterministic in-memory mutation."""
        if not self.apply_success:
            raise RuntimeError("BIND_APPLY_ERROR")
        self.state.update(self.pending_changes)
        return True

    def verify_postconditions(self, intent: ExecutionIntent, snapshot: Any) -> bool:
        """Return configured postcondition verdict."""
        return self.postcondition_success

    def revert(self, intent: ExecutionIntent, snapshot: Any) -> bool:
        """Restore state to pre-apply snapshot when configured to succeed."""
        if not self.revert_success:
            raise RuntimeError("BIND_REVERT_ERROR")
        if not isinstance(snapshot, dict):
            return False
        self.state.clear()
        self.state.update(_deep_copy_mapping(snapshot))
        return True

    def describe_target(self) -> str:
        """Return deterministic target descriptor."""
        return self.target_description


@dataclass(frozen=True)
class BindPolicyConfig:
    """Policy-driven bind adjudication toggles resolved from governance lineage."""

    drift_required: bool = True
    ttl_required: bool = False
    approval_freshness_required: bool = False
    missing_signal_outcome: AdmissibilityOutcome = AdmissibilityOutcome.BLOCK


def execute_bind_boundary(
    *,
    execution_intent: ExecutionIntent,
    adapter: BindBoundaryAdapter,
    bind_ts: str | None = None,
    bind_receipt_id: str | None = None,
    append_trustlog: bool = True,
) -> BindReceipt:
    """Orchestrate snapshot -> admissibility -> apply -> verify -> commit/revert.

    This path is deterministic and fail-closed. Any missing critical runtime
    signal results in non-committed outcomes.
    """
    ts = bind_ts or _utc_now_iso8601()

    if bind_receipt_id:
        base_receipt = BindReceipt(
            bind_receipt_id=bind_receipt_id,
            execution_intent_id=execution_intent.execution_intent_id,
            decision_id=execution_intent.decision_id,
            bind_ts=ts,
        )
    else:
        base_receipt = BindReceipt(
            execution_intent_id=execution_intent.execution_intent_id,
            decision_id=execution_intent.decision_id,
            bind_ts=ts,
        )

    try:
        pre_snapshot = adapter.snapshot()
        pre_fingerprint = adapter.fingerprint_state(pre_snapshot)
    except (TypeError, ValueError, RuntimeError) as exc:
        return _finalize_receipt(
            execution_intent=execution_intent,
            append_trustlog=append_trustlog,
            receipt=_with_receipt(
            base_receipt,
            live_state_fingerprint_before="",
            authority_check_result=_check_unknown("BIND_AUTHORITY_UNKNOWN", "snapshot unavailable"),
            constraint_check_result=_check_unknown(
                "BIND_CONSTRAINTS_UNKNOWN",
                "snapshot unavailable",
            ),
            drift_check_result=_check_unknown("BIND_DRIFT_UNKNOWN", "snapshot unavailable"),
            risk_check_result=_check_unknown("BIND_RUNTIME_RISK_UNKNOWN", "snapshot unavailable"),
            admissibility_result={
                "admissible": False,
                "recommended_outcome": AdmissibilityOutcome.BLOCK.value,
                "reason_codes": ["BIND_SNAPSHOT_FAILED"],
                "reason": str(exc),
            },
            final_outcome=FinalOutcome.SNAPSHOT_FAILED,
            ),
        )

    authority_signal = adapter.validate_authority(execution_intent, pre_snapshot)
    constraint_signals = adapter.validate_constraints(execution_intent, pre_snapshot)
    runtime_risk_signal = adapter.assess_runtime_risk(execution_intent, pre_snapshot)
    bind_policy = _resolve_bind_policy_config(execution_intent)
    ttl_expires_at = _build_ttl_expiry(execution_intent)
    approval_expires_at = _build_approval_expiry(execution_intent)

    admissibility = evaluate_bind_admissibility(
        BindAdmissibilityInput(
            execution_intent=execution_intent.execution_intent_id,
            current_timestamp=ts,
            authority_signal=authority_signal,
            constraint_signals=constraint_signals,
            live_state_fingerprint=pre_fingerprint,
            expected_state_fingerprint=execution_intent.expected_state_fingerprint,
            runtime_risk_signal=runtime_risk_signal,
            drift_sensitive=bind_policy.drift_required,
            ttl_required=bind_policy.ttl_required,
            approval_freshness_required=bind_policy.approval_freshness_required,
            missing_signal_outcome=bind_policy.missing_signal_outcome,
            ttl_expires_at=ttl_expires_at,
            approval_expires_at=approval_expires_at,
        )
    )

    authority_result = _check_from_runtime(admissibility.authority_check_result)
    constraint_result = _check_from_runtime(admissibility.constraint_check_result)
    drift_result = _check_from_runtime(admissibility.drift_check_result)
    risk_result = _check_from_runtime(admissibility.risk_check_result)

    if not admissibility.admissibility_result:
        blocked_outcome = FinalOutcome.BLOCKED
        escalation_reason = None
        if admissibility.recommended_outcome is AdmissibilityOutcome.ESCALATE:
            blocked_outcome = FinalOutcome.ESCALATED
            escalation_reason = "BIND_ADMISSIBILITY_ESCALATION_REQUIRED"

        return _finalize_receipt(
            execution_intent=execution_intent,
            append_trustlog=append_trustlog,
            receipt=_with_receipt(
            base_receipt,
            live_state_fingerprint_before=pre_fingerprint,
            authority_check_result=authority_result,
            constraint_check_result=constraint_result,
            drift_check_result=drift_result,
            risk_check_result=risk_result,
            admissibility_result={
                "admissible": False,
                "recommended_outcome": admissibility.recommended_outcome.value,
                "reason_codes": list(admissibility.reason_codes),
                "target": adapter.describe_target(),
            },
            final_outcome=blocked_outcome,
            escalation_reason=escalation_reason,
            ),
        )

    try:
        adapter.apply(execution_intent, pre_snapshot)
    except (TypeError, ValueError, RuntimeError) as exc:
        return _finalize_receipt(
            execution_intent=execution_intent,
            append_trustlog=append_trustlog,
            receipt=_with_receipt(
            base_receipt,
            live_state_fingerprint_before=pre_fingerprint,
            authority_check_result=authority_result,
            constraint_check_result=constraint_result,
            drift_check_result=drift_result,
            risk_check_result=risk_result,
            admissibility_result={
                "admissible": True,
                "recommended_outcome": admissibility.recommended_outcome.value,
                "reason_codes": [],
                "target": adapter.describe_target(),
            },
            final_outcome=FinalOutcome.APPLY_FAILED,
            rollback_reason=f"BIND_APPLY_FAILED:{exc}",
            ),
        )

    verified = adapter.verify_postconditions(execution_intent, pre_snapshot)
    if not verified:
        return _finalize_receipt(
            execution_intent=execution_intent,
            append_trustlog=append_trustlog,
            receipt=_rollback_after_verification_failure(
            base_receipt=base_receipt,
            adapter=adapter,
            execution_intent=execution_intent,
            pre_snapshot=pre_snapshot,
            pre_fingerprint=pre_fingerprint,
            authority_result=authority_result,
            constraint_result=constraint_result,
            drift_result=drift_result,
            risk_result=risk_result,
            recommended_outcome=admissibility.recommended_outcome.value,
            ),
        )

    try:
        post_snapshot = adapter.snapshot()
        post_fingerprint = adapter.fingerprint_state(post_snapshot)
    except (TypeError, ValueError, RuntimeError) as exc:
        return _finalize_receipt(
            execution_intent=execution_intent,
            append_trustlog=append_trustlog,
            receipt=_rollback_after_runtime_signal_failure(
            base_receipt=base_receipt,
            adapter=adapter,
            execution_intent=execution_intent,
            pre_snapshot=pre_snapshot,
            pre_fingerprint=pre_fingerprint,
            authority_result=authority_result,
            constraint_result=constraint_result,
            drift_result=drift_result,
            risk_result=risk_result,
            reason=f"BIND_POST_FINGERPRINT_FAILED:{exc}",
            recommended_outcome=admissibility.recommended_outcome.value,
            ),
        )

    return _finalize_receipt(
        execution_intent=execution_intent,
        append_trustlog=append_trustlog,
        receipt=_with_receipt(
            base_receipt,
            live_state_fingerprint_before=pre_fingerprint,
            live_state_fingerprint_after=post_fingerprint,
            authority_check_result=authority_result,
            constraint_check_result=constraint_result,
            drift_check_result=drift_result,
            risk_check_result=risk_result,
            admissibility_result={
                "admissible": True,
                "recommended_outcome": admissibility.recommended_outcome.value,
                "reason_codes": [],
                "target": adapter.describe_target(),
            },
            final_outcome=FinalOutcome.COMMITTED,
        ),
    )


def _rollback_after_verification_failure(
    *,
    base_receipt: BindReceipt,
    adapter: BindBoundaryAdapter,
    execution_intent: ExecutionIntent,
    pre_snapshot: Any,
    pre_fingerprint: str,
    authority_result: dict[str, str],
    constraint_result: dict[str, str],
    drift_result: dict[str, str],
    risk_result: dict[str, str],
    recommended_outcome: str,
) -> BindReceipt:
    """Handle verify failure with explicit rollback/escalation outcomes."""
    try:
        reverted = adapter.revert(execution_intent, pre_snapshot)
    except (TypeError, ValueError, RuntimeError) as exc:
        return _with_receipt(
            base_receipt,
            live_state_fingerprint_before=pre_fingerprint,
            authority_check_result=authority_result,
            constraint_check_result=constraint_result,
            drift_check_result=drift_result,
            risk_check_result=risk_result,
            admissibility_result={
                "admissible": True,
                "recommended_outcome": recommended_outcome,
                "reason_codes": ["BIND_POSTCONDITION_FAILED"],
                "target": adapter.describe_target(),
            },
            final_outcome=FinalOutcome.ESCALATED,
            rollback_reason="BIND_POSTCONDITION_FAILED",
            escalation_reason=f"BIND_REVERT_FAILED_AFTER_VERIFY_FAILURE:{exc}",
        )

    if not reverted:
        return _with_receipt(
            base_receipt,
            live_state_fingerprint_before=pre_fingerprint,
            authority_check_result=authority_result,
            constraint_check_result=constraint_result,
            drift_check_result=drift_result,
            risk_check_result=risk_result,
            admissibility_result={
                "admissible": True,
                "recommended_outcome": recommended_outcome,
                "reason_codes": ["BIND_POSTCONDITION_FAILED"],
                "target": adapter.describe_target(),
            },
            final_outcome=FinalOutcome.ESCALATED,
            rollback_reason="BIND_POSTCONDITION_FAILED",
            escalation_reason="BIND_REVERT_REPORTED_FALSE",
        )

    post_snapshot = adapter.snapshot()
    post_fingerprint = adapter.fingerprint_state(post_snapshot)

    return _with_receipt(
        base_receipt,
        live_state_fingerprint_before=pre_fingerprint,
        live_state_fingerprint_after=post_fingerprint,
        authority_check_result=authority_result,
        constraint_check_result=constraint_result,
        drift_check_result=drift_result,
        risk_check_result=risk_result,
        admissibility_result={
            "admissible": True,
            "recommended_outcome": recommended_outcome,
            "reason_codes": ["BIND_POSTCONDITION_FAILED"],
            "target": adapter.describe_target(),
        },
        final_outcome=FinalOutcome.ROLLED_BACK,
        rollback_reason="BIND_POSTCONDITION_FAILED",
    )


def _rollback_after_runtime_signal_failure(
    *,
    base_receipt: BindReceipt,
    adapter: BindBoundaryAdapter,
    execution_intent: ExecutionIntent,
    pre_snapshot: Any,
    pre_fingerprint: str,
    authority_result: dict[str, str],
    constraint_result: dict[str, str],
    drift_result: dict[str, str],
    risk_result: dict[str, str],
    reason: str,
    recommended_outcome: str,
) -> BindReceipt:
    """Fail closed when critical post-apply runtime signal cannot be read."""
    try:
        reverted = adapter.revert(execution_intent, pre_snapshot)
    except (TypeError, ValueError, RuntimeError) as exc:
        return _with_receipt(
            base_receipt,
            live_state_fingerprint_before=pre_fingerprint,
            authority_check_result=authority_result,
            constraint_check_result=constraint_result,
            drift_check_result=drift_result,
            risk_check_result=risk_result,
            admissibility_result={
                "admissible": True,
                "recommended_outcome": recommended_outcome,
                "reason_codes": ["BIND_POST_SIGNAL_MISSING"],
                "target": adapter.describe_target(),
            },
            final_outcome=FinalOutcome.ESCALATED,
            rollback_reason=reason,
            escalation_reason=f"BIND_REVERT_FAILED_AFTER_POST_SIGNAL_ERROR:{exc}",
        )

    if reverted:
        return _with_receipt(
            base_receipt,
            live_state_fingerprint_before=pre_fingerprint,
            authority_check_result=authority_result,
            constraint_check_result=constraint_result,
            drift_check_result=drift_result,
            risk_check_result=risk_result,
            admissibility_result={
                "admissible": True,
                "recommended_outcome": recommended_outcome,
                "reason_codes": ["BIND_POST_SIGNAL_MISSING"],
                "target": adapter.describe_target(),
            },
            final_outcome=FinalOutcome.ROLLED_BACK,
            rollback_reason=reason,
        )

    return _with_receipt(
        base_receipt,
        live_state_fingerprint_before=pre_fingerprint,
        authority_check_result=authority_result,
        constraint_check_result=constraint_result,
        drift_check_result=drift_result,
        risk_check_result=risk_result,
        admissibility_result={
            "admissible": True,
            "recommended_outcome": recommended_outcome,
            "reason_codes": ["BIND_POST_SIGNAL_MISSING"],
            "target": adapter.describe_target(),
        },
        final_outcome=FinalOutcome.ESCALATED,
        rollback_reason=reason,
        escalation_reason="BIND_REVERT_REPORTED_FALSE",
    )


def _check_from_runtime(check_result: Any) -> dict[str, str]:
    """Convert continuation-runtime check result into receipt payload."""
    return BindExecutionCheckResult(
        status=check_result.status.value,
        reason_code=check_result.reason_code,
        message=check_result.message,
    ).to_dict()


def _check_unknown(reason_code: str, message: str) -> dict[str, str]:
    """Build unknown check result payload when snapshot fails."""
    return BindExecutionCheckResult(
        status=CheckStatus.FAIL.value,
        reason_code=reason_code,
        message=message,
    ).to_dict()


def _build_ttl_expiry(execution_intent: ExecutionIntent) -> str | None:
    """Return TTL expiry timestamp when execution intent has both inputs."""
    if execution_intent.ttl_seconds is None:
        return None
    if not execution_intent.decision_ts:
        return None

    try:
        base_ts = _parse_timestamp(execution_intent.decision_ts)
    except ValueError:
        return None

    return (base_ts + timedelta(seconds=execution_intent.ttl_seconds)).isoformat().replace(
        "+00:00",
        "Z",
    )


def _build_approval_expiry(execution_intent: ExecutionIntent) -> str | None:
    """Return approval expiry from intent approval context when available."""
    if not isinstance(execution_intent.approval_context, dict):
        return None
    approval_expires_at = execution_intent.approval_context.get("approval_expires_at")
    if not isinstance(approval_expires_at, str) or not approval_expires_at.strip():
        return None
    return approval_expires_at.strip()


def _resolve_bind_policy_config(execution_intent: ExecutionIntent) -> BindPolicyConfig:
    """Resolve bind policy from existing governance policy-lineage style fields."""
    lineage_bind = {}
    if isinstance(execution_intent.policy_lineage, dict):
        lineage_bind = execution_intent.policy_lineage.get("bind_adjudication") or {}

    approval_bind = {}
    if isinstance(execution_intent.approval_context, dict):
        approval_bind = execution_intent.approval_context.get("bind_adjudication") or {}

    merged = {}
    if isinstance(lineage_bind, dict):
        merged.update(lineage_bind)
    if isinstance(approval_bind, dict):
        merged.update(approval_bind)

    return BindPolicyConfig(
        drift_required=bool(merged.get("drift_required", True)),
        ttl_required=bool(merged.get("ttl_required", False)),
        approval_freshness_required=bool(merged.get("approval_freshness_required", False)),
        missing_signal_outcome=_parse_missing_signal_outcome(
            merged.get("missing_signal_default", AdmissibilityOutcome.BLOCK.value)
        ),
    )


def _parse_missing_signal_outcome(raw_value: Any) -> AdmissibilityOutcome:
    """Parse configured missing-signal fallback outcome with fail-safe default."""
    if isinstance(raw_value, AdmissibilityOutcome):
        return raw_value
    if isinstance(raw_value, str):
        normalized = raw_value.strip().lower()
        if normalized == AdmissibilityOutcome.ESCALATE.value:
            return AdmissibilityOutcome.ESCALATE
    return AdmissibilityOutcome.BLOCK


def _with_receipt(base_receipt: BindReceipt, **updates: Any) -> BindReceipt:
    """Return a new ``BindReceipt`` preserving identifiers/timestamps."""
    payload = base_receipt.to_dict()
    payload.update(updates)
    return BindReceipt(**payload)


def _finalize_receipt(
    *,
    execution_intent: ExecutionIntent,
    append_trustlog: bool,
    receipt: BindReceipt,
) -> BindReceipt:
    """Return receipt with optional TrustLog lineage append for orchestration paths."""
    if not append_trustlog:
        return receipt
    append_execution_intent_trustlog(execution_intent)
    return append_bind_receipt_trustlog(receipt)


def _deep_copy_mapping(value: dict[str, Any]) -> dict[str, Any]:
    """Return deterministic deep copy via canonical JSON round-trip."""
    return _from_json(canonical_json_dumps(value))


def _from_json(payload: str) -> dict[str, Any]:
    """Decode a canonical JSON mapping payload."""
    import json

    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("BIND_JSON_MAPPING_REQUIRED")
    return data


def _parse_timestamp(raw_timestamp: str) -> datetime:
    """Parse ISO-8601 timestamp into UTC timezone-aware datetime."""
    normalized = raw_timestamp.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _utc_now_iso8601() -> str:
    """Return current UTC timestamp with deterministic seconds precision."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
