"""Persist Keycloak dispatch intent using the shared PostgreSQL effect store."""

from __future__ import annotations

from datetime import UTC, datetime

from veritas_os.policy.bind_effect_reconciliation import (
    EffectExecutionState,
    EffectStateRecord,
    PostgresAtomicEffectStateStore,
    _build_record,
)
from veritas_os.policy.keycloak_role_grant_binding import (
    KeycloakRoleGrantTarget,
    verify_keycloak_role_grant_binding,
)
from veritas_os.policy.live_adapter_bind_authorization_consumption_store import (
    AuthorizationConsumptionRecord,
)


async def reserve_keycloak_dispatch(
    *,
    target: KeycloakRoleGrantTarget,
    event_id: str,
    attempt_id: str,
    deployment_policy_digest: str,
    approved_reference: str,
    consumption: AuthorizationConsumptionRecord,
) -> EffectStateRecord | None:
    """Reserve the verified event and record possible dispatch in one transaction.

    The executor supplies the reference and consumption from the same verified
    intent, after authorization, freshness, and current-policy checks. This
    function is a persistence step and does not confer permission to send.
    Only the successful insert returns a record. A conflict returns None;
    a database exception must stop dispatch even if the row was committed.
    """
    binding = verify_keycloak_role_grant_binding(
        target=target,
        event_id=event_id,
        attempt_id=attempt_id,
        deployment_policy_digest=deployment_policy_digest,
        approved_reference=approved_reference,
    )
    record = _build_record(
        consumption=consumption,
        state=EffectExecutionState.EFFECT_UNKNOWN,
        revision=1,
        updated_at=datetime.now(UTC).isoformat(),
        reason_code="KEYCLOAK_DISPATCH_INTENT_PERSISTED_EFFECT_UNCONFIRMED",
    )
    if await PostgresAtomicEffectStateStore().reserve_dispatch_intent(
        record, business_event_key=binding.business_event_key,
    ):
        return record
    return None
