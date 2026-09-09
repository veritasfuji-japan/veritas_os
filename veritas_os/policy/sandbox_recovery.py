"""Owning crash-recovery coordinator for the native v2 sandbox path.

Recovery never resends an external effect. It reads durable state first and then
chooses exactly one safe path:

* pre-dispatch IN_FLIGHT -> terminal CONFIRMED_NO_EFFECT when the exact stored
  sandbox pre-effect claim proves transport was never eligible to start;
* EFFECT_UNKNOWN -> one independent read-only reconciliation attempt;
* CONFIRMED_EFFECT -> deterministic retrospective receipt publication/recovery;
* terminal CONFIRMED_NO_EFFECT -> idempotent terminal return.

Lookup absence, provider failure, storage ambiguity, substituted lineage or an
unexpected state never become permission to retry execution.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from veritas_os.policy.bind_effect_reconciliation import (
    EffectExecutionState,
    EffectStateRecord,
    InMemoryAtomicEffectStateStore,
    PostgresAtomicEffectStateStore,
    _build_record,
)
from veritas_os.policy.live_adapter_bind_authorization_codec import _timestamp
from veritas_os.policy.live_adapter_bind_authorization_consumption_store import (
    AuthorizationConsumptionRecord,
    InMemoryAtomicAuthorizationConsumptionStore,
    PostgresAtomicAuthorizationConsumptionStore,
    build_authorization_consumption_record,
)
from veritas_os.policy.live_adapter_bind_authorization_contracts import (
    BindAuthorizationTrustInputs,
    RealBindAuthorizationGovernanceInputs,
)
from veritas_os.policy.native_bind_authorization import (
    NativeAuthorizationSourceInputs,
    _verified_source,
    verify_native_bind_authorization,
)
from veritas_os.policy.sandbox_action_binding import SandboxDeployment, verify_sandbox_action_binding
from veritas_os.policy.sandbox_credential_resolution import SandboxCredentialProvider
from veritas_os.policy.sandbox_pre_effect import SandboxClockReading, _clock
from veritas_os.policy.sandbox_receipt_outcome import SandboxReceiptBundle, publish_sandbox_receipts
from veritas_os.policy.sandbox_reconciliation import (
    SandboxReaderPolicy,
    reconcile_sandbox_effect,
)
from veritas_os.policy.trusted_https_reconciliation import ReconciliationVerifierPolicy


class SandboxRecoveryError(ValueError):
    """Sanitized failure. The coordinator never implies that retry is safe."""


class SandboxRecoveryResult(BaseModel):
    """Durable recovery result; never execution authority."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    format_version: Literal["sandbox-crash-recovery/v1"] = "sandbox-crash-recovery/v1"
    operation_id: str
    authorization_id: str
    state: EffectExecutionState
    recovery_status: Literal[
        "CONFIRMED_NO_EFFECT",
        "STILL_UNKNOWN",
        "CONFIRMED_EFFECT",
    ]
    reason_code: str
    external_effect_retry_permitted: Literal[False] = False
    receipt_bundle: SandboxReceiptBundle | None = None


async def _verified_recovery_lineage(
    authorization: Any,
    payload_json: str,
    *,
    deployment: SandboxDeployment,
    issuance_source_inputs: NativeAuthorizationSourceInputs,
    historical_governance_inputs: RealBindAuthorizationGovernanceInputs,
    trust_inputs: BindAuthorizationTrustInputs,
    consumption_store: PostgresAtomicAuthorizationConsumptionStore | InMemoryAtomicAuthorizationConsumptionStore,
) -> AuthorizationConsumptionRecord:
    """Rebuild the exact historical sandbox consumption without reauthorizing."""

    verify_sandbox_action_binding(
        authorization,
        payload_json,
        deployment=deployment,
        source_inputs=issuance_source_inputs,
        governance_inputs=historical_governance_inputs,
        trust_inputs=trust_inputs,
    )
    verified = verify_native_bind_authorization(
        authorization,
        source_inputs=issuance_source_inputs,
        governance_inputs=historical_governance_inputs,
        trust_inputs=trust_inputs,
    )
    _, _, context = _verified_source(
        verified.source_runtime_risk_packet,
        issuance_source_inputs,
        historical_governance_inputs,
    )
    stored = await consumption_store.get(verified.authorization_id)
    if stored is None:
        raise ValueError("missing consumption")
    expected = build_authorization_consumption_record(
        live_adapter_bind_authorization_id=verified.authorization_id,
        live_adapter_bind_authorization_hash=verified.authorization_hash,
        idempotency_key=verified.idempotency_key,
        bind_context_hash=verified.bind_context_hash,
        execution_intent_id=verified.execution_intent_id,
        execution_intent_hash=verified.execution_intent_hash,
        endpoint_identity_binding_digest=context.endpoint_identity_binding_digest,
        credential_reference_digest=context.credential_reference_digest,
        credential_scope_binding_digest=context.credential_scope_binding_digest,
        consumed_at=stored.consumed_at,
    )
    consumed_at = datetime.fromisoformat(_timestamp(stored.consumed_at))
    if stored != expected or not (
        datetime.fromisoformat(verified.valid_from)
        <= consumed_at
        < datetime.fromisoformat(verified.valid_until)
    ):
        raise ValueError("consumption lineage")
    return stored


def _exact_pre_dispatch_record(
    consumption: AuthorizationConsumptionRecord,
    current: EffectStateRecord,
) -> EffectStateRecord:
    expected = _build_record(
        consumption=consumption,
        state=EffectExecutionState.IN_FLIGHT,
        revision=1,
        updated_at=current.updated_at,
        reason_code="SANDBOX_PRE_EFFECT_ATTEMPT_CLAIMED",
    )
    if current != expected:
        raise ValueError("not exact sandbox pre-dispatch state")
    return expected


async def _confirm_pre_dispatch_no_effect(
    *,
    consumption: AuthorizationConsumptionRecord,
    current: EffectStateRecord,
    effect_store: PostgresAtomicEffectStateStore | InMemoryAtomicEffectStateStore,
    observed_at: str,
) -> EffectStateRecord:
    """Close only an exact pre-dispatch claim.

    execute_sandbox_bind cannot enter transport until the same row has durably
    advanced to EFFECT_UNKNOWN and readback matches. Therefore an exact durable
    revision-1 sandbox pre-effect row proves this attempt never crossed the
    transport-entry gate.
    """

    _exact_pre_dispatch_record(consumption, current)
    terminal = _build_record(
        consumption=consumption,
        state=EffectExecutionState.CONFIRMED_NO_EFFECT,
        revision=2,
        updated_at=observed_at,
        reason_code="SANDBOX_RECOVERY_PRE_DISPATCH_CONFIRMED_NO_EFFECT",
    )
    try:
        changed = await effect_store.transition(
            operation_id=current.operation_id,
            expected_state=EffectExecutionState.IN_FLIGHT,
            record=terminal,
        )
    except Exception:
        changed = False

    # The transition acknowledgement may be lost. Trust a fresh durable read,
    # never the return value alone.
    stored = await effect_store.get(current.operation_id)
    if stored == terminal:
        return terminal
    if changed is True:
        raise ValueError("no-effect readback mismatch")
    if stored is not None and stored.state in {
        EffectExecutionState.EFFECT_UNKNOWN,
        EffectExecutionState.CONFIRMED_EFFECT,
        EffectExecutionState.CONFIRMED_NO_EFFECT,
    }:
        return stored
    raise ValueError("pre-dispatch recovery ambiguous")


async def recover_sandbox_attempt(
    authorization: Any,
    payload_json: str,
    *,
    deployment: SandboxDeployment,
    issuance_source_inputs: NativeAuthorizationSourceInputs,
    historical_governance_inputs: RealBindAuthorizationGovernanceInputs,
    trust_inputs: BindAuthorizationTrustInputs,
    consumption_store: PostgresAtomicAuthorizationConsumptionStore | InMemoryAtomicAuthorizationConsumptionStore,
    effect_store: PostgresAtomicEffectStateStore | InMemoryAtomicEffectStateStore,
    reader_policy: SandboxReaderPolicy,
    verifier_policy: ReconciliationVerifierPolicy,
    provider: SandboxCredentialProvider,
    trusted_clock: Any,
    allow_in_memory_for_testing: bool = False,
) -> SandboxRecoveryResult:
    """Recover one sandbox attempt from durable state without redispatch.

    This function is an owning composition boundary, not a scheduler. Repeated
    invocations are safe with respect to external effects: there is no POST,
    no authorization consumption, no credential use for execution and no
    transport resend. EFFECT_UNKNOWN may perform one read-only GET through the
    existing reconciler.
    """

    cancelled = False
    try:
        durable = (
            type(consumption_store) is PostgresAtomicAuthorizationConsumptionStore
            and type(effect_store) is PostgresAtomicEffectStateStore
        )
        test_only = (
            allow_in_memory_for_testing is True
            and type(consumption_store) is InMemoryAtomicAuthorizationConsumptionStore
            and type(effect_store) is InMemoryAtomicEffectStateStore
        )
        if not durable and not test_only:
            raise ValueError("durable stores")

        consumption = await _verified_recovery_lineage(
            authorization,
            payload_json,
            deployment=deployment,
            issuance_source_inputs=issuance_source_inputs,
            historical_governance_inputs=historical_governance_inputs,
            trust_inputs=trust_inputs,
            consumption_store=consumption_store,
        )
        current = await effect_store.get(consumption.consumption_id)
        if current is None:
            raise ValueError("missing effect state")
        if (
            current.operation_id != consumption.consumption_id
            or current.authorization_id != consumption.live_adapter_bind_authorization_id
            or current.authorization_hash != consumption.live_adapter_bind_authorization_hash
            or current.consumption_hash != consumption.consumption_hash
            or current.idempotency_key != consumption.idempotency_key
        ):
            raise ValueError("effect lineage")

        if current.state == EffectExecutionState.IN_FLIGHT:
            reading: SandboxClockReading = trusted_clock()
            now = _clock(reading)
            consumed_at = datetime.fromisoformat(_timestamp(consumption.consumed_at))
            if now < consumed_at:
                raise ValueError("clock before consumption")
            current = await _confirm_pre_dispatch_no_effect(
                consumption=consumption,
                current=current,
                effect_store=effect_store,
                observed_at=_timestamp(reading.now),
            )

        if current.state == EffectExecutionState.IN_FLIGHT:
            raise ValueError("in-flight not closed")

        if current.state == EffectExecutionState.EFFECT_UNKNOWN:
            reconciled = await reconcile_sandbox_effect(
                authorization,
                payload_json,
                deployment=deployment,
                issuance_source_inputs=issuance_source_inputs,
                historical_governance_inputs=historical_governance_inputs,
                trust_inputs=trust_inputs,
                consumption_store=consumption_store,
                effect_store=effect_store,
                reader_policy=reader_policy,
                verifier_policy=verifier_policy,
                provider=provider,
                trusted_clock=trusted_clock,
                allow_in_memory_for_testing=allow_in_memory_for_testing,
            )
            current = reconciled.record
            if current.state == EffectExecutionState.EFFECT_UNKNOWN:
                return SandboxRecoveryResult(
                    operation_id=current.operation_id,
                    authorization_id=current.authorization_id,
                    state=current.state,
                    recovery_status="STILL_UNKNOWN",
                    reason_code="SANDBOX_RECOVERY_LOOKUP_DID_NOT_CONFIRM",
                )

        if current.state == EffectExecutionState.CONFIRMED_EFFECT:
            bundle = await publish_sandbox_receipts(
                authorization,
                payload_json,
                deployment=deployment,
                issuance_source_inputs=issuance_source_inputs,
                historical_governance_inputs=historical_governance_inputs,
                trust_inputs=trust_inputs,
                consumption_store=consumption_store,
                effect_store=effect_store,
                reader_policy=reader_policy,
                verifier_policy=verifier_policy,
                allow_in_memory_for_testing=allow_in_memory_for_testing,
            )
            return SandboxRecoveryResult(
                operation_id=current.operation_id,
                authorization_id=current.authorization_id,
                state=current.state,
                recovery_status="CONFIRMED_EFFECT",
                reason_code="SANDBOX_RECOVERY_CONFIRMED_EFFECT_ARTIFACTS_AVAILABLE",
                receipt_bundle=bundle,
            )

        if current.state == EffectExecutionState.CONFIRMED_NO_EFFECT:
            if current.reason_code != "SANDBOX_RECOVERY_PRE_DISPATCH_CONFIRMED_NO_EFFECT":
                raise ValueError("unexpected no-effect lineage")
            return SandboxRecoveryResult(
                operation_id=current.operation_id,
                authorization_id=current.authorization_id,
                state=current.state,
                recovery_status="CONFIRMED_NO_EFFECT",
                reason_code=current.reason_code,
            )

        raise ValueError("unsupported recovery state")
    except asyncio.CancelledError:
        cancelled = True
    except Exception:
        pass
    if cancelled:
        raise asyncio.CancelledError()
    raise SandboxRecoveryError("SRC_RECOVERY_FAILED_NO_EFFECT_RETRY")


__all__ = [
    "SandboxRecoveryError",
    "SandboxRecoveryResult",
    "recover_sandbox_attempt",
]
