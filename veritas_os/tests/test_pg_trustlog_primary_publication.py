"""Real-PostgreSQL proof tests for TrustLog primary logical publication."""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest

from veritas_os.storage.db import close_pool, get_pool
from veritas_os.storage.trustlog_primary_publication import (
    PostgresTrustLogPrimaryPublisher,
    TrustLogPrimaryPublicationCollisionError,
    build_trustlog_publication_identity,
)

pytestmark = [pytest.mark.postgresql, pytest.mark.contention]


def _require_real_postgresql() -> None:
    if not os.getenv("VERITAS_DATABASE_URL", "").startswith("postgresql"):
        pytest.skip("real PostgreSQL service container is required")


async def _count_identity_rows(logical_identity_key: str) -> int:
    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT count(*) FROM trustlog_entries "
            "WHERE logical_identity_key = %s",
            (logical_identity_key,),
        )
        row = await cur.fetchone()
    return int(row[0]) if row else 0


@pytest.mark.asyncio
async def test_real_postgres_concurrent_same_publication_creates_one_row() -> None:
    """32 concurrent identical publications resolve to one durable row."""
    _require_real_postgresql()
    token = uuid4().hex
    publisher = PostgresTrustLogPrimaryPublisher()
    kwargs = {
        "entry_type": "review_packet",
        "entry_id": f"review:{token}",
        "payload": {"status": "verified", "sequence": 1},
    }
    identity = build_trustlog_publication_identity(**kwargs)

    try:
        await get_pool()
        results = await asyncio.gather(*(publisher.publish(**kwargs) for _ in range(32)))

        assert sum(result.created for result in results) == 1
        assert sum(not result.created for result in results) == 31
        assert len({result.trustlog_row_id for result in results}) == 1
        assert len({result.request_id for result in results}) == 1
        assert len({result.trustlog_chain_hash for result in results}) == 1
        assert await _count_identity_rows(identity.logical_identity_key) == 1
    finally:
        await close_pool()


@pytest.mark.asyncio
async def test_real_postgres_same_identity_different_payload_fails_closed() -> None:
    """One stable logical identity cannot be reused for changed content."""
    _require_real_postgresql()
    token = uuid4().hex
    publisher = PostgresTrustLogPrimaryPublisher()
    entry_id = f"outcome:{token}"
    original_identity = build_trustlog_publication_identity(
        entry_type="outcome_receipt",
        entry_id=entry_id,
        payload={"status": "confirmed", "amount": 10},
    )

    try:
        first = await publisher.publish(
            entry_type="outcome_receipt",
            entry_id=entry_id,
            payload={"status": "confirmed", "amount": 10},
        )
        assert first.created

        with pytest.raises(
            TrustLogPrimaryPublicationCollisionError,
            match="TRUSTLOG_PRIMARY_PUBLICATION_COLLISION",
        ):
            await publisher.publish(
                entry_type="outcome_receipt",
                entry_id=entry_id,
                payload={"status": "confirmed", "amount": 11},
            )

        assert await _count_identity_rows(original_identity.logical_identity_key) == 1
    finally:
        await close_pool()


@pytest.mark.asyncio
async def test_real_postgres_retry_after_lost_response_resolves_original_row() -> None:
    """A retry after a hypothetical lost success response does not append again."""
    _require_real_postgresql()
    token = uuid4().hex
    publisher = PostgresTrustLogPrimaryPublisher()
    kwargs = {
        "entry_type": "bind_receipt",
        "entry_id": f"bind:{token}",
        "payload": {"result": "committed", "attempt": 1},
    }
    identity = build_trustlog_publication_identity(**kwargs)

    try:
        committed = await publisher.publish(**kwargs)
        assert committed.created

        # Simulate the caller losing the successful response by discarding it
        # and retrying from durable identity only.
        retry = await publisher.publish(**kwargs)
        replay = await publisher.publish(**kwargs)

        assert not retry.created
        assert not replay.created
        assert retry.trustlog_row_id == committed.trustlog_row_id
        assert retry.request_id == committed.request_id
        assert retry.trustlog_chain_hash == committed.trustlog_chain_hash
        assert retry.receipt_hash == replay.receipt_hash
        assert await _count_identity_rows(identity.logical_identity_key) == 1
    finally:
        await close_pool()


@pytest.mark.asyncio
async def test_real_postgres_process_pool_restart_does_not_duplicate_publication() -> None:
    """Closing process-local pool state cannot permit a second logical row."""
    _require_real_postgresql()
    token = uuid4().hex
    kwargs = {
        "entry_type": "authority_evidence",
        "entry_id": f"authority:{token}",
        "payload": {"authority": "approved", "scope": ["read"]},
    }
    identity = build_trustlog_publication_identity(**kwargs)

    try:
        first = await PostgresTrustLogPrimaryPublisher().publish(**kwargs)
        assert first.created
        await close_pool()

        second = await PostgresTrustLogPrimaryPublisher().publish(**kwargs)
        assert not second.created
        assert second.trustlog_row_id == first.trustlog_row_id
        assert second.request_id == first.request_id
        assert await _count_identity_rows(identity.logical_identity_key) == 1
    finally:
        await close_pool()
