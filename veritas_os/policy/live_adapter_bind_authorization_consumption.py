"""Authorization Consumption / Bind Invocation Gate v1.

This is the first boundary allowed to consume a signed Real Bind Authorization,
resolve credential material, construct an Authorization header, instantiate an
adapter, and invoke Bind. Consumption happens atomically before any secret
access or effectful adapter construction. A consumed authorization is never
released or made reusable after a downstream failure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol

from veritas_os.policy.bind_artifacts import BindReceipt, ExecutionIntent, hash_execution_intent
from veritas_os.policy.bind_core.contracts import BindAdapterContract
from veritas_os.policy.bind_core.core import execute_bind_adjudication
from veritas_os.policy.bind_core.normalizers import normalize_execution_intent
from veritas_os.policy.live_adapter_bind_authorization import (
    BindAuthorizationTrustInputs,
    CanonicalLiveAdapterBindAuthorizationArtifact,
    LiveAdapterBindAuthorizationError,
    RealBindAuthorizationGovernanceInputs,
    validate_live_adapter_bind_authorization_temporal_validity,
)
from veritas_os.policy.live_adapter_bind_authorization_consumption_store import (
    AtomicAuthorizationConsumptionStore,
    AuthorizationConsumptionRecord,
    AuthorizationConsumptionStoreError,
    build_authorization_consumption_record,
)


class LiveAdapterBindAuthorizationConsumptionError(RuntimeError):
    """Stable fail-closed error at authorization consumption / Bind invocation."""


@dataclass(frozen=True, repr=False)
class ResolvedCredentialMaterial:
    """Ephemeral secret material returned by an injected credential resolver."""

    credential_reference_id: str
    credential_kind: str
    credential_provider_type: str
    material: bytes = field(repr=False)

    def __repr__(self) -> str:
        return (
            "ResolvedCredentialMaterial(credential_reference_id="
            f"{self.credential_reference_id!r}, credential_kind={self.credential_kind!r}, "
            f"credential_provider_type={self.credential_provider_type!r}, material=<redacted>)"
        )


@dataclass(frozen=True, repr=False)
class ConstructedAuthorizationHeader:
    """Ephemeral Authorization header; the value is never serialized by the gate."""

    name: str
    value: str = field(repr=False)

    def __repr__(self) -> str:
        return f"ConstructedAuthorizationHeader(name={self.name!r}, value=<redacted>)"


@dataclass(frozen=True)
class AuthorizedBindAdapterInstance:
    """Adapter plus exact non-secret bindings checked before Bind invocation."""

    adapter: BindAdapterContract = field(repr=False)
    adapter_contract_id: str
    adapter_contract_hash: str
    endpoint_identity_binding_digest: str
    credential_reference_digest: str
    credential_scope_binding_digest: str


class CredentialMaterialResolver(Protocol):
    async def resolve(
        self,
        credential_reference: Mapping[str, Any],
        *,
        credential_scope_binding: Mapping[str, Any],
        live_adapter_bind_authorization_id: str,
    ) -> ResolvedCredentialMaterial:
        ...


class AuthorizationHeaderConstructor(Protocol):
    async def construct(
        self,
        credential: ResolvedCredentialMaterial,
        *,
        credential_reference: Mapping[str, Any],
        credential_scope_binding: Mapping[str, Any],
        live_adapter_bind_authorization_id: str,
    ) -> ConstructedAuthorizationHeader:
        ...


class AuthorizedBindAdapterFactory(Protocol):
    async def build(
        self,
        *,
        authorization: CanonicalLiveAdapterBindAuthorizationArtifact,
        credential: ResolvedCredentialMaterial,
        authorization_header: ConstructedAuthorizationHeader,
    ) -> AuthorizedBindAdapterInstance:
        ...


@dataclass(frozen=True)
class BindAuthorizationConsumptionResult:
    """Non-secret evidence returned after one consumed Bind attempt."""

    consumption_record: AuthorizationConsumptionRecord
    bind_receipt: BindReceipt
    authorization_consumed: bool = True
    credential_material_accessed: bool = True
    authorization_header_constructed: bool = True
    bind_invoked: bool = True


def _timestamp(value: datetime | str) -> str:
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            raise LiveAdapterBindAuthorizationConsumptionError(
                "LABAC_TIMESTAMP_INVALID"
            ) from None
    if parsed.tzinfo is None:
        raise LiveAdapterBindAuthorizationConsumptionError("LABAC_TIMESTAMP_NAIVE")
    return parsed.astimezone(timezone.utc).isoformat()


def _validated_execution_intent(
    authorization: CanonicalLiveAdapterBindAuthorizationArtifact,
) -> ExecutionIntent:
    try:
        intent = normalize_execution_intent(authorization.execution_intent)
    except (TypeError, ValueError):
        raise LiveAdapterBindAuthorizationConsumptionError(
            "LABAC_EXECUTION_INTENT_INVALID"
        ) from None
    if (
        intent.execution_intent_id != authorization.execution_intent_id
        or hash_execution_intent(intent) != authorization.execution_intent_hash
    ):
        raise LiveAdapterBindAuthorizationConsumptionError(
            "LABAC_EXECUTION_INTENT_BINDING_MISMATCH"
        )
    return intent


def _validate_credential(
    authorization: CanonicalLiveAdapterBindAuthorizationArtifact,
    credential: ResolvedCredentialMaterial,
) -> None:
    reference = authorization.credential_reference
    if (
        credential.credential_reference_id != reference.get("credential_reference_id")
        or credential.credential_kind != reference.get("credential_kind")
        or credential.credential_provider_type != reference.get("credential_provider_type")
        or not isinstance(credential.material, bytes)
        or not credential.material
    ):
        raise LiveAdapterBindAuthorizationConsumptionError(
            "LABAC_RESOLVED_CREDENTIAL_BINDING_MISMATCH"
        )


def _validate_authorization_header(header: ConstructedAuthorizationHeader) -> None:
    if header.name.strip().lower() != "authorization":
        raise LiveAdapterBindAuthorizationConsumptionError(
            "LABAC_AUTHORIZATION_HEADER_NAME_INVALID"
        )
    if not header.value or "\r" in header.value or "\n" in header.value:
        raise LiveAdapterBindAuthorizationConsumptionError(
            "LABAC_AUTHORIZATION_HEADER_VALUE_INVALID"
        )


def _validate_adapter_binding(
    authorization: CanonicalLiveAdapterBindAuthorizationArtifact,
    built: AuthorizedBindAdapterInstance,
) -> None:
    expected = (
        authorization.adapter_contract_id,
        authorization.adapter_contract_hash,
        authorization.endpoint_identity_binding_digest,
        authorization.credential_reference_digest,
        authorization.credential_scope_binding_digest,
    )
    actual = (
        built.adapter_contract_id,
        built.adapter_contract_hash,
        built.endpoint_identity_binding_digest,
        built.credential_reference_digest,
        built.credential_scope_binding_digest,
    )
    if actual != expected:
        raise LiveAdapterBindAuthorizationConsumptionError(
            "LABAC_ADAPTER_BINDING_MISMATCH"
        )


async def consume_live_adapter_bind_authorization_and_invoke_bind(
    artifact: Any,
    *,
    governance_inputs: RealBindAuthorizationGovernanceInputs,
    trust_inputs: BindAuthorizationTrustInputs,
    now: datetime | str,
    consumption_store: AtomicAuthorizationConsumptionStore,
    credential_resolver: CredentialMaterialResolver,
    authorization_header_constructor: AuthorizationHeaderConstructor,
    adapter_factory: AuthorizedBindAdapterFactory,
    append_trustlog: bool = True,
    bind_ts: str | None = None,
) -> BindAuthorizationConsumptionResult:
    """Verify, consume once, access secrets, construct auth, then invoke Bind.

    Ordering is security critical:
      1. full authorization + temporal verification;
      2. exact ExecutionIntent reconstruction;
      3. atomic single-use consumption;
      4. credential resolution;
      5. Authorization-header construction;
      6. exact adapter binding validation;
      7. Bind invocation.

    Any failure after step 3 leaves the authorization consumed.
    """
    current = _timestamp(now)
    try:
        authorization = validate_live_adapter_bind_authorization_temporal_validity(
            artifact,
            now=current,
            governance_inputs=governance_inputs,
            trust_inputs=trust_inputs,
        )
    except LiveAdapterBindAuthorizationError:
        raise LiveAdapterBindAuthorizationConsumptionError(
            "LABAC_AUTHORIZATION_VERIFICATION_FAILED"
        ) from None

    intent = _validated_execution_intent(authorization)
    if (
        not authorization.single_use
        or not authorization.authorization_consumption_required
        or not authorization.replay_protection_required
        or not authorization.duplicate_dispatch_prohibited
        or authorization.authorization_consumption_state != "NOT_CONSUMED"
        or authorization.bind_invocation_state != "NOT_INVOKED"
    ):
        raise LiveAdapterBindAuthorizationConsumptionError(
            "LABAC_AUTHORIZATION_NOT_CONSUMABLE"
        )

    record = build_authorization_consumption_record(
        live_adapter_bind_authorization_id=authorization.live_adapter_bind_authorization_id,
        live_adapter_bind_authorization_hash=authorization.live_adapter_bind_authorization_hash,
        idempotency_key=authorization.idempotency_key,
        bind_context_hash=authorization.bind_context_hash,
        execution_intent_id=authorization.execution_intent_id,
        execution_intent_hash=authorization.execution_intent_hash,
        endpoint_identity_binding_digest=authorization.endpoint_identity_binding_digest,
        credential_reference_digest=authorization.credential_reference_digest,
        credential_scope_binding_digest=authorization.credential_scope_binding_digest,
        consumed_at=current,
    )
    try:
        claimed = await consumption_store.consume_once(record)
    except AuthorizationConsumptionStoreError:
        raise LiveAdapterBindAuthorizationConsumptionError(
            "LABAC_CONSUMPTION_STORE_FAILED"
        ) from None
    if not claimed:
        raise LiveAdapterBindAuthorizationConsumptionError(
            "LABAC_AUTHORIZATION_ALREADY_CONSUMED"
        )

    try:
        credential = await credential_resolver.resolve(
            authorization.credential_reference,
            credential_scope_binding=authorization.credential_scope_binding,
            live_adapter_bind_authorization_id=authorization.live_adapter_bind_authorization_id,
        )
    except Exception:
        raise LiveAdapterBindAuthorizationConsumptionError(
            "LABAC_CREDENTIAL_RESOLUTION_FAILED_AFTER_CONSUMPTION"
        ) from None
    _validate_credential(authorization, credential)

    try:
        header = await authorization_header_constructor.construct(
            credential,
            credential_reference=authorization.credential_reference,
            credential_scope_binding=authorization.credential_scope_binding,
            live_adapter_bind_authorization_id=authorization.live_adapter_bind_authorization_id,
        )
    except Exception:
        raise LiveAdapterBindAuthorizationConsumptionError(
            "LABAC_AUTHORIZATION_HEADER_CONSTRUCTION_FAILED_AFTER_CONSUMPTION"
        ) from None
    _validate_authorization_header(header)

    try:
        built = await adapter_factory.build(
            authorization=authorization,
            credential=credential,
            authorization_header=header,
        )
    except Exception:
        raise LiveAdapterBindAuthorizationConsumptionError(
            "LABAC_ADAPTER_CONSTRUCTION_FAILED_AFTER_CONSUMPTION"
        ) from None
    _validate_adapter_binding(authorization, built)

    receipt = execute_bind_adjudication(
        execution_intent=intent,
        adapter=built.adapter,
        bind_ts=bind_ts or current,
        append_trustlog=append_trustlog,
    )
    return BindAuthorizationConsumptionResult(
        consumption_record=record,
        bind_receipt=receipt,
    )


__all__ = [
    "AuthorizationHeaderConstructor",
    "AuthorizedBindAdapterFactory",
    "AuthorizedBindAdapterInstance",
    "BindAuthorizationConsumptionResult",
    "ConstructedAuthorizationHeader",
    "CredentialMaterialResolver",
    "LiveAdapterBindAuthorizationConsumptionError",
    "ResolvedCredentialMaterial",
    "consume_live_adapter_bind_authorization_and_invoke_bind",
]
