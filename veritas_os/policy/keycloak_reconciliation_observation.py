"""Persist the first positive Keycloak reconciliation observation for a reservation."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from veritas_os.policy.bind_effect_reconciliation import BindEffectStateError, EffectExecutionState

_SHA256 = r"^[0-9a-f]{64}$"


class KeycloakReconciliationObservation(BaseModel):
    """Point-in-time observation supplied by a trusted Keycloak reader."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format_version: Literal["keycloak-reconciliation-observation/v1"] = (
        "keycloak-reconciliation-observation/v1"
    )
    reservation_record_hash: str = Field(pattern=_SHA256)
    approved_reference: str = Field(pattern=r"^keycloak-client-role-grant:v1:sha256:[0-9a-f]{64}$")
    attempt_id: UUID
    audit_event_id: UUID
    audit_event_digest: str = Field(pattern=_SHA256)
    direct_mapping_digest: str = Field(pattern=_SHA256)
    mapping_observed_at: AwareDatetime


async def archive_keycloak_reconciliation_observation(
    operation_id: str, observation: KeycloakReconciliationObservation,
) -> bool:
    """Save one positive observation against the original pending reservation.

    The caller verifies the unique successful audit event and the current direct
    mapping before archiving. This archive has no effect-state transition or
    dispatch authority. A false result includes a prior committed observation,
    so a retry can read the winning record.
    """
    from psycopg.types.json import Jsonb
    from veritas_os.storage.db import get_pool

    try:
        pool = await get_pool()
        async with pool.connection() as conn:
            cursor = await conn.execute(
                "WITH pending AS ("
                "SELECT operation_id FROM bind_effect_states "
                "WHERE operation_id=%s AND state=%s AND record_hash=%s FOR SHARE"
                ") UPDATE bind_keycloak_dispatch_intents AS k "
                "SET reconciliation_observation=%s "
                "FROM pending WHERE pending.operation_id=k.operation_id "
                "AND k.intent->>'approved_reference'=%s AND k.intent->>'attempt_id'=%s "
                "AND k.reconciliation_observation IS NULL RETURNING k.operation_id",
                (
                    operation_id,
                    EffectExecutionState.EFFECT_UNKNOWN.value,
                    observation.reservation_record_hash,
                    Jsonb(observation.model_dump(mode="json")),
                    observation.approved_reference,
                    str(observation.attempt_id),
                ),
            )
            inserted = await cursor.fetchone() is not None
        return inserted
    except Exception:
        raise BindEffectStateError("KGR_OBSERVATION_ARCHIVE_FAILED") from None


async def get_keycloak_reconciliation_observation(
    operation_id: str,
) -> KeycloakReconciliationObservation | None:
    """Read the historical observation, checking its dispatch-intent lineage."""
    from veritas_os.storage.db import get_pool

    try:
        pool = await get_pool()
        async with pool.connection() as conn:
            cursor = await conn.execute(
                "SELECT reconciliation_observation, intent->>'approved_reference', "
                "intent->>'attempt_id' FROM bind_keycloak_dispatch_intents WHERE operation_id=%s",
                (operation_id,),
            )
            row = await cursor.fetchone()
        if row is None or row[0] is None:
            return None
        observation = KeycloakReconciliationObservation.model_validate(row[0])
        if (observation.approved_reference, str(observation.attempt_id)) != row[1:]:
            raise ValueError("stored observation lineage mismatch")
    except Exception:
        raise BindEffectStateError("KGR_OBSERVATION_READ_FAILED") from None
    return observation
