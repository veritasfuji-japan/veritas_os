"""Real native verification, durable-claim semantics and no-effect failures."""

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json

import pytest

from veritas_os.policy import sandbox_pre_effect as module
from veritas_os.policy.native_bind_authorization_consumption import consume_native_bind_authorization
from veritas_os.security.hash import sha256_of_canonical_json
from veritas_os.tests.test_native_bind_authorization_consumption import _fresh, _Revocation
from veritas_os.tests.test_sandbox_action_binding_integration import issued as issued_fixture
from veritas_os.tests.test_sandbox_action_binding import PAYLOAD, deployment

pytestmark = pytest.mark.slow
issued = issued_fixture


@pytest.fixture(scope="module")
def prepared_inputs(issued):
    artifact, inputs = issued
    consumed_at = inputs["governance_inputs"].verification_now + timedelta(seconds=1)
    risk, source = _fresh(inputs, consumed_at)
    store = module.InMemoryAtomicAuthorizationConsumptionStore()
    result = asyncio.run(consume_native_bind_authorization(
        artifact, issuance_source_inputs=inputs["source_inputs"],
        governance_inputs=inputs["governance_inputs"], trust_inputs=inputs["trust_inputs"],
        current_source_inputs=source, current_runtime_risk_packet=risk, now=consumed_at,
        consumption_store=store, allow_in_memory_for_testing=True,
    ))
    now = consumed_at + timedelta(seconds=1)
    risk, source = _fresh(inputs, now)
    snapshot = module.SandboxCurrentInputs(source, inputs["governance_inputs"], risk)
    clock = module.SandboxClockReading(now, 100.0, now, 0.0)
    return artifact, inputs, result.consumption_record, snapshot, clock


async def _args(prepared_inputs):
    artifact, inputs, record, current, clock = prepared_inputs
    store = module.InMemoryAtomicAuthorizationConsumptionStore()
    assert await store.consume_once(record)
    return artifact, dict(
        deployment=deployment(), issuance_source_inputs=inputs["source_inputs"],
        governance_inputs=inputs["governance_inputs"], trust_inputs=inputs["trust_inputs"],
        consumption_store=store, effect_store=module.InMemoryAtomicEffectStateStore(),
        trusted_clock=lambda: clock, load_current_inputs=lambda now: current,
        allow_in_memory_for_testing=True,
    )


async def _prepare(artifact, args):
    return await module.prepare_sandbox_attempt(artifact, json.dumps(PAYLOAD), **args)


@pytest.mark.asyncio
async def test_claim_and_current_checks_are_ordered_and_cannot_be_replayed(prepared_inputs):
    artifact, args = await _args(prepared_inputs)
    record, current = prepared_inputs[2:4]
    store = args["effect_store"]

    def load(now):
        assert store._records[record.consumption_id].state == module.EffectExecutionState.IN_FLIGHT
        return current

    args["load_current_inputs"] = load
    result = await _prepare(artifact, args)
    assert result.binding.idempotency_key == artifact.idempotency_key
    assert result.attempt == await store.get(record.consumption_id)
    assert result.runtime_risk_hash == current.runtime_risk_packet.packet_hash
    assert not result.durable_store_used
    with pytest.raises(module.SandboxPreEffectError, match="ATTEMPT_ALREADY_EXISTS"):
        await _prepare(artifact, args)
    assert await args["consumption_store"].get(artifact.authorization_id) == record


@pytest.mark.asyncio
async def test_competing_workers_have_one_prepared_attempt(prepared_inputs):
    artifact, args = await _args(prepared_inputs)
    results = await asyncio.gather(*(_prepare(artifact, args) for _ in range(4)), return_exceptions=True)
    assert sum(isinstance(x, module.SandboxPreparedAttempt) for x in results) == 1
    assert sum(isinstance(x, module.SandboxPreEffectError) for x in results) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [
    ("consumption_hash", "0" * 64), ("idempotency_key", "other"),
    ("live_adapter_bind_authorization_hash", "a" * 64),
    ("bind_context_hash", "b" * 64), ("execution_intent_hash", "c" * 64),
    ("credential_reference_digest", "changed"), ("single_use_enforced", False),
    ("consumption_state", "NOT_CONSUMED"),
])
async def test_stored_lineage_is_reconstructed_not_trusted_by_hash(prepared_inputs, field, value):
    artifact, args = await _args(prepared_inputs)
    record = prepared_inputs[2].model_copy(update={field: value})
    if field != "consumption_hash":
        body = record.model_dump(mode="json", exclude={"consumption_id", "consumption_hash"})
        digest = sha256_of_canonical_json(body)
        record = record.model_copy(update={
            "consumption_hash": digest, "consumption_id": f"labac:v1:sha256:{digest}",
        })
    args["consumption_store"]._by_authorization_id[artifact.authorization_id] = record
    with pytest.raises(module.SandboxPreEffectError, match="LINEAGE_MISMATCH"):
        await _prepare(artifact, args)
    assert not args["effect_store"]._records


@pytest.mark.asyncio
async def test_missing_consumption_is_not_replaced_by_caller_claim(prepared_inputs):
    artifact, args = await _args(prepared_inputs)
    args["consumption_store"] = module.InMemoryAtomicAuthorizationConsumptionStore()
    with pytest.raises(module.SandboxPreEffectError, match="CONSUMPTION_REQUIRED"):
        await _prepare(artifact, args)
    assert not args["effect_store"]._records


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["contract", "endpoint", "scope", "revoked", "stale_risk", "provider_error"])
async def test_post_claim_drift_stops_and_preserves_attempt(prepared_inputs, mode):
    artifact, args = await _args(prepared_inputs)
    _, inputs, record, current, _ = prepared_inputs
    if mode == "contract":
        contract = replace(current.governance.action_contract, human_approval_rules={"required": True})
        current = replace(current, governance=replace(current.governance, action_contract=contract))
    elif mode == "endpoint":
        current = replace(current, source=replace(current.source, current_endpoint={}))
    elif mode == "scope":
        current = replace(current, source=replace(current.source, required_credential_scope="admin"))
    elif mode == "revoked":
        current = replace(current, governance=replace(current.governance,
            authority_revocation_checker=_Revocation(current.governance, "revoked")))
    elif mode == "stale_risk":
        current = replace(current, source=inputs["source_inputs"], runtime_risk_packet=artifact.source_runtime_risk_packet)

    def load(now):
        if mode == "provider_error":
            raise RuntimeError("secret-provider-detail")
        return current

    args["load_current_inputs"] = load
    with pytest.raises(module.SandboxPreEffectError, match="^SPE_RECHECK_FAILED_ATTEMPT_RETAINED$"):
        await _prepare(artifact, args)
    assert await args["effect_store"].get(record.consumption_id) is not None
    with pytest.raises(module.SandboxPreEffectError, match="ATTEMPT_ALREADY_EXISTS"):
        await _prepare(artifact, args)


@pytest.mark.asyncio
async def test_lost_claim_acknowledgement_never_returns_prepared_result(prepared_inputs, monkeypatch):
    artifact, args = await _args(prepared_inputs)
    store = args["effect_store"]
    create = store.create_in_flight

    async def lost(record):
        await create(record)
        raise RuntimeError("secret-dsn")

    monkeypatch.setattr(store, "create_in_flight", lost)
    with pytest.raises(module.SandboxPreEffectError, match="^SPE_CLAIM_FAILED_OR_UNKNOWN$"):
        await _prepare(artifact, args)
    assert await store.get(prepared_inputs[2].consumption_id) is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["rollback", "monotonic_rollback", "slow", "unhealthy", "expiry"])
async def test_clock_failure_after_claim_retains_attempt(prepared_inputs, mode):
    artifact, args = await _args(prepared_inputs)
    clock = prepared_inputs[4]
    changed = clock
    if mode == "rollback":
        changed = replace(clock, now=clock.now - timedelta(seconds=1), health_checked_at=clock.now - timedelta(seconds=1))
    elif mode == "monotonic_rollback":
        changed = replace(clock, monotonic_seconds=99)
    elif mode == "slow":
        changed = replace(clock, monotonic_seconds=102)
    elif mode == "unhealthy":
        changed = replace(clock, uncertainty_seconds=2)
    else:
        changed = replace(clock, now=clock.now + timedelta(hours=1))
    readings = iter([clock, clock, changed])
    args["trusted_clock"] = lambda: next(readings)
    with pytest.raises(module.SandboxPreEffectError, match="RECHECK_FAILED_ATTEMPT_RETAINED"):
        await _prepare(artifact, args)
    assert await args["effect_store"].get(prepared_inputs[2].consumption_id) is not None


@pytest.mark.asyncio
async def test_non_durable_stores_rejected_by_default(prepared_inputs):
    artifact, args = await _args(prepared_inputs)
    args["allow_in_memory_for_testing"] = False
    with pytest.raises(module.SandboxPreEffectError, match="DURABLE_STORES_REQUIRED"):
        await _prepare(artifact, args)


@pytest.mark.parametrize("field,value", [
    ("monotonic_seconds", float("nan")), ("monotonic_seconds", -1),
    ("monotonic_seconds", True), ("uncertainty_seconds", float("inf")),
    ("uncertainty_seconds", -0.1), ("uncertainty_seconds", 1.01),
    ("health_checked_at", datetime(2026, 1, 1, tzinfo=timezone.utc)),
    ("health_checked_at", datetime(2026, 1, 3, tzinfo=timezone.utc)),
])
def test_unhealthy_clock_samples_reject(field, value):
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    sample = module.SandboxClockReading(now, 1.0, now, 0.1)
    with pytest.raises(ValueError):
        module._clock(replace(sample, **{field: value}))


def test_missing_clock_sample_rejects():
    with pytest.raises(ValueError):
        module._clock(None)


@pytest.mark.asyncio
async def test_postgres_read_errors_are_sanitized(monkeypatch):
    from veritas_os.storage import db

    async def failed():
        raise RuntimeError("secret-database-url")

    monkeypatch.setattr(db, "get_pool", failed)
    with pytest.raises(RuntimeError, match="^LABAC_POSTGRES_CONSUMPTION_READ_FAILED$"):
        await module.PostgresAtomicAuthorizationConsumptionStore().get("authorization")
