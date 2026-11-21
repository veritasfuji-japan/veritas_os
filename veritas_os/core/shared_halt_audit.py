"""Deliver committed resume audit records without locking emergency halt state."""

from __future__ import annotations

import asyncio
from dataclasses import replace
import json
import logging

from veritas_os.core import shared_halt
from veritas_os.logging.encryption import decrypt, encrypt
from veritas_os.logging.trust_log import append_trust_log
from veritas_os.policy.bind_artifacts import (
    BindReceipt,
    ExecutionIntent,
    build_bind_receipt_trustlog_entry,
    build_execution_intent_trustlog_entry,
    hash_bind_receipt,
)

logger = logging.getLogger(__name__)


def queue_resume_audit(halt_id: str, intent: ExecutionIntent, receipt: BindReceipt) -> dict:
    """Queue immutable audit entries in the transaction that clears the halt."""
    from psycopg.types.json import Jsonb

    finalized = replace(receipt, bind_receipt_hash=hash_bind_receipt(receipt)).to_dict()
    entries = [
        build_execution_intent_trustlog_entry(intent),
        build_bind_receipt_trustlog_entry(finalized),
    ]
    with shared_halt.transaction() as conn:
        conn.execute(
            """INSERT INTO deployment_resume_receipts (deployment_id, halt_id, receipt, audit_entries)
               VALUES (%s,%s,%s,%s)""",
            (shared_halt.deployment(), halt_id, Jsonb(finalized), encrypt(json.dumps(entries))),
        )
    return finalized


def publish_next_resume_audit() -> bool:
    """Deliver one pending receipt while locking only its durable audit row."""
    deployment = shared_halt.deployment()
    with shared_halt.transaction() as conn:
        row = conn.execute(
            """SELECT halt_id, receipt->>'bind_receipt_id', audit_entries
               FROM deployment_resume_receipts
               WHERE deployment_id=%s AND published_at IS NULL AND next_attempt_at <= clock_timestamp()
               ORDER BY queued_at, halt_id LIMIT 1 FOR UPDATE SKIP LOCKED""",
            (deployment,),
        ).fetchone()
        if row is None:
            return False
        halt_id, receipt_id, encrypted = row
        try:
            for entry in json.loads(decrypt(encrypted)):
                publication_id = f"{receipt_id}:{entry['kind']}"
                append_trust_log(entry, publication_id=publication_id)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            logger.warning("Resume audit publication will retry (%s)", type(exc).__name__)
            conn.execute(
                """UPDATE deployment_resume_receipts
                   SET next_attempt_at=clock_timestamp() + interval '30 seconds'
                   WHERE deployment_id=%s AND halt_id=%s""",
                (deployment, halt_id),
            )
        else:
            conn.execute(
                """UPDATE deployment_resume_receipts SET published_at=clock_timestamp()
                   WHERE deployment_id=%s AND halt_id=%s""",
                (deployment, halt_id),
            )
        return True


async def run_resume_audit_publisher() -> None:
    """Retry committed records across process restarts."""
    while True:
        try:
            for _ in range(16):
                if not await asyncio.to_thread(publish_next_resume_audit):
                    break
        except shared_halt.HaltStoreUnavailable:
            logger.warning("Resume audit queue unavailable, retrying")
        await asyncio.sleep(1)
