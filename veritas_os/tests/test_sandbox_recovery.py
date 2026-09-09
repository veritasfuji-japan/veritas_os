"""Automatic sandbox recovery composes durable state without redispatch."""

import json

import pytest

from veritas_os.policy import sandbox_recovery as module
from veritas_os.policy import sandbox_reconciliation as reconciliation
from veritas_os.policy.trusted_https_reconciliation import ApprovedReconciliationVerifier
from veritas_os.tests.test_sandbox_action_binding import PAYLOAD
from veritas_os.tests.test_sandbox_pre_effect import (
    _args as pre_effect_args,
    _prepare,
    prepared_inputs,
)
from veritas_os.tests.test_sandbox_reconciliation import (
    ReaderProvider,
    setup_case,
)

pytestmark = pytest.mark.slow


class BombProvider:
    async def describe(self, request):
        pytest.fail("recovery touched reader provider before EFFECT_UNKNOWN")

    async def resolve(self, request, *, expected_metadata_digest):
        pytest.fail("recovery resolved a credential before EFFECT_UNKNOWN")


def _reader_args(args):
    reader = reconciliation.SandboxReaderPolicy(
        "separate-reader",
        "reader-v1",
        "synthetic",
        "sandbox",
    )
    args["reader_policy"] = reader
    args["verifier_policy"] = reconciliation.ReconciliationVerifierPolicy(
        (
            ApprovedReconciliationVerifier(
                reconciliation.VERIFIER_ID,
                reconciliation.sandbox_reconciliation_policy_hash(
                    args["deployment"],
                    reader,
                ),
            ),
        )
    )
    return args


async def _pre_dispatch_case(prepared_inputs):
    artifact, args = await pre_effect_args(prepared_inputs)
    await _prepare(artifact, args)
    args["historical_governance_inputs"] = args.pop("governance_inputs")
    args.pop("load_current_inputs")
    args["provider"] = BombProvider()
    _reader_args(args)
    return artifact, args


async def _recover(artifact, args):
    return await module.recover_sandbox_attempt(
        artifact,
        json.dumps(PAYLOAD),
        **args,
    )


@pytest.mark.asyncio
async def test_pre_dispatch_crash_closes_no_effect_without_reader_or_resend(prepared_inputs):
    artifact, args = await _pre_dispatch_case(prepared_inputs)
    operation_id = prepared_inputs[2].consumption_id
    before = await args["effect_store"].get(operation_id)
    assert before is not None
    assert before.state == module.EffectExecutionState.IN_FLIGHT
    assert before.reason_code == "SANDBOX_PRE_EFFECT_ATTEMPT_CLAIMED"

    result = await _recover(artifact, args)
    assert result.recovery_status == "CONFIRMED_NO_EFFECT"
    assert result.state == module.EffectExecutionState.CONFIRMED_NO_EFFECT
    assert result.external_effect_retry_permitted is False
    assert result.receipt_bundle is None

    stored = await args["effect_store"].get(operation_id)
    assert stored is not None
    assert stored.state == module.EffectExecutionState.CONFIRMED_NO_EFFECT
    assert stored.reason_code == "SANDBOX_RECOVERY_PRE_DISPATCH_CONFIRMED_NO_EFFECT"

    # Idempotent restart: terminal no-effect is returned without any reader access.
    repeated = await _recover(artifact, args)
    assert repeated == result


@pytest.mark.asyncio
async def test_lost_no_effect_transition_ack_is_recovered_from_durable_read(prepared_inputs, monkeypatch):
    artifact, args = await _pre_dispatch_case(prepared_inputs)
    store = args["effect_store"]
    original = store.transition

    async def lost_ack(**kwargs):
        changed = await original(**kwargs)
        if changed:
            raise RuntimeError("synthetic acknowledgement loss")
        return changed

    monkeypatch.setattr(store, "transition", lost_ack)
    result = await _recover(artifact, args)
    assert result.recovery_status == "CONFIRMED_NO_EFFECT"
    assert (await store.get(result.operation_id)).state == module.EffectExecutionState.CONFIRMED_NO_EFFECT


@pytest.mark.asyncio
async def test_unexpected_in_flight_lineage_fails_closed(prepared_inputs):
    artifact, args = await _pre_dispatch_case(prepared_inputs)
    operation_id = prepared_inputs[2].consumption_id
    current = await args["effect_store"].get(operation_id)
    args["effect_store"]._records[operation_id] = current.model_copy(
        update={"reason_code": "UNTRUSTED_PRE_DISPATCH_REASON"},
    )

    with pytest.raises(module.SandboxRecoveryError, match="NO_EFFECT_RETRY"):
        await _recover(artifact, args)
    assert (await args["effect_store"].get(operation_id)).state == module.EffectExecutionState.IN_FLIGHT


@pytest.mark.asyncio
async def test_lookup_absence_remains_unknown_and_never_posts(prepared_inputs, monkeypatch):
    artifact, args, current, writer, calls = await setup_case(
        prepared_inputs,
        monkeypatch,
        status=404,
    )
    result = await _recover(artifact, args)

    assert result.recovery_status == "STILL_UNKNOWN"
    assert result.state == module.EffectExecutionState.EFFECT_UNKNOWN
    assert result.external_effect_retry_permitted is False
    assert result.receipt_bundle is None
    assert await args["effect_store"].get(current.operation_id) == current
    assert len(writer.writes) == 1
    assert writer.writes[0].startswith(b"GET ")
    assert b"POST" not in writer.writes[0]


@pytest.mark.asyncio
async def test_unknown_to_confirmed_effect_publishes_once_and_restart_does_not_lookup(
    prepared_inputs,
    monkeypatch,
):
    artifact, args, current, writer, calls = await setup_case(
        prepared_inputs,
        monkeypatch,
        status=200,
    )
    provider = args["provider"]

    result = await _recover(artifact, args)
    assert result.recovery_status == "CONFIRMED_EFFECT"
    assert result.state == module.EffectExecutionState.CONFIRMED_EFFECT
    assert result.receipt_bundle is not None
    assert result.receipt_bundle.bind_receipt["final_outcome"] == "COMMITTED"
    assert result.receipt_bundle.outcome_receipt["final_outcome"] == "COMMITTED"
    assert len(writer.writes) == 1
    assert writer.writes[0].startswith(b"GET ")
    assert b"POST" not in writer.writes[0]
    provider_calls = len(provider.calls)

    # Restart/lost receipt acknowledgement recovery uses stored archive/pair only.
    repeated = await _recover(artifact, args)
    assert repeated == result
    assert len(writer.writes) == 1
    assert len(provider.calls) == provider_calls


@pytest.mark.asyncio
async def test_in_memory_requires_explicit_test_opt_in(prepared_inputs):
    artifact, args = await _pre_dispatch_case(prepared_inputs)
    args["allow_in_memory_for_testing"] = False

    with pytest.raises(module.SandboxRecoveryError):
        await _recover(artifact, args)
