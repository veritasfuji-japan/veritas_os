"""Real PostgreSQL evidence for checkpoint pinning, tamper and rollback."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from psycopg.types.json import Jsonb

from scripts.validation.audit_registry_checkpoint_v0_1 import (
    _digest,
    capture_checkpoint,
    check_registry_against_pin,
)
from scripts.validation.audit_replay_registry_postgresql_v0_1 import (
    PostgresAuditReplayRegistry,
)
from veritas_os.storage.db import close_pool, get_pool
from test_cross_packet_replay_provenance import write_packet

pytestmark = [pytest.mark.postgresql, pytest.mark.contention]


def _require_pg():
    if not os.getenv("VERITAS_DATABASE_URL", "").startswith("postgresql"):
        pytest.skip("real isolated PostgreSQL required")


def _packet(tmp_path, name):
    import json
    token = uuid4().hex
    profile = write_packet(
        tmp_path, label=name, packet_id="anchor-" + token,
        operation_id="anchor-op-" + token, repository="Example/LocalAudit",
    )
    packet_id = json.loads((tmp_path / profile).read_text())["packet_id"]
    return profile, packet_id


async def _archive(tmp_path, name):
    path, packet_id = _packet(tmp_path, name)
    result = await PostgresAuditReplayRegistry().ingest(
        packet_root=tmp_path, profile_paths=[path],
    )
    assert result.status == "NEW_OBSERVATION", result
    return path, packet_id


async def _baseline():
    status, snap = await capture_checkpoint()
    assert status == "SNAPSHOT_READY_UNAUTHENTICATED", status
    assert snap is not None
    return snap, _digest(snap)


@pytest.mark.asyncio
async def test_real_pg_checkpoint_unchanged_after_pool_restart(tmp_path):
    _require_pg()
    try:
        await _archive(tmp_path, "first")
        baseline, pin = await _baseline()
        assert baseline["packet_count"] >= 1
        assert (await check_registry_against_pin(
            reference=baseline, pinned_reference_sha256=pin,
        )) == "HISTORY_UNCHANGED_UNAUTHENTICATED"
        await close_pool()
        assert (await check_registry_against_pin(
            reference=baseline, pinned_reference_sha256=pin,
        )) == "HISTORY_UNCHANGED_UNAUTHENTICATED"
    finally:
        await close_pool()


@pytest.mark.asyncio
async def test_real_pg_new_archive_is_append_only_relative_to_pin(tmp_path):
    _require_pg()
    try:
        await _archive(tmp_path, "before")
        baseline, pin = await _baseline()
        await _archive(tmp_path, "after")
        assert (await check_registry_against_pin(
            reference=baseline, pinned_reference_sha256=pin,
        )) == "HISTORY_EXTENDED_UNAUTHENTICATED"
    finally:
        await close_pool()


@pytest.mark.asyncio
async def test_real_pg_privileged_history_deletion_is_detected(tmp_path):
    _require_pg()
    try:
        await _archive(tmp_path, "keep")
        path, victim = await _archive(tmp_path, "delete")
        baseline, pin = await _baseline()
        pool = await get_pool()
        async with pool.connection() as conn:
            async with conn.transaction():
                await conn.execute(
                    "DELETE FROM audit_case_observations WHERE packet_id = %s",
                    (victim,),
                )
                await conn.execute(
                    "DELETE FROM audit_packet_inventory WHERE packet_id = %s",
                    (victim,),
                )
        assert (await check_registry_against_pin(
            reference=baseline, pinned_reference_sha256=pin,
        )) == "HISTORY_DIVERGED"
        # Archive can be rebuilt in this *synthetic* fixture. Reattaining a
        # matching local hash is NOT proof that a real rollback never happened.
        result = await PostgresAuditReplayRegistry().ingest(
            packet_root=tmp_path, profile_paths=[path],
        )
        assert result.status == "NEW_OBSERVATION", result
    finally:
        await close_pool()


@pytest.mark.asyncio
async def test_real_pg_in_place_case_tamper_is_incomplete_not_success(tmp_path):
    _require_pg()
    try:
        _, target = await _archive(tmp_path, "tamper")
        baseline, pin = await _baseline()
        pool = await get_pool()
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT record FROM audit_case_observations WHERE packet_id = %s",
                (target,),
            )
            original = (await cur.fetchone())[0]
            async with conn.transaction():
                await conn.execute(
                    "UPDATE audit_case_observations "
                    "SET record = jsonb_set(record, '{operation_id}', "
                    "to_jsonb(%s::text)) WHERE packet_id = %s",
                    ("forged-op", target),
                )
        try:
            assert (await check_registry_against_pin(
                reference=baseline, pinned_reference_sha256=pin,
            )) == "INCOMPLETE"
        finally:
            async with pool.connection() as conn:
                async with conn.transaction():
                    await conn.execute(
                        "UPDATE audit_case_observations SET record = %s "
                        "WHERE packet_id = %s", (Jsonb(original), target),
                    )
    finally:
        await close_pool()


@pytest.mark.asyncio
async def test_real_pg_anchor_substitution_and_storage_outage(tmp_path, monkeypatch):
    _require_pg()
    try:
        await _archive(tmp_path, "anchor")
        baseline, pin = await _baseline()
        assert (await check_registry_against_pin(
            reference=baseline, pinned_reference_sha256="f" * 64,
        )) == "REFERENCE_ANCHOR_MISMATCH"
        assert (await check_registry_against_pin(
            reference=baseline, pinned_reference_sha256="",
        )) == "ANCHOR_REQUIRED"

        async def down():
            raise OSError("synthetic service unavailable")

        monkeypatch.setattr(
            "scripts.validation.audit_registry_checkpoint_v0_1.get_pool",
            down,
        )
        assert (await check_registry_against_pin(
            reference=baseline, pinned_reference_sha256=pin,
        )) == "REGISTRY_UNAVAILABLE"
    finally:
        await close_pool()
