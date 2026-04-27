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
from veritas_os.governance.action_contracts import (
    ActionClassContract,
    validate_action_class_contract,
)
from veritas_os.governance.authority_evidence import AuthorityEvidence, VerificationResult
from veritas_os.governance.commit_boundary import CommitBoundaryResult, evaluate_commit_boundary
from veritas_os.policy.bind_artifacts import (
    BindReceipt,
    ExecutionIntent,
    FinalOutcome,
    append_bind_receipt_trustlog,
    append_execution_intent_trustlog,
    hash_execution_intent,
)
from veritas_os.policy.bind_core.constants import BindReasonCode
from veritas_os.policy.bind_core.constants import BindFailureCategory, BindRetrySafety
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
    adapter_idempotency_key = str(adapter.build_idempotency_key(normalized_intent) or "").strip()
    idempotency_key = _resolve_idempotency_key(
        adapter_key=adapter_idempotency_key,
        execution_intent=normalized_intent,
    )

    if append_trustlog and _idempotency_replay_enabled(
        adapter_key=adapter_idempotency_key,
        execution_intent=normalized_intent,
    ):
        duplicate_receipt = _find_duplicate_bind_receipt(
            execution_intent=normalized_intent,
            idempotency_key=idempotency_key,
        )
        if duplicate_receipt is not None:
            return _with_receipt(
                duplicate_receipt,
                idempotency_key=idempotency_key,
                idempotency_status="replayed",
                bind_reason_code=BindReasonCode.IDEMPOTENT_REPLAY.value,
                bind_failure_reason=(
                    f"{BindReasonCode.IDEMPOTENT_REPLAY.value}:"
                    f"{duplicate_receipt.bind_receipt_id}"
                ),
                retry_safety=BindRetrySafety.SAFE.value,
                rollback_status=duplicate_receipt.rollback_status or "not_required",
                failure_category=duplicate_receipt.failure_category or BindFailureCategory.NONE.value,
            )

    base_receipt = BindReceipt(
        bind_receipt_id=bind_receipt_id or "",
        execution_intent_id=normalized_intent.execution_intent_id,
        decision_id=normalized_intent.decision_id,
        bind_ts=ts,
        execution_intent_hash=hash_execution_intent(normalized_intent),
        policy_snapshot_id=normalized_intent.policy_snapshot_id,
        actor_identity=normalized_intent.actor_identity,
        decision_hash=normalized_intent.decision_hash,
        idempotency_key=idempotency_key,
        governance_identity=_extract_governance_identity(normalized_intent),
        revalidation_context=_build_revalidation_context(
            execution_intent=normalized_intent,
            bind_policy=BindPolicyConfig(),
            ttl_expires_at=_build_ttl_expiry(normalized_intent),
            approval_expires_at=_build_approval_expiry(normalized_intent),
            idempotency_key=idempotency_key,
        ),
    ) if bind_receipt_id else BindReceipt(
        execution_intent_id=normalized_intent.execution_intent_id,
        decision_id=normalized_intent.decision_id,
        bind_ts=ts,
        execution_intent_hash=hash_execution_intent(normalized_intent),
        policy_snapshot_id=normalized_intent.policy_snapshot_id,
        actor_identity=normalized_intent.actor_identity,
        decision_hash=normalized_intent.decision_hash,
        idempotency_key=idempotency_key,
        governance_identity=_extract_governance_identity(normalized_intent),
        revalidation_context=_build_revalidation_context(
            execution_intent=normalized_intent,
            bind_policy=BindPolicyConfig(),
            ttl_expires_at=_build_ttl_expiry(normalized_intent),
            approval_expires_at=_build_approval_expiry(normalized_intent),
            idempotency_key=idempotency_key,
        ),
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
    base_receipt = _with_receipt(
        base_receipt,
        revalidation_context=_build_revalidation_context(
            execution_intent=normalized_intent,
            bind_policy=bind_policy,
            ttl_expires_at=ttl_expires_at,
            approval_expires_at=approval_expires_at,
            idempotency_key=idempotency_key,
        ),
    )

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
    regulated_context = _resolve_regulated_action_context(normalized_intent)

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
                **_regulated_receipt_updates(regulated_context, None),
            ),
        )

    regulated_boundary_result = _evaluate_regulated_commit_boundary(
        execution_intent=normalized_intent,
        regulated_context=regulated_context,
    )
    try:
        regulated_receipt_updates = _regulated_receipt_updates(
            regulated_context,
            regulated_boundary_result,
        )
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"BIND_COMMIT_BOUNDARY_SERIALIZATION_FAILED:{exc}") from exc

    if regulated_boundary_result is not None:
        if regulated_boundary_result.commit_boundary_result == "block":
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
                        "recommended_outcome": "block",
                        "reason_codes": ["BIND_COMMIT_BOUNDARY_BLOCKED"],
                        "target": adapter.describe_target(),
                    },
                    final_outcome=FinalOutcome.BLOCKED,
                    **regulated_receipt_updates,
                ),
            )
        if regulated_boundary_result.commit_boundary_result == "escalate":
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
                        "recommended_outcome": "escalate",
                        "reason_codes": ["BIND_COMMIT_BOUNDARY_ESCALATED"],
                        "target": adapter.describe_target(),
                    },
                    final_outcome=FinalOutcome.ESCALATED,
                    escalation_reason="BIND_COMMIT_BOUNDARY_ESCALATED",
                    **regulated_receipt_updates,
                ),
            )
        if regulated_boundary_result.commit_boundary_result == "refuse":
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
                        "recommended_outcome": "block",
                        "reason_codes": ["BIND_COMMIT_BOUNDARY_REFUSED"],
                        "target": adapter.describe_target(),
                    },
                    final_outcome=FinalOutcome.BLOCKED,
                    **regulated_receipt_updates,
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
            **regulated_receipt_updates,
        ),
    )


def _resolve_regulated_action_context(execution_intent: ExecutionIntent) -> dict[str, Any]:
    """Resolve regulated action governance context from intent lineage."""
    for container in (execution_intent.approval_context, execution_intent.policy_lineage):
        if not isinstance(container, dict):
            continue
        candidate = container.get("regulated_action_governance")
        if isinstance(candidate, dict):
            return dict(candidate)
    return {}


def _evaluate_regulated_commit_boundary(
    *,
    execution_intent: ExecutionIntent,
    regulated_context: dict[str, Any],
) -> CommitBoundaryResult | None:
    """Evaluate commit boundary only when action-contract context is declared."""
    action_contract_payload = regulated_context.get("action_contract")
    action_contract_id = str(
        regulated_context.get("action_contract_id")
        or (action_contract_payload or {}).get("id")
        or ""
    ).strip()
    if not action_contract_id:
        return None

    authority_evidence_payload = regulated_context.get("authority_evidence")
    requested_scope = regulated_context.get("requested_scope")
    if not isinstance(requested_scope, list):
        requested_scope = []

    try:
        action_contract = (
            validate_action_class_contract(action_contract_payload)
            if isinstance(action_contract_payload, dict)
            else None
        )
        authority_evidence = (
            _build_authority_evidence(authority_evidence_payload)
            if isinstance(authority_evidence_payload, dict)
            else None
        )
        return evaluate_commit_boundary(
            execution_intent={
                "execution_intent_id": execution_intent.execution_intent_id,
                "action_class": str(regulated_context.get("action_class") or "").strip(),
                "admissible": True,
            },
            action_contract=action_contract,
            authority_evidence=authority_evidence,
            requested_scope=[str(item) for item in requested_scope],
            required_evidence_metadata=dict(regulated_context.get("required_evidence_metadata") or {}),
            evidence_freshness_metadata=dict(
                regulated_context.get("evidence_freshness_metadata") or {}
            ),
            policy_snapshot_id=execution_intent.policy_snapshot_id,
            actor_identity=execution_intent.actor_identity,
            human_approval_state=dict(regulated_context.get("human_approval_state") or {}),
            bind_context_metadata=dict(regulated_context.get("bind_context_metadata") or {}),
        )
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"BIND_COMMIT_BOUNDARY_EVALUATION_FAILED:{exc}") from exc


def _regulated_receipt_updates(
    regulated_context: dict[str, Any],
    result: CommitBoundaryResult | None,
) -> dict[str, Any]:
    """Build additive regulated-governance bind receipt fields."""
    if not regulated_context:
        return {}
    updates: dict[str, Any] = {
        "regulated_action_path_id": str(regulated_context.get("regulated_action_path_id") or "")
        or None,
    }
    if result is None:
        return {key: value for key, value in updates.items() if value is not None}

    updates.update(
        {
            "action_contract_id": result.action_contract_id or None,
            "action_contract_version": result.action_contract_version or None,
            "authority_evidence_id": result.authority_evidence_id or None,
            "authority_evidence_hash": result.authority_evidence_hash or None,
            "authority_validation_status": result.authority_validation_status or None,
            "admissibility_predicates": [_predicate_to_dict(item) for item in result.admissibility_predicates],
            "failed_predicates": [_predicate_to_dict(item) for item in result.failed_predicates],
            "stale_predicates": [_predicate_to_dict(item) for item in result.stale_predicates],
            "missing_predicates": [_predicate_to_dict(item) for item in result.missing_predicates],
            "irreversibility_boundary_id": result.irreversibility_boundary_id or None,
            "commit_boundary_result": result.commit_boundary_result,
            "refusal_basis": list(result.refusal_basis),
            "escalation_basis": list(result.escalation_basis),
            "authority_evidence_summary": {
                "reason_summary": result.reason_summary,
                "evaluated_at": result.evaluated_at,
            },
        }
    )
    return {key: value for key, value in updates.items() if value is not None}


def _predicate_to_dict(predicate: Any) -> dict[str, Any]:
    return {
        "predicate_id": str(getattr(predicate, "predicate_id", "")),
        "predicate_type": str(getattr(predicate, "predicate_type", "")),
        "status": str(getattr(predicate, "status", "")),
        "reason": str(getattr(predicate, "reason", "")),
        "evidence_ref": getattr(predicate, "evidence_ref", None),
        "severity": str(getattr(predicate, "severity", "")),
        "evaluated_at": str(getattr(predicate, "evaluated_at", "")),
        "metadata": dict(getattr(predicate, "metadata", {}) or {}),
    }


def _build_authority_evidence(payload: dict[str, Any]) -> AuthorityEvidence:
    """Build AuthorityEvidence from mapping with enum normalization."""
    normalized = dict(payload)
    verification_result = normalized.get("verification_result")
    if isinstance(verification_result, str):
        normalized["verification_result"] = VerificationResult(verification_result)
    return AuthorityEvidence(**normalized)


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
    final_outcome = payload.get("final_outcome")
    if isinstance(final_outcome, str):
        payload["final_outcome"] = FinalOutcome(final_outcome)
    return BindReceipt(**payload)


def _finalize_receipt(
    *,
    execution_intent: ExecutionIntent,
    append_trustlog: bool,
    receipt: BindReceipt,
) -> BindReceipt:
    if not receipt.bind_reason_code or not receipt.bind_failure_reason:
        reason_code, failure_reason = _resolve_receipt_failure_fields(receipt)
        receipt = _with_receipt(
            receipt,
            bind_reason_code=receipt.bind_reason_code or reason_code,
            bind_failure_reason=receipt.bind_failure_reason or failure_reason,
        )
    receipt = _with_receipt(
        receipt,
        idempotency_status=receipt.idempotency_status or "fresh",
        retry_safety=receipt.retry_safety or _resolve_retry_safety(receipt).value,
        rollback_status=receipt.rollback_status or _resolve_rollback_status(receipt),
        failure_category=receipt.failure_category or _resolve_failure_category(receipt).value,
    )
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


def _extract_governance_identity(execution_intent: ExecutionIntent) -> dict[str, Any] | None:
    """Extract governance identity lineage from execution intent payloads."""
    policy_lineage = execution_intent.policy_lineage
    if not isinstance(policy_lineage, dict):
        return None
    governance_identity = policy_lineage.get("governance_identity")
    if not isinstance(governance_identity, dict):
        return None
    return dict(governance_identity)


def _build_revalidation_context(
    *,
    execution_intent: ExecutionIntent,
    bind_policy: BindPolicyConfig,
    ttl_expires_at: str | None,
    approval_expires_at: str | None,
    idempotency_key: str,
) -> dict[str, Any]:
    """Build a minimal replay context required for bind admissibility re-checks."""
    return {
        "expected_state_fingerprint": execution_intent.expected_state_fingerprint,
        "ttl_expires_at": ttl_expires_at,
        "approval_expires_at": approval_expires_at,
        "drift_required": bind_policy.drift_required,
        "ttl_required": bind_policy.ttl_required,
        "approval_freshness_required": bind_policy.approval_freshness_required,
        "missing_signal_outcome": bind_policy.missing_signal_outcome.value,
        "idempotency_key": idempotency_key,
    }


def _resolve_idempotency_key(
    *,
    adapter_key: str,
    execution_intent: ExecutionIntent,
) -> str:
    """Resolve deterministic idempotency key from adapter and intent context."""
    if adapter_key:
        return adapter_key
    if isinstance(execution_intent.approval_context, dict):
        approval_key = execution_intent.approval_context.get("idempotency_key")
        if isinstance(approval_key, str) and approval_key.strip():
            return approval_key.strip()
    return execution_intent.execution_intent_id


def _idempotency_replay_enabled(
    *,
    adapter_key: str,
    execution_intent: ExecutionIntent,
) -> bool:
    """Return True when replay detection should dedupe repeated submissions."""
    if adapter_key:
        return True
    if not isinstance(execution_intent.approval_context, dict):
        return False
    raw_key = execution_intent.approval_context.get("idempotency_key")
    return isinstance(raw_key, str) and bool(raw_key.strip())


def _find_duplicate_bind_receipt(
    *,
    execution_intent: ExecutionIntent,
    idempotency_key: str,
) -> BindReceipt | None:
    """Return the latest receipt for the same intent/idempotency key."""
    from veritas_os.policy.bind_artifacts import find_bind_receipts

    receipts = find_bind_receipts(
        execution_intent_id=execution_intent.execution_intent_id,
        decision_id=execution_intent.decision_id,
    )
    for receipt in reversed(receipts):
        receipt_key = ""
        if isinstance(receipt.revalidation_context, dict):
            receipt_key = str(receipt.revalidation_context.get("idempotency_key") or "").strip()
        if receipt_key and receipt_key == idempotency_key:
            return receipt
    return None


def _resolve_retry_safety(receipt: BindReceipt) -> BindRetrySafety:
    """Classify retry safety for operator-visible bind semantics."""
    if receipt.final_outcome in {FinalOutcome.COMMITTED, FinalOutcome.ROLLED_BACK}:
        return BindRetrySafety.SAFE
    if receipt.final_outcome is FinalOutcome.BLOCKED:
        return BindRetrySafety.SAFE
    if receipt.final_outcome in {FinalOutcome.ESCALATED, FinalOutcome.APPLY_FAILED}:
        return BindRetrySafety.REQUIRES_ESCALATION
    if receipt.final_outcome in {FinalOutcome.SNAPSHOT_FAILED, FinalOutcome.PRECONDITION_FAILED}:
        return BindRetrySafety.UNSAFE
    return BindRetrySafety.REQUIRES_ESCALATION


def _resolve_rollback_status(receipt: BindReceipt) -> str:
    """Resolve rollback status label from final outcome and reason context."""
    if receipt.final_outcome is FinalOutcome.ROLLED_BACK:
        return "rolled_back"
    if receipt.final_outcome is FinalOutcome.COMMITTED:
        return "not_required"
    if receipt.final_outcome is FinalOutcome.ESCALATED:
        if isinstance(receipt.escalation_reason, str) and "BIND_REVERT" in receipt.escalation_reason:
            return "rollback_failed"
        return "manual_intervention_required"
    if receipt.final_outcome is FinalOutcome.APPLY_FAILED:
        return "rollback_not_attempted"
    return "not_required"


def _resolve_failure_category(receipt: BindReceipt) -> BindFailureCategory:
    """Map receipt outcomes/reasons into a minimal failure taxonomy."""
    if receipt.final_outcome is FinalOutcome.COMMITTED:
        return BindFailureCategory.NONE
    if receipt.final_outcome is FinalOutcome.PRECONDITION_FAILED:
        return BindFailureCategory.PRECONDITION
    if receipt.final_outcome is FinalOutcome.SNAPSHOT_FAILED:
        return BindFailureCategory.SNAPSHOT
    if receipt.final_outcome is FinalOutcome.APPLY_FAILED:
        return BindFailureCategory.APPLY
    if receipt.final_outcome is FinalOutcome.BLOCKED:
        return BindFailureCategory.ADMISSIBILITY
    if receipt.final_outcome is FinalOutcome.ROLLED_BACK:
        if isinstance(receipt.rollback_reason, str) and receipt.rollback_reason.startswith(
            BindReasonCode.APPLY_FAILED.value
        ):
            return BindFailureCategory.APPLY
        return BindFailureCategory.POSTCONDITION
    if receipt.final_outcome is FinalOutcome.ESCALATED:
        if isinstance(receipt.escalation_reason, str) and "BIND_REVERT" in receipt.escalation_reason:
            return BindFailureCategory.ROLLBACK
        if isinstance(receipt.rollback_reason, str) and receipt.rollback_reason.startswith(
            BindReasonCode.APPLY_FAILED.value
        ):
            return BindFailureCategory.APPLY
        return BindFailureCategory.POSTCONDITION
    return BindFailureCategory.ADMISSIBILITY


def _resolve_receipt_failure_fields(receipt: BindReceipt) -> tuple[str | None, str | None]:
    """Resolve canonical failure reason code and summary from receipt payload."""
    if isinstance(receipt.admissibility_result, dict):
        reason_codes = receipt.admissibility_result.get("reason_codes")
        if isinstance(reason_codes, list) and reason_codes:
            first_code = reason_codes[0]
            if isinstance(first_code, str) and first_code.strip():
                reason = str(receipt.admissibility_result.get("reason") or "").strip() or None
                if reason:
                    return first_code.strip(), reason
    for check_payload in (
        receipt.authority_check_result,
        receipt.constraint_check_result,
        receipt.drift_check_result,
        receipt.risk_check_result,
    ):
        if not isinstance(check_payload, dict):
            continue
        reason_code = str(check_payload.get("reason_code") or "").strip() or None
        message = str(check_payload.get("message") or "").strip() or None
        if reason_code:
            return reason_code, message
    for value in (
        receipt.rollback_reason,
        receipt.escalation_reason,
    ):
        if not isinstance(value, str) or not value.strip():
            continue
        prefix = value.split(":", 1)[0].strip()
        return prefix or None, value.strip()
    return None, None
