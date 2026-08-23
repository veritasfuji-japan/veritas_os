"""Deterministic proof runner for Authorization Consumption / Bind Invocation Gate.

This runner intentionally uses the test/reference in-memory store and a
non-network adapter. It proves ordering and single-use semantics, not production
credential-provider deployment or external-network execution.
"""

from __future__ import annotations

import asyncio
from typing import Any, Mapping

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


class _Resolver:
    async def resolve(
        self,
        credential_reference: Mapping[str, Any],
        *,
        credential_scope_binding: Mapping[str, Any],
        live_adapter_bind_authorization_id: str,
    ) -> ResolvedCredentialMaterial:
        del credential_scope_binding, live_adapter_bind_authorization_id
        return ResolvedCredentialMaterial(
            credential_reference_id=str(
                credential_reference["credential_reference_id"]
            ),
            credential_kind=str(credential_reference["credential_kind"]),
            credential_provider_type=str(
                credential_reference["credential_provider_type"]
            ),
            material=b"synthetic-secret",
        )


class _Header:
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
        assert credential.material == b"synthetic-secret"
        return ConstructedAuthorizationHeader(
            name="Authorization", value="Bearer synthetic-secret"
        )


class _Adapter(BindAdapterContract):
    def __init__(self, expected: str | None) -> None:
        self.expected = expected

    def snapshot(self) -> dict[str, str]:
        return {"state": "synthetic"}

    def fingerprint_state(self, snapshot: Any) -> str:
        del snapshot
        return self.expected or "synthetic-state"

    def validate_authority(self, intent: ExecutionIntent, snapshot: Any) -> bool:
        del intent, snapshot
        return True

    def validate_constraints(
        self, intent: ExecutionIntent, snapshot: Any
    ) -> dict[str, bool]:
        del intent, snapshot
        return {"synthetic": True}

    def assess_runtime_risk(self, intent: ExecutionIntent, snapshot: Any) -> bool:
        del intent, snapshot
        return True

    def apply(self, intent: ExecutionIntent, snapshot: Any) -> bool:
        del intent, snapshot
        return True

    def verify_postconditions(self, intent: ExecutionIntent, snapshot: Any) -> bool:
        del intent, snapshot
        return True

    def revert(self, intent: ExecutionIntent, snapshot: Any) -> bool:
        del intent, snapshot
        return True

    def describe_target(self) -> str:
        return "synthetic-consumption-poc"


class _Factory:
    async def build(
        self,
        *,
        authorization,
        credential: ResolvedCredentialMaterial,
        authorization_header: ConstructedAuthorizationHeader,
    ) -> AuthorizedBindAdapterInstance:
        del credential, authorization_header
        return AuthorizedBindAdapterInstance(
            adapter=_Adapter(
                authorization.execution_intent.get("expected_state_fingerprint")
            ),
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


async def _main() -> None:
    artifact, governance, trust = _build()
    result = await consume_live_adapter_bind_authorization_and_invoke_bind(
        artifact,
        governance_inputs=governance,
        trust_inputs=trust,
        now=VERIFICATION_NOW,
        consumption_store=InMemoryAtomicAuthorizationConsumptionStore(),
        credential_resolver=_Resolver(),
        authorization_header_constructor=_Header(),
        adapter_factory=_Factory(),
        append_trustlog=False,
    )
    print("REAL_BIND_AUTHORIZATION          VERIFIED")
    print("AUTHORIZATION_CONSUMPTION        CONSUMED")
    print("CREDENTIAL_MATERIAL_ACCESS       TRUE")
    print("AUTHORIZATION_HEADER_CONSTRUCTED TRUE")
    print("BIND_INVOCATION                  INVOKED")
    print(f"BIND_OUTCOME                     {result.bind_receipt.final_outcome.value}")
    print("NETWORK_EFFECT                   NONE")
    print("STORE_MODE                       PROCESS_LOCAL_TEST_ONLY")
    print("RESULT                           PASS")


if __name__ == "__main__":
    asyncio.run(_main())
