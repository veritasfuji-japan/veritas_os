"""Dedicated sandbox event persistence; never use the VERITAS governance DB.

One immutable row is both the synthetic event and its operation record. Unique
constraints arbitrate races. Success is returned only after transaction commit.
No delete, retry, upsert mutation or deduplication expiry is provided.
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from veritas_os.policy.sandbox_action_binding import _unique_object
from veritas_os.security.hash import sha256_of_canonical_json


class SandboxEventConflict(ValueError):
    """The key or event ID already belongs to a different request."""


class SandboxEventStoreError(RuntimeError):
    """Database outcome is unknown; no automatic retry is authorized."""


class SandboxEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    event_id: str
    message: str


class SandboxOperation(BaseModel):
    """Service observation only, not a VERITAS Receipt or confirmation."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    operation_id: str
    idempotency_key: str
    event_id: str
    payload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    state: Literal["PERSISTED"] = "PERSISTED"


def validate_key(key: str) -> str:
    if type(key) is not str or not re.fullmatch(r"[A-Za-z0-9._:-]{1,256}", key):
        raise ValueError("SSE_INVALID_KEY")
    return key


def validate_uuid(value: str) -> str:
    if type(value) is not str or str(UUID(value)) != value:
        raise ValueError("SSE_INVALID_ID")
    return value


def parse_event(raw: bytes) -> SandboxEvent:
    """Reject extra/duplicate fields, non-UTF8 JSON and oversized messages."""
    if type(raw) is not bytes or len(raw) > 4096:
        raise ValueError("SSE_INVALID_BODY")
    body = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    event = SandboxEvent.model_validate(body)
    validate_uuid(event.event_id)
    if "\x00" in event.message or not 1 <= len(event.message.encode("utf-8")) <= 256:
        raise ValueError("SSE_INVALID_MESSAGE")
    return event


class PostgresSandboxEventStore:
    """Use an operator-supplied dedicated psycopg async pool and installed schema.

The pool must hand out idle connections. Each registration explicitly uses
READ COMMITTED, so a conflict loser can read the winner in its next statement.
The DDL is installed separately, never by serving a request.
"""

    def __init__(self, pool: Any) -> None:
        if pool is None:
            raise ValueError("SSE_DEDICATED_POOL_REQUIRED")
        self._pool = pool

    async def register(self, raw: bytes, key: str) -> tuple[SandboxOperation, bool]:
        event, key = parse_event(raw), validate_key(key)
        digest = sha256_of_canonical_json(event.model_dump())
        operation_id = str(uuid4())
        conflict = False
        try:
            async with self._pool.connection() as conn:
                async with conn.transaction():
                    await conn.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
                    await conn.execute("SET LOCAL synchronous_commit = on")
                    await conn.execute("SET LOCAL statement_timeout = '4000ms'")
                    cur = await conn.execute(
                        "INSERT INTO sandbox_events "
                        "(operation_id, idempotency_key, event_id, message, payload_digest) "
                        "VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING "
                        "RETURNING operation_id",
                        (operation_id, key, event.event_id, event.message, digest),
                    )
                    created = await cur.fetchone() is not None
                    cur = await conn.execute(
                        "SELECT operation_id, idempotency_key, event_id, payload_digest, message "
                        "FROM sandbox_events WHERE idempotency_key=%s", (key,),
                    )
                    row = await cur.fetchone()
                    if row is None or (str(row[2]), row[3], row[4]) != (
                        event.event_id, digest, event.message,
                    ):
                        conflict = True
                    else:
                        operation = _operation(row)
            if not conflict:
                return operation, created
        except Exception:
            # Raise outside the handler; do not retain SQL/connection exceptions.
            pass
        else:
            raise SandboxEventConflict("SSE_CONFLICT")
        raise SandboxEventStoreError("SSE_DATABASE_OUTCOME_UNKNOWN")

    async def lookup(
        self, *, operation_id: str | None = None, key: str | None = None,
    ) -> SandboxOperation | None:
        if (operation_id is None) == (key is None):
            raise ValueError("SSE_ONE_LOOKUP_REQUIRED")
        if operation_id is not None:
            value, column = validate_uuid(operation_id), "operation_id"
        else:
            value, column = validate_key(key), "idempotency_key"
        try:
            async with self._pool.connection() as conn:
                async with conn.transaction():
                    await conn.execute("SET TRANSACTION READ ONLY")
                    await conn.execute("SET LOCAL statement_timeout = '4000ms'")
                    cur = await conn.execute(
                        "SELECT operation_id, idempotency_key, event_id, payload_digest "
                        f"FROM sandbox_events WHERE {column}=%s", (value,),
                    )
                    row = await cur.fetchone()
                    result = None if row is None else _operation(row)
            return result
        except Exception:
            pass
        raise SandboxEventStoreError("SSE_DATABASE_LOOKUP_FAILED")


def _operation(row: Any) -> SandboxOperation:
    return SandboxOperation(
        operation_id=validate_uuid(str(row[0])), idempotency_key=validate_key(row[1]),
        event_id=validate_uuid(str(row[2])), payload_digest=row[3],
    )
