"""Atomic write-once receipt pairs on an already reconciled sandbox effect row.

Internal persistence seam: the owning receipt publisher reconstructs and verifies
all inputs. Matching stored bytes are required on repeat calls and readback.
"""
from __future__ import annotations

from typing import Any

from veritas_os.policy.bind_effect_reconciliation import (
    EffectStateRecord, InMemoryAtomicEffectStateStore, PostgresAtomicEffectStateStore,
)
from veritas_os.policy.sandbox_reconciliation_archive import SandboxReconciliationArchive, validate_archive
from veritas_os.security.hash import canonical_json_dumps


async def _persist_receipts(
    store: PostgresAtomicEffectStateStore | InMemoryAtomicEffectStateStore, *,
    record: EffectStateRecord, archive: SandboxReconciliationArchive, bundle: dict[str, Any],
) -> None:
    """Commit the complete pair once; reject stale lineage or different contents.

    No effect state, archive or consumption is changed. A lost acknowledgement
    can raise after commit; repeating the owning publisher recovers the same pair.
    """
    validate_archive(record, archive)
    expected = canonical_json_dumps(bundle)
    if type(store) is InMemoryAtomicEffectStateStore:
        async with store._lock:
            if store._records.get(record.operation_id) != record or store._archives.get(record.operation_id) != archive:
                raise ValueError("changed archive")
            previous = store._sandbox_receipts.get(record.operation_id)
            if previous is not None and previous != expected:
                raise ValueError("different receipts")
            store._sandbox_receipts[record.operation_id] = expected
        return
    if type(store) is not PostgresAtomicEffectStateStore:
        raise ValueError("unsupported store")
    from psycopg.types.json import Jsonb
    from veritas_os.storage.db import get_pool

    pool = await get_pool()
    params = (
        record.operation_id, record.state.value, record.revision, record.record_hash,
        Jsonb(record.model_dump(mode="json")), Jsonb(archive.model_dump(mode="json")),
    )
    read_query = (
        "SELECT sandbox_receipt_bundle FROM bind_effect_states WHERE "
        "operation_id=%s AND state=%s AND revision=%s AND record_hash=%s "
        "AND record::jsonb=%s::jsonb AND reconciliation_archive::jsonb=%s::jsonb"
    )
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE bind_effect_states SET sandbox_receipt_bundle=%s WHERE "
            "operation_id=%s AND state=%s AND revision=%s AND record_hash=%s "
            "AND record::jsonb=%s::jsonb AND reconciliation_archive::jsonb=%s::jsonb "
            "AND sandbox_receipt_bundle IS NULL", (Jsonb(bundle), *params),
        )
        cur = await conn.execute(read_query, params)
        row = await cur.fetchone()
        if row is None or canonical_json_dumps(row[0]) != expected:
            raise ValueError("receipt readback")
    # A separate committed snapshot is required before reporting publication.
    async with pool.connection() as conn:
        cur = await conn.execute(read_query, params)
        row = await cur.fetchone()
        if row is None or canonical_json_dumps(row[0]) != expected:
            raise ValueError("committed receipt readback")
