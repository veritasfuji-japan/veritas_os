"""Integration tests for the real Bind -> lineage -> effect-state runtime."""

from __future__ import annotations

from dataclasses import replace

import pytest

from veritas_os.policy.bind_artifacts import hash_bind_receipt
from veritas_os.policy.bind_effect_reconciliation import (
    EffectExecutionState,
    InMemoryAtomicEffectStateStore,
)
from veritas_os.policy.bind_effect_runtime import (
    consume_bind_record_lineage_and_effect_state,
    recover_in_flight_after_consumption,
)
from veritas_os.policy.bind_outcome_lineage import BindOutcomeLineageError
from veritas_os.policy.live_adapter_bind_authorization_consumption_store import (
    InMemoryAtomicAuthorizationConsumptionStore,
    build_authorization_consumption_record,
)
from veritas_os.tests.test_bind_outcome_lineage import _BlockedFactory
from veritas_os.tests.test_live_adapter_bind_authorization import VERIFICATION_NOW, _build
from veritas_os.tests.test_live_adapter_bind_authorization_consumption import (
    _Factory,
    _HeaderConstructor,
    _Resolver,
)


def _install_fake_trustlog(monkeypatch) -> None:
    import veritas_os.policy.bind_outcome_lineage as lineage

    monkeypatch.setattr(
        lineage,
        "append_execution_intent_trustlog",
        lambda intent: {"sha256": "a" * 64, "execution_intent_id": intent.execution_intent_id},
    )

    def _append_bind(receipt):
        with_hash = replace(receipt, bind_receipt_hash=hash_bind_receipt(receipt))
        return replace(with_hash, trustlog_hash="b" * 64)

    monkeypatch.setattr(lineage, "append_bind_receipt_trustlog", _append_bind)
    monkeypatch.setattr(lineage, "append_trust_log", lambda entry: {**entry, "sha256": "c" * 64})


@pytest.mark.asyncio
async def test_real_runtime_apply_attempt_automatically_becomes_effect_unknown(monkeypatch) -> None:
    _install_fake_trustlog(monkeypatch)
    artifact, governance, trust = _build()
    effects = InMemoryAtomicEffectStateStore()

    result = await consume_bind_record_lineage_and_effect_state(
        artifact,
        governance_inputs=governance,
        trust_inputs=trust,
        now=VERIFICATION_NOW,
        consumption_store=InMemoryAtomicAuthorizationConsumptionStore(),
        effect_store=effects,
        credential_resolver=_Resolver(),
        authorization_header_constructor=_HeaderConstructor(),
        adapter_factory=_Factory(),
    )

    assert result.lineage.consumption_result.adapter_apply_attempted is True
    assert result.effect_state.state == EffectExecutionState.EFFECT_UNKNOWN
    assert result.effect_state.reason_code == "ADAPTER_APPLY_ATTEMPTED_WITHOUT_VERIFIED_EXTERNAL_ACK"
    persisted = await effects.get(result.effect_state.operation_id)
    assert persisted == result.effect_state


@pytest.mark.asyncio
async def test_real_runtime_block_before_apply_is_confirmed_no_effect(monkeypatch) -> None:
    _install_fake_trustlog(monkeypatch)
    artifact, governance, trust = _build()
    effects = InMemoryAtomicEffectStateStore()

    result = await consume_bind_record_lineage_and_effect_state(
        artifact,
        governance_inputs=governance,
        trust_inputs=trust,
        now=VERIFICATION_NOW,
        consumption_store=InMemoryAtomicAuthorizationConsumptionStore(),
        effect_store=effects,
        credential_resolver=_Resolver(),
        authorization_header_constructor=_HeaderConstructor(),
        adapter_factory=_BlockedFactory(),
    )

    assert result.lineage.consumption_result.adapter_apply_attempted is False
    assert result.effect_state.state == EffectExecutionState.CONFIRMED_NO_EFFECT
    assert result.effect_state.reason_code == "BIND_COMPLETED_WITHOUT_ADAPTER_APPLY"


@pytest.mark.asyncio
async def test_trustlog_failure_after_real_apply_is_effect_unknown_and_not_reusable(monkeypatch) -> None:
    import veritas_os.policy.bind_outcome_lineage as lineage

    artifact, governance, trust = _build()
    consumptions = InMemoryAtomicAuthorizationConsumptionStore()
    effects = InMemoryAtomicEffectStateStore()

    def _fail(_intent):
        raise RuntimeError("audit-store-unavailable")

    monkeypatch.setattr(lineage, "append_execution_intent_trustlog", _fail)

    with pytest.raises(
        BindOutcomeLineageError,
        match="BOL_TRUSTLOG_PERSISTENCE_FAILED_AFTER_BIND_ATTEMPT",
    ):
        await consume_bind_record_lineage_and_effect_state(
            artifact,
            governance_inputs=governance,
            trust_inputs=trust,
            now=VERIFICATION_NOW,
            consumption_store=consumptions,
            effect_store=effects,
            credential_resolver=_Resolver(),
            authorization_header_constructor=_HeaderConstructor(),
            adapter_factory=_Factory(),
        )

    consumed = await consumptions.get(artifact.live_adapter_bind_authorization_id)
    assert consumed is not None
    state = await effects.get(consumed.consumption_id)
    assert state is not None
    assert state.state == EffectExecutionState.EFFECT_UNKNOWN


@pytest.mark.asyncio
async def test_missing_in_flight_can_be_recovered_from_consumption_without_redispatch() -> None:
    consumption = build_authorization_consumption_record(
        live_adapter_bind_authorization_id="auth-recovery",
        live_adapter_bind_authorization_hash="a" * 64,
        idempotency_key="idem-recovery",
        bind_context_hash="b" * 64,
        execution_intent_id="intent-recovery",
        execution_intent_hash="c" * 64,
        endpoint_identity_binding_digest="endpoint",
        credential_reference_digest="credential",
        credential_scope_binding_digest="scope",
        consumed_at="2026-08-24T00:00:00+00:00",
    )
    effects = InMemoryAtomicEffectStateStore()

    recovered = await recover_in_flight_after_consumption(
        consumption=consumption,
        effect_store=effects,
        updated_at="2026-08-24T00:00:01+00:00",
    )

    assert recovered.state == EffectExecutionState.IN_FLIGHT
    assert recovered.consumption_hash == consumption.consumption_hash
    assert recovered.reason_code == "RECOVERED_FROM_DURABLE_AUTHORIZATION_CONSUMPTION"
    again = await recover_in_flight_after_consumption(
        consumption=consumption,
        effect_store=effects,
        updated_at="2026-08-24T00:00:02+00:00",
    )
    assert again == recovered
