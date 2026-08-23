"""Atomic single-use stores for Real Bind Authorization consumption.

The store boundary records only non-secret authorization lineage. Credential
material and constructed headers must never enter this module.
"""

from __future__ import annotations

import asyncio
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from veritas_os.security.hash import sha256_of_canonical_json

_HASH_PATTERN = r"^[0-9a-f]{64}$"
_CONSUMPTION_ID_PATTERN = r"^labac:v1:sha256:[0-9a-f]{64}$"


class AuthorizationConsumptionStoreError(RuntimeError):
    """Fail-closed storage failure at the authorization consumption boundary."""


class AuthorizationConsumptionRecord(BaseModel):
    """Non-secret record proving one authorization was atomically consumed."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format_version: str = "live-adapter-bind-authorization-consumption/v1"
    consumption_id: str = Field(pattern=_CONSUMPTION_ID_PATTERN)
    consumption_hash: str = Field(pattern=_HASH_PATTERN)
    live_adapter_bind_authorization_id: str = Field(min_length=1)
    live_adapter_bind_authorization_hash: str = Field(pattern=_HASH_PATTERN)
    idempotency_key: str = Field(min_length=1)
    bind_context_hash: str = Field(pattern=_HASH_PATTERN)
    execution_intent_id: str = Field(min_length=1)
    execution_intent_hash: str = Field(pattern=_HASH_PATTERN)
    endpoint_identity_binding_digest: str = Field(min_length=1)
    credential_reference_digest: str = Field(min_length=1)
    credential_scope_binding_digest: str = Field(min_length=1)
    consumed_at: str = Field(min_length=1)
    consumption_state: str = "CONSUMED"
    single_use_enforced: bool = True


class AtomicAuthorizationConsumptionStore(Protocol):
    """Atomic compare-and-set store used before any credential access or Bind."""

    async def consume_once(self, record: AuthorizationConsumptionRecord) -> bool:
        """Return True exactly once; False for any duplicate authorization/key."""


def build_authorization_consumption_record(
    *,
    live_adapter_bind_authorization_id: str,
    live_adapter_bind_authorization_hash: str,
    idempotency_key: str,
    bind_context_hash: str,
    execution_intent_id: str,
    execution_intent_hash: str,
    endpoint_identity_binding_digest: str,
    credential_reference_digest: str,
    credential_scope_binding_digest: str,
    consumed_at: str,
) -> AuthorizationConsumptionRecord:
    """Build a deterministic, non-secret consumption record."""
    body = {
        "format_version": "live-adapter-bind-authorization-consumption/v1",
        "live_adapter_bind_authorization_id": live_adapter_bind_authorization_id,
        "live_adapter_bind_authorization_hash": live_adapter_bind_authorization_hash,
        "idempotency_key": idempotency_key,
        "bind_context_hash": bind_context_hash,
        "execution_intent_id": execution_intent_id,
        "execution_intent_hash": execution_intent_hash,
        "endpoint_identity_binding_digest": endpoint_identity_binding_digest,
        "credential_reference_digest": credential_reference_digest,
        "credential_scope_binding_digest": credential_scope_binding_digest,
        "consumed_at": consumed_at,
        "consumption_state": "CONSUMED",
        "single_use_enforced": True,
    }
    digest = sha256_of_canonical_json(body)
    return AuthorizationConsumptionRecord(
        **body,
        consumption_hash=digest,
        consumption_id=f"labac:v1:sha256:{digest}",
    )


class InMemoryAtomicAuthorizationConsumptionStore:
    """Process-local atomic store for tests and deterministic reference use only."""

    production_safe = False

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._by_authorization_id: dict[str, AuthorizationConsumptionRecord] = {}
        self._idempotency_keys: set[str] = set()

    async def consume_once(self, record: AuthorizationConsumptionRecord) -> bool:
        async with self._lock:
            if (
                record.live_adapter_bind_authorization_id in self._by_authorization_id
                or record.idempotency_key in self._idempotency_keys
            ):
                return False
            self._by_authorization_id[record.live_adapter_bind_authorization_id] = record
            self._idempotency_keys.add(record.idempotency_key)
            return True

    async def get(
        self, live_adapter_bind_authorization_id: str
    ) -> AuthorizationConsumptionRecord | None:
        async with self._lock:
            return self._by_authorization_id.get(live_adapter_bind_authorization_id)


class PostgresAtomicAuthorizationConsumptionStore:
    """Cross-process atomic store backed by PostgreSQL UNIQUE constraints."""

    production_safe = True

    async def consume_once(self, record: AuthorizationConsumptionRecord) -> bool:
        try:
            from psycopg.types.json import Jsonb
            from veritas_os.storage.db import get_pool

            pool = await get_pool()
            async with pool.connection() as conn:
                async with conn.transaction():
                    cur = await conn.execute(
                        "INSERT INTO bind_authorization_consumptions "
                        "(consumption_id, consumption_hash, authorization_id, "
                        "authorization_hash, idempotency_key, bind_context_hash, "
                        "execution_intent_id, execution_intent_hash, consumed_at, record) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                        "ON CONFLICT DO NOTHING RETURNING consumption_id",
                        (
                            record.consumption_id,
                            record.consumption_hash,
                            record.live_adapter_bind_authorization_id,
                            record.live_adapter_bind_authorization_hash,
                            record.idempotency_key,
                            record.bind_context_hash,
                            record.execution_intent_id,
                            record.execution_intent_hash,
                            record.consumed_at,
                            Jsonb(record.model_dump(mode="json")),
                        ),
                    )
                    row = await cur.fetchone()
                    return row is not None
        except AuthorizationConsumptionStoreError:
            raise
        except Exception:
            raise AuthorizationConsumptionStoreError(
                "LABAC_POSTGRES_CONSUMPTION_STORE_FAILED"
            ) from None
