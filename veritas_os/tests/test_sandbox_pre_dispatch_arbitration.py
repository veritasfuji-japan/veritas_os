"""Adversarial proof tests for sandbox ownership-vs-NO_EFFECT arbitration."""

from __future__ import annotations

import asyncio
import copy
import pickle

import pytest

from veritas_os.policy.bind_effect_reconciliation import (
    BindEffectStateError,
    EffectExecutionState,
    EffectProvenance,
    SandboxOwnershipState,
    _build_record,
)
from veritas_os.policy import sandbox_pre_effect as pre
from veritas_os.tests.test_sandbox_pre_effect import (
    _args,
    _prepare,
    prepared_inputs as prepared_inputs_fixture,
)

pytestmark = pytest.mark.slow
prepared_inputs = prepared_inputs_fixture


async def _prepared(prepared_inputs):
    artifact, args = await _args(prepared_inputs)
    prepared = await _prepare(artifact, args)
    return artifact, args, prepared


@pytest.mark.asyncio
async def test_handle_is_linear_noncopyable_and_single_use(prepared_inputs):
    _, args, prepared = await _prepared(prepared_inputs)
    handle = prepared.ownership_handle

    with pytest.raises(TypeError):
        copy.copy(handle)
    with pytest.raises(TypeError):
        copy.deepcopy(handle)
    with pytest.raises(TypeError):
        pickle.dumps(handle)

    assert handle.state == "UNUSED"
    await pre.consume_sandbox_ownership(prepared, effect_store=args["effect_store"])
    assert handle.state == "SPENT"
    ownership = await args["effect_store"].get_sandbox_ownership(prepared.attempt.operation_id)
    assert ownership is not None
    assert ownership.state == SandboxOwnershipState.CONSUMED

    with pytest.raises(pre.SandboxPreEffectError, match="SEO_HANDLE_ALREADY_SPENT"):
        await pre.consume_sandbox_ownership(prepared, effect_store=args["effect_store"])


@pytest.mark.asyncio
@pytest.mark.parametrize("winner", ["ownership", "recovery"])
async def test_32_handle_presentations_and_no_effect_recovery_have_one_durable_winner(
    prepared_inputs, monkeypatch, winner,
):
    _, args, prepared = await _prepared(prepared_inputs)
    store = args["effect_store"]
    start = asyncio.Event()
    gate_entered = asyncio.Event()
    gate_release = asyncio.Event()
    continuation_entries = 0

    if winner == "ownership":
        original_recovery = store.confirm_pre_dispatch_no_effect

        async def blocked_recovery(**kwargs):
            gate_entered.set()
            await gate_release.wait()
            return await original_recovery(**kwargs)

        monkeypatch.setattr(store, "confirm_pre_dispatch_no_effect", blocked_recovery)

        async def recovery():
            await start.wait()
            return await store.confirm_pre_dispatch_no_effect(
                expected=prepared.attempt,
                updated_at="2026-08-24T00:00:03+00:00",
            )

        recovery_task = asyncio.create_task(recovery())
        start.set()
        await gate_entered.wait()

        async def present():
            nonlocal continuation_entries
            try:
                result = await pre.consume_sandbox_ownership(
                    prepared,
                    effect_store=store,
                    updated_at="2026-08-24T00:00:02+00:00",
                )
                continuation_entries += 1
                return result
            except Exception as exc:
                return exc

        presentations = await asyncio.gather(*(present() for _ in range(32)))
        assert sum(x is prepared for x in presentations) == 1
        gate_release.set()
        recovery_result = await recovery_task
        assert recovery_result is None
    else:
        original_consume = store.consume_sandbox_ownership

        async def blocked_consume(**kwargs):
            gate_entered.set()
            await gate_release.wait()
            return await original_consume(**kwargs)

        monkeypatch.setattr(store, "consume_sandbox_ownership", blocked_consume)

        async def present():
            nonlocal continuation_entries
            await start.wait()
            try:
                result = await pre.consume_sandbox_ownership(
                    prepared,
                    effect_store=store,
                    updated_at="2026-08-24T00:00:02+00:00",
                )
                continuation_entries += 1
                return result
            except Exception as exc:
                return exc

        tasks = [asyncio.create_task(present()) for _ in range(32)]
        start.set()
        await gate_entered.wait()
        recovery_result = await store.confirm_pre_dispatch_no_effect(
            expected=prepared.attempt,
            updated_at="2026-08-24T00:00:03+00:00",
        )
        assert recovery_result is not None
        gate_release.set()
        presentations = await asyncio.gather(*tasks)
        assert sum(x is prepared for x in presentations) == 0

    effect = await store.get(prepared.attempt.operation_id)
    ownership = await store.get_sandbox_ownership(prepared.attempt.operation_id)
    assert effect is not None and ownership is not None

    if winner == "ownership":
        assert continuation_entries == 1
        assert ownership.state == SandboxOwnershipState.CONSUMED
        assert effect.state == EffectExecutionState.IN_FLIGHT
        assert prepared.attempt.operation_id in store._operation_business_events
    else:
        assert continuation_entries == 0
        assert ownership.state == SandboxOwnershipState.CANCELLED
        assert effect.state == EffectExecutionState.CONFIRMED_NO_EFFECT
        assert prepared.attempt.operation_id not in store._operation_business_events

    assert not (
        ownership.state == SandboxOwnershipState.CONSUMED
        and effect.state == EffectExecutionState.CONFIRMED_NO_EFFECT
    )


@pytest.mark.asyncio
async def test_consumed_ownership_blocks_pre_dispatch_no_effect_after_restart_equivalent(
    prepared_inputs,
):
    _, args, prepared = await _prepared(prepared_inputs)
    store = args["effect_store"]

    await pre.consume_sandbox_ownership(prepared, effect_store=store)
    terminal = await store.confirm_pre_dispatch_no_effect(
        expected=prepared.attempt,
        updated_at="2026-08-24T00:00:03+00:00",
    )
    assert terminal is None

    effect = await store.get(prepared.attempt.operation_id)
    ownership = await store.get_sandbox_ownership(prepared.attempt.operation_id)
    assert effect is not None
    assert effect.state == EffectExecutionState.IN_FLIGHT
    assert ownership is not None
    assert ownership.state == SandboxOwnershipState.CONSUMED
    assert prepared.attempt.operation_id in store._operation_business_events


@pytest.mark.asyncio
async def test_no_effect_cancellation_permanently_rejects_delayed_valid_handle(
    prepared_inputs,
):
    _, args, prepared = await _prepared(prepared_inputs)
    store = args["effect_store"]

    terminal = await store.confirm_pre_dispatch_no_effect(
        expected=prepared.attempt,
        updated_at="2026-08-24T00:00:03+00:00",
    )
    assert terminal is not None
    assert terminal.state == EffectExecutionState.CONFIRMED_NO_EFFECT

    with pytest.raises(pre.SandboxPreEffectError, match="SEO_PRE_DISPATCH_ARBITRATION_LOST"):
        await pre.consume_sandbox_ownership(prepared, effect_store=store)

    ownership = await store.get_sandbox_ownership(prepared.attempt.operation_id)
    assert ownership is not None
    assert ownership.state == SandboxOwnershipState.CANCELLED
    assert prepared.ownership_handle.state == "SPENT"


@pytest.mark.asyncio
async def test_ambiguous_ownership_ack_never_allows_continuation_or_retry(
    prepared_inputs, monkeypatch,
):
    _, args, prepared = await _prepared(prepared_inputs)
    store = args["effect_store"]
    original = store.consume_sandbox_ownership

    async def lost_ack(**kwargs):
        changed = await original(**kwargs)
        assert changed is True
        raise RuntimeError("synthetic ownership acknowledgement loss")

    monkeypatch.setattr(store, "consume_sandbox_ownership", lost_ack)
    with pytest.raises(
        pre.SandboxPreEffectError,
        match="SEO_OWNERSHIP_COMMIT_FAILED_OR_UNKNOWN",
    ):
        await pre.consume_sandbox_ownership(prepared, effect_store=store)

    assert prepared.ownership_handle.state == "SPENT"
    ownership = await store.get_sandbox_ownership(prepared.attempt.operation_id)
    assert ownership is not None
    assert ownership.state == SandboxOwnershipState.CONSUMED

    with pytest.raises(pre.SandboxPreEffectError, match="SEO_HANDLE_ALREADY_SPENT"):
        await pre.consume_sandbox_ownership(prepared, effect_store=store)

    assert await store.confirm_pre_dispatch_no_effect(
        expected=prepared.attempt,
        updated_at="2026-08-24T00:00:04+00:00",
    ) is None


@pytest.mark.asyncio
async def test_raw_transition_cannot_bypass_pre_dispatch_no_effect_arbitration(
    prepared_inputs,
):
    _, args, prepared = await _prepared(prepared_inputs)
    store = args["effect_store"]
    values = prepared.attempt.model_dump(mode="json")
    values.update(
        state=EffectExecutionState.CONFIRMED_NO_EFFECT.value,
        revision=2,
        updated_at="2026-08-24T00:00:03+00:00",
        reason_code="FORGED_NO_EFFECT",
    )
    values.pop("record_hash")
    forged = prepared.attempt.__class__(
        **values,
        record_hash=pre.sha256_of_canonical_json(values),
    )
    assert not await store.transition(
        operation_id=prepared.attempt.operation_id,
        expected_state=EffectExecutionState.IN_FLIGHT,
        record=forged,
    )



@pytest.mark.asyncio
async def test_cancellation_during_durable_ownership_await_spends_handle_and_allows_only_recovery(
    prepared_inputs, monkeypatch,
):
    _, args, prepared = await _prepared(prepared_inputs)
    store = args["effect_store"]
    entered = asyncio.Event()
    release = asyncio.Event()
    original = store.consume_sandbox_ownership

    async def blocked(**kwargs):
        entered.set()
        await release.wait()
        return await original(**kwargs)

    monkeypatch.setattr(store, "consume_sandbox_ownership", blocked)
    task = asyncio.create_task(
        pre.consume_sandbox_ownership(prepared, effect_store=store)
    )
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert prepared.ownership_handle.state == "SPENT"
    ownership = await store.get_sandbox_ownership(prepared.attempt.operation_id)
    assert ownership is not None
    assert ownership.state == SandboxOwnershipState.AVAILABLE

    with pytest.raises(pre.SandboxPreEffectError, match="SEO_HANDLE_ALREADY_SPENT"):
        await pre.consume_sandbox_ownership(prepared, effect_store=store)

    terminal = await store.confirm_pre_dispatch_no_effect(
        expected=prepared.attempt,
        updated_at="2026-08-24T00:00:04+00:00",
    )
    assert terminal is not None
    assert terminal.state == EffectExecutionState.CONFIRMED_NO_EFFECT
    ownership = await store.get_sandbox_ownership(prepared.attempt.operation_id)
    assert ownership is not None
    assert ownership.state == SandboxOwnershipState.CANCELLED



@pytest.mark.asyncio
async def test_generic_or_raw_caller_cannot_originate_sandbox_security_provenance(
    prepared_inputs,
):
    _, args, _ = await _prepared(prepared_inputs)
    # Use a fresh store/operation because _prepared already claimed the fixture operation.
    _, fresh_args = await _args(prepared_inputs)
    record = prepared_inputs[2]
    store = fresh_args["effect_store"]
    # Semantic sandbox origin rejects any caller that lacks the private capability.
    with pytest.raises(BindEffectStateError, match="BES_SANDBOX_ORIGIN_AUTHORITY_REQUIRED"):
        await store.create_sandbox_pre_dispatch_attempt(
            consumption=record,
            updated_at=record.consumed_at,
            business_event_key="sandbox-business-event:v1:sha256:" + "a" * 64,
            ownership_digest="b" * 64,
            origin_authority=object(),
        )

    forged = _build_record(
        consumption=record,
        state=EffectExecutionState.IN_FLIGHT,
        revision=1,
        updated_at=record.consumed_at,
        reason_code="FORGED_SANDBOX_ORIGIN",
        effect_provenance=EffectProvenance.SANDBOX_PRE_DISPATCH_V1,
    )
    with pytest.raises(BindEffectStateError, match="BES_RAW_SANDBOX_ORIGIN_FORBIDDEN"):
        await store.create_in_flight(forged)
