"""Real-PostgreSQL contention tests for bind effect-state CAS semantics."""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest

from veritas_os.policy.bind_effect_reconciliation import (
    EffectExecutionState,
    PostgresAtomicEffectStateStore,
    _build_record,
)
from veritas_os.policy.live_adapter_bind_authorization_consumption_store import (
    build_authorization_consumption_record,
)

pytestmark = [pytest.mark.postgresql, pytest.mark.contention]


def _require_real_postgresql() -> None:
    if not os.getenv("VERITAS_DATABASE_URL", "").startswith("postgresql"):
        pytest.skip("real PostgreSQL service container is required")


def _consumption(token: str):
    return build_authorization_consumption_record(
        live_adapter_bind_authorization_id=f"auth-{token}",
        live_adapter_bind_authorization_hash="a" * 64,
        idempotency_key=f"idem-{token}",
        bind_context_hash="b" * 64,
        execution_intent_id=f"intent-{token}",
        execution_intent_hash="c" * 64,
        endpoint_identity_binding_digest="endpoint",
        credential_reference_digest="credential",
        credential_scope_binding_digest="scope",
        consumed_at="2026-08-24T00:00:00+00:00",
    )


@pytest.mark.asyncio
async def test_real_postgres_effect_state_transition_has_one_winner() -> None:
    _require_real_postgresql()
    token = uuid4().hex
    consumption = _consumption(token)
    store = PostgresAtomicEffectStateStore()
    inflight = _build_record(
        consumption=consumption,
        state=EffectExecutionState.IN_FLIGHT,
        revision=1,
        updated_at="2026-08-24T00:00:00+00:00",
        reason_code="TEST_IN_FLIGHT",
    )
    assert await store.create_in_flight(inflight)

    candidates = [
        _build_record(
            consumption=consumption,
            state=EffectExecutionState.EFFECT_UNKNOWN,
            revision=2,
            updated_at="2026-08-24T00:00:01+00:00",
            reason_code=f"RACE_{index}",
        )
        for index in range(32)
    ]
    outcomes = await asyncio.gather(
        *(
            store.transition(
                operation_id=consumption.consumption_id,
                expected_state=EffectExecutionState.IN_FLIGHT,
                record=candidate,
            )
            for candidate in candidates
        )
    )
    assert outcomes.count(True) == 1
    assert outcomes.count(False) == 31
    stored = await store.get(consumption.consumption_id)
    assert stored is not None
    assert stored.state == EffectExecutionState.EFFECT_UNKNOWN
    assert stored.revision == 2
