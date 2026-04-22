"""Shared bind adjudication core."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

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
from veritas_os.policy.bind_core.constants import BindReasonCode
from veritas_os.policy.bind_core.contracts import BindAdapterContract
from veritas_os.policy.bind_core.normalizers import normalize_execution_intent
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


class BindBoundaryAdapter(BindAdapterContract):
    """Backward-compatible adapter contract alias."""


@dataclass
class ReferenceBindAdapter(BindBoundaryAdapter):
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
        if not self.snapshot_success:
            raise RuntimeError("BIND_SNAPSHOT_READ_ERROR")
        return _deep_copy_mapping(self.state)

    def fingerprint_state(self, snapshot: Any) -> str:
        if not isinstance(snapshot, dict):
            raise ValueError("BIND_STATE_SNAPSHOT_INVALID")
        return sha256_of_canonical_json(snapshot)

    def validate_authority(self, intent: ExecutionIntent, snapshot: Any) -> bool | None:
        del intent, snapshot
        return self.authority_signal

    def validate_constraints(
        self,
        intent: ExecutionIntent,
        snapshot: Any,
    ) -> dict[str, bool] | None:
        del intent, snapshot
        if self.constraint_signals is None:
            return None
        return dict(self.constraint_signals)

    def assess_runtime_risk(self, intent: ExecutionIntent, snapshot: Any) -> bool | None:
        del intent, snapshot
        return self.runtime_risk_signal

    def apply(self, intent: ExecutionIntent, snapshot: Any) -> bool:
        del intent, snapshot
        if not self.apply_success:
            raise RuntimeError("BIND_APPLY_ERROR")
        self.state.update(self.pending_changes)
        return True

    def verify_postconditions(self, intent: ExecutionIntent, snapshot: Any) -> bool:
        del intent, snapshot
        return self.postcondition_success

    def revert(self, intent: ExecutionIntent, snapshot: Any) -> bool:
        del intent
        if not self.revert_success:
            raise RuntimeError("BIND_REVERT_ERROR")
        if not isinstance(snapshot, dict):
            return False
        self.state.clear()
        self.state.update(_deep_copy_mapping(snapshot))
        return True

    def describe_target(self) -> str:
        return self.target_description


@dataclass(frozen=True)
class BindPolicyConfig:
    """Policy-driven bind adjudication toggles resolved from governance lineage."""

    drift_required: bool = True
    ttl_required: bool = False
    approval_freshness_required: bool = False
    rollback_on_apply_failure: bool = False
    missing_signal_outcome: AdmissibilityOutcome = AdmissibilityOutcome.BLOCK


def execute_bind_adjudication(
    *,
    execution_intent: ExecutionIntent | dict[str, Any],
    adapter: BindBoundaryAdapter,
    bind_ts: str | None = None,
    bind_receipt_id: str | None = None,
    append_trustlog: bool = True,
) -> BindReceipt:
    """Orchestrate snapshot -> admissibility -> apply -> verify -> commit/revert."""
    normalized_intent = normalize_execution_intent(execution_intent)
    ts = bind_ts or _utc_now_iso8601()

    base_receipt = BindReceipt(
        bind_receipt_id=bind_receipt_id or "",
        execution_intent_id=normalized_intent.execution_intent_id,
        decision_id=normalized_intent.decision_id,
        bind_ts=ts,
    ) if bind_receipt_id else BindReceipt(
        execution_intent_id=normalized_intent.execution_intent_id,
        decision_id=normalized_intent.decision_id,
        bind_ts=ts,
    )

    precondition_error = _validate_intent_preconditions(normalized_intent)
    if precondition_error:
        return _finalize_receipt(
            execution_intent=normalized_intent,
            append_trustlog=append_trustlog,
            receipt=_with_receipt(
                base_receipt,
                admissibility_result={
                    "admissible": False,
                    "reason_codes": [BindReasonCode.PRECONDITION_INVALID.value],
                    "reason": precondition_error,
                    "target": adapter.describe_target(),
                },
                final_outcome=FinalOutcome.PRECONDITION_FAILED,
            ),
        )

    try:
        pre_snapshot = adapter.snapshot()
        pre_fingerprint = adapter.fingerprint_state(pre_snapshot)
    except (OSError, TypeError, ValueError, RuntimeError) as exc:
        return _finalize_receipt(
            execution_intent=normalized_intent,
            append_trustlog=append_trustlog,
            receipt=_with_receipt(
                base_receipt,
                live_state_fingerprint_before="",
                authority_check_result=_check_unknown(
                    "BIND_AUTHORITY_UNKNOWN", "snapshot unavailable"
                ),
                constraint_check_result=_check_unknown(
                    "BIND_CONSTRAINTS_UNKNOWN",
                    "snapshot unavailable",
                ),
                drift_check_result=_check_unknown("BIND_DRIFT_UNKNOWN", "snapshot unavailable"),
                risk_check_result=_check_unknown(
                    "BIND_RUNTIME_RISK_UNKNOWN", "snapshot unavailable"
                ),
                admissibility_result={
                    "admissible": False,
                    "recommended_outcome": AdmissibilityOutcome.BLOCK.value,
                    "reason_codes": [BindReasonCode.SNAPSHOT_FAILED.value],
                    "reason": str(exc),
                },
                final_outcome=FinalOutcome.SNAPSHOT_FAILED,
            ),
        )

    authority_signal = adapter.validate_authority(normalized_intent, pre_snapshot)
    constraint_signals = adapter.validate_constraints(normalized_intent, pre_snapshot)
    runtime_risk_signal = adapter.assess_runtime_risk(normalized_intent, pre_snapshot)
    bind_policy = _resolve_bind_policy_config(normalized_intent)
    ttl_expires_at = _build_ttl_expiry(normalized_intent)
    approval_expires_at = _build_approval_expiry(normalized_intent)

    admissibility = evaluate_bind_admissibility(
        BindAdmissibilityInput(
            execution_intent=normalized_intent.execution_intent_id,
            current_timestamp=ts,
            authority_signal=authority_signal,
            constraint_signals=constraint_signals,
            live_state_fingerprint=pre_fingerprint,
            expected_state_fingerprint=normalized_intent.expected_state_fingerprint,
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
            escalation_reason = BindReasonCode.ADMISSIBILITY_ESCALATION_REQUIRED.value

        return _finalize_receipt(
            execution_intent=normalized_intent,
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
        adapter.apply(normalized_intent, pre_snapshot)
    except (OSError, TypeError, ValueError, RuntimeError) as exc:
        if bind_policy.rollback_on_apply_failure:
            return _finalize_receipt(
                execution_intent=normalized_intent,
                append_trustlog=append_trustlog,
                receipt=_rollback_after_apply_failure(
                    base_receipt=base_receipt,
                    adapter=adapter,
                    execution_intent=normalized_intent,
                    pre_snapshot=pre_snapshot,
                    pre_fingerprint=pre_fingerprint,
                    authority_result=authority_result,
                    constraint_result=constraint_result,
                    drift_result=drift_result,
                    risk_result=risk_result,
                    recommended_outcome=admissibility.recommended_outcome.value,
                    apply_error=exc,
                ),
            )
        return _finalize_receipt(
            execution_intent=normalized_intent,
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
                rollback_reason=f"{BindReasonCode.APPLY_FAILED.value}:{exc}",
            ),
        )

    if not adapter.verify_postconditions(normalized_intent, pre_snapshot):
        return _finalize_receipt(
            execution_intent=normalized_intent,
            append_trustlog=append_trustlog,
            receipt=_rollback_after_verification_failure(
                base_receipt=base_receipt,
                adapter=adapter,
                execution_intent=normalized_intent,
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
    except (OSError, TypeError, ValueError, RuntimeError) as exc:
        return _finalize_receipt(
            execution_intent=normalized_intent,
            append_trustlog=append_trustlog,
            receipt=_rollback_after_runtime_signal_failure(
                base_receipt=base_receipt,
                adapter=adapter,
                execution_intent=normalized_intent,
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
        execution_intent=normalized_intent,
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


def _validate_intent_preconditions(execution_intent: ExecutionIntent) -> str | None:
    if not execution_intent.execution_intent_id:
        return "execution_intent_id is required"
    if not execution_intent.decision_id:
        return "decision_id is required"
    if not execution_intent.target_resource:
        return "target_resource is required"
    if not execution_intent.intended_action:
        return "intended_action is required"
    return None


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
    try:
        reverted = adapter.revert(execution_intent, pre_snapshot)
    except (OSError, TypeError, ValueError, RuntimeError) as exc:
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
                "reason_codes": [BindReasonCode.POSTCONDITION_FAILED.value],
                "target": adapter.describe_target(),
            },
            final_outcome=FinalOutcome.ESCALATED,
            rollback_reason=BindReasonCode.POSTCONDITION_FAILED.value,
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
                "reason_codes": [BindReasonCode.POSTCONDITION_FAILED.value],
                "target": adapter.describe_target(),
            },
            final_outcome=FinalOutcome.ESCALATED,
            rollback_reason=BindReasonCode.POSTCONDITION_FAILED.value,
            escalation_reason="BIND_REVERT_REPORTED_FALSE",
        )

    try:
        post_snapshot = adapter.snapshot()
        post_fingerprint = adapter.fingerprint_state(post_snapshot)
    except (OSError, TypeError, ValueError, RuntimeError) as exc:
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
                "reason_codes": [BindReasonCode.POSTCONDITION_FAILED.value],
                "target": adapter.describe_target(),
            },
            final_outcome=FinalOutcome.ESCALATED,
            rollback_reason=BindReasonCode.POSTCONDITION_FAILED.value,
            escalation_reason=f"BIND_POST_ROLLBACK_SNAPSHOT_FAILED:{exc}",
        )

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
            "reason_codes": [BindReasonCode.POSTCONDITION_FAILED.value],
            "target": adapter.describe_target(),
        },
        final_outcome=FinalOutcome.ROLLED_BACK,
        rollback_reason=BindReasonCode.POSTCONDITION_FAILED.value,
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
    try:
        reverted = adapter.revert(execution_intent, pre_snapshot)
    except (OSError, TypeError, ValueError, RuntimeError) as exc:
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
                "reason_codes": [BindReasonCode.POST_SIGNAL_MISSING.value],
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
                "reason_codes": [BindReasonCode.POST_SIGNAL_MISSING.value],
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
            "reason_codes": [BindReasonCode.POST_SIGNAL_MISSING.value],
            "target": adapter.describe_target(),
        },
        final_outcome=FinalOutcome.ESCALATED,
        rollback_reason=reason,
        escalation_reason="BIND_REVERT_REPORTED_FALSE",
    )


def _rollback_after_apply_failure(
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
    apply_error: Exception,
) -> BindReceipt:
    apply_reason = f"{BindReasonCode.APPLY_FAILED.value}:{apply_error}"
    try:
        reverted = adapter.revert(execution_intent, pre_snapshot)
    except (OSError, TypeError, ValueError, RuntimeError) as exc:
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
                "reason_codes": [BindReasonCode.APPLY_FAILED.value],
                "target": adapter.describe_target(),
            },
            final_outcome=FinalOutcome.ESCALATED,
            rollback_reason=apply_reason,
            escalation_reason=f"BIND_REVERT_FAILED_AFTER_APPLY_ERROR:{exc}",
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
                "reason_codes": [BindReasonCode.APPLY_FAILED.value],
                "target": adapter.describe_target(),
            },
            final_outcome=FinalOutcome.ROLLED_BACK,
            rollback_reason=apply_reason,
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
            "reason_codes": [BindReasonCode.APPLY_FAILED.value],
            "target": adapter.describe_target(),
        },
        final_outcome=FinalOutcome.ESCALATED,
        rollback_reason=apply_reason,
        escalation_reason="BIND_REVERT_REPORTED_FALSE",
    )


def _check_from_runtime(check_result: Any) -> dict[str, str]:
    return BindExecutionCheckResult(
        status=check_result.status.value,
        reason_code=check_result.reason_code,
        message=check_result.message,
    ).to_dict()


def _check_unknown(reason_code: str, message: str) -> dict[str, str]:
    return BindExecutionCheckResult(
        status=CheckStatus.FAIL.value,
        reason_code=reason_code,
        message=message,
    ).to_dict()


def _build_ttl_expiry(execution_intent: ExecutionIntent) -> str | None:
    if execution_intent.ttl_seconds is None or not execution_intent.decision_ts:
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
    if not isinstance(execution_intent.approval_context, dict):
        return None
    approval_expires_at = execution_intent.approval_context.get("approval_expires_at")
    if not isinstance(approval_expires_at, str) or not approval_expires_at.strip():
        return None
    return approval_expires_at.strip()


def _resolve_bind_policy_config(execution_intent: ExecutionIntent) -> BindPolicyConfig:
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
        rollback_on_apply_failure=bool(merged.get("rollback_on_apply_failure", False)),
        missing_signal_outcome=_parse_missing_signal_outcome(
            merged.get("missing_signal_default", AdmissibilityOutcome.BLOCK.value)
        ),
    )


def _parse_missing_signal_outcome(raw_value: Any) -> AdmissibilityOutcome:
    if isinstance(raw_value, AdmissibilityOutcome):
        return raw_value
    if isinstance(raw_value, str) and raw_value.strip().lower() == AdmissibilityOutcome.ESCALATE.value:
        return AdmissibilityOutcome.ESCALATE
    return AdmissibilityOutcome.BLOCK


def _with_receipt(base_receipt: BindReceipt, **updates: Any) -> BindReceipt:
    payload = base_receipt.to_dict()
    payload.update(updates)
    return BindReceipt(**payload)


def _finalize_receipt(
    *,
    execution_intent: ExecutionIntent,
    append_trustlog: bool,
    receipt: BindReceipt,
) -> BindReceipt:
    if not append_trustlog:
        return receipt
    append_execution_intent_trustlog(execution_intent)
    return append_bind_receipt_trustlog(receipt)


def _deep_copy_mapping(value: dict[str, Any]) -> dict[str, Any]:
    return _from_json(canonical_json_dumps(value))


def _from_json(payload: str) -> dict[str, Any]:
    import json

    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("BIND_JSON_MAPPING_REQUIRED")
    return data


def _parse_timestamp(raw_timestamp: str) -> datetime:
    normalized = raw_timestamp.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _utc_now_iso8601() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
