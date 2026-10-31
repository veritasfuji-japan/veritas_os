"""Real PostgreSQL tests for local audit-observation retention and replay.

All synthetic fixtures are self-declared. Persistence is not signature trust,
actual effect proof, or an execution authorization single-use check.
"""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest

from scripts.validation.audit_replay_registry_postgresql_v0_1 import (
    PostgresAuditReplayRegistry,
)
from veritas_os.storage.db import close_pool, get_pool
from test_cross_packet_replay_provenance import write_packet

pytestmark = [pytest.mark.postgresql, pytest.mark.contention]


def _require_pg() -> None:
    if not os.getenv("VERITAS_DATABASE_URL", "").startswith("postgresql"):
        pytest.skip("real PostgreSQL service container required")


def _packet(tmp_path, *, label, operation, repo="Example/Audit"):
    token = uuid4().hex
    return write_packet(
        tmp_path, label=label, packet_id="packet-" + token,
        operation_id=operation, repository=repo,
    )


@pytest.mark.asyncio
async def test_real_postgres_archive_restart_readback_and_idempotent_retry(tmp_path):
    _require_pg()
    store = PostgresAuditReplayRegistry()
    path = _packet(tmp_path, label="p", operation="op-" + uuid4().hex)
    try:
        result = await store.ingest(packet_root=tmp_path, profile_paths=[path])
        assert result.status == "NEW_OBSERVATION", result
        assert result.packet_count == result.case_count == 1
        assert (await store.ingest(packet_root=tmp_path, profile_paths=[path])).status == "ALREADY_PRESENT"

        from json import loads
        packet_id = loads((tmp_path / path).read_text())["packet_id"]
        status, cases = await store.readback(packet_id)
        assert status == "FOUND_UNAUTHENTICATED"
        assert len(cases) == 1
        assert cases[0]["origin_authentication"] == "NOT_PERFORMED"

        await close_pool()
        # Reconnect using a new pool: no reliance on process-local memory.
        restarted = PostgresAuditReplayRegistry()
        status, persisted = await restarted.readback(packet_id)
        assert status == "FOUND_UNAUTHENTICATED"
        assert persisted == cases
        assert (await restarted.ingest(packet_root=tmp_path, profile_paths=[path])).status == "ALREADY_PRESENT"
    finally:
        await close_pool()


@pytest.mark.asyncio
async def test_real_postgres_concurrent_exact_packet_has_one_new_archive(tmp_path):
    _require_pg()
    path = _packet(tmp_path, label="race", operation="op-" + uuid4().hex)
    try:
        await get_pool()
        results = await asyncio.gather(*(
            PostgresAuditReplayRegistry().ingest(
                packet_root=tmp_path, profile_paths=[path],
            ) for _ in range(12)
        ))
        assert [r.status for r in results].count("NEW_OBSERVATION") == 1, results
        assert [r.status for r in results].count("ALREADY_PRESENT") == 11, results
    finally:
        await close_pool()


@pytest.mark.asyncio
async def test_real_postgres_detects_previous_operation_across_separate_scans(tmp_path):
    _require_pg()
    operation = "shared-" + uuid4().hex
    a = _packet(tmp_path, label="a", operation=operation)
    b = _packet(tmp_path, label="b", operation=operation)
    try:
        store = PostgresAuditReplayRegistry()
        assert (await store.ingest(packet_root=tmp_path, profile_paths=[a])).status == "NEW_OBSERVATION"
        assert (await store.ingest(packet_root=tmp_path, profile_paths=[b])).status == "REPLAY_DETECTED"
        from json import loads
        packet_id = loads((tmp_path / b).read_text())["packet_id"]
        assert (await store.readback(packet_id))[0] == "NOT_FOUND"
    finally:
        await close_pool()


@pytest.mark.asyncio
async def test_real_postgres_same_operation_in_different_claimed_repo_allowed(tmp_path):
    _require_pg()
    operation = "scoped-" + uuid4().hex
    a = _packet(tmp_path, label="a", operation=operation, repo="Example/Tenant-A")
    b = _packet(tmp_path, label="b", operation=operation, repo="example/tenant-b")
    try:
        store = PostgresAuditReplayRegistry()
        assert (await store.ingest(packet_root=tmp_path, profile_paths=[a])).status == "NEW_OBSERVATION"
        assert (await store.ingest(packet_root=tmp_path, profile_paths=[b])).status == "NEW_OBSERVATION"
    finally:
        await close_pool()


@pytest.mark.asyncio
async def test_real_postgres_batch_rollback_on_later_case_replay(tmp_path):
    _require_pg()
    old_operation = "prev-" + uuid4().hex
    seed = _packet(tmp_path, label="seed", operation=old_operation)
    fresh = _packet(tmp_path, label="fresh", operation="fresh-" + uuid4().hex)
    conflicting = _packet(tmp_path, label="bad", operation=old_operation)
    try:
        store = PostgresAuditReplayRegistry()
        assert (await store.ingest(packet_root=tmp_path, profile_paths=[seed])).status == "NEW_OBSERVATION"
        result = await store.ingest(packet_root=tmp_path, profile_paths=[fresh, conflicting])
        assert result.status == "REPLAY_DETECTED", result
        from json import loads
        fresh_id = loads((tmp_path / fresh).read_text())["packet_id"]
        bad_id = loads((tmp_path / conflicting).read_text())["packet_id"]
        assert (await store.readback(fresh_id))[0] == "NOT_FOUND"
        assert (await store.readback(bad_id))[0] == "NOT_FOUND"
    finally:
        await close_pool()


@pytest.mark.asyncio
async def test_real_postgres_mixed_previous_and_new_batch_rolls_back(tmp_path):
    _require_pg()
    old = _packet(tmp_path, label="old", operation="old-" + uuid4().hex)
    new = _packet(tmp_path, label="new", operation="new-" + uuid4().hex)
    try:
        store = PostgresAuditReplayRegistry()
        assert (await store.ingest(packet_root=tmp_path, profile_paths=[old])).status == "NEW_OBSERVATION"
        assert (await store.ingest(packet_root=tmp_path, profile_paths=[old, new])).status == "REPLAY_DETECTED"
        from json import loads
        new_id = loads((tmp_path / new).read_text())["packet_id"]
        assert (await store.readback(new_id))[0] == "NOT_FOUND"
    finally:
        await close_pool()


@pytest.mark.asyncio
async def test_real_postgres_fail_closed_for_invalid_scan_and_missing_packet(tmp_path):
    _require_pg()
    store = PostgresAuditReplayRegistry()
    try:
        assert (await store.ingest(
            packet_root=tmp_path, profile_paths=["does-not-exist/profile.json"],
        )).status == "INPUT_INVALID"
        assert (await store.readback("not-present-" + uuid4().hex))[0] == "NOT_FOUND"
    finally:
        await close_pool()


@pytest.mark.asyncio
async def test_real_postgres_reused_packet_id_with_distinct_contents_is_replay(tmp_path):
    _require_pg()
    shared_id = "reused-" + uuid4().hex
    a = write_packet(
        tmp_path, label="first", packet_id=shared_id,
        operation_id="op-a-" + uuid4().hex, repository="Example/Audit",
    )
    b = write_packet(
        tmp_path, label="second", packet_id=shared_id,
        operation_id="op-b-" + uuid4().hex, repository="Example/Audit",
    )
    try:
        store = PostgresAuditReplayRegistry()
        assert (await store.ingest(packet_root=tmp_path, profile_paths=[a])).status == "NEW_OBSERVATION"
        assert (await store.ingest(packet_root=tmp_path, profile_paths=[b])).status == "REPLAY_DETECTED"
        status, records = await store.readback(shared_id)
        assert status == "FOUND_UNAUTHENTICATED"
        assert records[0]["operation_id"].startswith("op-a-")
    finally:
        await close_pool()


@pytest.mark.asyncio
async def test_storage_outage_fail_closed_without_claiming_rollback(tmp_path, monkeypatch):
    path = _packet(tmp_path, label="outage", operation="op-" + uuid4().hex)

    async def unavailable():
        raise OSError("synthetic storage outage")

    monkeypatch.setattr(
        "scripts.validation.audit_replay_registry_postgresql_v0_1.get_pool",
        unavailable,
    )
    result = await PostgresAuditReplayRegistry().ingest(
        packet_root=tmp_path, profile_paths=[path],
    )
    assert result.status == "REGISTRY_UNAVAILABLE"
    assert result.packet_count == result.case_count == 0
    assert (await PostgresAuditReplayRegistry().readback("unknown"))[0] == "REGISTRY_UNAVAILABLE"
