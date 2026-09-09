"""Durable sandbox business-event claims block replacement execution attempts."""

import json

import pytest

from veritas_os.policy import sandbox_pre_effect as pre_effect
from veritas_os.policy.bind_effect_reconciliation import (
    EffectExecutionState,
    InMemoryAtomicEffectStateStore,
    _build_record,
)
from veritas_os.policy.live_adapter_bind_authorization_consumption_store import (
    build_authorization_consumption_record,
)
from veritas_os.tests.test_sandbox_action_binding import PAYLOAD, deployment


def _consumption(token: str):
    return build_authorization_consumption_record(
        live_adapter_bind_authorization_id=f"auth-{token}",
        live_adapter_bind_authorization_hash=(token[0] if token else "a") * 64,
        idempotency_key=f"idem-{token}",
        bind_context_hash="b" * 64,
        execution_intent_id=f"intent-{token}",
        execution_intent_hash="c" * 64,
        endpoint_identity_binding_digest="endpoint",
        credential_reference_digest="credential",
        credential_scope_binding_digest="scope",
        consumed_at="2026-09-09T00:00:00+00:00",
    )


def _record(consumption, state=EffectExecutionState.IN_FLIGHT, revision=1):
    return _build_record(
        consumption=consumption,
        state=state,
        revision=revision,
        updated_at=f"2026-09-09T00:00:0{min(revision, 9)}+00:00",
        reason_code=f"TEST_{state.value}",
    )


def _key(payload=None, config=None):
    return pre_effect._sandbox_business_event_key(
        json.dumps(PAYLOAD if payload is None else payload),
        deployment() if config is None else config,
    )


def test_business_event_identity_ignores_message_and_authorization_metadata():
    original = _key()
    changed_message = _key({**PAYLOAD, "message": "replacement payload"})
    changed_event = _key({
        **PAYLOAD,
        "event_id": "12345678-1234-4234-8234-123456789abd",
    })
    assert original == changed_message
    assert original != changed_event
    assert original.startswith("sandbox-business-event:v1:sha256:")


@pytest.mark.asyncio
async def test_unresolved_business_event_blocks_different_authorization():
    store = InMemoryAtomicEffectStateStore()
    first = _consumption("a1")
    replacement = _consumption("d2")
    key = _key()

    original = _record(first)
    assert await store.create_in_flight(original, business_event_key=key)
    unknown = _record(first, EffectExecutionState.EFFECT_UNKNOWN, 2)
    assert await store.transition(
        operation_id=original.operation_id,
        expected_state=EffectExecutionState.IN_FLIGHT,
        record=unknown,
    )

    assert not await store.create_in_flight(
        _record(replacement), business_event_key=key,
    )
    assert await store.get(replacement.consumption_id) is None
    assert await store.get(original.operation_id) == unknown


@pytest.mark.asyncio
async def test_confirmed_effect_keeps_claim_but_confirmed_no_effect_releases_it():
    key = _key()

    effect_store = InMemoryAtomicEffectStateStore()
    first = _consumption("a1")
    replacement = _consumption("d2")
    original = _record(first)
    assert await effect_store.create_in_flight(original, business_event_key=key)
    confirmed = _record(first, EffectExecutionState.CONFIRMED_EFFECT, 2)
    assert await effect_store.transition(
        operation_id=original.operation_id,
        expected_state=EffectExecutionState.IN_FLIGHT,
        record=confirmed,
    )
    assert not await effect_store.create_in_flight(
        _record(replacement), business_event_key=key,
    )

    no_effect_store = InMemoryAtomicEffectStateStore()
    first = _consumption("e3")
    replacement = _consumption("f4")
    original = _record(first)
    assert await no_effect_store.create_in_flight(original, business_event_key=key)
    no_effect = _record(first, EffectExecutionState.CONFIRMED_NO_EFFECT, 2)
    assert await no_effect_store.transition(
        operation_id=original.operation_id,
        expected_state=EffectExecutionState.IN_FLIGHT,
        record=no_effect,
    )
    assert await no_effect_store.create_in_flight(
        _record(replacement), business_event_key=key,
    )
