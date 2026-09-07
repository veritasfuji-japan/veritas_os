"""Native consume-only tests with real source and Ed25519 verifiers."""

import asyncio
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta

import pytest

from veritas_os.policy import native_bind_authorization_consumption as module
from veritas_os.policy.promotion_requirement_runtime_risk import (
    build_promotion_requirement_runtime_risk_packet,
)
from veritas_os.tests.test_native_bind_authorization import (
    issued as issued_fixture,
    api_risk_source as source_fixture,
)

pytestmark = pytest.mark.slow
issued = issued_fixture
api_risk_source = source_fixture


def _fresh(inputs, now, **changes):
    src = inputs["source_inputs"]
    gov = inputs["governance_inputs"]
    decision = {**src.expected_risk_decision, "reviewed_at": now.isoformat(), **changes}
    risk = build_promotion_requirement_runtime_risk_packet(
        src.final_recheck,
        decision,
        now,
        expected_source=gov.expected_source,
        expected_contract=gov.action_contract,
        expected_verified_at=src.expected_verified_at,
        expected_rechecked_at=src.expected_rechecked_at,
        current_endpoint=src.current_endpoint,
        current_credential_reference=src.current_credential_reference,
        required_credential_scope=src.required_credential_scope,
    )
    return risk, replace(src, expected_risk_decision=decision, expected_recorded_at=now)


@pytest.fixture(scope="module")
def consumable(issued):
    artifact, inputs, *_ = issued
    now = inputs["governance_inputs"].verification_now + timedelta(seconds=1)
    risk, source = _fresh(inputs, now)
    return (
        artifact,
        dict(
            issuance_source_inputs=inputs["source_inputs"],
            governance_inputs=inputs["governance_inputs"],
            trust_inputs=inputs["trust_inputs"],
            current_source_inputs=source,
            current_runtime_risk_packet=risk,
            now=now,
        ),
        inputs,
    )


def _store_inputs(inputs):
    store = module.InMemoryAtomicAuthorizationConsumptionStore()
    return store, {
        **inputs,
        "consumption_store": store,
        "allow_in_memory_for_testing": True,
    }


class _Revocation:
    def __init__(self, gov, mode="valid"):
        self.original = gov.authority_revocation_checker
        self.issued_at = gov.verification_now
        self.mode = mode
        self.times = []

    def check(self, evidence_id, *, now):
        self.times.append(now)
        result = self.original.check(evidence_id, now=now)
        if now <= self.issued_at:
            return result
        if self.mode == "revoked":
            return replace(result, revoked=True)
        if self.mode == "stale":
            return replace(result, checked_at=(now - timedelta(seconds=61)).isoformat())
        if self.mode == "unavailable":
            raise ValueError("fixture: revocation unavailable")
        return result


@pytest.mark.asyncio
async def test_consume_once_preserves_signed_proofs_and_rechecks_current_governance(
    consumable,
):
    artifact, original, _ = consumable
    before = artifact.model_dump(mode="json")
    checker = _Revocation(original["governance_inputs"])
    store, inputs = _store_inputs(original)
    inputs["governance_inputs"] = replace(
        inputs["governance_inputs"], authority_revocation_checker=checker
    )
    result = await module.consume_native_bind_authorization(artifact, **inputs)
    assert checker.times == [
        inputs["governance_inputs"].verification_now,
        inputs["now"],
    ]
    assert (
        result.authorization.model_dump(mode="json")
        == before
        == artifact.model_dump(mode="json")
    )
    assert (
        result.current_authority_proof_digest
        != artifact.authority_verification_proof_digest
    )
    assert result.consumption_record == await store.get(artifact.authorization_id)
    assert result.consumption_record.idempotency_key == artifact.idempotency_key
    assert result.authorization_consumed and not result.durable_store_used
    assert (
        result.current_runtime_risk_hash
        == original["current_runtime_risk_packet"].packet_hash
    )
    for name in (
        "execution_authority_created",
        "credential_material_accessed",
        "bind_invoked",
        "bind_receipt_created",
        "external_action_executed",
    ):
        assert getattr(result, name) is False
    with pytest.raises(ValueError, match="NABC_ALREADY_CONSUMED"):
        await module.consume_native_bind_authorization(artifact, **inputs)


@pytest.mark.asyncio
async def test_four_parallel_consumers_have_one_winner(consumable):
    artifact, original, _ = consumable
    _, inputs = _store_inputs(original)
    outcomes = await asyncio.gather(
        *(
            module.consume_native_bind_authorization(artifact, **inputs)
            for _ in range(4)
        ),
        return_exceptions=True,
    )
    assert (
        sum(
            isinstance(x, module.NativeAuthorizationConsumptionResult) for x in outcomes
        )
        == 1
    )
    assert (
        sum(isinstance(x, module.NativeAuthorizationConsumptionError) for x in outcomes)
        == 3
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["revoked", "stale", "unavailable"])
async def test_changed_revocation_rejects_before_store(consumable, mode):
    artifact, original, _ = consumable
    store, inputs = _store_inputs(original)
    checker = _Revocation(inputs["governance_inputs"], mode)
    inputs["governance_inputs"] = replace(
        inputs["governance_inputs"], authority_revocation_checker=checker
    )
    with pytest.raises(ValueError):
        await module.consume_native_bind_authorization(artifact, **inputs)
    assert inputs["now"] in checker.times
    assert await store.get(artifact.authorization_id) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["negative", "missing", "drift", "issuance_review"])
async def test_current_risk_is_independent_and_fresh(consumable, mode):
    artifact, original, issuance = consumable
    store, inputs = _store_inputs(original)
    if mode == "issuance_review":
        inputs["current_source_inputs"] = issuance["source_inputs"]
        inputs["current_runtime_risk_packet"] = artifact.source_runtime_risk_packet
    else:
        changes = (
            {"observed_state_fingerprint": "different"}
            if mode == "drift"
            else {"runtime_risk_signal": False if mode == "negative" else None}
        )
        risk, source = _fresh(issuance, inputs["now"], **changes)
        inputs.update(current_runtime_risk_packet=risk, current_source_inputs=source)
    with pytest.raises(ValueError):
        await module.consume_native_bind_authorization(artifact, **inputs)
    assert await store.get(artifact.authorization_id) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode", ["backdated", "naive", "expired", "contract", "endpoint", "tampered"]
)
async def test_invalid_clock_or_context_never_consumes(consumable, mode):
    artifact, original, _ = consumable
    store, inputs = _store_inputs(original)
    if mode == "backdated":
        inputs["now"] = inputs["governance_inputs"].verification_now - timedelta(
            seconds=1
        )
    elif mode == "naive":
        inputs["now"] = inputs["now"].replace(tzinfo=None)
    elif mode == "expired":
        inputs["now"] = artifact.valid_until
    elif mode == "contract":
        contract = deepcopy(inputs["governance_inputs"].action_contract)
        contract.human_approval_rules["required"] = not contract.human_approval_rules[
            "required"
        ]
        inputs["governance_inputs"] = replace(
            inputs["governance_inputs"], action_contract=contract
        )
    elif mode == "endpoint":
        inputs["current_source_inputs"] = replace(
            inputs["current_source_inputs"], current_endpoint={}
        )
    else:
        artifact = artifact.model_copy(update={"bind_context_hash": "0" * 64})
    with pytest.raises(ValueError):
        await module.consume_native_bind_authorization(artifact, **inputs)
    assert await store.get(artifact.authorization_id) is None


@pytest.mark.asyncio
async def test_memory_store_is_not_production_default(consumable):
    artifact, original, _ = consumable
    store, inputs = _store_inputs(original)
    inputs["allow_in_memory_for_testing"] = False
    with pytest.raises(ValueError, match="NABC_DURABLE_STORE_REQUIRED"):
        await module.consume_native_bind_authorization(artifact, **inputs)
    assert await store.get(artifact.authorization_id) is None


@pytest.mark.asyncio
async def test_lost_store_acknowledgement_never_releases_consumption(
    consumable, monkeypatch
):
    artifact, original, _ = consumable
    store, inputs = _store_inputs(original)
    real_consume = store.consume_once

    async def lost_ack(record):
        await real_consume(record)
        raise RuntimeError("sensitive-backend-detail")

    monkeypatch.setattr(store, "consume_once", lost_ack)
    with pytest.raises(ValueError, match="^NABC_STORE_FAILED_OR_UNKNOWN$"):
        await module.consume_native_bind_authorization(artifact, **inputs)
    assert await store.get(artifact.authorization_id) is not None
    monkeypatch.setattr(store, "consume_once", real_consume)
    with pytest.raises(ValueError, match="NABC_ALREADY_CONSUMED"):
        await module.consume_native_bind_authorization(artifact, **inputs)


@pytest.mark.asyncio
async def test_human_signature_trust_is_rechecked_at_consumption(consumable):
    artifact, original, _ = consumable
    store, inputs = _store_inputs(original)
    gov = inputs["governance_inputs"]
    checker = _Revocation(gov)
    calls = []

    class WithdrawnVerifier:
        def verify(self, envelope):
            calls.append(checker.times[-1])
            result = gov.human_approval_signature_verifier.verify(envelope)
            if checker.times[-1] == inputs["now"]:
                return replace(result, verified=False)
            return result

    inputs["governance_inputs"] = replace(
        gov,
        authority_revocation_checker=checker,
        human_approval_signature_verifier=WithdrawnVerifier(),
    )
    if gov.signed_human_approval_artifact is None:
        await module.consume_native_bind_authorization(artifact, **inputs)
        assert calls == []
    else:
        with pytest.raises(ValueError, match="HUMAN_APPROVAL_VERIFICATION_FAILED"):
            await module.consume_native_bind_authorization(artifact, **inputs)
        assert calls == [gov.verification_now, inputs["now"]]
        assert await store.get(artifact.authorization_id) is None


@pytest.mark.asyncio
async def test_store_cannot_self_assert_production_safety(consumable):
    artifact, inputs, _ = consumable

    class FakeStore:
        production_safe = True

        async def consume_once(self, record):
            pytest.fail("unrecognized store must not be called")

    with pytest.raises(ValueError, match="NABC_DURABLE_STORE_REQUIRED"):
        await module.consume_native_bind_authorization(
            artifact, **inputs, consumption_store=FakeStore()
        )


@pytest.mark.asyncio
async def test_valid_new_gate_cannot_replace_authorized_context(consumable):
    """A fully rebuilt PASS for another gate is not this authorization."""
    from veritas_os.tests.test_promotion_requirement_final_rechecks import _complete

    artifact, original, issuance = consumable
    gov = original["governance_inputs"]
    changed_time = issuance["source_inputs"].expected_verified_at + timedelta(seconds=1)
    _, _, final, _ = _complete(gov.expected_source, gov.action_contract, changed_time)
    assert final.bind_context_hash != artifact.bind_context_hash
    source = replace(
        issuance["source_inputs"],
        final_recheck=final,
        expected_verified_at=changed_time,
        expected_rechecked_at=changed_time,
        expected_risk_decision={
            **issuance["source_inputs"].expected_risk_decision,
            "source_final_recheck_id": final.packet_id,
            "source_final_recheck_hash": final.packet_hash,
            "bind_context_hash": final.bind_context_hash,
        },
    )
    risk, current_source = _fresh(
        {**issuance, "source_inputs": source}, original["now"]
    )
    store, inputs = _store_inputs(original)
    inputs.update(
        current_source_inputs=current_source, current_runtime_risk_packet=risk
    )
    with pytest.raises(ValueError, match="NABC_CURRENT_CONTEXT_MISMATCH"):
        await module.consume_native_bind_authorization(artifact, **inputs)
    assert await store.get(artifact.authorization_id) is None
