"""Bind -> Outcome -> TrustLog lineage closure for one consumed authorization.

This module composes the merged authorization-consumption gate with the
existing BindReceipt and OutcomeReceipt artifacts.  It does not change Bind
admissibility or authorization semantics; it makes the post-bind lineage
explicit and auditable.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any

from veritas_os.governance.outcome_receipt import (
    OutcomeReceipt,
    build_outcome_receipt,
    validate_outcome_receipt,
)
from veritas_os.logging.trust_log import append_trust_log
from veritas_os.policy.bind_artifacts import (
    BindReceipt,
    FinalOutcome,
    append_bind_receipt_trustlog,
    append_execution_intent_trustlog,
)
from veritas_os.policy.bind_core.normalizers import normalize_execution_intent
from veritas_os.policy.live_adapter_bind_authorization import (
    BindAuthorizationTrustInputs,
    RealBindAuthorizationGovernanceInputs,
)
from veritas_os.policy.live_adapter_bind_authorization_consumption import (
    AuthorizationHeaderConstructor,
    AuthorizedBindAdapterFactory,
    BindAuthorizationConsumptionResult,
    CredentialMaterialResolver,
    consume_live_adapter_bind_authorization_and_invoke_bind,
)
from veritas_os.policy.live_adapter_bind_authorization_consumption_store import (
    AtomicAuthorizationConsumptionStore,
)


class BindOutcomeLineageError(RuntimeError):
    """Stable fail-closed error for post-bind lineage construction/persistence."""


@dataclass(frozen=True)
class BindOutcomeLineageResult:
    """Complete non-secret lineage returned after one consumed Bind attempt."""

    consumption_result: BindAuthorizationConsumptionResult
    bind_receipt: BindReceipt
    outcome_receipt: OutcomeReceipt
    outcome_trustlog_hash: str


def _now_iso(value: datetime | str) -> str:
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            raise BindOutcomeLineageError("BOL_TIMESTAMP_INVALID") from None
    if parsed.tzinfo is None:
        raise BindOutcomeLineageError("BOL_TIMESTAMP_NAIVE")
    return parsed.astimezone(timezone.utc).isoformat()


def _requested_scope(authorization: Any) -> list[str]:
    raw = authorization.authority_evidence_reference_bundle.get("bundle_scope")
    if not isinstance(raw, list):
        raise BindOutcomeLineageError("BOL_REQUESTED_SCOPE_MISSING")
    values = [str(item).strip() for item in raw if str(item).strip()]
    if not values or len(set(values)) != len(values):
        raise BindOutcomeLineageError("BOL_REQUESTED_SCOPE_INVALID")
    return values


def _postcondition_status(receipt: BindReceipt) -> str:
    if receipt.final_outcome == FinalOutcome.COMMITTED:
        return "passed"
    if receipt.final_outcome in {
        FinalOutcome.APPLY_FAILED,
        FinalOutcome.ROLLED_BACK,
    }:
        return "failed"
    if receipt.final_outcome == FinalOutcome.ESCALATED:
        return "indeterminate"
    return "skipped"


def _failure_reasons(receipt: BindReceipt) -> list[str]:
    values = [
        receipt.bind_failure_reason,
        receipt.rollback_reason,
        receipt.escalation_reason,
    ]
    return sorted({str(value) for value in values if value})


def _lineage_identity(
    *,
    authorization: Any,
    consumption_result: BindAuthorizationConsumptionResult,
    receipt: BindReceipt,
) -> dict[str, Any]:
    current = dict(receipt.governance_identity or {})
    current["real_bind_authorization"] = {
        "live_adapter_bind_authorization_id": (
            authorization.live_adapter_bind_authorization_id
        ),
        "live_adapter_bind_authorization_hash": (
            authorization.live_adapter_bind_authorization_hash
        ),
        "authorization_decision_digest": authorization.authorization_decision_digest,
        "authorization_issuer_verifier_policy_hash": (
            authorization.authorization_issuer_verification.verifier_policy_hash
        ),
    }
    current["authorization_consumption"] = {
        "consumption_id": consumption_result.consumption_record.consumption_id,
        "consumption_hash": consumption_result.consumption_record.consumption_hash,
        "consumed_at": consumption_result.consumption_record.consumed_at,
        "idempotency_key": consumption_result.consumption_record.idempotency_key,
        "single_use_enforced": (
            consumption_result.consumption_record.single_use_enforced
        ),
    }
    current["bind_invocation"] = {
        "bind_core_invoked": consumption_result.bind_core_invoked,
        "adapter_apply_attempted": consumption_result.adapter_apply_attempted,
    }
    return current


def _build_outcome(
    *,
    authorization: Any,
    governance_inputs: RealBindAuthorizationGovernanceInputs,
    consumption_result: BindAuthorizationConsumptionResult,
    receipt: BindReceipt,
    evaluated_at: str,
) -> OutcomeReceipt:
    intent = normalize_execution_intent(authorization.execution_intent)
    metadata = {
        "live_adapter_bind_authorization_id": (
            authorization.live_adapter_bind_authorization_id
        ),
        "live_adapter_bind_authorization_hash": (
            authorization.live_adapter_bind_authorization_hash
        ),
        "authorization_consumption_id": (
            consumption_result.consumption_record.consumption_id
        ),
        "authorization_consumption_hash": (
            consumption_result.consumption_record.consumption_hash
        ),
        "bind_receipt_hash": receipt.bind_receipt_hash,
        "bind_trustlog_hash": receipt.trustlog_hash,
        "bind_context_hash": authorization.bind_context_hash,
        "idempotency_key": authorization.idempotency_key,
        "bind_core_invoked": consumption_result.bind_core_invoked,
        "adapter_apply_attempted": consumption_result.adapter_apply_attempted,
        "external_effect_claim": "NOT_INFERRED_FROM_GENERIC_ADAPTER_APPLY",
    }
    outcome = build_outcome_receipt(
        decision_id=intent.decision_id,
        execution_intent_id=intent.execution_intent_id,
        bind_receipt_id=receipt.bind_receipt_id,
        operation_id=consumption_result.consumption_record.consumption_id,
        action_class=governance_inputs.action_contract.action_class,
        target_system=intent.target_system,
        target_resource=intent.target_resource,
        intended_action=intent.intended_action,
        requested_scope=_requested_scope(authorization),
        final_outcome=receipt.final_outcome.value,
        pre_state_fingerprint=receipt.live_state_fingerprint_before or None,
        post_state_fingerprint=receipt.live_state_fingerprint_after or None,
        postcondition_status=_postcondition_status(receipt),
        observed_effects=[
            {
                "kind": "adapter_apply_attempt",
                "attempted": consumption_result.adapter_apply_attempted,
                "external_effect_inferred": False,
            }
        ],
        failure_reasons=_failure_reasons(receipt),
        rollback_status=receipt.rollback_status,
        evaluated_at=evaluated_at,
        metadata=metadata,
    )
    validation = validate_outcome_receipt(outcome)
    if not validation.is_valid or outcome.outcome_hash != outcome.deterministic_digest():
        raise BindOutcomeLineageError("BOL_OUTCOME_RECEIPT_INVALID")
    return outcome


def append_outcome_receipt_trustlog(outcome: OutcomeReceipt) -> str:
    """Append an OutcomeReceipt after its linked BindReceipt and return TrustLog hash."""
    entry = append_trust_log(
        {
            "kind": "governance.outcome_receipt",
            "request_id": outcome.decision_id,
            "decision_id": outcome.decision_id,
            "execution_intent_id": outcome.execution_intent_id,
            "bind_receipt_id": outcome.bind_receipt_id,
            "outcome_receipt_id": outcome.outcome_receipt_id,
            "outcome_hash": outcome.outcome_hash,
            "outcome_receipt": outcome.to_dict(),
        }
    )
    value = str(entry.get("sha256") or "")
    if not value:
        raise BindOutcomeLineageError("BOL_OUTCOME_TRUSTLOG_HASH_MISSING")
    return value


async def consume_bind_and_record_outcome_lineage(
    artifact: Any,
    *,
    governance_inputs: RealBindAuthorizationGovernanceInputs,
    trust_inputs: BindAuthorizationTrustInputs,
    now: datetime | str,
    consumption_store: AtomicAuthorizationConsumptionStore,
    credential_resolver: CredentialMaterialResolver,
    authorization_header_constructor: AuthorizationHeaderConstructor,
    adapter_factory: AuthorizedBindAdapterFactory,
    bind_ts: str | None = None,
) -> BindOutcomeLineageResult:
    """Consume one authorization, invoke Bind, then persist Bind+Outcome lineage.

    The underlying consumption gate is invoked with ``append_trustlog=False`` so
    the BindReceipt is first enriched with authorization/consumption lineage and
    then written exactly once in its final form.  Outcome evidence is appended
    after the linked BindReceipt.

    A TrustLog persistence failure can occur after adapter apply has been
    attempted; this function therefore raises rather than pretending the effect
    did not happen.  Crash/unknown-effect reconciliation is intentionally a
    separate boundary.
    """
    current = _now_iso(now)
    consumption = await consume_live_adapter_bind_authorization_and_invoke_bind(
        artifact,
        governance_inputs=governance_inputs,
        trust_inputs=trust_inputs,
        now=current,
        consumption_store=consumption_store,
        credential_resolver=credential_resolver,
        authorization_header_constructor=authorization_header_constructor,
        adapter_factory=adapter_factory,
        append_trustlog=False,
        bind_ts=bind_ts or current,
    )

    authorization = artifact
    intent = normalize_execution_intent(authorization.execution_intent)
    enriched_receipt = replace(
        consumption.bind_receipt,
        governance_identity=_lineage_identity(
            authorization=authorization,
            consumption_result=consumption,
            receipt=consumption.bind_receipt,
        ),
    )

    try:
        append_execution_intent_trustlog(intent)
        persisted_receipt = append_bind_receipt_trustlog(enriched_receipt)
        outcome = _build_outcome(
            authorization=authorization,
            governance_inputs=governance_inputs,
            consumption_result=consumption,
            receipt=persisted_receipt,
            evaluated_at=current,
        )
        outcome_trustlog_hash = append_outcome_receipt_trustlog(outcome)
    except BindOutcomeLineageError:
        raise
    except Exception:
        raise BindOutcomeLineageError(
            "BOL_TRUSTLOG_PERSISTENCE_FAILED_AFTER_BIND_ATTEMPT"
        ) from None

    return BindOutcomeLineageResult(
        consumption_result=consumption,
        bind_receipt=persisted_receipt,
        outcome_receipt=outcome,
        outcome_trustlog_hash=outcome_trustlog_hash,
    )


__all__ = [
    "BindOutcomeLineageError",
    "BindOutcomeLineageResult",
    "append_outcome_receipt_trustlog",
    "consume_bind_and_record_outcome_lineage",
]
