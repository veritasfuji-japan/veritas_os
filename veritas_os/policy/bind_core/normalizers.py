"""Normalization helpers for bind core artifacts."""

from __future__ import annotations

from typing import Any

from veritas_os.policy.bind_artifacts import BindReceipt, ExecutionIntent, FinalOutcome


def normalize_execution_intent(
    payload: ExecutionIntent | dict[str, Any],
) -> ExecutionIntent:
    """Return normalized ``ExecutionIntent`` with compatible defaults."""
    if isinstance(payload, ExecutionIntent):
        return payload
    data = dict(payload)
    evidence_refs = data.get("evidence_refs")
    if not isinstance(evidence_refs, list):
        evidence_refs = []

    return ExecutionIntent(
        execution_intent_id=str(data.get("execution_intent_id") or ""),
        decision_id=str(data.get("decision_id") or ""),
        request_id=str(data.get("request_id") or ""),
        policy_snapshot_id=str(data.get("policy_snapshot_id") or ""),
        actor_identity=str(data.get("actor_identity") or ""),
        target_system=str(data.get("target_system") or ""),
        target_resource=str(data.get("target_resource") or ""),
        intended_action=str(data.get("intended_action") or ""),
        evidence_refs=[str(item) for item in evidence_refs],
        decision_hash=str(data.get("decision_hash") or ""),
        decision_ts=str(data.get("decision_ts") or ""),
        ttl_seconds=data.get("ttl_seconds"),
        expected_state_fingerprint=data.get("expected_state_fingerprint"),
        approval_context=(
            dict(data.get("approval_context"))
            if isinstance(data.get("approval_context"), dict)
            else None
        ),
        policy_lineage=(
            dict(data.get("policy_lineage"))
            if isinstance(data.get("policy_lineage"), dict)
            else None
        ),
    )


def normalize_bind_receipt(payload: BindReceipt | dict[str, Any]) -> BindReceipt:
    """Return normalized ``BindReceipt`` with canonical enum mapping."""
    if isinstance(payload, BindReceipt):
        data = payload.to_dict()
    else:
        data = dict(payload)
    final_outcome = data.get("final_outcome") or FinalOutcome.BLOCKED.value
    return BindReceipt(
        bind_receipt_id=str(data.get("bind_receipt_id") or ""),
        execution_intent_id=str(data.get("execution_intent_id") or ""),
        decision_id=str(data.get("decision_id") or ""),
        bind_ts=str(data.get("bind_ts") or ""),
        live_state_fingerprint_before=str(data.get("live_state_fingerprint_before") or ""),
        live_state_fingerprint_after=str(data.get("live_state_fingerprint_after") or ""),
        authority_check_result=dict(data.get("authority_check_result") or {}),
        constraint_check_result=dict(data.get("constraint_check_result") or {}),
        drift_check_result=dict(data.get("drift_check_result") or {}),
        risk_check_result=dict(data.get("risk_check_result") or {}),
        admissibility_result=dict(data.get("admissibility_result") or {}),
        final_outcome=FinalOutcome(str(final_outcome)),
        rollback_reason=(str(data.get("rollback_reason")) if data.get("rollback_reason") else None),
        escalation_reason=(
            str(data.get("escalation_reason")) if data.get("escalation_reason") else None
        ),
        trustlog_hash=str(data.get("trustlog_hash") or ""),
        prev_bind_hash=(str(data.get("prev_bind_hash")) if data.get("prev_bind_hash") else None),
        bind_receipt_hash=str(data.get("bind_receipt_hash") or ""),
        execution_intent_hash=str(data.get("execution_intent_hash") or ""),
        policy_snapshot_id=str(data.get("policy_snapshot_id") or ""),
        actor_identity=str(data.get("actor_identity") or ""),
        decision_hash=str(data.get("decision_hash") or ""),
        governance_identity=(
            dict(data.get("governance_identity"))
            if isinstance(data.get("governance_identity"), dict)
            else None
        ),
        revalidation_context=dict(data.get("revalidation_context") or {}),
        bind_reason_code=(str(data.get("bind_reason_code")) if data.get("bind_reason_code") else None),
        bind_failure_reason=(
            str(data.get("bind_failure_reason")) if data.get("bind_failure_reason") else None
        ),
        idempotency_key=(str(data.get("idempotency_key")) if data.get("idempotency_key") else None),
        idempotency_status=(
            str(data.get("idempotency_status")) if data.get("idempotency_status") else None
        ),
        retry_safety=(str(data.get("retry_safety")) if data.get("retry_safety") else None),
        rollback_status=(str(data.get("rollback_status")) if data.get("rollback_status") else None),
        failure_category=(str(data.get("failure_category")) if data.get("failure_category") else None),
        target_path=str(data.get("target_path") or ""),
        target_type=str(data.get("target_type") or ""),
        target_path_type=str(data.get("target_path_type") or "other"),
        target_label=str(data.get("target_label") or "other"),
        operator_surface=str(data.get("operator_surface") or "audit"),
        relevant_ui_href=str(data.get("relevant_ui_href") or "/audit"),
        regulated_action_path_id=(
            str(data.get("regulated_action_path_id"))
            if data.get("regulated_action_path_id")
            else None
        ),
        action_contract_id=(
            str(data.get("action_contract_id")) if data.get("action_contract_id") else None
        ),
        action_contract_version=(
            str(data.get("action_contract_version"))
            if data.get("action_contract_version")
            else None
        ),
        authority_evidence_id=(
            str(data.get("authority_evidence_id"))
            if data.get("authority_evidence_id")
            else None
        ),
        authority_evidence_hash=(
            str(data.get("authority_evidence_hash"))
            if data.get("authority_evidence_hash")
            else None
        ),
        authority_validation_status=(
            str(data.get("authority_validation_status"))
            if data.get("authority_validation_status")
            else None
        ),
        admissibility_predicates=_normalize_dict_list(data.get("admissibility_predicates")),
        failed_predicates=_normalize_dict_list(data.get("failed_predicates")),
        stale_predicates=_normalize_dict_list(data.get("stale_predicates")),
        missing_predicates=_normalize_dict_list(data.get("missing_predicates")),
        irreversibility_boundary_id=(
            str(data.get("irreversibility_boundary_id"))
            if data.get("irreversibility_boundary_id")
            else None
        ),
        commit_boundary_result=(
            str(data.get("commit_boundary_result"))
            if data.get("commit_boundary_result")
            else None
        ),
        refusal_basis=_normalize_string_list(data.get("refusal_basis")),
        escalation_basis=_normalize_string_list(data.get("escalation_basis")),
        authority_evidence_summary=(
            dict(data.get("authority_evidence_summary"))
            if isinstance(data.get("authority_evidence_summary"), dict)
            else None
        ),
    )


def _normalize_string_list(raw_value: Any) -> list[str] | None:
    if raw_value is None:
        return None
    if not isinstance(raw_value, list):
        return None
    return [str(item) for item in raw_value]


def _normalize_dict_list(raw_value: Any) -> list[dict[str, Any]] | None:
    if raw_value is None:
        return None
    if not isinstance(raw_value, list):
        return None
    return [dict(item) for item in raw_value if isinstance(item, dict)]
