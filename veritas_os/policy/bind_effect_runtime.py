"""Runtime composition for Bind outcome lineage plus durable effect-state tracking.

This module is the effect-aware orchestration boundary. It composes the merged
Bind -> Outcome -> TrustLog path with the #2137 effect-state machine so that a
real consumed authorization cannot execute without entering durable IN_FLIGHT
tracking first.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from veritas_os.policy.bind_effect_reconciliation import (
    AtomicEffectStateStore,
    BindEffectStateError,
    EffectExecutionState,
    EffectStateRecord,
    EffectStateTrackingConsumptionStore,
    classify_bind_exception,
    classify_completed_bind_attempt,
)
from veritas_os.policy.bind_outcome_lineage import (
    BindOutcomeLineageResult,
    consume_bind_and_record_outcome_lineage,
)
from veritas_os.policy.live_adapter_bind_authorization import (
    BindAuthorizationTrustInputs,
    RealBindAuthorizationGovernanceInputs,
)
from veritas_os.policy.live_adapter_bind_authorization_consumption import (
    AuthorizationHeaderConstructor,
    AuthorizedBindAdapterFactory,
    CredentialMaterialResolver,
)
from veritas_os.policy.live_adapter_bind_authorization_consumption_store import (
    AtomicAuthorizationConsumptionStore,
    AuthorizationConsumptionRecord,
)
from veritas_os.security.hash import sha256_of_canonical_json


class BindEffectRuntimeError(RuntimeError):
    """Fail-closed runtime error after effect-state orchestration has taken over."""


@dataclass(frozen=True)
class BindEffectRuntimeResult:
    lineage: BindOutcomeLineageResult
    effect_state: EffectStateRecord


class _CapturingConsumptionStore:
    """Capture the exact non-secret record presented to the tracking store."""

    def __init__(self, delegate: EffectStateTrackingConsumptionStore) -> None:
        self._delegate = delegate
        self.record: AuthorizationConsumptionRecord | None = None

    async def consume_once(self, record: AuthorizationConsumptionRecord) -> bool:
        self.record = record
        return await self._delegate.consume_once(record)


def _timestamp(value: datetime | str) -> str:
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            raise BindEffectRuntimeError("BER_TIMESTAMP_INVALID") from None
    if parsed.tzinfo is None:
        raise BindEffectRuntimeError("BER_TIMESTAMP_NAIVE")
    return parsed.astimezone(timezone.utc).isoformat()


def _in_flight_record(
    consumption: AuthorizationConsumptionRecord,
    *,
    updated_at: str,
    reason_code: str,
) -> EffectStateRecord:
    values: dict[str, Any] = {
        "format_version": "bind-effect-state/v1",
        "operation_id": consumption.consumption_id,
        "authorization_id": consumption.live_adapter_bind_authorization_id,
        "authorization_hash": consumption.live_adapter_bind_authorization_hash,
        "consumption_id": consumption.consumption_id,
        "consumption_hash": consumption.consumption_hash,
        "execution_intent_id": consumption.execution_intent_id,
        "idempotency_key": consumption.idempotency_key,
        "state": EffectExecutionState.IN_FLIGHT,
        "revision": 1,
        "updated_at": updated_at,
        "reason_code": reason_code,
        "reconciliation_evidence_hash": None,
    }
    values["record_hash"] = sha256_of_canonical_json(values)
    return EffectStateRecord.model_validate(values)


async def recover_in_flight_after_consumption(
    *,
    consumption: AuthorizationConsumptionRecord,
    effect_store: AtomicEffectStateStore,
    updated_at: datetime | str,
) -> EffectStateRecord:
    """Recover a missing IN_FLIGHT marker from an already-consumed record.

    This never releases or re-consumes the authorization. Existing state must
    match the exact authorization/consumption lineage; otherwise recovery fails
    closed. The operation remains non-effectful: it only repairs durable state.
    """
    current = _timestamp(updated_at)
    existing = await effect_store.get(consumption.consumption_id)
    if existing is not None:
        if (
            existing.authorization_id != consumption.live_adapter_bind_authorization_id
            or existing.authorization_hash != consumption.live_adapter_bind_authorization_hash
            or existing.consumption_id != consumption.consumption_id
            or existing.consumption_hash != consumption.consumption_hash
        ):
            raise BindEffectRuntimeError("BER_RECOVERY_LINEAGE_MISMATCH")
        return existing

    recovered = _in_flight_record(
        consumption,
        updated_at=current,
        reason_code="RECOVERED_FROM_DURABLE_AUTHORIZATION_CONSUMPTION",
    )
    try:
        created = await effect_store.create_in_flight(recovered)
    except Exception:
        raise BindEffectRuntimeError("BER_IN_FLIGHT_RECOVERY_STORE_FAILED") from None
    if not created:
        raced = await effect_store.get(consumption.consumption_id)
        if raced is None:
            raise BindEffectRuntimeError("BER_IN_FLIGHT_RECOVERY_CAS_FAILED")
        if (
            raced.authorization_id != consumption.live_adapter_bind_authorization_id
            or raced.consumption_hash != consumption.consumption_hash
        ):
            raise BindEffectRuntimeError("BER_RECOVERY_LINEAGE_MISMATCH")
        return raced
    return recovered


async def consume_bind_record_lineage_and_effect_state(
    artifact: Any,
    *,
    governance_inputs: RealBindAuthorizationGovernanceInputs,
    trust_inputs: BindAuthorizationTrustInputs,
    now: datetime | str,
    consumption_store: AtomicAuthorizationConsumptionStore,
    effect_store: AtomicEffectStateStore,
    credential_resolver: CredentialMaterialResolver,
    authorization_header_constructor: AuthorizationHeaderConstructor,
    adapter_factory: AuthorizedBindAdapterFactory,
    bind_ts: str | None = None,
) -> BindEffectRuntimeResult:
    """Run the real Bind path with automatic durable effect classification.

    Atomic authorization consumption is decorated so IN_FLIGHT is created
    before credential access. A completed Bind is classified from the actual
    adapter-apply observation. Any exception after consumption is classified
    conservatively; post-apply/audit uncertainty becomes EFFECT_UNKNOWN.
    """
    current = _timestamp(now)
    tracking = EffectStateTrackingConsumptionStore(consumption_store, effect_store)
    capturing = _CapturingConsumptionStore(tracking)

    try:
        lineage = await consume_bind_and_record_outcome_lineage(
            artifact,
            governance_inputs=governance_inputs,
            trust_inputs=trust_inputs,
            now=current,
            consumption_store=capturing,
            credential_resolver=credential_resolver,
            authorization_header_constructor=authorization_header_constructor,
            adapter_factory=adapter_factory,
            bind_ts=bind_ts,
        )
    except Exception as exc:
        record = capturing.record
        if record is None:
            raise
        state = await effect_store.get(record.consumption_id)
        if state is None:
            # Consumption may have committed while IN_FLIGHT persistence failed.
            # Repair from the immutable consumption record; never retry dispatch.
            state = await recover_in_flight_after_consumption(
                consumption=record,
                effect_store=effect_store,
                updated_at=current,
            )
        if state.state == EffectExecutionState.IN_FLIGHT:
            try:
                await classify_bind_exception(
                    consumption=record,
                    error=exc,
                    effect_store=effect_store,
                    updated_at=current,
                )
            except BindEffectStateError as classify_exc:
                raise BindEffectRuntimeError(
                    "BER_EXCEPTION_EFFECT_CLASSIFICATION_FAILED"
                ) from classify_exc
        raise

    try:
        effect_state = await classify_completed_bind_attempt(
            result=lineage.consumption_result,
            effect_store=effect_store,
            updated_at=current,
        )
    except BindEffectStateError as exc:
        raise BindEffectRuntimeError("BER_COMPLETED_EFFECT_CLASSIFICATION_FAILED") from exc

    return BindEffectRuntimeResult(lineage=lineage, effect_state=effect_state)


__all__ = [
    "BindEffectRuntimeError",
    "BindEffectRuntimeResult",
    "consume_bind_record_lineage_and_effect_state",
    "recover_in_flight_after_consumption",
]
