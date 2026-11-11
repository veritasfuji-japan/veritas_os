"""Real TLS GET-only custody service and PostgreSQL rollback integration."""
from __future__ import annotations

from contextlib import contextmanager
import http.client
import os
from pathlib import Path
import ssl
import threading

from http.server import ThreadingHTTPServer

import pytest

from scripts.validation.audit_checkpoint_signed_custody_v0_1 import sign_checkpoint
from scripts.validation.audit_custody_head_store_v0_1 import (
    create_store, make_readonly_handler, publish, read_head,
)
from scripts.validation.audit_remote_custody_https_v0_1 import (
    fetch_https_anchor, verify_registry_against_https_custody,
)
from scripts.validation.audit_registry_checkpoint_v0_1 import _digest
from test_audit_checkpoint_signed_custody_postgresql_v0_1 import (
    ZERO, archive, baseline, ephemeral_key,
)
from test_audit_checkpoint_signed_custody_v0_1 import fixture
from test_audit_remote_custody_https_v0_1 import _make_tls_certs
from veritas_os.storage.db import close_pool, get_pool


@contextmanager
def actual_tls_service(tmp_path: Path, db: Path):
    ca, cert, key = _make_tls_certs(tmp_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_readonly_handler(db))
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(str(cert), str(key))
    server.socket = ctx.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield "https://localhost:" + str(server.server_port) + "/v1/audit/checkpoints/latest", ca
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


@pytest.mark.asyncio
async def test_real_tls_readonly_head_and_explicit_write_denial(tmp_path):
    db = tmp_path / "custody.sqlite"
    ref, private, pub, receipt = fixture()
    assert create_store(db, signer_public_key_hex=pub) == "STORE_CREATED"
    with actual_tls_service(tmp_path / "tls", db) as (url, ca):
        assert (await fetch_https_anchor(
            endpoint=url, expected_hostname="localhost", ca_bundle=ca,
        ))[0] == "REMOTE_ANCHOR_UNAVAILABLE"
        assert publish(db, reference=ref, receipt=receipt) == "NEW_HEAD_PUBLISHED"
        result, head = await fetch_https_anchor(
            endpoint=url, expected_hostname="localhost", ca_bundle=ca,
        )
        assert result == "REMOTE_ANCHOR_OBSERVED"
        assert head == read_head(db)[1]
        ctx = ssl.create_default_context(cafile=str(ca))
        client = http.client.HTTPSConnection("localhost", int(url.split(":")[2].split("/")[0]), context=ctx)
        try:
            client.request("POST", "/v1/audit/checkpoints/latest", body=b"{}")
            assert client.getresponse().status == 405
        finally:
            client.close()
        assert read_head(db)[1]["sequence"] == 1


@pytest.mark.postgresql
@pytest.mark.contention
@pytest.mark.asyncio
async def test_actual_https_custodian_head_detects_privileged_pg_restore(tmp_path):
    if not os.getenv("VERITAS_DATABASE_URL", "").startswith("postgresql"):
        pytest.skip("real PostgreSQL required")
    try:
        await archive(tmp_path, "independent-custody-source")
        victim = await archive(tmp_path, "independent-custody-victim")
        ref = await baseline()
        private, pub = ephemeral_key()
        receipt = sign_checkpoint(
            ref, private_key_raw=private,
            sequence=1, previous_receipt_sha256=ZERO,
        )
        db = tmp_path / "separate-custody.sqlite"
        assert create_store(db, signer_public_key_hex=pub) == "STORE_CREATED"
        assert publish(db, reference=ref, receipt=receipt) == "NEW_HEAD_PUBLISHED"
        with actual_tls_service(tmp_path / "https", db) as (url, ca):
            params = {
                "reference": ref,
                "receipt": receipt,
                "endpoint": url,
                "expected_hostname": "localhost",
                "ca_bundle": ca,
                "trusted_signer_public_key_hex": pub,
                "minimum_sequence": 1,
            }
            assert await verify_registry_against_https_custody(**params) == (
                "HISTORY_UNCHANGED_UNAUTHENTICATED"
            )
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
            assert await verify_registry_against_https_custody(**params) == "HISTORY_DIVERGED"
            assert read_head(db)[1]["latest_receipt_sha256"] == _digest(receipt)
    finally:
        await close_pool()
