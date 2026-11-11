"""Real PostgreSQL + actual TLS tests for remote custody anchor verification.

A local HTTPS fixture is NOT an independently hosted custodian. The test
exercises transport/cert checking, cryptographic pinning, and SQL tamper
detection together without production credentials or live external effects.
"""
from __future__ import annotations

import os

import pytest

from scripts.validation.audit_checkpoint_signed_custody_v0_1 import sign_checkpoint
from scripts.validation.audit_remote_custody_https_v0_1 import (
    verify_registry_against_https_custody,
)
from scripts.validation.audit_registry_checkpoint_v0_1 import _digest
from test_audit_checkpoint_signed_custody_postgresql_v0_1 import (
    ZERO, archive, baseline, ephemeral_key,
)
from test_audit_remote_custody_https_v0_1 import synthetic_https_anchor
from veritas_os.storage.db import close_pool, get_pool

pytestmark = [pytest.mark.postgresql, pytest.mark.contention]


@pytest.mark.asyncio
async def test_signed_remote_https_head_detects_deleted_postgresql_packet(tmp_path):
    if not os.getenv("VERITAS_DATABASE_URL", "").startswith("postgresql"):
        pytest.skip("PostgreSQL service required")
    try:
        await archive(tmp_path, "remote-anchor-seed")
        packet_id = await archive(tmp_path, "remote-anchor-to-delete")
        reference = await baseline()
        key, pub = ephemeral_key()
        receipt = sign_checkpoint(
            reference, private_key_raw=key, sequence=1,
            previous_receipt_sha256=ZERO,
        )
        anchor = {
            "format_version": "veritas.audit-custody-remote-head/0.1",
            "scope": "LOCAL_AUDIT_OBSERVATION_ONLY",
            "signer_public_key_hex": pub,
            "latest_receipt_sha256": _digest(receipt),
            "sequence": 1,
        }
        with synthetic_https_anchor(tmp_path / "tls", anchor) as (url, ca):
            args = {
                "reference": reference, "receipt": receipt,
                "endpoint": url, "expected_hostname": "localhost",
                "ca_bundle": ca, "trusted_signer_public_key_hex": pub,
                "minimum_sequence": 1,
            }
            assert await verify_registry_against_https_custody(**args) == (
                "HISTORY_UNCHANGED_UNAUTHENTICATED"
            )
            pool = await get_pool()
            async with pool.connection() as conn:
                async with conn.transaction():
                    await conn.execute(
                        "DELETE FROM audit_case_observations WHERE packet_id=%s",
                        (packet_id,),
                    )
                    await conn.execute(
                        "DELETE FROM audit_packet_inventory WHERE packet_id=%s",
                        (packet_id,),
                    )
            assert await verify_registry_against_https_custody(**args) == (
                "HISTORY_DIVERGED"
            )
            assert await verify_registry_against_https_custody(
                **{**args, "minimum_sequence": 2}
            ) == "REMOTE_HEAD_SEQUENCE_ROLLBACK"
    finally:
        await close_pool()
