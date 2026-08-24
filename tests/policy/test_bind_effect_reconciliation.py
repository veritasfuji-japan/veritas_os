from __future__ import annotations

from dataclasses import dataclass

import pytest

from veritas_os.policy.bind_effect_reconciliation import (
    BindEffectStateError,
    EffectExecutionState,
    EffectStateTrackingConsumptionStore,
    InMemoryAtomicEffectStateStore,
    ReconciliationClaim,
    ReconciliationEvidence,
    VerifiedReconciliationEvidence,
    classify_completed_bind_attempt,
    reconcile_effect_unknown,
)
from veritas_os.policy.live_adapter_bind_authorization_consumption import (
    BindAuthorizationConsumptionResult,
)
from veritas_os.policy.live_adapter_bind_authorization_consumption_store import (
    InMemoryAtomicAuthorizationConsumptionStore,
    build_authorization_consumption_record,
)
from veritas_os.security.hash import sha256_of_canonical_json


@dataclass(frozen=True)
class _Receipt:
    pass


class _Verifier:
    async def verify(self, evidence: ReconciliationEvidence) -> VerifiedReconciliationEvidence:
        return VerifiedReconciliationEvidence(
            evidence=evidence,
            verifier_id="fixture-verifier",
            verifier_policy_hash="1" * 64,
            verification_proof_hash="2" * 64,
            verified_at="2026-08-24T00:00:02+00:00",
        )


def _consumption():
    return build_authorization_consumption_record(
        live_adapter_bind_authorization_id="auth-1",
        live_adapter_bind_authorization_hash="a" * 64,
        idempotency_key="idem-1",
        bind_context_hash="b" * 64,
        execution_intent_id="intent-1",
        execution_intent_hash="c" * 64,
        endpoint_identity_binding_digest="endpoint-digest",
        credential_reference_digest="credential-digest",
        credential_scope_binding_digest="scope-digest",
        consumed_at="2026-08-24T00:00:00+00:00",
    )


@pytest.mark.asyncio
async def test_consumption_creates_in_flight_before_effect_boundary() -> None:
    base = InMemoryAtomicAuthorizationConsumptionStore()
    effects = InMemoryAtomicEffectStateStore()
    store = EffectStateTrackingConsumptionStore(base, effects)
    record = _consumption()

    assert await store.consume_once(record) is True
    state = await effects.get(record.consumption_id)
    assert state is not None
    assert state.state == EffectExecutionState.IN_FLIGHT
    assert await store.consume_once(record) is False


@pytest.mark.asyncio
async def test_apply_attempt_without_external_ack_becomes_effect_unknown() -> None:
    base = InMemoryAtomicAuthorizationConsumptionStore()
    effects = InMemoryAtomicEffectStateStore()
    store = EffectStateTrackingConsumptionStore(base, effects)
    record = _consumption()
    assert await store.consume_once(record)

    result = BindAuthorizationConsumptionResult(
        consumption_record=record,
        bind_receipt=_Receipt(),  # type: ignore[arg-type]
        adapter_apply_attempted=True,
    )
    state = await classify_completed_bind_attempt(
        result=result,
        effect_store=effects,
        updated_at="2026-08-24T00:00:01+00:00",
    )
    assert state.state == EffectExecutionState.EFFECT_UNKNOWN


@pytest.mark.asyncio
async def test_no_apply_is_confirmed_no_effect() -> None:
    base = InMemoryAtomicAuthorizationConsumptionStore()
    effects = InMemoryAtomicEffectStateStore()
    store = EffectStateTrackingConsumptionStore(base, effects)
    record = _consumption()
    assert await store.consume_once(record)

    result = BindAuthorizationConsumptionResult(
        consumption_record=record,
        bind_receipt=_Receipt(),  # type: ignore[arg-type]
        adapter_apply_attempted=False,
    )
    state = await classify_completed_bind_attempt(
        result=result,
        effect_store=effects,
        updated_at="2026-08-24T00:00:01+00:00",
    )
    assert state.state == EffectExecutionState.CONFIRMED_NO_EFFECT


@pytest.mark.asyncio
async def test_effect_unknown_requires_verified_reconciliation() -> None:
    base = InMemoryAtomicAuthorizationConsumptionStore()
    effects = InMemoryAtomicEffectStateStore()
    store = EffectStateTrackingConsumptionStore(base, effects)
    record = _consumption()
    assert await store.consume_once(record)
    result = BindAuthorizationConsumptionResult(
        consumption_record=record,
        bind_receipt=_Receipt(),  # type: ignore[arg-type]
        adapter_apply_attempted=True,
    )
    await classify_completed_bind_attempt(
        result=result,
        effect_store=effects,
        updated_at="2026-08-24T00:00:01+00:00",
    )

    observation = {
        "operation_id": record.consumption_id,
        "authorization_id": record.live_adapter_bind_authorization_id,
        "consumption_id": record.consumption_id,
        "claim": ReconciliationClaim.CONFIRMED_EFFECT,
        "source_type": "external_api",
        "source_identity": "fixture-ledger",
        "observed_at": "2026-08-24T00:00:02+00:00",
        "external_operation_reference": "ext-123",
        "external_ack_digest": "d" * 64,
    }
    evidence = ReconciliationEvidence(
        **observation,
        observation_digest=sha256_of_canonical_json(observation),
    )
    terminal = await reconcile_effect_unknown(
        operation_id=record.consumption_id,
        evidence=evidence,
        verifier=_Verifier(),
        effect_store=effects,
        updated_at="2026-08-24T00:00:03+00:00",
    )
    assert terminal.state == EffectExecutionState.CONFIRMED_EFFECT

    with pytest.raises(BindEffectStateError, match="BES_TERMINAL_STATE_IMMUTABLE"):
        await reconcile_effect_unknown(
            operation_id=record.consumption_id,
            evidence=evidence,
            verifier=_Verifier(),
            effect_store=effects,
            updated_at="2026-08-24T00:00:04+00:00",
        )


@pytest.mark.asyncio
async def test_reconciliation_lineage_mismatch_fails_closed() -> None:
    base = InMemoryAtomicAuthorizationConsumptionStore()
    effects = InMemoryAtomicEffectStateStore()
    store = EffectStateTrackingConsumptionStore(base, effects)
    record = _consumption()
    assert await store.consume_once(record)
    result = BindAuthorizationConsumptionResult(
        consumption_record=record,
        bind_receipt=_Receipt(),  # type: ignore[arg-type]
        adapter_apply_attempted=True,
    )
    await classify_completed_bind_attempt(
        result=result,
        effect_store=effects,
        updated_at="2026-08-24T00:00:01+00:00",
    )
    evidence = ReconciliationEvidence(
        operation_id=record.consumption_id,
        authorization_id="wrong-auth",
        consumption_id=record.consumption_id,
        claim=ReconciliationClaim.CONFIRMED_NO_EFFECT,
        source_type="external_api",
        source_identity="fixture-ledger",
        observed_at="2026-08-24T00:00:02+00:00",
        observation_digest="e" * 64,
    )
    with pytest.raises(BindEffectStateError, match="BES_RECONCILIATION_LINEAGE_MISMATCH"):
        await reconcile_effect_unknown(
            operation_id=record.consumption_id,
            evidence=evidence,
            verifier=_Verifier(),
            effect_store=effects,
            updated_at="2026-08-24T00:00:03+00:00",
        )
