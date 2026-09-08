"""Inert dispatch seam with real native verification; never accesses a network."""

import asyncio
from dataclasses import replace
import json
import traceback

import pytest

from veritas_os.policy import sandbox_bind_execution as module
from veritas_os.tests.test_sandbox_action_binding import PAYLOAD
from veritas_os.tests.test_sandbox_pre_effect import (
    issued as issued_fixture, prepared_inputs as prepared_inputs_fixture, _args,
)
from veritas_os.tests.test_sandbox_credential_resolution_integration import Provider
from veritas_os.tests.test_sandbox_credential_resolution import TOKEN
from veritas_os.tests.test_native_bind_authorization_consumption import _Revocation

pytestmark = pytest.mark.slow
issued = issued_fixture
prepared_inputs = prepared_inputs_fixture


class Transport:
    """Records only a synthetic send, after asserting durable intent."""

    def __init__(self, args, mode="valid"):
        self.args = args
        self.mode = mode
        self.calls = []
        self.sent = []

    async def send_once(self, request, *, take_material):
        self.calls.append(request)
        self.take_material = take_material
        row = await self.args["effect_store"].get(request.attempt_id)
        assert row.state == module.EffectExecutionState.EFFECT_UNKNOWN
        assert row.reason_code == "SANDBOX_DISPATCH_INTENT_PERSISTED_EFFECT_UNCONFIRMED"
        if self.mode == "no_take":
            return
        if self.mode == "late":
            clock = self.args["trusted_clock"]()
            self.args["clock_cell"][0] = replace(clock, monotonic_seconds=clock.monotonic_seconds + 1.01)
        assert take_material().get_secret_value() == TOKEN
        self.sent.append(request)
        if self.mode == "twice":
            take_material()
        if self.mode == "error":
            raise RuntimeError(TOKEN.decode())
        if self.mode == "cancel":
            raise asyncio.CancelledError(TOKEN.decode())
        if self.mode == "timeout":
            await asyncio.Event().wait()


async def run(artifact, args, provider, transport):
    return await module.execute_sandbox_bind(
        artifact, json.dumps(PAYLOAD), provider=provider, transport=transport,
        **{key: value for key, value in args.items() if key != "clock_cell"},
    )


@pytest.mark.asyncio
async def test_exact_request_is_sent_once_but_never_claims_success(prepared_inputs):
    artifact, args = await _args(prepared_inputs)
    provider, transport = Provider(prepared_inputs, args), Transport(args)
    result = await run(artifact, args, provider, transport)
    assert result.state == "UNKNOWN"
    assert result.reason_code == "TRANSPORT_RETURNED_UNVERIFIED"
    assert len(transport.sent) == 1
    request = transport.sent[0]
    assert request.idempotency_key == artifact.idempotency_key
    assert request.endpoint_url == args["deployment"].endpoint_url
    assert json.loads(request.payload_json) == PAYLOAD
    assert module.SandboxDispatchRequest.model_validate_json(request.model_dump_json()) == request
    assert module.SandboxDispatchObservation.model_validate_json(result.model_dump_json()) == result
    assert TOKEN.decode() not in repr(result) + result.model_dump_json() + request.model_dump_json()
    with pytest.raises(module.SandboxBindExecutionError):
        transport.take_material()
    with pytest.raises(module.SandboxBindExecutionError):
        await run(artifact, args, provider, transport)
    assert len(transport.sent) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["error", "twice", "no_take", "timeout", "late"])
async def test_transport_ambiguity_remains_unknown_without_resend(prepared_inputs, mode, monkeypatch, caplog):
    artifact, args = await _args(prepared_inputs)
    cell = [prepared_inputs[4]]
    args.update(trusted_clock=lambda: cell[0], clock_cell=cell)
    provider, transport = Provider(prepared_inputs, args), Transport(args, mode)
    if mode == "timeout":
        monkeypatch.setattr(module, "REQUEST_TIMEOUT_SECONDS", 0.01)
    result = await run(artifact, args, provider, transport)
    assert result.reason_code == "TRANSPORT_FAILED_OR_UNKNOWN"
    assert result.state == "UNKNOWN"
    assert len(transport.calls) == 1
    assert len(transport.sent) == (0 if mode in {"no_take", "late"} else 1)
    assert TOKEN.decode() not in result.model_dump_json() + caplog.text
    row = await args["effect_store"].get(result.attempt_id)
    assert row.state == module.EffectExecutionState.EFFECT_UNKNOWN


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["lost_ack", "cas_false", "readback_changed", "slow_commit", "clock_rollback"])
async def test_intent_persistence_failure_never_enters_transport(prepared_inputs, mode, monkeypatch):
    artifact, args = await _args(prepared_inputs)
    cell = [prepared_inputs[4]]
    args["trusted_clock"] = lambda: cell[0]
    provider, transport = Provider(prepared_inputs, args), Transport(args)
    store = args["effect_store"]
    transition = store.transition

    async def commit(**kwargs):
        if mode == "cas_false":
            return False
        result = await transition(**kwargs)
        if mode == "lost_ack":
            raise RuntimeError(TOKEN.decode())
        if mode == "readback_changed":
            row = kwargs["record"]
            store._records[row.operation_id] = row.model_copy(update={"reason_code": "changed"})
        if mode in {"slow_commit", "clock_rollback"}:
            delta = 1.01 if mode == "slow_commit" else -0.01
            cell[0] = replace(cell[0], monotonic_seconds=cell[0].monotonic_seconds + delta)
        return result

    monkeypatch.setattr(store, "transition", commit)
    with pytest.raises(module.SandboxBindExecutionError) as caught:
        await run(artifact, args, provider, transport)
    assert caught.value.__context__ is None
    assert TOKEN.decode() not in "".join(traceback.format_exception(caught.value))
    assert not transport.calls
    assert await args["consumption_store"].get(artifact.authorization_id) == prepared_inputs[2]
    assert await store.get(prepared_inputs[2].consumption_id) is not None


@pytest.mark.asyncio
async def test_cancel_after_possible_send_retains_unknown_and_sanitizes(prepared_inputs):
    artifact, args = await _args(prepared_inputs)
    transport = Transport(args, "cancel")
    with pytest.raises(asyncio.CancelledError) as caught:
        await run(artifact, args, Provider(prepared_inputs, args), transport)
    assert not caught.value.args and caught.value.__context__ is None
    row = await args["effect_store"].get(prepared_inputs[2].consumption_id)
    assert row.state == module.EffectExecutionState.EFFECT_UNKNOWN
    with pytest.raises(ValueError):
        transport.take_material()


@pytest.mark.asyncio
async def test_competing_executors_only_one_can_dispatch(prepared_inputs):
    artifact, args = await _args(prepared_inputs)
    provider, transport = Provider(prepared_inputs, args), Transport(args)
    results = await asyncio.gather(
        run(artifact, args, provider, transport), run(artifact, args, provider, transport),
        return_exceptions=True,
    )
    assert sum(isinstance(x, module.SandboxDispatchObservation) for x in results) == 1
    assert sum(isinstance(x, module.SandboxBindExecutionError) for x in results) == 1
    assert len(transport.sent) == 1
    assert len(provider.calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["revoked", "contract", "endpoint", "scope"])
async def test_final_recheck_drift_stops_before_intent(prepared_inputs, mode):
    artifact, args = await _args(prepared_inputs)
    original = args["load_current_inputs"]
    count = 0

    def load(now):
        nonlocal count
        count += 1
        current = original(now)
        if count == 4:
            if mode == "revoked":
                current = replace(current, governance=replace(current.governance,
                    authority_revocation_checker=_Revocation(current.governance, "revoked")))
            elif mode == "contract":
                contract = replace(current.governance.action_contract, human_approval_rules={"required": True})
                current = replace(current, governance=replace(current.governance, action_contract=contract))
            elif mode == "endpoint":
                current = replace(current, source=replace(current.source, current_endpoint={}))
            else:
                current = replace(current, source=replace(current.source, required_credential_scope="admin"))
        return current

    args["load_current_inputs"] = load
    provider, transport = Provider(prepared_inputs, args), Transport(args)
    with pytest.raises(module.SandboxBindExecutionError):
        await run(artifact, args, provider, transport)
    assert len(provider.calls) == 2 and count == 4
    assert not transport.calls
    row = await args["effect_store"].get(prepared_inputs[2].consumption_id)
    assert row.state == module.EffectExecutionState.IN_FLIGHT


@pytest.mark.asyncio
async def test_missing_transport_stops_before_claim_or_provider(prepared_inputs):
    artifact, args = await _args(prepared_inputs)
    provider = Provider(prepared_inputs, args)
    with pytest.raises(module.SandboxBindExecutionError):
        await run(artifact, args, provider, None)
    assert not provider.calls and not args["effect_store"]._records
