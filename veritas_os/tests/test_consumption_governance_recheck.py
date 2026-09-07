"""Consumption-clock regression and v0.3 local runtime integration.

Real packet/signature verifiers, ephemeral keys and in-memory stores are used.
The adapter, credential provider and TrustLog sink are test doubles: this is
not a live decision, real network effect or durable production audit proof.
"""

from dataclasses import replace
from datetime import timedelta

import pytest

from veritas_os.policy.live_adapter_bind_authorization_verification import (
    validate_live_adapter_bind_authorization_temporal_validity as validate,
)
from veritas_os.policy.live_adapter_bind_authorization_consumption import (
    consume_live_adapter_bind_authorization_and_invoke_bind as consume,
    LiveAdapterBindAuthorizationConsumptionError,
)
from veritas_os.policy.live_adapter_bind_authorization_consumption_store import (
    InMemoryAtomicAuthorizationConsumptionStore,
)
from veritas_os.policy.bind_effect_runtime import (
    consume_bind_record_lineage_and_effect_state,
)
from veritas_os.policy.bind_effect_reconciliation import (
    EffectExecutionState,
    InMemoryAtomicEffectStateStore,
)
from veritas_os.tests.test_v03_issuance_trust import case, _issue
from veritas_os.tests.test_live_adapter_bind_authorization_consumption import (
    _Factory,
    _Resolver,
    _HeaderConstructor,
)
from veritas_os.tests.test_bind_outcome_lineage import (
    _BlockedFactory,
    _install_fake_trustlog,
)

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def authorized(case):
    return _issue(case), case[1], case[3]


class _TimedRevocation:
    """Return authentic fixture status at issuance, then change at consumption."""

    def __init__(self, governance, mode="valid"):
        self.original = governance.authority_revocation_checker
        self.issued = governance.verification_now
        self.mode = mode
        self.times = []

    def check(self, evidence_id, *, now):
        self.times.append(now)
        result = self.original.check(evidence_id, now=now)
        if now <= self.issued:
            return result
        if self.mode == "revoked":
            return replace(result, revoked=True, reason="revoked_after_issuance")
        if self.mode == "stale":
            return replace(result, checked_at=self.issued.isoformat())
        if self.mode == "unavailable":
            raise ValueError("revocation_status_unavailable")
        if self.mode == "future":
            return replace(result, checked_at=(now + timedelta(seconds=1)).isoformat())
        return result


def test_later_consumption_rechecks_governance_without_rewriting_signed_proofs(
    authorized,
    monkeypatch,
):
    import veritas_os.policy.live_adapter_bind_authorization_governance as module

    artifact, governance, trust = authorized
    before = artifact.model_dump(mode="json")
    checker = _TimedRevocation(governance)
    current = governance.verification_now + timedelta(seconds=90)
    approval_times = []
    real_verify = module.verify_human_approval_receipt_artifact_to_proof

    def record_approval(*args, **kwargs):
        approval_times.append(kwargs["now"])
        return real_verify(*args, **kwargs)

    monkeypatch.setattr(
        module, "verify_human_approval_receipt_artifact_to_proof", record_approval
    )
    supplied = replace(governance, authority_revocation_checker=checker)
    verified = validate(
        artifact, now=current, governance_inputs=supplied, trust_inputs=trust
    )
    assert checker.times == [governance.verification_now, current]
    if governance.signed_human_approval_artifact is not None:
        assert approval_times == [governance.verification_now, current]
    else:
        assert approval_times == []
    assert verified.model_dump(mode="json") == before
    assert artifact.model_dump(mode="json") == before
    assert supplied.verification_now == governance.verification_now


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["revoked", "stale", "unavailable", "future"])
async def test_changed_revocation_rejects_before_consumption_or_secret_access(
    authorized, mode
):
    artifact, governance, trust = authorized
    checker = _TimedRevocation(governance, mode)
    current = governance.verification_now + timedelta(seconds=90)
    store = InMemoryAtomicAuthorizationConsumptionStore()
    resolver, headers, factory = _Resolver(), _HeaderConstructor(), _Factory()
    with pytest.raises(
        LiveAdapterBindAuthorizationConsumptionError,
        match="AUTHORIZATION_VERIFICATION_FAILED",
    ):
        await consume(
            artifact,
            now=current,
            governance_inputs=replace(governance, authority_revocation_checker=checker),
            trust_inputs=trust,
            consumption_store=store,
            credential_resolver=resolver,
            authorization_header_constructor=headers,
            adapter_factory=factory,
            append_trustlog=False,
        )
    assert current in checker.times
    assert await store.get(artifact.live_adapter_bind_authorization_id) is None
    assert resolver.calls == headers.calls == factory.calls == 0


@pytest.mark.parametrize("time_case", ["backdated", "naive", "expired"])
def test_invalid_consumption_clock_or_expired_authorization_fails_closed(
    authorized, time_case
):
    artifact, governance, trust = authorized
    if time_case == "backdated":
        current = governance.verification_now - timedelta(microseconds=1)
    elif time_case == "naive":
        current = governance.verification_now.replace(tzinfo=None)
    else:
        current = artifact.valid_until
    with pytest.raises(ValueError):
        validate(
            artifact, now=current, governance_inputs=governance, trust_inputs=trust
        )


@pytest.mark.asyncio
async def test_current_human_signature_trust_is_required_before_consumption(authorized):
    artifact, governance, trust = authorized
    checker = _TimedRevocation(governance)
    current = governance.verification_now + timedelta(seconds=30)
    calls = []

    class WithdrawnHumanVerifier:
        def verify(self, envelope):
            # Simulate signing trust withdrawn after the historical evaluation.
            calls.append(checker.times[-1])
            assert governance.human_approval_signature_verifier is not None
            result = governance.human_approval_signature_verifier.verify(envelope)
            if checker.times[-1] == current:
                return replace(
                    result, verified=False, reason="test_signing_trust_withdrawn"
                )
            return result

    store = InMemoryAtomicAuthorizationConsumptionStore()
    resolver, headers, factory = _Resolver(), _HeaderConstructor(), _Factory()
    kwargs = dict(
        now=current,
        governance_inputs=replace(
            governance,
            authority_revocation_checker=checker,
            human_approval_signature_verifier=WithdrawnHumanVerifier(),
        ),
        trust_inputs=trust,
        consumption_store=store,
        credential_resolver=resolver,
        authorization_header_constructor=headers,
        adapter_factory=factory,
        append_trustlog=False,
    )
    if governance.signed_human_approval_artifact is None:
        await consume(artifact, **kwargs)
        assert calls == []
        assert resolver.calls == 1
    else:
        with pytest.raises(
            LiveAdapterBindAuthorizationConsumptionError,
            match="AUTHORIZATION_VERIFICATION_FAILED",
        ):
            await consume(artifact, **kwargs)
        assert calls == [governance.verification_now, current]
        assert await store.get(artifact.live_adapter_bind_authorization_id) is None
        assert resolver.calls == headers.calls == factory.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("blocked", [False, True])
async def test_v03_local_operation_records_outcome_and_never_reexecutes(
    authorized,
    monkeypatch,
    blocked,
):
    _install_fake_trustlog(monkeypatch)
    artifact, governance, trust = authorized
    before = artifact.model_dump(mode="json")
    consumptions = InMemoryAtomicAuthorizationConsumptionStore()
    effects = InMemoryAtomicEffectStateStore()
    resolver, headers = _Resolver(), _HeaderConstructor()
    factory = _BlockedFactory() if blocked else _Factory()
    current = governance.verification_now + timedelta(seconds=30)
    kwargs = dict(
        governance_inputs=governance,
        trust_inputs=trust,
        now=current,
        consumption_store=consumptions,
        effect_store=effects,
        credential_resolver=resolver,
        authorization_header_constructor=headers,
        adapter_factory=factory,
    )
    result = await consume_bind_record_lineage_and_effect_state(artifact, **kwargs)
    lineage = result.lineage
    record = lineage.consumption_result.consumption_record
    assert await consumptions.get(artifact.live_adapter_bind_authorization_id) == record
    assert await effects.get(record.consumption_id) == result.effect_state
    assert lineage.consumption_result.adapter_apply_attempted is not blocked
    assert factory.adapter.apply_calls == (0 if blocked else 1)
    assert result.effect_state.state == (
        EffectExecutionState.CONFIRMED_NO_EFFECT
        if blocked
        else EffectExecutionState.EFFECT_UNKNOWN
    )
    assert lineage.bind_receipt.execution_intent_id == artifact.execution_intent_id
    assert (
        lineage.outcome_receipt.bind_receipt_id == lineage.bind_receipt.bind_receipt_id
    )
    assert (
        lineage.outcome_receipt.outcome_hash
        == lineage.outcome_receipt.deterministic_digest()
    )
    assert (
        lineage.outcome_receipt.metadata["external_effect_claim"]
        == "NOT_INFERRED_FROM_GENERIC_ADAPTER_APPLY"
    )
    with pytest.raises(
        LiveAdapterBindAuthorizationConsumptionError, match="ALREADY_CONSUMED"
    ):
        await consume_bind_record_lineage_and_effect_state(artifact, **kwargs)
    assert resolver.calls == headers.calls == factory.calls == 1
    assert factory.adapter.apply_calls == (0 if blocked else 1)
    assert artifact.model_dump(mode="json") == before
