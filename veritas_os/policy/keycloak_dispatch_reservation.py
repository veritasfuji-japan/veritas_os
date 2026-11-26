"""Commit a Keycloak dispatch reservation and its restart inputs together."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal, TypedDict, Unpack

from pydantic import BaseModel, ConfigDict

from veritas_os.policy.bind_effect_reconciliation import (
    BindEffectStateError,
    EffectExecutionState,
    EffectStateRecord,
    KeycloakDispatchOrder,
    PostgresAtomicEffectStateStore,
    _build_record,
)
from veritas_os.policy.keycloak_role_grant_binding import (
    ACTION,
    REFERENCE_PREFIX,
    KeycloakRoleGrantBinding,
    KeycloakRoleGrantTarget,
    verify_keycloak_role_grant_binding,
)
from veritas_os.policy.live_adapter_bind_authorization_contracts import (
    BindAuthorizationTrustInputs,
    RealBindAuthorizationGovernanceInputs,
)
from veritas_os.policy.live_adapter_bind_authorization_consumption_store import (
    AuthorizationConsumptionRecord,
    PostgresAtomicAuthorizationConsumptionStore,
    build_authorization_consumption_record,
)
from veritas_os.policy.native_bind_authorization import (
    NativeAuthorizationSourceInputs,
    NativeBindAuthorizationArtifact,
    _verified_source,
    verify_native_bind_authorization,
)
from veritas_os.storage import sandbox_restore


class KeycloakDispatchIntent(BaseModel):
    """Non-secret, versioned original request parameters and authorization lineage."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    format_version: Literal["keycloak-dispatch-intent/v1"] = "keycloak-dispatch-intent/v1"
    target: KeycloakRoleGrantTarget
    event_id: str
    attempt_id: str
    deployment_policy_digest: str
    approved_reference: str
    endpoint_url: str
    body_digest: str
    business_event_key: str
    authorization_id: str
    authorization_hash: str
    execution_intent_hash: str


class KeycloakAuthorizationInputs(TypedDict):
    """Signed, deployment-bound inputs shared by preparation and cancellation."""

    target: KeycloakRoleGrantTarget
    event_id: str
    attempt_id: str
    deployment_policy_digest: str
    authorization: Any
    source_inputs: NativeAuthorizationSourceInputs
    governance_inputs: RealBindAuthorizationGovernanceInputs
    trust_inputs: BindAuthorizationTrustInputs


class _KeycloakReservationInputs(KeycloakAuthorizationInputs):
    consumption: AuthorizationConsumptionRecord


def _verify_keycloak_dispatch(
    *,
    target: KeycloakRoleGrantTarget,
    event_id: str,
    attempt_id: str,
    deployment_policy_digest: str,
    authorization: Any,
    source_inputs: NativeAuthorizationSourceInputs,
    governance_inputs: RealBindAuthorizationGovernanceInputs,
    trust_inputs: BindAuthorizationTrustInputs,
) -> tuple[NativeBindAuthorizationArtifact, KeycloakRoleGrantBinding]:
    verified = verify_native_bind_authorization(
        authorization, source_inputs=source_inputs, governance_inputs=governance_inputs,
        trust_inputs=trust_inputs,
    )
    intent = verified.execution_intent
    refs = [
        ref for ref in intent["evidence_refs"]
        if isinstance(ref, str) and ref.startswith(REFERENCE_PREFIX)
    ]
    if intent.get("intended_action") != ACTION or len(refs) != 1:
        raise BindEffectStateError("KGR_SIGNED_REFERENCE_REQUIRED")
    binding = verify_keycloak_role_grant_binding(
        target=target, event_id=event_id, attempt_id=attempt_id,
        deployment_policy_digest=deployment_policy_digest, approved_reference=refs[0],
    )
    if intent.get("target_resource") != binding.endpoint_url:
        raise BindEffectStateError("KGR_SIGNED_TARGET_MISMATCH")
    return verified, binding


async def reserve_keycloak_dispatch(
    *,
    target: KeycloakRoleGrantTarget,
    event_id: str,
    attempt_id: str,
    deployment_policy_digest: str,
    authorization: Any,
    source_inputs: NativeAuthorizationSourceInputs,
    governance_inputs: RealBindAuthorizationGovernanceInputs,
    trust_inputs: BindAuthorizationTrustInputs,
    consumption: AuthorizationConsumptionRecord,
) -> EffectStateRecord | None:
    """Reserve only the request and consumption from the verified native grant.

    The executor remains responsible for fresh governance and dispatch checks.
    A durable intent is a recovery input, never permission to send on restart.
    """
    verified, binding = _verify_keycloak_dispatch(
        target=target, event_id=event_id, attempt_id=attempt_id,
        deployment_policy_digest=deployment_policy_digest, authorization=authorization,
        source_inputs=source_inputs, governance_inputs=governance_inputs, trust_inputs=trust_inputs,
    )
    _, _, context = _verified_source(
        verified.source_runtime_risk_packet, source_inputs, governance_inputs,
    )
    expected = build_authorization_consumption_record(
        live_adapter_bind_authorization_id=verified.authorization_id,
        live_adapter_bind_authorization_hash=verified.authorization_hash,
        idempotency_key=verified.idempotency_key,
        bind_context_hash=verified.bind_context_hash,
        execution_intent_id=verified.execution_intent_id,
        execution_intent_hash=verified.execution_intent_hash,
        endpoint_identity_binding_digest=context.endpoint_identity_binding_digest,
        credential_reference_digest=context.credential_reference_digest,
        credential_scope_binding_digest=context.credential_scope_binding_digest,
        consumed_at=consumption.consumed_at,
    )
    if consumption != expected:
        raise BindEffectStateError("KGR_CONSUMPTION_LINEAGE_MISMATCH")

    if await PostgresAtomicAuthorizationConsumptionStore().get(verified.authorization_id) != expected:
        return None
    record = _build_record(
        consumption=expected,
        state=EffectExecutionState.EFFECT_UNKNOWN,
        revision=1,
        updated_at=datetime.now(UTC).isoformat(),
        reason_code="KEYCLOAK_DISPATCH_INTENT_PERSISTED_EFFECT_UNCONFIRMED",
    )
    durable_intent = KeycloakDispatchIntent(
        target=target, event_id=event_id, attempt_id=attempt_id,
        deployment_policy_digest=deployment_policy_digest, approved_reference=binding.reference,
        endpoint_url=binding.endpoint_url, body_digest=binding.body_digest,
        business_event_key=binding.business_event_key,
        authorization_id=verified.authorization_id, authorization_hash=verified.authorization_hash,
        execution_intent_hash=verified.execution_intent_hash,
    )
    if await PostgresAtomicEffectStateStore().reserve_dispatch_intent(
        record, business_event_key=binding.business_event_key,
        keycloak_intent=durable_intent.model_dump(mode="json"),
    ):
        return record
    return None


async def revoke_keycloak_authorization(
    **inputs: Unpack[KeycloakAuthorizationInputs],
) -> KeycloakDispatchOrder:
    """Order a trusted control-plane cancellation of a verified Keycloak grant.

    The signed issuance and its request binding establish scope before any
    consumption or reservation. This internal function is not an operator API.
    """
    from veritas_os.storage.db import get_pool

    verified, _ = _verify_keycloak_dispatch(**inputs)
    try:
        pool = await get_pool()
        async with pool.connection() as conn:
            await conn.execute(sandbox_restore.LOCK_SHARED)
            recovery = await conn.execute(sandbox_restore.RECOVERY_PENDING)
            if await recovery.fetchone() != (False,):
                raise BindEffectStateError("KGR_RESTORE_RECOVERY_PENDING")
            cursor = await conn.execute(
                """INSERT INTO bind_sandbox_dispatch_order AS ordering (authorization_id, resolution)
                   VALUES (%s, %s)
                   ON CONFLICT (authorization_id) DO UPDATE SET resolution =
                       CASE WHEN ordering.resolution = %s THEN ordering.resolution ELSE EXCLUDED.resolution END
                   WHERE ordering.resolution IN (%s, %s, %s)
                   RETURNING ordering.resolution""",
                (
                    verified.authorization_id, KeycloakDispatchOrder.REVOKED.value,
                    KeycloakDispatchOrder.COMMITTED.value, KeycloakDispatchOrder.RESERVED.value,
                    KeycloakDispatchOrder.REVOKED.value, KeycloakDispatchOrder.COMMITTED.value,
                ),
            )
            row = await cursor.fetchone()
            if row is None:
                raise BindEffectStateError("KGR_REVOCATION_SCOPE_MISMATCH")
            result = KeycloakDispatchOrder(row[0])
        return result
    except BindEffectStateError:
        raise
    except Exception:
        raise BindEffectStateError("KGR_REVOCATION_FAILED_OR_UNKNOWN") from None


async def reserve_and_commit_keycloak_dispatch(
    **inputs: Unpack[_KeycloakReservationInputs],
) -> EffectStateRecord | None:
    """Reserve a fresh attempt and commit its place in the ordering.

    Only a reservation acknowledged to this call can be committed here.
    Recovery has no entry point for resuming an existing reservation. This
    records DB ordering only. The future executor owns fresh governance,
    connection and transport checks. No credentials or network are used here.
    """
    from veritas_os.storage.db import get_pool

    record = await reserve_keycloak_dispatch(**inputs)
    if record is None:
        return None
    try:
        pool = await get_pool()
        async with pool.connection() as conn:
            await conn.execute(sandbox_restore.LOCK_SHARED)
            recovery = await conn.execute(sandbox_restore.RECOVERY_PENDING)
            if await recovery.fetchone() != (False,):
                return None
            cursor = await conn.execute(
                """UPDATE bind_sandbox_dispatch_order
                   SET resolution = %s
                   WHERE authorization_id = %s AND resolution = %s
                   AND EXISTS (
                       SELECT 1 FROM bind_effect_states AS effect
                       JOIN bind_keycloak_dispatch_intents USING (operation_id)
                       WHERE effect.operation_id = %s
                         AND effect.authorization_id = %s
                         AND effect.record_hash = %s
                         AND effect.state = 'EFFECT_UNKNOWN'
                         AND effect.revision = 1
                       FOR UPDATE OF effect
                   )
                   RETURNING authorization_id""",
                (
                    KeycloakDispatchOrder.COMMITTED.value, record.authorization_id,
                    KeycloakDispatchOrder.RESERVED.value, record.operation_id,
                    record.authorization_id, record.record_hash,
                ),
            )
            applied = await cursor.fetchone() is not None
        return record if applied else None
    except Exception:
        raise BindEffectStateError("KGR_DISPATCH_COMMIT_FAILED_OR_UNKNOWN") from None


async def get_keycloak_dispatch_intent(operation_id: str) -> KeycloakDispatchIntent | None:
    """Rebuild the persisted request and check its effect and consumption lineage."""
    from veritas_os.storage.db import get_pool

    try:
        pool = await get_pool()
        async with pool.connection() as conn:
            cursor = await conn.execute(
                "SELECT k.intent, e.business_event_key, e.authorization_id, "
                "e.authorization_hash, c.execution_intent_hash "
                "FROM bind_keycloak_dispatch_intents k "
                "JOIN bind_effect_states e USING (operation_id) "
                "LEFT JOIN bind_authorization_consumptions c "
                "ON c.consumption_id=e.consumption_id AND c.consumption_hash=e.consumption_hash "
                "AND c.authorization_id=e.authorization_id "
                "AND c.authorization_hash=e.authorization_hash "
                "AND c.execution_intent_id=e.execution_intent_id "
                "AND c.idempotency_key=e.idempotency_key "
                "WHERE k.operation_id=%s",
                (operation_id,),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        intent = KeycloakDispatchIntent.model_validate(row[0])
        binding = verify_keycloak_role_grant_binding(
            target=intent.target, event_id=intent.event_id, attempt_id=intent.attempt_id,
            deployment_policy_digest=intent.deployment_policy_digest,
            approved_reference=intent.approved_reference,
        )
        if row[1:] != (
            intent.business_event_key, intent.authorization_id, intent.authorization_hash,
            intent.execution_intent_hash,
        ) or (binding.business_event_key, binding.endpoint_url, binding.body_digest) != (
            intent.business_event_key, intent.endpoint_url, intent.body_digest,
        ):
            raise ValueError("stored request lineage mismatch")
    except Exception:
        raise BindEffectStateError("KGR_DISPATCH_INTENT_READ_FAILED") from None
    return intent
