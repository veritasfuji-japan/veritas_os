"""Security and lineage tests for Bind -> Outcome -> TrustLog v1."""

from __future__ import annotations

from dataclasses import replace

import pytest

from veritas_os.policy.bind_artifacts import hash_bind_receipt
from veritas_os.policy.bind_outcome_lineage import (
    BindOutcomeLineageError,
    consume_bind_and_record_outcome_lineage,
)
from veritas_os.policy.live_adapter_bind_authorization_consumption import (
    AuthorizedBindAdapterInstance,
)
from veritas_os.policy.live_adapter_bind_authorization_consumption_store import (
    InMemoryAtomicAuthorizationConsumptionStore,
)
from veritas_os.tests.test_live_adapter_bind_authorization import VERIFICATION_NOW, _build
from veritas_os.tests.test_live_adapter_bind_authorization_consumption import (
    _Factory,
    _HeaderConstructor,
    _RecordingAdapter,
    _Resolver,
)


def _install_fake_trustlog(monkeypatch) -> None:
    import veritas_os.policy.bind_outcome_lineage as lineage

    monkeypatch.setattr(
        lineage,
        "append_execution_intent_trustlog",
        lambda intent: {"sha256": "a" * 64, "execution_intent_id": intent.execution_intent_id},
    )

    def _append_bind(receipt):
        with_hash = replace(receipt, bind_receipt_hash=hash_bind_receipt(receipt))
        return replace(with_hash, trustlog_hash="b" * 64)

    monkeypatch.setattr(lineage, "append_bind_receipt_trustlog", _append_bind)
    monkeypatch.setattr(lineage, "append_trust_log", lambda entry: {**entry, "sha256": "c" * 64})


@pytest.mark.asyncio
async def test_complete_lineage_binds_authorization_consumption_bind_and_outcome(monkeypatch) -> None:
    _install_fake_trustlog(monkeypatch)
    artifact, governance, trust = _build()
    store = InMemoryAtomicAuthorizationConsumptionStore()

    result = await consume_bind_and_record_outcome_lineage(
        artifact,
        governance_inputs=governance,
        trust_inputs=trust,
        now=VERIFICATION_NOW,
        consumption_store=store,
        credential_resolver=_Resolver(),
        authorization_header_constructor=_HeaderConstructor(),
        adapter_factory=_Factory(),
    )

    identity = result.bind_receipt.governance_identity or {}
    auth = identity["real_bind_authorization"]
    consumption = identity["authorization_consumption"]
    invocation = identity["bind_invocation"]

    assert auth["live_adapter_bind_authorization_id"] == artifact.live_adapter_bind_authorization_id
    assert auth["live_adapter_bind_authorization_hash"] == artifact.live_adapter_bind_authorization_hash
    assert consumption["consumption_id"] == result.consumption_result.consumption_record.consumption_id
    assert consumption["consumption_hash"] == result.consumption_result.consumption_record.consumption_hash
    assert consumption["single_use_enforced"] is True
    assert invocation["bind_core_invoked"] is True
    assert invocation["adapter_apply_attempted"] is True

    outcome = result.outcome_receipt
    assert outcome.bind_receipt_id == result.bind_receipt.bind_receipt_id
    assert outcome.outcome_hash == outcome.deterministic_digest()
    assert outcome.metadata["bind_receipt_hash"] == result.bind_receipt.bind_receipt_hash
    assert outcome.metadata["bind_trustlog_hash"] == "b" * 64
    assert outcome.metadata["authorization_consumption_hash"] == consumption["consumption_hash"]
    assert outcome.metadata["external_effect_claim"] == "NOT_INFERRED_FROM_GENERIC_ADAPTER_APPLY"
    assert outcome.observed_effects == [
        {
            "kind": "adapter_apply_attempt",
            "attempted": True,
            "external_effect_inferred": False,
        }
    ]
    assert result.outcome_trustlog_hash == "c" * 64


@pytest.mark.asyncio
async def test_serialized_authorization_is_canonicalized_before_bind_and_lineage(monkeypatch) -> None:
    _install_fake_trustlog(monkeypatch)
    artifact, governance, trust = _build()
    serialized = artifact.model_dump(mode="json")

    result = await consume_bind_and_record_outcome_lineage(
        serialized,
        governance_inputs=governance,
        trust_inputs=trust,
        now=VERIFICATION_NOW,
        consumption_store=InMemoryAtomicAuthorizationConsumptionStore(),
        credential_resolver=_Resolver(),
        authorization_header_constructor=_HeaderConstructor(),
        adapter_factory=_Factory(),
    )

    identity = result.bind_receipt.governance_identity or {}
    assert (
        identity["real_bind_authorization"]["live_adapter_bind_authorization_id"]
        == artifact.live_adapter_bind_authorization_id
    )
    assert result.outcome_receipt.bind_receipt_id == result.bind_receipt.bind_receipt_id
    assert result.outcome_receipt.outcome_hash == result.outcome_receipt.deterministic_digest()
    assert result.outcome_trustlog_hash == "c" * 64


class _BlockedAdapter(_RecordingAdapter):
    def validate_authority(self, intent, snapshot):
        del intent, snapshot
        return False


class _BlockedFactory(_Factory):
    async def build(self, *, authorization, credential, authorization_header):
        del credential, authorization_header
        self.calls += 1
        self.adapter = _BlockedAdapter(
            authorization.execution_intent.get("expected_state_fingerprint")
        )
        return AuthorizedBindAdapterInstance(
            adapter=self.adapter,
            adapter_contract_id=authorization.adapter_contract_id,
            adapter_contract_hash=authorization.adapter_contract_hash,
            endpoint_identity_binding_digest=authorization.endpoint_identity_binding_digest,
            credential_reference_digest=authorization.credential_reference_digest,
            credential_scope_binding_digest=authorization.credential_scope_binding_digest,
        )


@pytest.mark.asyncio
async def test_blocked_bind_records_core_entry_without_claiming_apply(monkeypatch) -> None:
    _install_fake_trustlog(monkeypatch)
    artifact, governance, trust = _build()

    result = await consume_bind_and_record_outcome_lineage(
        artifact,
        governance_inputs=governance,
        trust_inputs=trust,
        now=VERIFICATION_NOW,
        consumption_store=InMemoryAtomicAuthorizationConsumptionStore(),
        credential_resolver=_Resolver(),
        authorization_header_constructor=_HeaderConstructor(),
        adapter_factory=_BlockedFactory(),
    )

    assert result.consumption_result.bind_core_invoked is True
    assert result.consumption_result.adapter_apply_attempted is False
    assert result.outcome_receipt.observed_effects[0]["attempted"] is False
    assert result.outcome_receipt.observed_effects[0]["external_effect_inferred"] is False
    assert result.outcome_receipt.blocked is True


@pytest.mark.asyncio
async def test_trustlog_failure_after_bind_attempt_is_explicit_and_authorization_stays_consumed(
    monkeypatch,
) -> None:
    import veritas_os.policy.bind_outcome_lineage as lineage

    artifact, governance, trust = _build()
    store = InMemoryAtomicAuthorizationConsumptionStore()

    def _fail(_intent):
        raise RuntimeError("audit-store-unavailable")

    monkeypatch.setattr(lineage, "append_execution_intent_trustlog", _fail)

    with pytest.raises(
        BindOutcomeLineageError,
        match="BOL_TRUSTLOG_PERSISTENCE_FAILED_AFTER_BIND_ATTEMPT",
    ):
        await consume_bind_and_record_outcome_lineage(
            artifact,
            governance_inputs=governance,
            trust_inputs=trust,
            now=VERIFICATION_NOW,
            consumption_store=store,
            credential_resolver=_Resolver(),
            authorization_header_constructor=_HeaderConstructor(),
            adapter_factory=_Factory(),
        )

    assert await store.get(artifact.live_adapter_bind_authorization_id) is not None
