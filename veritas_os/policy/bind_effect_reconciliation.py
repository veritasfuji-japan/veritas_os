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
from typing import TYPE_CHECKING, Any, Protocol

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

if TYPE_CHECKING:
    from veritas_os.policy.sandbox_reconciliation_archive import SandboxReconciliationArchive

_HASH = r"^[0-9a-f]{64}$"
_SANDBOX_ORIGIN_CAPABILITY = object()


class EffectExecutionState(StrEnum):
    IN_FLIGHT = "IN_FLIGHT"
    EFFECT_UNKNOWN = "EFFECT_UNKNOWN"
    CONFIRMED_EFFECT = "CONFIRMED_EFFECT"
    CONFIRMED_NO_EFFECT = "CONFIRMED_NO_EFFECT"


class EffectProvenance(StrEnum):
    GENERIC_AMBIGUOUS_V1 = "GENERIC_AMBIGUOUS_V1"
    SANDBOX_PRE_DISPATCH_V1 = "SANDBOX_PRE_DISPATCH_V1"


class SandboxOwnershipState(StrEnum):
    AVAILABLE = "AVAILABLE"
    CONSUMED = "CONSUMED"
    CANCELLED = "CANCELLED"


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

    format_version: str = "bind-effect-state/v2"
    operation_id: str = Field(min_length=1)
    authorization_id: str = Field(min_length=1)
    authorization_hash: str = Field(pattern=_HASH)
    consumption_id: str = Field(min_length=1)
    consumption_hash: str = Field(pattern=_HASH)
    execution_intent_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    effect_provenance: EffectProvenance = EffectProvenance.GENERIC_AMBIGUOUS_V1
    state: EffectExecutionState
    revision: int = Field(ge=1)
    updated_at: str = Field(min_length=1)
    reason_code: str = Field(min_length=1)
    reconciliation_evidence_hash: str | None = Field(default=None, pattern=_HASH)
    record_hash: str = Field(pattern=_HASH)


class SandboxOwnershipRecord(BaseModel):
    """Durable one-shot sandbox execution ownership bound to one origin record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format_version: str = "sandbox-execution-ownership/v1"
    operation_id: str = Field(min_length=1)
    origin_record_hash: str = Field(pattern=_HASH)
    immutable_lineage_digest: str = Field(pattern=_HASH)
    ownership_digest: str = Field(pattern=_HASH)
    state: SandboxOwnershipState
    revision: int = Field(ge=1)
    updated_at: str = Field(min_length=1)
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
    async def create_in_flight(
        self, record: EffectStateRecord, *, business_event_key: str | None = None,
    ) -> bool:
        ...

    async def create_sandbox_pre_dispatch_attempt(
        self,
        *,
        consumption: AuthorizationConsumptionRecord,
        updated_at: str,
        business_event_key: str,
        ownership_digest: str,
        origin_authority: object,
    ) -> EffectStateRecord | None:
        ...

    async def consume_sandbox_ownership(
        self,
        *,
        expected: EffectStateRecord,
        ownership_digest: str,
        immutable_lineage_digest: str,
        updated_at: str,
    ) -> bool:
        ...

    async def confirm_pre_dispatch_no_effect(
        self,
        *,
        expected: EffectStateRecord,
        updated_at: str,
    ) -> EffectStateRecord | None:
        ...

    async def get_sandbox_ownership(
        self, operation_id: str,
    ) -> SandboxOwnershipRecord | None:
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


def _ownership_hash_payload(values: dict[str, Any]) -> dict[str, Any]:
    payload = dict(values)
    payload.pop("record_hash", None)
    return payload


def _immutable_effect_lineage_digest(record: EffectStateRecord) -> str:
    return sha256_of_canonical_json(
        {
            "operation_id": record.operation_id,
            "authorization_id": record.authorization_id,
            "authorization_hash": record.authorization_hash,
            "consumption_id": record.consumption_id,
            "consumption_hash": record.consumption_hash,
            "execution_intent_id": record.execution_intent_id,
            "idempotency_key": record.idempotency_key,
            "effect_provenance": record.effect_provenance.value,
        }
    )


def _record_hash_valid(record: EffectStateRecord) -> bool:
    values = record.model_dump(mode="json")
    # v1 rows predate explicit provenance; validate their historical hash
    # without silently upgrading them to sandbox-qualified provenance.
    if record.format_version == "bind-effect-state/v1":
        values.pop("effect_provenance", None)
    return record.record_hash == sha256_of_canonical_json(_record_hash_payload(values))


def _build_ownership_record(
    *,
    operation_id: str,
    origin_record_hash: str,
    immutable_lineage_digest: str,
    ownership_digest: str,
    state: SandboxOwnershipState,
    revision: int,
    updated_at: str,
) -> SandboxOwnershipRecord:
    values = {
        "format_version": "sandbox-execution-ownership/v1",
        "operation_id": operation_id,
        "origin_record_hash": origin_record_hash,
        "immutable_lineage_digest": immutable_lineage_digest,
        "ownership_digest": ownership_digest,
        "state": state,
        "revision": revision,
        "updated_at": updated_at,
    }
    return SandboxOwnershipRecord(
        **values,
        record_hash=sha256_of_canonical_json(_ownership_hash_payload(values)),
    )


_ALLOWED_TRANSITIONS: dict[EffectExecutionState, set[EffectExecutionState]] = {
    EffectExecutionState.IN_FLIGHT: {EffectExecutionState.EFFECT_UNKNOWN},
    EffectExecutionState.EFFECT_UNKNOWN: {
        EffectExecutionState.EFFECT_UNKNOWN,
        EffectExecutionState.CONFIRMED_EFFECT,
    },
    EffectExecutionState.CONFIRMED_EFFECT: set(),
    EffectExecutionState.CONFIRMED_NO_EFFECT: set(),
}


def _legal_transition(
    current: EffectStateRecord, record: EffectStateRecord,
) -> bool:
    return (
        _record_hash_valid(current)
        and _record_hash_valid(record)
        and record.state in _ALLOWED_TRANSITIONS[current.state]
        and record.revision == current.revision + 1
        and _immutable_effect_lineage_digest(record)
        == _immutable_effect_lineage_digest(current)
        and record.effect_provenance == current.effect_provenance
        and record.operation_id == current.operation_id
    )


def _build_record(
    *,
    consumption: AuthorizationConsumptionRecord,
    state: EffectExecutionState,
    revision: int,
    updated_at: str,
    reason_code: str,
    reconciliation_evidence_hash: str | None = None,
    effect_provenance: EffectProvenance = EffectProvenance.GENERIC_AMBIGUOUS_V1,
) -> EffectStateRecord:
    values = {
        "format_version": "bind-effect-state/v2",
        "operation_id": consumption.consumption_id,
        "authorization_id": consumption.live_adapter_bind_authorization_id,
        "authorization_hash": consumption.live_adapter_bind_authorization_hash,
        "consumption_id": consumption.consumption_id,
        "consumption_hash": consumption.consumption_hash,
        "execution_intent_id": consumption.execution_intent_id,
        "idempotency_key": consumption.idempotency_key,
        "effect_provenance": effect_provenance.value,
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
        self._ownership: dict[str, SandboxOwnershipRecord] = {}
        self._archives: dict[str, SandboxReconciliationArchive] = {}
        self._sandbox_receipts: dict[str, str] = {}
        self._business_events: dict[str, str] = {}
        self._operation_business_events: dict[str, str] = {}

    async def create_in_flight(
        self, record: EffectStateRecord, *, business_event_key: str | None = None,
    ) -> bool:
        if record.effect_provenance == EffectProvenance.SANDBOX_PRE_DISPATCH_V1:
            raise BindEffectStateError("BES_RAW_SANDBOX_ORIGIN_FORBIDDEN")
        async with self._lock:
            if record.operation_id in self._records:
                return False
            if business_event_key is not None and business_event_key in self._business_events:
                return False
            self._records[record.operation_id] = record
            if business_event_key is not None:
                self._business_events[business_event_key] = record.operation_id
                self._operation_business_events[record.operation_id] = business_event_key
            return True

    async def create_sandbox_pre_dispatch_attempt(
        self,
        *,
        consumption: AuthorizationConsumptionRecord,
        updated_at: str,
        business_event_key: str,
        ownership_digest: str,
        origin_authority: object,
    ) -> EffectStateRecord | None:
        if origin_authority is not _SANDBOX_ORIGIN_CAPABILITY:
            raise BindEffectStateError("BES_SANDBOX_ORIGIN_AUTHORITY_REQUIRED")
        record = _build_record(
            consumption=consumption,
            state=EffectExecutionState.IN_FLIGHT,
            revision=1,
            updated_at=updated_at,
            reason_code="SANDBOX_PRE_EFFECT_ATTEMPT_CLAIMED",
            effect_provenance=EffectProvenance.SANDBOX_PRE_DISPATCH_V1,
        )
        lineage = _immutable_effect_lineage_digest(record)
        ownership = _build_ownership_record(
            operation_id=record.operation_id,
            origin_record_hash=record.record_hash,
            immutable_lineage_digest=lineage,
            ownership_digest=ownership_digest,
            state=SandboxOwnershipState.AVAILABLE,
            revision=1,
            updated_at=updated_at,
        )
        async with self._lock:
            if record.operation_id in self._records:
                return None
            if business_event_key in self._business_events:
                return None
            self._records[record.operation_id] = record
            self._ownership[record.operation_id] = ownership
            self._business_events[business_event_key] = record.operation_id
            self._operation_business_events[record.operation_id] = business_event_key
            return record

    async def consume_sandbox_ownership(
        self,
        *,
        expected: EffectStateRecord,
        ownership_digest: str,
        immutable_lineage_digest: str,
        updated_at: str,
    ) -> bool:
        async with self._lock:
            current = self._records.get(expected.operation_id)
            ownership = self._ownership.get(expected.operation_id)
            if (
                current != expected
                or not _record_hash_valid(expected)
                or expected.state != EffectExecutionState.IN_FLIGHT
                or expected.revision != 1
                or expected.effect_provenance != EffectProvenance.SANDBOX_PRE_DISPATCH_V1
                or ownership is None
                or ownership.state != SandboxOwnershipState.AVAILABLE
                or ownership.origin_record_hash != expected.record_hash
                or ownership.ownership_digest != ownership_digest
                or ownership.immutable_lineage_digest != immutable_lineage_digest
                or immutable_lineage_digest != _immutable_effect_lineage_digest(expected)
            ):
                return False
            self._ownership[expected.operation_id] = _build_ownership_record(
                operation_id=ownership.operation_id,
                origin_record_hash=ownership.origin_record_hash,
                immutable_lineage_digest=ownership.immutable_lineage_digest,
                ownership_digest=ownership.ownership_digest,
                state=SandboxOwnershipState.CONSUMED,
                revision=ownership.revision + 1,
                updated_at=updated_at,
            )
            return True

    async def confirm_pre_dispatch_no_effect(
        self,
        *,
        expected: EffectStateRecord,
        updated_at: str,
    ) -> EffectStateRecord | None:
        async with self._lock:
            current = self._records.get(expected.operation_id)
            ownership = self._ownership.get(expected.operation_id)
            if (
                current != expected
                or not _record_hash_valid(expected)
                or expected.state != EffectExecutionState.IN_FLIGHT
                or expected.revision != 1
                or expected.effect_provenance != EffectProvenance.SANDBOX_PRE_DISPATCH_V1
                or ownership is None
                or ownership.state != SandboxOwnershipState.AVAILABLE
                or ownership.origin_record_hash != expected.record_hash
                or ownership.immutable_lineage_digest != _immutable_effect_lineage_digest(expected)
            ):
                return None
            values = expected.model_dump(mode="json")
            values.update(
                state=EffectExecutionState.CONFIRMED_NO_EFFECT.value,
                revision=expected.revision + 1,
                updated_at=updated_at,
                reason_code="SANDBOX_RECOVERY_PRE_DISPATCH_CONFIRMED_NO_EFFECT",
            )
            values.pop("record_hash")
            terminal = EffectStateRecord(
                **values,
                record_hash=sha256_of_canonical_json(_record_hash_payload(values)),
            )
            cancelled = _build_ownership_record(
                operation_id=ownership.operation_id,
                origin_record_hash=ownership.origin_record_hash,
                immutable_lineage_digest=ownership.immutable_lineage_digest,
                ownership_digest=ownership.ownership_digest,
                state=SandboxOwnershipState.CANCELLED,
                revision=ownership.revision + 1,
                updated_at=updated_at,
            )
            self._records[expected.operation_id] = terminal
            self._ownership[expected.operation_id] = cancelled
            business_event_key = self._operation_business_events.pop(expected.operation_id, None)
            if business_event_key is not None:
                self._business_events.pop(business_event_key, None)
            return terminal

    async def transition(
        self,
        *,
        operation_id: str,
        expected_state: EffectExecutionState,
        record: EffectStateRecord,
    ) -> bool:
        async with self._lock:
            current = self._records.get(operation_id)
            if (
                current is None
                or current.state != expected_state
                or operation_id in self._archives
                or not _legal_transition(current, record)
            ):
                return False
            self._records[operation_id] = record
            return True

    async def confirm_reconciliation(
        self, *, expected: EffectStateRecord, record: EffectStateRecord,
        archive: SandboxReconciliationArchive,
    ) -> bool:
        """Test-only atomic state and archive commit under the same lock."""
        from veritas_os.policy.sandbox_reconciliation_archive import validate_archive

        archive = validate_archive(record, archive)
        if archive.original_record != expected:
            raise BindEffectStateError("BES_ARCHIVE_EXPECTED_MISMATCH")
        async with self._lock:
            current = self._records.get(expected.operation_id)
            if (
                current != expected
                or expected.operation_id in self._archives
                or record.state == EffectExecutionState.CONFIRMED_NO_EFFECT
                or not _legal_transition(expected, record)
            ):
                return False
            self._archives[expected.operation_id] = archive
            self._records[expected.operation_id] = record
            return True

    async def get_sandbox_ownership(
        self, operation_id: str,
    ) -> SandboxOwnershipRecord | None:
        async with self._lock:
            return self._ownership.get(operation_id)

    async def get_reconciliation(self, operation_id: str) -> SandboxReconciliationArchive | None:
        """Read and integrity-check the record/archive pair under one lock."""
        from veritas_os.policy.sandbox_reconciliation_archive import validate_archive

        async with self._lock:
            record = self._records.get(operation_id)
            archive = self._archives.get(operation_id)
            if record is None and archive is None:
                return None
            if record is None or archive is None or record.operation_id != operation_id:
                raise BindEffectStateError("BES_ARCHIVE_MISSING_OR_MISMATCHED")
            return validate_archive(record, archive)

    async def get(self, operation_id: str) -> EffectStateRecord | None:
        async with self._lock:
            return self._records.get(operation_id)


class PostgresAtomicEffectStateStore:
    """Cross-process compare-and-set effect-state and ownership store."""

    production_safe = True

    async def create_in_flight(
        self, record: EffectStateRecord, *, business_event_key: str | None = None,
    ) -> bool:
        if record.effect_provenance == EffectProvenance.SANDBOX_PRE_DISPATCH_V1:
            raise BindEffectStateError("BES_RAW_SANDBOX_ORIGIN_FORBIDDEN")
        try:
            from psycopg.types.json import Jsonb
            from veritas_os.storage.db import get_pool

            pool = await get_pool()
            async with pool.connection() as conn:
                cur = await conn.execute(
                    "INSERT INTO bind_effect_states "
                    "(operation_id, authorization_id, authorization_hash, consumption_id, "
                    "consumption_hash, execution_intent_id, idempotency_key, effect_provenance, "
                    "state, revision, record_hash, updated_at, record, business_event_key) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT DO NOTHING RETURNING operation_id",
                    (
                        record.operation_id,
                        record.authorization_id,
                        record.authorization_hash,
                        record.consumption_id,
                        record.consumption_hash,
                        record.execution_intent_id,
                        record.idempotency_key,
                        record.effect_provenance.value,
                        record.state.value,
                        record.revision,
                        record.record_hash,
                        record.updated_at,
                        Jsonb(record.model_dump(mode="json")),
                        business_event_key,
                    ),
                )
                return await cur.fetchone() is not None
        except BindEffectStateError:
            raise
        except Exception:
            raise BindEffectStateError("BES_POSTGRES_CREATE_FAILED") from None

    async def create_sandbox_pre_dispatch_attempt(
        self,
        *,
        consumption: AuthorizationConsumptionRecord,
        updated_at: str,
        business_event_key: str,
        ownership_digest: str,
        origin_authority: object,
    ) -> EffectStateRecord | None:
        if origin_authority is not _SANDBOX_ORIGIN_CAPABILITY:
            raise BindEffectStateError("BES_SANDBOX_ORIGIN_AUTHORITY_REQUIRED")
        record = _build_record(
            consumption=consumption,
            state=EffectExecutionState.IN_FLIGHT,
            revision=1,
            updated_at=updated_at,
            reason_code="SANDBOX_PRE_EFFECT_ATTEMPT_CLAIMED",
            effect_provenance=EffectProvenance.SANDBOX_PRE_DISPATCH_V1,
        )
        lineage = _immutable_effect_lineage_digest(record)
        ownership = _build_ownership_record(
            operation_id=record.operation_id,
            origin_record_hash=record.record_hash,
            immutable_lineage_digest=lineage,
            ownership_digest=ownership_digest,
            state=SandboxOwnershipState.AVAILABLE,
            revision=1,
            updated_at=updated_at,
        )
        try:
            from psycopg.types.json import Jsonb
            from veritas_os.storage.db import get_pool

            pool = await get_pool()
            async with pool.connection() as conn:
                cur = await conn.execute(
                    "INSERT INTO bind_effect_states "
                    "(operation_id, authorization_id, authorization_hash, consumption_id, "
                    "consumption_hash, execution_intent_id, idempotency_key, effect_provenance, "
                    "state, revision, record_hash, updated_at, record, business_event_key, "
                    "ownership_state, ownership_digest, ownership_origin_record_hash, "
                    "ownership_lineage_digest, ownership_revision, ownership_updated_at, "
                    "ownership_record_hash) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                    "%s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT DO NOTHING RETURNING operation_id",
                    (
                        record.operation_id,
                        record.authorization_id,
                        record.authorization_hash,
                        record.consumption_id,
                        record.consumption_hash,
                        record.execution_intent_id,
                        record.idempotency_key,
                        record.effect_provenance.value,
                        record.state.value,
                        record.revision,
                        record.record_hash,
                        record.updated_at,
                        Jsonb(record.model_dump(mode="json")),
                        business_event_key,
                        ownership.state.value,
                        ownership.ownership_digest,
                        ownership.origin_record_hash,
                        ownership.immutable_lineage_digest,
                        ownership.revision,
                        ownership.updated_at,
                        ownership.record_hash,
                    ),
                )
                return record if await cur.fetchone() is not None else None
        except Exception:
            raise BindEffectStateError("BES_POSTGRES_SANDBOX_CREATE_FAILED") from None

    async def consume_sandbox_ownership(
        self,
        *,
        expected: EffectStateRecord,
        ownership_digest: str,
        immutable_lineage_digest: str,
        updated_at: str,
    ) -> bool:
        if (
            not _record_hash_valid(expected)
            or expected.state != EffectExecutionState.IN_FLIGHT
            or expected.revision != 1
            or expected.effect_provenance != EffectProvenance.SANDBOX_PRE_DISPATCH_V1
            or immutable_lineage_digest != _immutable_effect_lineage_digest(expected)
        ):
            return False
        consumed = _build_ownership_record(
            operation_id=expected.operation_id,
            origin_record_hash=expected.record_hash,
            immutable_lineage_digest=immutable_lineage_digest,
            ownership_digest=ownership_digest,
            state=SandboxOwnershipState.CONSUMED,
            revision=2,
            updated_at=updated_at,
        )
        try:
            from psycopg.types.json import Jsonb
            from veritas_os.storage.db import get_pool

            pool = await get_pool()
            async with pool.connection() as conn:
                cur = await conn.execute(
                    "UPDATE bind_effect_states SET "
                    "ownership_state=%s, ownership_revision=%s, ownership_updated_at=%s, "
                    "ownership_record_hash=%s "
                    "WHERE operation_id=%s "
                    "AND authorization_id=%s AND authorization_hash=%s "
                    "AND consumption_id=%s AND consumption_hash=%s "
                    "AND execution_intent_id=%s AND idempotency_key=%s "
                    "AND effect_provenance=%s "
                    "AND state=%s AND revision=%s AND record_hash=%s "
                    "AND record::jsonb=%s::jsonb "
                    "AND ownership_state=%s AND ownership_digest=%s "
                    "AND ownership_origin_record_hash=%s AND ownership_lineage_digest=%s "
                    "AND ownership_revision=1 AND business_event_key IS NOT NULL "
                    "AND reconciliation_archive IS NULL "
                    "RETURNING operation_id",
                    (
                        consumed.state.value,
                        consumed.revision,
                        consumed.updated_at,
                        consumed.record_hash,
                        expected.operation_id,
                        expected.authorization_id,
                        expected.authorization_hash,
                        expected.consumption_id,
                        expected.consumption_hash,
                        expected.execution_intent_id,
                        expected.idempotency_key,
                        expected.effect_provenance.value,
                        expected.state.value,
                        expected.revision,
                        expected.record_hash,
                        Jsonb(expected.model_dump(mode="json")),
                        SandboxOwnershipState.AVAILABLE.value,
                        ownership_digest,
                        expected.record_hash,
                        immutable_lineage_digest,
                    ),
                )
                return await cur.fetchone() is not None
        except Exception:
            raise BindEffectStateError("BES_POSTGRES_OWNERSHIP_CONSUME_FAILED") from None

    async def confirm_pre_dispatch_no_effect(
        self,
        *,
        expected: EffectStateRecord,
        updated_at: str,
    ) -> EffectStateRecord | None:
        if (
            not _record_hash_valid(expected)
            or expected.state != EffectExecutionState.IN_FLIGHT
            or expected.revision != 1
            or expected.effect_provenance != EffectProvenance.SANDBOX_PRE_DISPATCH_V1
        ):
            return None
        values = expected.model_dump(mode="json")
        values.update(
            state=EffectExecutionState.CONFIRMED_NO_EFFECT.value,
            revision=expected.revision + 1,
            updated_at=updated_at,
            reason_code="SANDBOX_RECOVERY_PRE_DISPATCH_CONFIRMED_NO_EFFECT",
        )
        values.pop("record_hash")
        terminal = EffectStateRecord(
            **values,
            record_hash=sha256_of_canonical_json(_record_hash_payload(values)),
        )
        lineage = _immutable_effect_lineage_digest(expected)
        try:
            from psycopg.types.json import Jsonb
            from veritas_os.storage.db import get_pool

            pool = await get_pool()
            async with pool.connection() as conn:
                async with conn.transaction():
                    cur = await conn.execute(
                        "SELECT ownership_digest, ownership_origin_record_hash, "
                        "ownership_lineage_digest, ownership_revision "
                        "FROM bind_effect_states "
                        "WHERE operation_id=%s AND state=%s AND revision=%s AND record_hash=%s "
                        "AND effect_provenance=%s AND record::jsonb=%s::jsonb "
                        "AND ownership_state=%s FOR UPDATE",
                        (
                            expected.operation_id,
                            expected.state.value,
                            expected.revision,
                            expected.record_hash,
                            expected.effect_provenance.value,
                            Jsonb(expected.model_dump(mode="json")),
                            SandboxOwnershipState.AVAILABLE.value,
                        ),
                    )
                    row = await cur.fetchone()
                    if row is None:
                        return None
                    ownership_digest, origin_hash, ownership_lineage, ownership_revision = row
                    if (
                        origin_hash != expected.record_hash
                        or ownership_lineage != lineage
                        or ownership_revision != 1
                    ):
                        return None
                    cancelled = _build_ownership_record(
                        operation_id=expected.operation_id,
                        origin_record_hash=expected.record_hash,
                        immutable_lineage_digest=lineage,
                        ownership_digest=ownership_digest,
                        state=SandboxOwnershipState.CANCELLED,
                        revision=2,
                        updated_at=updated_at,
                    )
                    cur = await conn.execute(
                        "UPDATE bind_effect_states SET "
                        "state=%s, revision=%s, record_hash=%s, updated_at=%s, record=%s, "
                        "ownership_state=%s, ownership_revision=%s, ownership_updated_at=%s, "
                        "ownership_record_hash=%s, business_event_key=NULL "
                        "WHERE operation_id=%s AND state=%s AND revision=%s AND record_hash=%s "
                        "AND effect_provenance=%s AND record::jsonb=%s::jsonb "
                        "AND ownership_state=%s AND ownership_digest=%s "
                        "AND ownership_origin_record_hash=%s AND ownership_lineage_digest=%s "
                        "AND ownership_revision=1 AND reconciliation_archive IS NULL "
                        "RETURNING operation_id",
                        (
                            terminal.state.value,
                            terminal.revision,
                            terminal.record_hash,
                            terminal.updated_at,
                            Jsonb(terminal.model_dump(mode="json")),
                            cancelled.state.value,
                            cancelled.revision,
                            cancelled.updated_at,
                            cancelled.record_hash,
                            expected.operation_id,
                            expected.state.value,
                            expected.revision,
                            expected.record_hash,
                            expected.effect_provenance.value,
                            Jsonb(expected.model_dump(mode="json")),
                            SandboxOwnershipState.AVAILABLE.value,
                            ownership_digest,
                            expected.record_hash,
                            lineage,
                        ),
                    )
                    return terminal if await cur.fetchone() is not None else None
        except Exception:
            raise BindEffectStateError("BES_POSTGRES_NO_EFFECT_ARBITRATION_FAILED") from None

    async def transition(
        self,
        *,
        operation_id: str,
        expected_state: EffectExecutionState,
        record: EffectStateRecord,
    ) -> bool:
        if (
            operation_id != record.operation_id
            or record.state == EffectExecutionState.CONFIRMED_NO_EFFECT
            or not _record_hash_valid(record)
        ):
            return False
        if record.state not in _ALLOWED_TRANSITIONS.get(expected_state, set()):
            return False
        try:
            from psycopg.types.json import Jsonb
            from veritas_os.storage.db import get_pool

            pool = await get_pool()
            async with pool.connection() as conn:
                cur = await conn.execute(
                    "UPDATE bind_effect_states SET state=%s, revision=%s, record_hash=%s, "
                    "updated_at=%s, record=%s "
                    "WHERE operation_id=%s AND authorization_id=%s AND authorization_hash=%s "
                    "AND consumption_id=%s AND consumption_hash=%s "
                    "AND execution_intent_id=%s AND idempotency_key=%s "
                    "AND effect_provenance=%s AND state=%s "
                    "AND revision=%s AND reconciliation_archive IS NULL RETURNING operation_id",
                    (
                        record.state.value,
                        record.revision,
                        record.record_hash,
                        record.updated_at,
                        Jsonb(record.model_dump(mode="json")),
                        operation_id,
                        record.authorization_id,
                        record.authorization_hash,
                        record.consumption_id,
                        record.consumption_hash,
                        record.execution_intent_id,
                        record.idempotency_key,
                        record.effect_provenance.value,
                        expected_state.value,
                        record.revision - 1,
                    ),
                )
                return await cur.fetchone() is not None
        except Exception:
            raise BindEffectStateError("BES_POSTGRES_TRANSITION_FAILED") from None

    async def confirm_reconciliation(
        self, *, expected: EffectStateRecord, record: EffectStateRecord,
        archive: SandboxReconciliationArchive,
    ) -> bool:
        """One SQL CAS commits full evidence and terminal effect state together."""
        if record.state == EffectExecutionState.CONFIRMED_NO_EFFECT or not _legal_transition(expected, record):
            return False
        try:
            from psycopg.types.json import Jsonb
            from veritas_os.storage.db import get_pool
            from veritas_os.policy.sandbox_reconciliation_archive import validate_archive

            archive = validate_archive(record, archive)
            if archive.original_record != expected:
                raise ValueError("expected record")
            pool = await get_pool()
            async with pool.connection() as conn:
                cur = await conn.execute(
                    "UPDATE bind_effect_states SET state=%s, revision=%s, record_hash=%s, "
                    "updated_at=%s, record=%s, reconciliation_archive=%s "
                    "WHERE operation_id=%s AND authorization_id=%s AND authorization_hash=%s "
                    "AND consumption_id=%s AND consumption_hash=%s "
                    "AND execution_intent_id=%s AND idempotency_key=%s "
                    "AND effect_provenance=%s AND state=%s AND revision=%s AND record_hash=%s "
                    "AND record::jsonb=%s::jsonb AND reconciliation_archive IS NULL "
                    "RETURNING operation_id",
                    (
                        record.state.value,
                        record.revision,
                        record.record_hash,
                        record.updated_at,
                        Jsonb(record.model_dump(mode="json")),
                        Jsonb(archive.model_dump(mode="json")),
                        expected.operation_id,
                        expected.authorization_id,
                        expected.authorization_hash,
                        expected.consumption_id,
                        expected.consumption_hash,
                        expected.execution_intent_id,
                        expected.idempotency_key,
                        expected.effect_provenance.value,
                        expected.state.value,
                        expected.revision,
                        expected.record_hash,
                        Jsonb(expected.model_dump(mode="json")),
                    ),
                )
                return await cur.fetchone() is not None
        except Exception:
            pass
        raise BindEffectStateError("BES_ARCHIVE_COMMIT_FAILED")

    async def get_sandbox_ownership(
        self, operation_id: str,
    ) -> SandboxOwnershipRecord | None:
        try:
            from veritas_os.storage.db import get_pool

            pool = await get_pool()
            async with pool.connection() as conn:
                cur = await conn.execute(
                    "SELECT ownership_state, ownership_digest, ownership_origin_record_hash, "
                    "ownership_lineage_digest, ownership_revision, ownership_updated_at, "
                    "ownership_record_hash FROM bind_effect_states WHERE operation_id=%s",
                    (operation_id,),
                )
                row = await cur.fetchone()
            if row is None or row[0] is None:
                return None
            values = {
                "format_version": "sandbox-execution-ownership/v1",
                "operation_id": operation_id,
                "state": row[0],
                "ownership_digest": row[1],
                "origin_record_hash": row[2],
                "immutable_lineage_digest": row[3],
                "revision": row[4],
                "updated_at": row[5].isoformat() if hasattr(row[5], "isoformat") else str(row[5]),
                "record_hash": row[6],
            }
            ownership = SandboxOwnershipRecord.model_validate(values)
            if ownership.record_hash != sha256_of_canonical_json(_ownership_hash_payload(ownership.model_dump(mode="json"))):
                raise ValueError("ownership hash")
            return ownership
        except Exception:
            raise BindEffectStateError("BES_POSTGRES_OWNERSHIP_READ_FAILED") from None

    async def get_reconciliation(self, operation_id: str) -> SandboxReconciliationArchive | None:
        """Read both values in one snapshot; never return unvalidated evidence."""
        try:
            from veritas_os.storage.db import get_pool
            from veritas_os.policy.sandbox_reconciliation_archive import (
                SandboxReconciliationArchive, validate_archive,
            )

            pool = await get_pool()
            async with pool.connection() as conn:
                cur = await conn.execute(
                    "SELECT record, reconciliation_archive FROM bind_effect_states WHERE operation_id=%s",
                    (operation_id,),
                )
                row = await cur.fetchone()
            if row is None:
                return None
            record = EffectStateRecord.model_validate(row[0])
            if record.operation_id != operation_id or row[1] is None:
                raise ValueError("missing archive")
            return validate_archive(record, SandboxReconciliationArchive.model_validate(row[1]))
        except Exception:
            pass
        raise BindEffectStateError("BES_ARCHIVE_READ_FAILED")

    async def get(self, operation_id: str) -> EffectStateRecord | None:
        try:
            from veritas_os.storage.db import get_pool

            pool = await get_pool()
            async with pool.connection() as conn:
                cur = await conn.execute(
                    "SELECT authorization_id, authorization_hash, consumption_id, consumption_hash, "
                    "execution_intent_id, idempotency_key, effect_provenance, state, revision, "
                    "record_hash, record FROM bind_effect_states WHERE operation_id=%s",
                    (operation_id,),
                )
                row = await cur.fetchone()
                if row is None:
                    return None
            raw_record = row[10]
            record = EffectStateRecord.model_validate(raw_record)
            if isinstance(raw_record, dict) and "effect_provenance" in raw_record and not _record_hash_valid(record):
                raise ValueError("record hash")
            relational = (
                operation_id, row[0], row[1], row[2], row[3], row[4], row[5], row[6],
                row[7], row[8], row[9],
            )
            embedded = (
                record.operation_id, record.authorization_id, record.authorization_hash,
                record.consumption_id, record.consumption_hash, record.execution_intent_id,
                record.idempotency_key, record.effect_provenance.value,
                record.state.value, record.revision, record.record_hash,
            )
            if relational != embedded:
                raise ValueError("persisted identity divergence")
            return record
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
        next_state = EffectExecutionState.EFFECT_UNKNOWN
        reason = "GENERIC_NO_EFFECT_NOT_DURABLY_PROVEN"
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
        state = EffectExecutionState.EFFECT_UNKNOWN
        reason = "KNOWN_PRE_APPLY_FAILURE_EFFECT_NOT_DURABLY_PROVEN"
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
        state = EffectExecutionState.EFFECT_UNKNOWN
        reason = "RECONCILIATION_NO_EFFECT_UNSAFE_AFTER_DISPATCH_FENCE"
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
        effect_provenance=current.effect_provenance,
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
    "EffectProvenance",
    "EffectStateRecord",
    "EffectStateTrackingConsumptionStore",
    "InMemoryAtomicEffectStateStore",
    "PostgresAtomicEffectStateStore",
    "ReconciliationClaim",
    "SandboxOwnershipRecord",
    "SandboxOwnershipState",
    "ReconciliationEvidence",
    "ReconciliationEvidenceVerifier",
    "VerifiedReconciliationEvidence",
    "_immutable_effect_lineage_digest",
    "classify_bind_exception",
    "classify_completed_bind_attempt",
    "reconcile_effect_unknown",
]
