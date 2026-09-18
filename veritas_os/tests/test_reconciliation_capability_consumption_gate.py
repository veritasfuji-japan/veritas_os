"""Policy-gated reconciliation capability proofs at authorization consumption."""

from dataclasses import replace
from datetime import timedelta

import pytest

from veritas_os.governance.reconciliation_capability_evidence import (
    ReconciliationCapabilityClass,
    ReconciliationCapabilityEvidence,
)
from veritas_os.policy import native_bind_authorization_consumption as module
from veritas_os.tests.test_native_bind_authorization import (
    api_risk_source as api_risk_source_fixture,
    issued as issued_fixture,
)
from veritas_os.tests.test_native_bind_authorization_consumption import (
    _store_inputs,
    consumable as consumable_fixture,
)

pytestmark = pytest.mark.slow
api_risk_source = api_risk_source_fixture
issued = issued_fixture
consumable = consumable_fixture

_TARGET_CONFIGURATION_DIGEST = "b" * 64
_VERIFIER_POLICY_HASH = "d" * 64


def _current_context(original):
    governance = replace(
        original["governance_inputs"],
        verification_now=original["now"],
    )
    _, _, context = module._verified_source(
        original["current_runtime_risk_packet"],
        original["current_source_inputs"],
        governance,
    )
    return context


def _evidence(
    original,
    *,
    capability_class=ReconciliationCapabilityClass.AUTHORITATIVE_QUERY,
    endpoint_digest=None,
    target_configuration_digest=_TARGET_CONFIGURATION_DIGEST,
    verifier_id="reconciliation-capability-verifier/v1",
    verifier_policy_id="reconciliation-capability-policy/v1",
    verifier_policy_hash=_VERIFIER_POLICY_HASH,
    assessed_at=None,
    valid_until=None,
):
    context = _current_context(original)
    if assessed_at is None:
        assessed_at = original["now"] - timedelta(seconds=1)
    if valid_until is None:
        valid_until = original["now"] + timedelta(minutes=5)

    authoritative_query = (
        capability_class is ReconciliationCapabilityClass.AUTHORITATIVE_QUERY
    )
    authoritative_evidence = (
        capability_class is ReconciliationCapabilityClass.AUTHORITATIVE_EVIDENCE
    )
    authoritative = authoritative_query or authoritative_evidence

    return ReconciliationCapabilityEvidence(
        evidence_id="rce-consumption-gate-001",
        target_id="payments-sandbox",
        endpoint_identity_binding_digest=(
            endpoint_digest or context.endpoint_identity_binding_digest
        ),
        target_configuration_digest=target_configuration_digest,
        capability_class=capability_class,
        correlation_identity_type="idempotency_key" if authoritative_query else None,
        correlation_identity_pre_dispatch=authoritative_query,
        correlation_identity_caller_controlled=authoritative_query,
        exact_attempt_lookup_available=authoritative_query,
        exact_lineage_binding_supported=authoritative,
        downstream_durability_supported=authoritative,
        non_mutating_observation_supported=authoritative,
        authoritative_evidence_available=authoritative_evidence,
        source_type="target_capability_assessment",
        source_identity="assessment:payments-sandbox:v1",
        source_digest="c" * 64,
        verifier_id=verifier_id if authoritative else None,
        verifier_policy_id=verifier_policy_id if authoritative else None,
        verifier_policy_hash=verifier_policy_hash if authoritative else None,
        assessed_at=assessed_at.isoformat(),
        valid_until=valid_until.isoformat(),
        metadata={"profile": "policy-gated-consumption-v1"},
    )


def _required_policy(
    evidence,
    *,
    current_target_configuration_digest=_TARGET_CONFIGURATION_DIGEST,
    expected_verifier_id="reconciliation-capability-verifier/v1",
    expected_verifier_policy_id="reconciliation-capability-policy/v1",
    expected_verifier_policy_hash=_VERIFIER_POLICY_HASH,
    expected_evidence_digest=None,
):
    return module.ReconciliationCapabilityExecutionPolicy(
        policy_id="reconciliation-required/v1",
        require_authoritative_reconciliation=True,
        current_target_configuration_digest=current_target_configuration_digest,
        expected_verifier_id=expected_verifier_id,
        expected_verifier_policy_id=expected_verifier_policy_id,
        expected_verifier_policy_hash=expected_verifier_policy_hash,
        expected_evidence_digest=(
            expected_evidence_digest or evidence.deterministic_digest()
        ),
    )


async def _assert_rejected_before_consumption(
    artifact,
    original,
    *,
    policy,
    evidence,
    expected_reason="NABC_RECONCILIATION_CAPABILITY_REJECTED",
    monkeypatch,
):
    store, inputs = _store_inputs(original)
    real_consume_once = store.consume_once
    calls = 0

    async def spy_consume_once(record):
        nonlocal calls
        calls += 1
        return await real_consume_once(record)

    monkeypatch.setattr(store, "consume_once", spy_consume_once)

    with pytest.raises(module.NativeAuthorizationConsumptionError, match=expected_reason):
        await module.consume_native_bind_authorization(
            artifact,
            **inputs,
            reconciliation_capability_policy=policy,
            reconciliation_capability_evidence=evidence,
        )

    assert calls == 0
    assert await store.get(artifact.authorization_id) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "capability_class",
    [
        ReconciliationCapabilityClass.AUTHORITATIVE_QUERY,
        ReconciliationCapabilityClass.AUTHORITATIVE_EVIDENCE,
    ],
)
async def test_required_authoritative_capability_passes_before_consumption(
    consumable,
    capability_class,
):
    artifact, original, _ = consumable
    evidence = _evidence(original, capability_class=capability_class)
    policy = _required_policy(evidence)
    store, inputs = _store_inputs(original)

    result = await module.consume_native_bind_authorization(
        artifact,
        **inputs,
        reconciliation_capability_policy=policy,
        reconciliation_capability_evidence=evidence,
    )

    assert result.authorization_consumed is True
    assert result.reconciliation_capability_required is True
    assert result.reconciliation_capability_satisfied is True
    assert result.reconciliation_capability_policy_id == policy.policy_id
    assert (
        result.reconciliation_capability_evidence_digest
        == evidence.deterministic_digest()
    )
    assert await store.get(artifact.authorization_id) == result.consumption_record
    assert result.execution_authority_created is False
    assert result.external_action_executed is False


@pytest.mark.asyncio
async def test_policy_not_requiring_capability_preserves_existing_contract(consumable):
    artifact, original, _ = consumable
    store, inputs = _store_inputs(original)
    policy = module.ReconciliationCapabilityExecutionPolicy(
        policy_id="reconciliation-optional/v1",
        require_authoritative_reconciliation=False,
    )

    result = await module.consume_native_bind_authorization(
        artifact,
        **inputs,
        reconciliation_capability_policy=policy,
    )

    assert result.authorization_consumed is True
    assert result.reconciliation_capability_required is False
    assert result.reconciliation_capability_satisfied is False
    assert result.reconciliation_capability_policy_id == policy.policy_id
    assert result.reconciliation_capability_evidence_digest is None
    assert await store.get(artifact.authorization_id) == result.consumption_record


@pytest.mark.asyncio
async def test_required_capability_missing_fails_before_consumption(
    consumable,
    monkeypatch,
):
    artifact, original, _ = consumable
    evidence = _evidence(original)
    await _assert_rejected_before_consumption(
        artifact,
        original,
        policy=_required_policy(evidence),
        evidence=None,
        expected_reason="NABC_RECONCILIATION_CAPABILITY_REQUIRED",
        monkeypatch=monkeypatch,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "capability_class",
    [
        ReconciliationCapabilityClass.HEURISTIC_ONLY,
        ReconciliationCapabilityClass.UNAVAILABLE_OR_UNVERIFIED,
    ],
)
async def test_non_authoritative_capability_fails_before_consumption(
    consumable,
    capability_class,
    monkeypatch,
):
    artifact, original, _ = consumable
    evidence = _evidence(original, capability_class=capability_class)
    await _assert_rejected_before_consumption(
        artifact,
        original,
        policy=_required_policy(evidence),
        evidence=evidence,
        monkeypatch=monkeypatch,
    )


@pytest.mark.asyncio
async def test_expired_capability_fails_before_consumption(consumable, monkeypatch):
    artifact, original, _ = consumable
    evidence = _evidence(
        original,
        assessed_at=original["now"] - timedelta(minutes=2),
        valid_until=original["now"] - timedelta(seconds=1),
    )
    await _assert_rejected_before_consumption(
        artifact,
        original,
        policy=_required_policy(evidence),
        evidence=evidence,
        monkeypatch=monkeypatch,
    )


@pytest.mark.asyncio
async def test_endpoint_identity_drift_fails_before_consumption(
    consumable,
    monkeypatch,
):
    artifact, original, _ = consumable
    evidence = _evidence(original, endpoint_digest="e" * 64)
    await _assert_rejected_before_consumption(
        artifact,
        original,
        policy=_required_policy(evidence),
        evidence=evidence,
        monkeypatch=monkeypatch,
    )


@pytest.mark.asyncio
async def test_target_configuration_drift_fails_before_consumption(
    consumable,
    monkeypatch,
):
    artifact, original, _ = consumable
    evidence = _evidence(original, target_configuration_digest="e" * 64)
    await _assert_rejected_before_consumption(
        artifact,
        original,
        policy=_required_policy(evidence),
        evidence=evidence,
        monkeypatch=monkeypatch,
    )


@pytest.mark.asyncio
async def test_verifier_anchor_mismatch_fails_before_consumption(
    consumable,
    monkeypatch,
):
    artifact, original, _ = consumable
    evidence = _evidence(
        original,
        verifier_id="caller-declared-verifier",
        verifier_policy_id="caller-declared-policy",
        verifier_policy_hash="e" * 64,
    )
    await _assert_rejected_before_consumption(
        artifact,
        original,
        policy=_required_policy(evidence),
        evidence=evidence,
        monkeypatch=monkeypatch,
    )


@pytest.mark.asyncio
async def test_evidence_digest_mismatch_fails_before_consumption(
    consumable,
    monkeypatch,
):
    artifact, original, _ = consumable
    evidence = _evidence(original)
    await _assert_rejected_before_consumption(
        artifact,
        original,
        policy=_required_policy(
            evidence,
            expected_evidence_digest="0" * 64,
        ),
        evidence=evidence,
        monkeypatch=monkeypatch,
    )


@pytest.mark.asyncio
async def test_incomplete_required_policy_fails_before_consumption(
    consumable,
    monkeypatch,
):
    artifact, original, _ = consumable
    evidence = _evidence(original)
    policy = module.ReconciliationCapabilityExecutionPolicy(
        policy_id="reconciliation-required/v1",
        require_authoritative_reconciliation=True,
        current_target_configuration_digest=_TARGET_CONFIGURATION_DIGEST,
    )
    await _assert_rejected_before_consumption(
        artifact,
        original,
        policy=policy,
        evidence=evidence,
        expected_reason="NABC_RECONCILIATION_CAPABILITY_POLICY_INVALID",
        monkeypatch=monkeypatch,
    )


@pytest.mark.asyncio
async def test_untyped_policy_input_cannot_downgrade_gate(consumable):
    artifact, original, _ = consumable
    store, inputs = _store_inputs(original)

    with pytest.raises(
        module.NativeAuthorizationConsumptionError,
        match="NABC_RECONCILIATION_CAPABILITY_POLICY_INVALID",
    ):
        await module.consume_native_bind_authorization(
            artifact,
            **inputs,
            reconciliation_capability_policy={
                "policy_id": "request-supplied",
                "require_authoritative_reconciliation": False,
            },
        )

    assert await store.get(artifact.authorization_id) is None
