"""Security tests for Authorization Consumption / Bind Invocation Gate v1."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Mapping

import pytest

from veritas_os.policy.bind_artifacts import ExecutionIntent
from veritas_os.policy.bind_core.contracts import BindAdapterContract
from veritas_os.policy.live_adapter_bind_authorization_consumption import (
    AuthorizedBindAdapterInstance,
    ConstructedAuthorizationHeader,
    LiveAdapterBindAuthorizationConsumptionError,
    ResolvedCredentialMaterial,
    consume_live_adapter_bind_authorization_and_invoke_bind,
)
from veritas_os.policy.live_adapter_bind_authorization_consumption_store import (
    InMemoryAtomicAuthorizationConsumptionStore,
    build_authorization_consumption_record,
)
from veritas_os.tests.test_live_adapter_bind_authorization import (
    VERIFICATION_NOW,
    _build,
)


class _Resolver:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls = 0
        self.fail = fail

    async def resolve(
        self,
        credential_reference: Mapping[str, Any],
        *,
        credential_scope_binding: Mapping[str, Any],
        live_adapter_bind_authorization_id: str,
    ) -> ResolvedCredentialMaterial:
        del credential_scope_binding, live_adapter_bind_authorization_id
        self.calls += 1
        if self.fail:
            raise RuntimeError("secret-provider-details-must-not-escape")
        return ResolvedCredentialMaterial(
            credential_reference_id=str(
                credential_reference["credential_reference_id"]
            ),
            credential_kind=str(credential_reference["credential_kind"]),
            credential_provider_type=str(
                credential_reference["credential_provider_type"]
            ),
            material=b"super-secret-test-credential",
        )


class _HeaderConstructor:
    def __init__(self) -> None:
        self.calls = 0

    async def construct(
        self,
        credential: ResolvedCredentialMaterial,
        *,
        credential_reference: Mapping[str, Any],
        credential_scope_binding: Mapping[str, Any],
        live_adapter_bind_authorization_id: str,
    ) -> ConstructedAuthorizationHeader:
        del credential_reference, credential_scope_binding
        del live_adapter_bind_authorization_id
        self.calls += 1
        assert credential.material == b"super-secret-test-credential"
        return ConstructedAuthorizationHeader(
            name="Authorization",
            value="Bearer super-secret-test-credential",
        )


@dataclass
class _RecordingAdapter(BindAdapterContract):
    expected_fingerprint: str | None
    apply_calls: int = 0

    def snapshot(self) -> dict[str, str]:
        return {"state": "before"}

    def fingerprint_state(self, snapshot: Any) -> str:
        del snapshot
        return self.expected_fingerprint or "live-state"

    def validate_authority(self, intent: ExecutionIntent, snapshot: Any) -> bool:
        del intent, snapshot
        return True

    def validate_constraints(
        self, intent: ExecutionIntent, snapshot: Any
    ) -> dict[str, bool]:
        del intent, snapshot
        return {"authorized_consumption": True}

    def assess_runtime_risk(self, intent: ExecutionIntent, snapshot: Any) -> bool:
        del intent, snapshot
        return True

    def apply(self, intent: ExecutionIntent, snapshot: Any) -> bool:
        del intent, snapshot
        self.apply_calls += 1
        return True

    def verify_postconditions(self, intent: ExecutionIntent, snapshot: Any) -> bool:
        del intent, snapshot
        return True

    def revert(self, intent: ExecutionIntent, snapshot: Any) -> bool:
        del intent, snapshot
        return True

    def describe_target(self) -> str:
        return "authorized-consumption-test-target"


class _Factory:
    def __init__(self) -> None:
        self.calls = 0
        self.adapter: _RecordingAdapter | None = None

    async def build(
        self,
        *,
        authorization,
        credential: ResolvedCredentialMaterial,
        authorization_header: ConstructedAuthorizationHeader,
    ) -> AuthorizedBindAdapterInstance:
        self.calls += 1
        assert credential.material == b"super-secret-test-credential"
        assert authorization_header.value.startswith("Bearer ")
        self.adapter = _RecordingAdapter(
            authorization.execution_intent.get("expected_state_fingerprint")
        )
        return AuthorizedBindAdapterInstance(
            adapter=self.adapter,
            adapter_contract_id=authorization.adapter_contract_id,
            adapter_contract_hash=authorization.adapter_contract_hash,
            endpoint_identity_binding_digest=(
                authorization.endpoint_identity_binding_digest
            ),
            credential_reference_digest=authorization.credential_reference_digest,
            credential_scope_binding_digest=(
                authorization.credential_scope_binding_digest
            ),
        )


@pytest.mark.asyncio
async def test_verified_authorization_consumes_once_before_bind() -> None:
    artifact, governance, trust = _build()
    store = InMemoryAtomicAuthorizationConsumptionStore()
    resolver = _Resolver()
    header = _HeaderConstructor()
    factory = _Factory()

    result = await consume_live_adapter_bind_authorization_and_invoke_bind(
        artifact,
        governance_inputs=governance,
        trust_inputs=trust,
        now=VERIFICATION_NOW,
        consumption_store=store,
        credential_resolver=resolver,
        authorization_header_constructor=header,
        adapter_factory=factory,
        append_trustlog=False,
    )

    assert result.authorization_consumed
    assert result.credential_material_accessed
    assert result.authorization_header_constructed
    assert result.bind_invoked
    assert result.consumption_record.consumption_state == "CONSUMED"
    assert result.bind_receipt.execution_intent_id == artifact.execution_intent_id
    assert resolver.calls == 1
    assert header.calls == 1
    assert factory.calls == 1

    with pytest.raises(
        LiveAdapterBindAuthorizationConsumptionError,
        match="LABAC_AUTHORIZATION_ALREADY_CONSUMED",
    ):
        await consume_live_adapter_bind_authorization_and_invoke_bind(
            artifact,
            governance_inputs=governance,
            trust_inputs=trust,
            now=VERIFICATION_NOW,
            consumption_store=store,
            credential_resolver=resolver,
            authorization_header_constructor=header,
            adapter_factory=factory,
            append_trustlog=False,
        )
    assert resolver.calls == 1
    assert header.calls == 1
    assert factory.calls == 1


@pytest.mark.asyncio
async def test_tampered_authorization_fails_before_consumption_or_secret_access() -> None:
    artifact, governance, trust = _build()
    raw = artifact.model_dump(mode="json")
    raw["execution_intent_hash"] = "0" * 64
    store = InMemoryAtomicAuthorizationConsumptionStore()
    resolver = _Resolver()

    with pytest.raises(
        LiveAdapterBindAuthorizationConsumptionError,
        match="LABAC_AUTHORIZATION_VERIFICATION_FAILED",
    ):
        await consume_live_adapter_bind_authorization_and_invoke_bind(
            raw,
            governance_inputs=governance,
            trust_inputs=trust,
            now=VERIFICATION_NOW,
            consumption_store=store,
            credential_resolver=resolver,
            authorization_header_constructor=_HeaderConstructor(),
            adapter_factory=_Factory(),
            append_trustlog=False,
        )
    assert resolver.calls == 0
    assert await store.get(artifact.live_adapter_bind_authorization_id) is None


@pytest.mark.asyncio
async def test_expired_authorization_fails_before_consumption() -> None:
    artifact, governance, trust = _build()
    store = InMemoryAtomicAuthorizationConsumptionStore()
    resolver = _Resolver()

    with pytest.raises(
        LiveAdapterBindAuthorizationConsumptionError,
        match="LABAC_AUTHORIZATION_VERIFICATION_FAILED",
    ):
        await consume_live_adapter_bind_authorization_and_invoke_bind(
            artifact,
            governance_inputs=governance,
            trust_inputs=trust,
            now=VERIFICATION_NOW + timedelta(days=1),
            consumption_store=store,
            credential_resolver=resolver,
            authorization_header_constructor=_HeaderConstructor(),
            adapter_factory=_Factory(),
            append_trustlog=False,
        )
    assert resolver.calls == 0


@pytest.mark.asyncio
async def test_failure_after_consumption_never_releases_authorization() -> None:
    artifact, governance, trust = _build()
    store = InMemoryAtomicAuthorizationConsumptionStore()
    failing = _Resolver(fail=True)

    with pytest.raises(
        LiveAdapterBindAuthorizationConsumptionError,
        match="LABAC_CREDENTIAL_RESOLUTION_FAILED_AFTER_CONSUMPTION",
    ):
        await consume_live_adapter_bind_authorization_and_invoke_bind(
            artifact,
            governance_inputs=governance,
            trust_inputs=trust,
            now=VERIFICATION_NOW,
            consumption_store=store,
            credential_resolver=failing,
            authorization_header_constructor=_HeaderConstructor(),
            adapter_factory=_Factory(),
            append_trustlog=False,
        )

    assert await store.get(artifact.live_adapter_bind_authorization_id) is not None
    second = _Resolver()
    with pytest.raises(
        LiveAdapterBindAuthorizationConsumptionError,
        match="LABAC_AUTHORIZATION_ALREADY_CONSUMED",
    ):
        await consume_live_adapter_bind_authorization_and_invoke_bind(
            artifact,
            governance_inputs=governance,
            trust_inputs=trust,
            now=VERIFICATION_NOW,
            consumption_store=store,
            credential_resolver=second,
            authorization_header_constructor=_HeaderConstructor(),
            adapter_factory=_Factory(),
            append_trustlog=False,
        )
    assert second.calls == 0


@pytest.mark.asyncio
async def test_in_memory_store_allows_only_one_concurrent_consumer() -> None:
    store = InMemoryAtomicAuthorizationConsumptionStore()
    record = build_authorization_consumption_record(
        live_adapter_bind_authorization_id="laba:v1:sha256:" + "1" * 64,
        live_adapter_bind_authorization_hash="1" * 64,
        idempotency_key="laba-idem:v1:sha256:" + "2" * 64,
        bind_context_hash="3" * 64,
        execution_intent_id="intent:one",
        execution_intent_hash="4" * 64,
        endpoint_identity_binding_digest="endpoint-digest",
        credential_reference_digest="credential-digest",
        credential_scope_binding_digest="scope-digest",
        consumed_at=VERIFICATION_NOW.isoformat(),
    )
    outcomes = await asyncio.gather(*(store.consume_once(record) for _ in range(20)))
    assert outcomes.count(True) == 1
    assert outcomes.count(False) == 19


def test_secret_material_and_header_repr_are_redacted() -> None:
    credential = ResolvedCredentialMaterial(
        credential_reference_id="ref",
        credential_kind="API_CREDENTIAL",
        credential_provider_type="LOCAL_REFERENCE",
        material=b"do-not-print-me",
    )
    header = ConstructedAuthorizationHeader(
        name="Authorization",
        value="Bearer do-not-print-me",
    )
    assert "do-not-print-me" not in repr(credential)
    assert "do-not-print-me" not in repr(header)
