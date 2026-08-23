"""Invocation-semantics tests for the authorization consumption gate."""

from __future__ import annotations

from typing import Any

import pytest

from veritas_os.policy.bind_artifacts import ExecutionIntent
from veritas_os.policy.bind_core.contracts import BindAdapterContract
from veritas_os.policy.live_adapter_bind_authorization_consumption import (
    AuthorizedBindAdapterInstance,
    ConstructedAuthorizationHeader,
    ResolvedCredentialMaterial,
    consume_live_adapter_bind_authorization_and_invoke_bind,
)
from veritas_os.policy.live_adapter_bind_authorization_consumption_store import (
    InMemoryAtomicAuthorizationConsumptionStore,
)
from veritas_os.tests.test_live_adapter_bind_authorization import (
    VERIFICATION_NOW,
    _build,
)
from veritas_os.tests.test_live_adapter_bind_authorization_consumption import (
    _Factory,
    _HeaderConstructor,
    _Resolver,
)


class _BlockedBeforeApplyAdapter(BindAdapterContract):
    """Adapter whose bind-time authority check blocks before ``apply``."""

    def __init__(self, expected_fingerprint: str | None) -> None:
        self.expected_fingerprint = expected_fingerprint
        self.apply_calls = 0

    def snapshot(self) -> dict[str, str]:
        return {"state": "before"}

    def fingerprint_state(self, snapshot: Any) -> str:
        del snapshot
        return self.expected_fingerprint or "live-state"

    def validate_authority(self, intent: ExecutionIntent, snapshot: Any) -> bool:
        del intent, snapshot
        return False

    def validate_constraints(
        self,
        intent: ExecutionIntent,
        snapshot: Any,
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
        return "blocked-before-apply"


class _BlockedFactory:
    def __init__(self) -> None:
        self.adapter: _BlockedBeforeApplyAdapter | None = None

    async def build(
        self,
        *,
        authorization,
        credential: ResolvedCredentialMaterial,
        authorization_header: ConstructedAuthorizationHeader,
    ) -> AuthorizedBindAdapterInstance:
        del credential, authorization_header
        self.adapter = _BlockedBeforeApplyAdapter(
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
async def test_committed_bind_reports_core_entry_and_apply_attempt() -> None:
    artifact, governance, trust = _build()
    factory = _Factory()

    result = await consume_live_adapter_bind_authorization_and_invoke_bind(
        artifact,
        governance_inputs=governance,
        trust_inputs=trust,
        now=VERIFICATION_NOW,
        consumption_store=InMemoryAtomicAuthorizationConsumptionStore(),
        credential_resolver=_Resolver(),
        authorization_header_constructor=_HeaderConstructor(),
        adapter_factory=factory,
        append_trustlog=False,
    )

    assert result.bind_core_invoked is True
    assert result.adapter_apply_attempted is True
    assert result.bind_invoked is True
    assert factory.adapter is not None
    assert factory.adapter.apply_calls == 1


@pytest.mark.asyncio
async def test_blocked_bind_reports_core_entry_without_apply_attempt() -> None:
    artifact, governance, trust = _build()
    factory = _BlockedFactory()

    result = await consume_live_adapter_bind_authorization_and_invoke_bind(
        artifact,
        governance_inputs=governance,
        trust_inputs=trust,
        now=VERIFICATION_NOW,
        consumption_store=InMemoryAtomicAuthorizationConsumptionStore(),
        credential_resolver=_Resolver(),
        authorization_header_constructor=_HeaderConstructor(),
        adapter_factory=factory,
        append_trustlog=False,
    )

    assert result.authorization_consumed is True
    assert result.bind_core_invoked is True
    assert result.adapter_apply_attempted is False
    assert result.bind_receipt.final_outcome.value == "BLOCKED"
    assert factory.adapter is not None
    assert factory.adapter.apply_calls == 0
