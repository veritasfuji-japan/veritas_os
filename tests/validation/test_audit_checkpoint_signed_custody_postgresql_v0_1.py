"""Real PostgreSQL continuity tests with externally pinned Ed25519 receipts.

Synthetic fixture and ephemeral keys: this does NOT assert remote independent
custody, authenticated record origins or a trusted time source.
"""
from __future__ import annotations

from uuid import uuid4
import json
import os

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from psycopg.types.json import Jsonb
import pytest

from scripts.validation.audit_checkpoint_signed_custody_v0_1 import (
    check_registry_against_signed_reference,
    sign_checkpoint,
)
from scripts.validation.audit_registry_checkpoint_v0_1 import (
    _digest,
    capture_checkpoint,
)
from scripts.validation.audit_replay_registry_postgresql_v0_1 import (
    PostgresAuditReplayRegistry,
)
from veritas_os.storage.db import get_pool, close_pool
from test_cross_packet_replay_provenance import write_packet

pytestmark = [pytest.mark.postgresql, pytest.mark.contention]
ZERO = "0" * 64


def require_postgres():
    if not os.environ.get("VERITAS_DATABASE_URL", "").startswith("postgresql"):
        pytest.skip("isolated PostgreSQL service required")


async def archive(tmp_path, name):
    label = uuid4().hex
    path = write_packet(
        tmp_path, label=name + label,
        packet_id="custody-" + label,
        operation_id="custody-op-" + label,
        repository="Example/Custody",
    )
    result = await PostgresAuditReplayRegistry().ingest(
        packet_root=tmp_path, profile_paths=[path],
    )
    assert result.status == "NEW_OBSERVATION", result
    return json.loads((tmp_path / path).read_text())["packet_id"]


async def baseline():
    status, reference = await capture_checkpoint()
    assert status == "SNAPSHOT_READY_UNAUTHENTICATED"
    assert reference is not None
    return reference


def ephemeral_key():
    key = Ed25519PrivateKey.generate()
    return (
        key.private_bytes_raw(),
        key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex(),
    )


async def check(reference, receipt, pub, head):
    return await check_registry_against_signed_reference(
        reference=reference, receipt=receipt,
        trusted_public_key_hex=pub, expected_head_sha256=head,
    )


@pytest.mark.asyncio
async def test_postgresql_signed_head_survives_restart_detects_extension_and_restore(tmp_path):
    require_postgres()
    try:
        await archive(tmp_path, "initial")
        key, pub = ephemeral_key()
        first = await baseline()
        first_receipt = sign_checkpoint(
            first, private_key_raw=key,
            sequence=1, previous_receipt_sha256=ZERO,
        )
        first_head = _digest(first_receipt)
        assert await check(first, first_receipt, pub, first_head) == (
            "HISTORY_UNCHANGED_UNAUTHENTICATED"
        )
        await close_pool()
        assert await check(first, first_receipt, pub, first_head) == (
            "HISTORY_UNCHANGED_UNAUTHENTICATED"
        )
        victim = await archive(tmp_path, "later")
        assert await check(first, first_receipt, pub, first_head) == (
            "HISTORY_EXTENDED_UNAUTHENTICATED"
        )

        updated = await baseline()
        second = sign_checkpoint(
            updated, private_key_raw=key,
            sequence=2, previous_receipt_sha256=first_head,
        )
        second_head = _digest(second)
        assert await check(updated, second, pub, second_head) == (
            "HISTORY_UNCHANGED_UNAUTHENTICATED"
        )
        assert await check(first, first_receipt, pub, second_head) == (
            "CUSTODY_HEAD_MISMATCH"
        )

        # Simulate a privileged rollback by removing an archived packet.
        pool = await get_pool()
        async with pool.connection() as conn:
            async with conn.transaction():
                await conn.execute(
                    "DELETE FROM audit_case_observations WHERE packet_id=%s",
                    (victim,),
                )
                await conn.execute(
                    "DELETE FROM audit_packet_inventory WHERE packet_id=%s",
                    (victim,),
                )
        assert await check(updated, second, pub, second_head) == "HISTORY_DIVERGED"
    finally:
        await close_pool()


@pytest.mark.asyncio
async def test_postgresql_signed_head_rejects_modified_local_json(tmp_path):
    require_postgres()
    try:
        packet_id = await archive(tmp_path, "corrupt")
        ref = await baseline()
        key, pub = ephemeral_key()
        receipt = sign_checkpoint(
            ref, private_key_raw=key,
            sequence=1, previous_receipt_sha256=ZERO,
        )
        pool = await get_pool()
        async with pool.connection() as conn:
            original_row = await (
                await conn.execute(
                    "SELECT record FROM audit_case_observations WHERE packet_id=%s",
                    (packet_id,),
                )
            ).fetchone()
            assert original_row is not None
            original = original_row[0]
            async with conn.transaction():
                await conn.execute(
                    "UPDATE audit_case_observations "
                    "SET record=jsonb_set(record, '{operation_id}', to_jsonb(%s::text)) "
                    "WHERE packet_id=%s",
                    ("malicious-substitution", packet_id),
                )
        try:
            assert await check(ref, receipt, pub, _digest(receipt)) == "INCOMPLETE"
        finally:
            async with pool.connection() as conn:
                async with conn.transaction():
                    await conn.execute(
                        "UPDATE audit_case_observations SET record=%s "
                        "WHERE packet_id=%s", (Jsonb(original), packet_id),
                    )
    finally:
        await close_pool()
