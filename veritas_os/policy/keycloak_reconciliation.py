"""Recheck an archived Keycloak observation through a trusted read-only source."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
import json
from urllib.parse import urlsplit

from veritas_os.policy.bind_effect_reconciliation import (
    BindEffectStateError,
    EffectExecutionState,
    EffectStateRecord,
    PostgresAtomicEffectStateStore,
)
from veritas_os.policy.keycloak_dispatch_reservation import (
    KeycloakDispatchIntent,
    get_keycloak_dispatch_intent,
)
from veritas_os.policy.keycloak_reconciliation_observation import (
    KeycloakReconciliationObservation,
    get_keycloak_reconciliation_observation,
)
from veritas_os.policy.keycloak_role_grant_binding import verify_keycloak_role_grant_binding
from veritas_os.security.hash import sha256_of_canonical_json

AUDIT_PAGE_LIMIT = 100
_RECHECK_TIMEOUT_SECONDS = 5


def keycloak_reconciliation_policy_digest(writer_user: str, writer_client: str) -> str:
    """Bind the expected provider writer and verification rules into the approved intent."""
    return sha256_of_canonical_json({
        "profile": "keycloak-direct-role-and-audit/v1",
        "writer_user": writer_user,
        "writer_client": writer_client,
        "audit_page_limit": AUDIT_PAGE_LIMIT,
    })


def _match_audit_event(
    events: object,
    *,
    intent: KeycloakDispatchIntent,
    observation: KeycloakReconciliationObservation,
    reservation: EffectStateRecord,
    writer_user: str,
    writer_client: str,
) -> bool:
    if not isinstance(events, list) or len(events) >= AUDIT_PAGE_LIMIT:
        return False
    bound = verify_keycloak_role_grant_binding(
        target=intent.target, event_id=intent.event_id, attempt_id=intent.attempt_id,
        deployment_policy_digest=intent.deployment_policy_digest,
        approved_reference=intent.approved_reference,
    )
    payload = json.loads(bound.body)
    expected_roles = [{**payload[0], "composite": False}]
    resource_path = urlsplit(bound.endpoint_url).path.removeprefix(
        f"/admin/realms/{intent.target.realm_name}/",
    )
    start_ms = int(datetime.fromisoformat(reservation.updated_at).timestamp() * 1000)
    end_ms = int(observation.mapping_observed_at.timestamp() * 1000)
    matches = []
    for event in events:
        if not isinstance(event, dict):
            return False
        if (
            event.get("realmId") != intent.target.realm_id
            or event.get("resourcePath") != resource_path
            or event.get("operationType") != "CREATE"
            or event.get("resourceType") != "CLIENT_ROLE_MAPPING"
            or event.get("error")
        ):
            continue
        actor = event.get("authDetails")
        if not isinstance(actor, dict):
            return False
        if (
            actor.get("realmId") != intent.target.realm_id
            or actor.get("userId") != writer_user
            or actor.get("clientId") != writer_client
        ):
            continue
        try:
            roles = json.loads(event["representation"])
        except (KeyError, TypeError, ValueError):
            return False
        event_time = event.get("time")
        if roles == expected_roles:
            if type(event_time) is not int or not start_ms <= event_time <= end_ms:
                return False
            matches.append(event)
    return (
        len(matches) == 1
        and matches[0].get("id") == str(observation.audit_event_id)
        and sha256_of_canonical_json(matches[0]) == observation.audit_event_digest
    )


async def confirm_keycloak_reconciliation(
    operation_id: str,
    *,
    writer_user: str,
    writer_client: str,
    read_admin_events: Callable[[KeycloakDispatchIntent], Awaitable[object]],
    read_direct_mappings: Callable[[KeycloakDispatchIntent], Awaitable[object]],
) -> EffectStateRecord | None:
    """Confirm one reservation using read callbacks supplied by trusted application wiring.

    The callbacks must query the authenticated Keycloak target from the supplied
    intent and return complete, fresh results. This service has no provider
    write path. Absent, ambiguous, or mismatching evidence leaves the row pending.
    """
    if not writer_user or not writer_client:
        return None
    current = await PostgresAtomicEffectStateStore().get(operation_id)
    if current is None or current.state != EffectExecutionState.EFFECT_UNKNOWN:
        return None
    intent = await get_keycloak_dispatch_intent(operation_id)
    observation = await get_keycloak_reconciliation_observation(operation_id) if intent else None
    if (
        intent is None or observation is None
        or observation.reservation_record_hash != current.record_hash
        or observation.approved_reference != intent.approved_reference
        or str(observation.attempt_id) != intent.attempt_id
        or observation.mapping_observed_at > datetime.now(UTC)
        or intent.deployment_policy_digest != keycloak_reconciliation_policy_digest(
            writer_user, writer_client,
        )
    ):
        return None
    try:
        async with asyncio.timeout(_RECHECK_TIMEOUT_SECONDS):
            events = await read_admin_events(intent)
            if not _match_audit_event(
                events, intent=intent, observation=observation, reservation=current,
                writer_user=writer_user, writer_client=writer_client,
            ):
                return None
            mappings = await read_direct_mappings(intent)
    except Exception:
        return None

    role = {"id": intent.target.role_id, "name": intent.target.role_name}
    if (
        not isinstance(mappings, list)
        or mappings.count(role) != 1
        or observation.direct_mapping_digest != sha256_of_canonical_json(role)
    ):
        return None
    verified_at = datetime.now(UTC).isoformat()
    values = current.model_dump(mode="json", exclude={"record_hash"})
    values.update(
        state=EffectExecutionState.CONFIRMED_EFFECT.value,
        revision=current.revision + 1,
        updated_at=verified_at,
        reason_code="KEYCLOAK_AUDIT_AND_DIRECT_MAPPING_REVERIFIED",
        reconciliation_evidence_hash=sha256_of_canonical_json({
            "format_version": "keycloak-reconciliation-confirmation/v1",
            "operation_id": operation_id,
            "policy_digest": intent.deployment_policy_digest,
            "observation": observation.model_dump(mode="json"),
            "verified_at": verified_at,
        }),
    )
    record = EffectStateRecord(**values, record_hash=sha256_of_canonical_json(values))
    return await _commit_keycloak_confirmation(current, record, observation)


async def _commit_keycloak_confirmation(
    current: EffectStateRecord,
    record: EffectStateRecord,
    observation: KeycloakReconciliationObservation,
) -> EffectStateRecord | None:
    from psycopg.types.json import Jsonb
    from veritas_os.storage.db import get_pool

    try:
        pool = await get_pool()
        async with pool.connection() as conn:
            cursor = await conn.execute(
                "UPDATE bind_effect_states AS e "
                "SET state=%s, revision=%s, updated_at=%s, record_hash=%s, record=%s "
                "FROM bind_keycloak_dispatch_intents AS k "
                "WHERE k.operation_id=e.operation_id AND e.operation_id=%s "
                "AND e.state=%s AND e.revision=%s AND e.record_hash=%s "
                "AND e.record::jsonb=%s::jsonb AND e.reconciliation_archive IS NULL "
                "AND k.reconciliation_observation::jsonb=%s::jsonb RETURNING e.operation_id",
                (
                    record.state.value, record.revision, record.updated_at, record.record_hash,
                    Jsonb(record.model_dump(mode="json")), current.operation_id, current.state.value,
                    current.revision, current.record_hash, Jsonb(current.model_dump(mode="json")),
                    Jsonb(observation.model_dump(mode="json")),
                ),
            )
            committed = await cursor.fetchone() is not None
        return record if committed else None
    except Exception:
        raise BindEffectStateError("KGR_CONFIRMATION_COMMIT_FAILED") from None
