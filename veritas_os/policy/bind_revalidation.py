"""Bind receipt replay/revalidation helpers.

This module provides internal, side-effect free helpers that move bind receipts
from simple logs toward replayable governance artifacts.
"""

from __future__ import annotations

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
    hash_bind_receipt,
    hash_execution_intent,
)
from veritas_os.policy.bind_core.normalizers import (
    normalize_bind_receipt,
    normalize_execution_intent,
)


def replay_bind_receipt_admissibility(
    receipt: BindReceipt | dict[str, Any],
) -> dict[str, Any]:
    """Replay bind admissibility checks from receipt-contained metadata."""
    normalized = normalize_bind_receipt(receipt)
    context = dict(normalized.revalidation_context or {})

    authority_signal = _status_to_signal(normalized.authority_check_result)
    runtime_risk_signal = _status_to_signal(normalized.risk_check_result)
    constraint_signals = _constraint_signals_from_receipt(normalized.constraint_check_result)
    expected_state_fingerprint = context.get("expected_state_fingerprint")
    if not isinstance(expected_state_fingerprint, str):
        expected_state_fingerprint = None

    replay_result = evaluate_bind_admissibility(
        BindAdmissibilityInput(
            execution_intent=normalized.execution_intent_id,
            current_timestamp=normalized.bind_ts,
            authority_signal=authority_signal,
            constraint_signals=constraint_signals,
            live_state_fingerprint=normalized.live_state_fingerprint_before,
            expected_state_fingerprint=expected_state_fingerprint,
            runtime_risk_signal=runtime_risk_signal,
            drift_sensitive=bool(context.get("drift_required", True)),
            ttl_required=bool(context.get("ttl_required", False)),
            approval_freshness_required=bool(
                context.get("approval_freshness_required", False)
            ),
            missing_signal_outcome=_parse_missing_signal_outcome(
                context.get("missing_signal_outcome")
            ),
            ttl_expires_at=_to_optional_str(context.get("ttl_expires_at")),
            approval_expires_at=_to_optional_str(context.get("approval_expires_at")),
        )
    )

    stored_reason_codes = normalized.admissibility_result.get("reason_codes")
    if not isinstance(stored_reason_codes, list):
        stored_reason_codes = []
    replay_reason_codes = list(replay_result.reason_codes)

    return {
        "replayable": bool(normalized.bind_ts and normalized.live_state_fingerprint_before),
        "replayed_admissible": replay_result.admissibility_result,
        "stored_admissible": bool(normalized.admissibility_result.get("admissible", False)),
        "replayed_recommended_outcome": replay_result.recommended_outcome.value,
        "stored_recommended_outcome": normalized.admissibility_result.get(
            "recommended_outcome"
        ),
        "replayed_reason_codes": replay_reason_codes,
        "stored_reason_codes": [str(code) for code in stored_reason_codes],
        "admissibility_matches": (
            replay_result.admissibility_result
            == bool(normalized.admissibility_result.get("admissible", False))
            and replay_reason_codes == [str(code) for code in stored_reason_codes]
        ),
    }


def revalidate_bind_receipt(
    *,
    receipt: BindReceipt | dict[str, Any],
    execution_intent: ExecutionIntent | dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Revalidate bind receipt integrity and replay prerequisites."""
    normalized_receipt = normalize_bind_receipt(receipt)
    replay = replay_bind_receipt_admissibility(normalized_receipt)

    recomputed_bind_hash = hash_bind_receipt(normalized_receipt)
    bind_hash_matches = (
        not normalized_receipt.bind_receipt_hash
        or normalized_receipt.bind_receipt_hash == recomputed_bind_hash
    )

    execution_intent_hash_matches = True
    execution_intent_id_matches = execution_intent is None
    if execution_intent is not None:
        normalized_intent = normalize_execution_intent(execution_intent)
        execution_intent_id_matches = (
            normalized_intent.execution_intent_id == normalized_receipt.execution_intent_id
        )
        recomputed_intent_hash = hash_execution_intent(normalized_intent)
        execution_intent_hash_matches = (
            not normalized_receipt.execution_intent_hash
            or normalized_receipt.execution_intent_hash == recomputed_intent_hash
        )

    lineage = {
        "decision_id": normalized_receipt.decision_id,
        "execution_intent_id": normalized_receipt.execution_intent_id,
        "policy_snapshot_id": normalized_receipt.policy_snapshot_id,
        "governance_identity_present": isinstance(
            normalized_receipt.governance_identity, dict
        ),
    }
    final_outcome = (
        normalized_receipt.final_outcome.value
        if isinstance(normalized_receipt.final_outcome, FinalOutcome)
        else str(normalized_receipt.final_outcome)
    )

    return {
        "ok": (
            bind_hash_matches
            and execution_intent_hash_matches
            and execution_intent_id_matches
            and replay["admissibility_matches"]
        ),
        "lineage": lineage,
        "bind_hash_matches": bind_hash_matches,
        "execution_intent_hash_matches": execution_intent_hash_matches,
        "execution_intent_id_matches": execution_intent_id_matches,
        "recorded_bind_reason_code": normalized_receipt.bind_reason_code,
        "recorded_bind_failure_reason": normalized_receipt.bind_failure_reason,
        "replay": replay,
        "final_outcome": final_outcome,
        "terminal_failure": final_outcome
        in {
            FinalOutcome.BLOCKED.value,
            FinalOutcome.ESCALATED.value,
            FinalOutcome.ROLLED_BACK.value,
            FinalOutcome.APPLY_FAILED.value,
            FinalOutcome.SNAPSHOT_FAILED.value,
            FinalOutcome.PRECONDITION_FAILED.value,
        },
    }


def _status_to_signal(check_result: dict[str, Any]) -> bool | None:
    status = str(check_result.get("status") or "").strip().lower()
    if status == CheckStatus.PASS.value:
        return True
    if status == CheckStatus.FAIL.value:
        return False
    return None


def _constraint_signals_from_receipt(
    check_result: dict[str, Any],
) -> dict[str, bool] | None:
    signal = _status_to_signal(check_result)
    if signal is None:
        return None
    return {"receipt_constraint": signal}


def _parse_missing_signal_outcome(raw_value: Any) -> AdmissibilityOutcome:
    if isinstance(raw_value, str) and raw_value.strip().lower() == "escalate":
        return AdmissibilityOutcome.ESCALATE
    return AdmissibilityOutcome.BLOCK


def _to_optional_str(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
