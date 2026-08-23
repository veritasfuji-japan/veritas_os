"""Durable IN_FLIGHT / EFFECT_UNKNOWN reconciliation boundary.

This module never infers an external effect from Bind-core success or generic
adapter ``apply``. A consumed authorization enters IN_FLIGHT before credential
access. If adapter apply may have happened without verified external evidence,
the operation becomes EFFECT_UNKNOWN and requires reconciliation.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from veritas_os.policy.live_adapter_bind_authorization_consumption import (
    BindAuthorizationConsumptionResult,
    LiveAdapterBindAuthorizationConsumptionError,
)
from veritas_os.policy.live_adapter_bind_authorization_consumption_store import (
    AtomicAuthorizationConsumptionStore,
    AuthorizationConsumptionRecord,
    AuthorizationConsumptionStoreError,
)
from veritas_os.security.hash import sha256_of_canonical_json

_HASH = r"^[0-9a-f]{64}$"


class EffectExecutionState(StrEnum):
    IN_FLIGHT = "IN_FLIGHT"
    EFFECT_UNKNOWN = "EFFECT_UNKNOWN"
    CONFIRMED_EFFECT = "CONFIRMED_EFFECT"
    CONFIRMED_NO_EFFECT = "CONFIRMED_NO_EFFECT"


class ReconciliationClaim(StrEnum):
    CONFIRMED_EFFECT = "CONFIRMED_EFFECT"
    CONFIRMED_NO_EFFECT = "CONFIRMED_NO_EFFECT"
    STILL_UNKNOWN = "STILL_UNKNOWN"


_TERMINAL = {
    EffectExecutionState.CONFIRMED_EFFECT,
    EffectExecutionState.CONFIRMED_NO_EFFECT,
}


class BindEffectStateError(RuntimeError):
    """Fail-closed error for effect-state persistence or reconciliation."""


class EffectStateRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    format_version: str = "bind-effect-state/v1"
    operation_id: str = Field(min_length=1)
    authorization_id: str = Field(min_length=1)
    authorization_hash: str = Field(pattern=_HASH)
    consumption_id: str = Field(min_length=1)
    consumption_hash: str = Field(pattern=_HASH)
    execution_intent_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    state: EffectExecutionState
    revision: int = Field(ge=1)
    updated_at: str = Field(min_length=1)
    reason_code: str = Field(min_length=1)
    reconciliation_evidence_hash: str | None = Field(default=None, pattern=_HASH)
    record_hash: str = Field(pattern=_HASH)


class ReconciliationEvidence(BaseModel):
    """External observation input. This object alone is not trusted evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format_version: str = "bind-effect-reconciliation-evidence/v1"
    operation_id: str = Field(min_length=1)
    authorization_id: str = Field(min_length=1)
    consumption_id: str = Field(min_length=1)
    claim: ReconciliationClaim
    source_type: str = Field(min_length=1)
    source_identity: str = Field(min_length=1)
    observed_at: str = Field(min_length=1)
    external_operation_reference: str | None = None
    external_ack_digest: str | None = Field(default=None, pattern=_HASH)
    observation_digest: str = Field(pattern=_HASH)


class VerifiedReconciliationEvidence(BaseModel):
    """Evidence after independent verifier validation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence: ReconciliationEvidence
    verifier_id: str = Field(min_length=1)
    verifier_policy_hash: str = Field(pattern=_HASH)
    verification_proof_hash: str = Field(pattern=_HASH)
    verified_at: str = Field(min_length=1)

    def deterministic_digest(self) -> str:
        return sha256_of_canonical_json(self.model_dump(mode="json"))


class ReconciliationEvidenceVerifier(Protocol):
    async def verify(
        self, evidence: ReconciliationEvidence
    ) -> VerifiedReconciliationEvidence:
        ...


class AtomicEffectStateStore(Protocol):
    async def create_in_flight(self, record: EffectStateRecord) -> bool:
        ...

    async def transition(
        self,
        *,
        operation_id: str,
        expected_state: EffectExecutionState,
        record: EffectStateRecord,
    ) -> bool:
        ...

    async def get(self, operation_id: str) -> EffectStateRecord | None:
        ...


def _record_hash_payload(values: dict[str, Any]) -> dict[str, Any]:
    payload = dict(values)
    payload.pop("record_hash", None)
    return payload


def _build_record(
    *,
    consumption: AuthorizationConsumptionRecord,
    state: EffectExecutionState,
    revision: int,
    updated_at: str,
    reason_code: str,
    reconciliation_evidence_hash: str | None = None,
) -> EffectStateRecord:
    values = {
        "format_version": "bind-effect-state/v1",
        "operation_id": consumption.consumption_id,
        "authorization_id": consumption.live_adapter_bind_authorization_id,
        "authorization_hash": consumption.live_adapter_bind_authorization_hash,
        "consumption_id": consumption.consumption_id,
        "consumption_hash": consumption.consumption_hash,
        "execution_intent_id": consumption.execution_intent_id,
        "idempotency_key": consumption.idempotency_key,
        "state": state,
        "revision": revision,
        "updated_at": updated_at,
        "reason_code": reason_code,
        "reconciliation_evidence_hash": reconciliation_evidence_hash,
    }
    return EffectStateRecord(
        **values,
        record_hash=sha256_of_canonical_json(_record_hash_payload(values)),
    )


class InMemoryAtomicEffectStateStore:
    production_safe = False

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._records: dict[str, EffectStateRecord] = {}

    async def create_in_flight(self, record: EffectStateRecord) -> bool:
        async with self._lock:
            if record.operation_id in self._records:
                return False
            self._records[record.operation_id] = record
            return True

    async def transition(
        self,
        *,
        operation_id: str,
        expected_state: EffectExecutionState,
        record: EffectStateRecord,
    ) -> bool:
        async with self._lock:
            current = self._records.get(operation_id)
            if current is None or current.state != expected_state:
                return False
            if record.revision != current.revision + 1:
                return False
            self._records[operation_id] = record
            return True

    async def get(self, operation_id: str) -> EffectStateRecord | None:
        async with self._lock:
            return self._records.get(operation_id)


class PostgresAtomicEffectStateStore:
    """Cross-process compare-and-set effect-state store."""

    production_safe = True

    async def create_in_flight(self, record: EffectStateRecord) -> bool:
        try:
            from psycopg.types.json import Jsonb
            from veritas_os.storage.db import get_pool

            pool = await get_pool()
            async with pool.connection() as conn:
                cur = await conn.execute(
                    "INSERT INTO bind_effect_states "
                    "(operation_id, authorization_id, consumption_id, state, revision, "
                    "record_hash, updated_at, record) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT DO NOTHING RETURNING operation_id",
                    (
                        record.operation_id,
                        record.authorization_id,
                        record.consumption_id,
                        record.state.value,
                        record.revision,
                        record.record_hash,
                        record.updated_at,
                        Jsonb(record.model_dump(mode="json")),
                    ),
                )
                return await cur.fetchone() is not None
        except Exception:
            raise BindEffectStateError("BES_POSTGRES_CREATE_FAILED") from None

    async def transition(
        self,
        *,
        operation_id: str,
        expected_state: EffectExecutionState,
        record: EffectStateRecord,
    ) -> bool:
        try:
            from psycopg.types.json import Jsonb
            from veritas_os.storage.db import get_pool

            pool = await get_pool()
            async with pool.connection() as conn:
                cur = await conn.execute(
                    "UPDATE bind_effect_states SET state=%s, revision=%s, record_hash=%s, "
                    "updated_at=%s, record=%s WHERE operation_id=%s AND state=%s "
                    "AND revision=%s RETURNING operation_id",
                    (
                        record.state.value,
                        record.revision,
                        record.record_hash,
                        record.updated_at,
                        Jsonb(record.model_dump(mode="json")),
                        operation_id,
                        expected_state.value,
                        record.revision - 1,
                    ),
                )
                return await cur.fetchone() is not None
        except Exception:
            raise BindEffectStateError("BES_POSTGRES_TRANSITION_FAILED") from None

    async def get(self, operation_id: str) -> EffectStateRecord | None:
        try:
            from veritas_os.storage.db import get_pool

            pool = await get_pool()
            async with pool.connection() as conn:
                cur = await conn.execute(
                    "SELECT record FROM bind_effect_states WHERE operation_id=%s",
                    (operation_id,),
                )
                row = await cur.fetchone()
                if row is None:
                    return None
                return EffectStateRecord.model_validate(row[0])
        except Exception:
            raise BindEffectStateError("BES_POSTGRES_READ_FAILED") from None


class EffectStateTrackingConsumptionStore:
    """Decorates atomic authorization consumption with durable IN_FLIGHT creation."""

    def __init__(
        self,
        delegate: AtomicAuthorizationConsumptionStore,
        effect_store: AtomicEffectStateStore,
    ) -> None:
        self._delegate = delegate
        self._effect_store = effect_store

    async def consume_once(self, record: AuthorizationConsumptionRecord) -> bool:
        claimed = await self._delegate.consume_once(record)
        if not claimed:
            return False
        inflight = _build_record(
            consumption=record,
            state=EffectExecutionState.IN_FLIGHT,
            revision=1,
            updated_at=record.consumed_at,
            reason_code="AUTHORIZATION_CONSUMED_BEFORE_EFFECT_BOUNDARY",
        )
        try:
            created = await self._effect_store.create_in_flight(inflight)
        except Exception:
            raise AuthorizationConsumptionStoreError(
                "BES_IN_FLIGHT_PERSISTENCE_FAILED_AFTER_CONSUMPTION"
            ) from None
        if not created:
            raise AuthorizationConsumptionStoreError(
                "BES_IN_FLIGHT_DUPLICATE_AFTER_CONSUMPTION"
            )
        return True


_PRE_APPLY_FAILURES = {
    "LABAC_CREDENTIAL_RESOLUTION_FAILED_AFTER_CONSUMPTION",
    "LABAC_AUTHORIZATION_HEADER_CONSTRUCTION_FAILED_AFTER_CONSUMPTION",
    "LABAC_ADAPTER_CONSTRUCTION_FAILED_AFTER_CONSUMPTION",
    "LABAC_RESOLVED_CREDENTIAL_BINDING_MISMATCH",
    "LABAC_AUTHORIZATION_HEADER_NAME_INVALID",
    "LABAC_AUTHORIZATION_HEADER_VALUE_INVALID",
    "LABAC_ADAPTER_BINDING_MISMATCH",
}


async def classify_completed_bind_attempt(
    *,
    result: BindAuthorizationConsumptionResult,
    effect_store: AtomicEffectStateStore,
    updated_at: str,
) -> EffectStateRecord:
    current = await effect_store.get(result.consumption_record.consumption_id)
    if current is None or current.state != EffectExecutionState.IN_FLIGHT:
        raise BindEffectStateError("BES_IN_FLIGHT_STATE_MISSING")
    if result.adapter_apply_attempted:
        next_state = EffectExecutionState.EFFECT_UNKNOWN
        reason = "ADAPTER_APPLY_ATTEMPTED_WITHOUT_VERIFIED_EXTERNAL_ACK"
    else:
        next_state = EffectExecutionState.CONFIRMED_NO_EFFECT
        reason = "BIND_COMPLETED_WITHOUT_ADAPTER_APPLY"
    record = _build_record(
        consumption=result.consumption_record,
        state=next_state,
        revision=current.revision + 1,
        updated_at=updated_at,
        reason_code=reason,
    )
    if not await effect_store.transition(
        operation_id=current.operation_id,
        expected_state=EffectExecutionState.IN_FLIGHT,
        record=record,
    ):
        raise BindEffectStateError("BES_CLASSIFICATION_CAS_FAILED")
    return record


async def classify_bind_exception(
    *,
    consumption: AuthorizationConsumptionRecord,
    error: Exception,
    effect_store: AtomicEffectStateStore,
    updated_at: str,
) -> EffectStateRecord:
    current = await effect_store.get(consumption.consumption_id)
    if current is None or current.state != EffectExecutionState.IN_FLIGHT:
        raise BindEffectStateError("BES_IN_FLIGHT_STATE_MISSING")
    code = str(error)
    if isinstance(error, LiveAdapterBindAuthorizationConsumptionError) and code in _PRE_APPLY_FAILURES:
        state = EffectExecutionState.CONFIRMED_NO_EFFECT
        reason = "KNOWN_PRE_APPLY_FAILURE"
    else:
        state = EffectExecutionState.EFFECT_UNKNOWN
        reason = "EXECUTION_INTERRUPTED_EFFECT_CANNOT_BE_PROVEN"
    record = _build_record(
        consumption=consumption,
        state=state,
        revision=current.revision + 1,
        updated_at=updated_at,
        reason_code=reason,
    )
    if not await effect_store.transition(
        operation_id=current.operation_id,
        expected_state=EffectExecutionState.IN_FLIGHT,
        record=record,
    ):
        raise BindEffectStateError("BES_EXCEPTION_CLASSIFICATION_CAS_FAILED")
    return record


async def reconcile_effect_unknown(
    *,
    operation_id: str,
    evidence: ReconciliationEvidence,
    verifier: ReconciliationEvidenceVerifier,
    effect_store: AtomicEffectStateStore,
    updated_at: str,
) -> EffectStateRecord:
    current = await effect_store.get(operation_id)
    if current is None:
        raise BindEffectStateError("BES_OPERATION_NOT_FOUND")
    if current.state in _TERMINAL:
        raise BindEffectStateError("BES_TERMINAL_STATE_IMMUTABLE")
    if current.state != EffectExecutionState.EFFECT_UNKNOWN:
        raise BindEffectStateError("BES_RECONCILIATION_REQUIRES_EFFECT_UNKNOWN")
    if (
        evidence.operation_id != current.operation_id
        or evidence.authorization_id != current.authorization_id
        or evidence.consumption_id != current.consumption_id
    ):
        raise BindEffectStateError("BES_RECONCILIATION_LINEAGE_MISMATCH")
    try:
        verified = await verifier.verify(evidence)
    except Exception:
        raise BindEffectStateError("BES_RECONCILIATION_VERIFICATION_FAILED") from None
    if verified.evidence != evidence:
        raise BindEffectStateError("BES_VERIFIED_EVIDENCE_SUBSTITUTION")
    if evidence.claim == ReconciliationClaim.STILL_UNKNOWN:
        state = EffectExecutionState.EFFECT_UNKNOWN
        reason = "RECONCILIATION_STILL_UNKNOWN"
    elif evidence.claim == ReconciliationClaim.CONFIRMED_EFFECT:
        state = EffectExecutionState.CONFIRMED_EFFECT
        reason = "VERIFIED_EXTERNAL_EFFECT_CONFIRMED"
    else:
        state = EffectExecutionState.CONFIRMED_NO_EFFECT
        reason = "VERIFIED_EXTERNAL_NO_EFFECT_CONFIRMED"
    record = _build_record(
        consumption=AuthorizationConsumptionRecord(
            consumption_id=current.consumption_id,
            consumption_hash=current.consumption_hash,
            live_adapter_bind_authorization_id=current.authorization_id,
            live_adapter_bind_authorization_hash=current.authorization_hash,
            idempotency_key=current.idempotency_key,
            bind_context_hash="0" * 64,
            execution_intent_id=current.execution_intent_id,
            execution_intent_hash="0" * 64,
            endpoint_identity_binding_digest="reconciliation",
            credential_reference_digest="reconciliation",
            credential_scope_binding_digest="reconciliation",
            consumed_at=current.updated_at,
        ),
        state=state,
        revision=current.revision + 1,
        updated_at=updated_at,
        reason_code=reason,
        reconciliation_evidence_hash=verified.deterministic_digest(),
    )
    # Preserve original lineage hashes that are not carried by the compact state.
    values = record.model_dump(mode="json")
    values["authorization_hash"] = current.authorization_hash
    values["consumption_hash"] = current.consumption_hash
    values["record_hash"] = sha256_of_canonical_json(_record_hash_payload(values))
    record = EffectStateRecord.model_validate(values)
    if not await effect_store.transition(
        operation_id=operation_id,
        expected_state=EffectExecutionState.EFFECT_UNKNOWN,
        record=record,
    ):
        raise BindEffectStateError("BES_RECONCILIATION_CAS_FAILED")
    return record


__all__ = [
    "AtomicEffectStateStore",
    "BindEffectStateError",
    "EffectExecutionState",
    "EffectStateRecord",
    "EffectStateTrackingConsumptionStore",
    "InMemoryAtomicEffectStateStore",
    "PostgresAtomicEffectStateStore",
    "ReconciliationClaim",
    "ReconciliationEvidence",
    "ReconciliationEvidenceVerifier",
    "VerifiedReconciliationEvidence",
    "classify_bind_exception",
    "classify_completed_bind_attempt",
    "reconcile_effect_unknown",
]
