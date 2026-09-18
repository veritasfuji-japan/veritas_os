"""Policy-gated verified reconciliation capability proofs at consumption."""

from dataclasses import replace
from datetime import timedelta

import pytest

from veritas_os.governance.reconciliation_capability_evidence import (
    ApprovedReconciliationCapabilityVerifier,
    ReconciliationCapabilityClass,
    ReconciliationCapabilityEvidence,
    ReconciliationCapabilityVerificationResult,
    ReconciliationCapabilityVerifierTrustPolicy,
    VerifiedReconciliationCapabilityEvidence,
    verify_reconciliation_capability_evidence_to_proof,
)
from veritas_os.policy import native_bind_authorization_consumption as module
from veritas_os.security.hash import sha256_of_canonical_json
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
_VERIFIER_ID = "reconciliation-capability-verifier/v1"
_VERIFIER_POLICY_ID = "reconciliation-capability-policy/v1"
_VERIFIER_POLICY_HASH = "d" * 64
_TRUST_POLICY_ID = "reconciliation-capability-trust/v1"


class _ControlledVerifier:
    def __init__(
        self,
        *,
        verifier_id=_VERIFIER_ID,
        verifier_policy_id=_VERIFIER_POLICY_ID,
        verifier_policy_hash=_VERIFIER_POLICY_HASH,
    ):
        self.verifier_id = verifier_id
        self.verifier_policy_id = verifier_policy_id
        self.verifier_policy_hash = verifier_policy_hash

    def verify(self, evidence):
        material = sha256_of_canonical_json(
            {
                "domain": "test.reconciliation-capability-verifier/v1",
                "evidence_digest": evidence.deterministic_digest(),
                "verifier_id": self.verifier_id,
                "verifier_policy_id": self.verifier_policy_id,
                "verifier_policy_hash": self.verifier_policy_hash,
            }
        )
        return ReconciliationCapabilityVerificationResult(
            verified=True,
            evidence_digest=evidence.deterministic_digest(),
            verifier_id=self.verifier_id,
            verifier_policy_id=self.verifier_policy_id,
            verifier_policy_hash=self.verifier_policy_hash,
            verification_material_digest=material,
            semantic_consistent=True,
            reason="controlled-test-verification",
        )


def _trust_policy(
    *,
    verifier_id=_VERIFIER_ID,
    verifier_policy_id=_VERIFIER_POLICY_ID,
    verifier_policy_hash=_VERIFIER_POLICY_HASH,
    policy_id=_TRUST_POLICY_ID,
):
    return ReconciliationCapabilityVerifierTrustPolicy(
        policy_id=policy_id,
        approved_verifiers=(
            ApprovedReconciliationCapabilityVerifier(
                verifier_id=verifier_id,
                verifier_policy_id=verifier_policy_id,
                verifier_policy_hash=verifier_policy_hash,
            ),
        ),
    )


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
    verifier_id=_VERIFIER_ID,
    verifier_policy_id=_VERIFIER_POLICY_ID,
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


def _proof(
    evidence,
    *,
    verified_at,
    verifier=None,
    trust_policy=None,
):
    trust = trust_policy or _trust_policy()
    actual_verifier = verifier or _ControlledVerifier()
    return verify_reconciliation_capability_evidence_to_proof(
        evidence,
        verifier=actual_verifier,
        trust_policy=trust,
        verified_at=verified_at,
    )


def _required_policy(
    evidence,
    trust_policy,
    *,
    current_target_configuration_digest=_TARGET_CONFIGURATION_DIGEST,
    expected_verifier_id=_VERIFIER_ID,
    expected_verifier_policy_id=_VERIFIER_POLICY_ID,
    expected_verifier_policy_hash=_VERIFIER_POLICY_HASH,
    expected_evidence_digest=None,
    expected_trust_policy_id=None,
    expected_trust_policy_hash=None,
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
        expected_trust_policy_id=(
            expected_trust_policy_id or trust_policy.policy_id
        ),
        expected_trust_policy_hash=(
            expected_trust_policy_hash or trust_policy.deterministic_hash()
        ),
    )


async def _assert_rejected_before_consumption(
    artifact,
    original,
    *,
    policy,
    proof=None,
    trust_policy=None,
    raw_evidence=None,
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

    with pytest.raises(
        module.NativeAuthorizationConsumptionError,
        match=expected_reason,
    ):
        await module.consume_native_bind_authorization(
            artifact,
            **inputs,
            reconciliation_capability_policy=policy,
            reconciliation_capability_proof=proof,
            reconciliation_capability_trust_policy=trust_policy,
            reconciliation_capability_evidence=raw_evidence,
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
async def test_required_verified_authoritative_capability_passes_before_consumption(
    consumable,
    capability_class,
):
    artifact, original, _ = consumable
    evidence = _evidence(original, capability_class=capability_class)
    trust_policy = _trust_policy()
    proof = _proof(
        evidence,
        verified_at=original["now"],
        trust_policy=trust_policy,
    )
    policy = _required_policy(evidence, trust_policy)
    store, inputs = _store_inputs(original)

    result = await module.consume_native_bind_authorization(
        artifact,
        **inputs,
        reconciliation_capability_policy=policy,
        reconciliation_capability_proof=proof,
        reconciliation_capability_trust_policy=trust_policy,
    )

    assert result.authorization_consumed is True
    assert result.reconciliation_capability_required is True
    assert result.reconciliation_capability_satisfied is True
    assert result.reconciliation_capability_policy_id == policy.policy_id
    assert (
        result.reconciliation_capability_evidence_digest
        == evidence.deterministic_digest()
    )
    assert (
        result.reconciliation_capability_verification_proof_hash
        == proof.verification_proof_hash
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
    assert result.reconciliation_capability_verification_proof_hash is None
    assert await store.get(artifact.authorization_id) == result.consumption_record


@pytest.mark.asyncio
async def test_required_raw_evidence_alone_cannot_satisfy_gate(
    consumable,
    monkeypatch,
):
    artifact, original, _ = consumable
    evidence = _evidence(original)
    trust_policy = _trust_policy()
    await _assert_rejected_before_consumption(
        artifact,
        original,
        policy=_required_policy(evidence, trust_policy),
        trust_policy=trust_policy,
        raw_evidence=evidence,
        expected_reason="NABC_RECONCILIATION_CAPABILITY_VERIFIED_PROOF_REQUIRED",
        monkeypatch=monkeypatch,
    )


@pytest.mark.asyncio
async def test_required_missing_trust_policy_fails_before_consumption(
    consumable,
    monkeypatch,
):
    artifact, original, _ = consumable
    evidence = _evidence(original)
    trust_policy = _trust_policy()
    proof = _proof(evidence, verified_at=original["now"], trust_policy=trust_policy)
    await _assert_rejected_before_consumption(
        artifact,
        original,
        policy=_required_policy(evidence, trust_policy),
        proof=proof,
        expected_reason="NABC_RECONCILIATION_CAPABILITY_TRUST_POLICY_REQUIRED",
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
async def test_verified_non_authoritative_capability_fails_before_consumption(
    consumable,
    capability_class,
    monkeypatch,
):
    artifact, original, _ = consumable
    evidence = _evidence(original, capability_class=capability_class)
    trust_policy = _trust_policy()
    proof = _proof(evidence, verified_at=original["now"], trust_policy=trust_policy)
    await _assert_rejected_before_consumption(
        artifact,
        original,
        policy=_required_policy(evidence, trust_policy),
        proof=proof,
        trust_policy=trust_policy,
        monkeypatch=monkeypatch,
    )


@pytest.mark.asyncio
async def test_expired_verified_capability_fails_before_consumption(
    consumable,
    monkeypatch,
):
    artifact, original, _ = consumable
    evidence = _evidence(
        original,
        assessed_at=original["now"] - timedelta(minutes=2),
        valid_until=original["now"] - timedelta(seconds=1),
    )
    trust_policy = _trust_policy()
    proof = _proof(
        evidence,
        verified_at=original["now"] - timedelta(seconds=2),
        trust_policy=trust_policy,
    )
    await _assert_rejected_before_consumption(
        artifact,
        original,
        policy=_required_policy(evidence, trust_policy),
        proof=proof,
        trust_policy=trust_policy,
        monkeypatch=monkeypatch,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("endpoint", "e" * 64),
        ("target", "e" * 64),
    ],
)
async def test_verified_target_drift_fails_before_consumption(
    consumable,
    field,
    value,
    monkeypatch,
):
    artifact, original, _ = consumable
    evidence = _evidence(
        original,
        endpoint_digest=value if field == "endpoint" else None,
        target_configuration_digest=(
            value if field == "target" else _TARGET_CONFIGURATION_DIGEST
        ),
    )
    trust_policy = _trust_policy()
    proof = _proof(evidence, verified_at=original["now"], trust_policy=trust_policy)
    await _assert_rejected_before_consumption(
        artifact,
        original,
        policy=_required_policy(evidence, trust_policy),
        proof=proof,
        trust_policy=trust_policy,
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
        verifier_id="other-verifier",
        verifier_policy_id="other-policy",
        verifier_policy_hash="e" * 64,
    )
    trust_policy = _trust_policy(
        verifier_id="other-verifier",
        verifier_policy_id="other-policy",
        verifier_policy_hash="e" * 64,
    )
    proof = _proof(
        evidence,
        verified_at=original["now"],
        verifier=_ControlledVerifier(
            verifier_id="other-verifier",
            verifier_policy_id="other-policy",
            verifier_policy_hash="e" * 64,
        ),
        trust_policy=trust_policy,
    )
    policy = _required_policy(
        evidence,
        trust_policy,
        expected_verifier_id=_VERIFIER_ID,
        expected_verifier_policy_id=_VERIFIER_POLICY_ID,
        expected_verifier_policy_hash=_VERIFIER_POLICY_HASH,
    )
    await _assert_rejected_before_consumption(
        artifact,
        original,
        policy=policy,
        proof=proof,
        trust_policy=trust_policy,
        monkeypatch=monkeypatch,
    )


@pytest.mark.asyncio
async def test_evidence_digest_mismatch_fails_before_consumption(
    consumable,
    monkeypatch,
):
    artifact, original, _ = consumable
    evidence = _evidence(original)
    trust_policy = _trust_policy()
    proof = _proof(evidence, verified_at=original["now"], trust_policy=trust_policy)
    policy = _required_policy(
        evidence,
        trust_policy,
        expected_evidence_digest="0" * 64,
    )
    await _assert_rejected_before_consumption(
        artifact,
        original,
        policy=policy,
        proof=proof,
        trust_policy=trust_policy,
        monkeypatch=monkeypatch,
    )


@pytest.mark.asyncio
async def test_trust_policy_anchor_mismatch_fails_before_consumption(
    consumable,
    monkeypatch,
):
    artifact, original, _ = consumable
    evidence = _evidence(original)
    trust_policy = _trust_policy()
    proof = _proof(evidence, verified_at=original["now"], trust_policy=trust_policy)
    policy = _required_policy(
        evidence,
        trust_policy,
        expected_trust_policy_hash="0" * 64,
    )
    await _assert_rejected_before_consumption(
        artifact,
        original,
        policy=policy,
        proof=proof,
        trust_policy=trust_policy,
        expected_reason="NABC_RECONCILIATION_CAPABILITY_TRUST_POLICY_MISMATCH",
        monkeypatch=monkeypatch,
    )


@pytest.mark.asyncio
async def test_caller_constructed_verified_lookalike_fails_before_consumption(
    consumable,
    monkeypatch,
):
    artifact, original, _ = consumable
    evidence = _evidence(original)
    trust_policy = _trust_policy()
    sealed = _proof(
        evidence,
        verified_at=original["now"],
        trust_policy=trust_policy,
    )
    forged = VerifiedReconciliationCapabilityEvidence(
        **sealed.model_dump(mode="json")
    )
    await _assert_rejected_before_consumption(
        artifact,
        original,
        policy=_required_policy(evidence, trust_policy),
        proof=forged,
        trust_policy=trust_policy,
        monkeypatch=monkeypatch,
    )


@pytest.mark.asyncio
async def test_raw_evidence_is_rejected_even_beside_valid_sealed_proof(
    consumable,
    monkeypatch,
):
    artifact, original, _ = consumable
    evidence = _evidence(original)
    trust_policy = _trust_policy()
    proof = _proof(evidence, verified_at=original["now"], trust_policy=trust_policy)
    await _assert_rejected_before_consumption(
        artifact,
        original,
        policy=_required_policy(evidence, trust_policy),
        proof=proof,
        trust_policy=trust_policy,
        raw_evidence=evidence,
        expected_reason="NABC_RECONCILIATION_CAPABILITY_RAW_EVIDENCE_NOT_ACCEPTED",
        monkeypatch=monkeypatch,
    )


@pytest.mark.asyncio
async def test_incomplete_required_policy_fails_before_consumption(
    consumable,
    monkeypatch,
):
    artifact, original, _ = consumable
    evidence = _evidence(original)
    trust_policy = _trust_policy()
    proof = _proof(evidence, verified_at=original["now"], trust_policy=trust_policy)
    policy = module.ReconciliationCapabilityExecutionPolicy(
        policy_id="reconciliation-required/v1",
        require_authoritative_reconciliation=True,
        current_target_configuration_digest=_TARGET_CONFIGURATION_DIGEST,
    )
    await _assert_rejected_before_consumption(
        artifact,
        original,
        policy=policy,
        proof=proof,
        trust_policy=trust_policy,
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
