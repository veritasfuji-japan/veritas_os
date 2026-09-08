"""ASGI-only tests with synthetic tokens; no listener or real credential access."""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from veritas_os.policy.sandbox_event_service import (
    SandboxServiceTokens, create_sandbox_event_service,
)
from veritas_os.policy.sandbox_event_store import (
    PostgresSandboxEventStore, SandboxEventStoreError, SandboxOperation, parse_event,
)
from veritas_os.security.hash import sha256_of_canonical_json

NOW = datetime(2026, 9, 8, tzinfo=timezone.utc)
WRITER = "synthetic-writer-" + "w" * 32
READER = "synthetic-reader-" + "r" * 32
EVENT = {"event_id": "9d914b43-0cb6-4c48-84fa-d4f7a05231ca", "message": "synthetic"}


class Pool:
    """SQL-shape double only; concurrency proof belongs to real PostgreSQL tests."""

    def __init__(self):
        self.rows = {}
        self.result = None
        self.fail_commit = False
        self.fail_read = False
        self.calls = []

    @asynccontextmanager
    async def connection(self):
        yield self

    @asynccontextmanager
    async def transaction(self):
        yield self
        if self.fail_commit:
            raise RuntimeError(WRITER)

    async def execute(self, sql, args=None):
        self.calls.append(sql)
        if sql.startswith("INSERT"):
            op, key, event, message, digest = args
            duplicate = key in self.rows or any(row[2] == event for row in self.rows.values())
            self.result = None if duplicate else (op,)
            if not duplicate:
                self.rows[key] = (op, key, event, digest, message)
        elif sql.startswith("SELECT"):
            if self.fail_read:
                raise RuntimeError(WRITER)
            if "WHERE operation_id=" in sql:
                self.result = next((row for row in self.rows.values() if row[0] == args[0]), None)
            else:
                self.result = self.rows.get(args[0])
        return self

    async def fetchone(self):
        return self.result


def tokens(**changes):
    return SandboxServiceTokens(**{
        "writer": SecretStr(WRITER), "reader": SecretStr(READER),
        "valid_until": NOW + timedelta(hours=1), **changes,
    })


def client(pool=None, config=None, clock=lambda: NOW):
    store = PostgresSandboxEventStore(pool or Pool())
    app = create_sandbox_event_service(store=store, tokens=config or tokens(), clock=clock)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test.invalid")


def headers(token=WRITER, key="original-key"):
    return {"Authorization": f"Bearer {token}", "Idempotency-Key": key, "Content-Type": "application/json"}


@pytest.mark.asyncio
async def test_registration_duplicates_conflicts_and_lookup():
    pool = Pool()
    async with client(pool) as c:
        a = await c.post("/v1/events", json=EVENT, headers=headers())
        assert a.status_code == 201
        b = await c.post("/v1/events", json=EVENT, headers=headers())
        assert b.status_code == 200 and a.json() == b.json()
        for body, key in [({**EVENT, "message": "changed"}, "original-key"), (EVENT, "another-key")]:
            assert (await c.post("/v1/events", json=body, headers=headers(key=key))).status_code == 409
        op = a.json()
        for path in [f'/v1/operations/{op["operation_id"]}', "/v1/operations?idempotency_key=original-key"]:
            r = await c.get(path, headers=headers(READER))
            assert r.status_code == 200 and r.json() == op
            assert r.headers["cache-control"] == "no-store"
        assert (await c.post("/v1/events", json=EVENT, headers=headers(READER))).status_code == 401
    assert len(pool.rows) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("auth", [None, "Bearer wrong", "Basic wrong", "Bearer 日本語"])
async def test_unauthorized_never_touches_db(auth):
    pool = Pool()
    h = {} if auth is None else {"authorization": auth}
    if auth and "日本語" in auth:
        h = [(b"authorization", auth.encode("utf-8"))]
    async with client(pool) as c:
        assert (await c.post("/v1/events", content=b"bad", headers=h)).status_code == 401
        assert (await c.get("/v1/operations?idempotency_key=key", headers=h)).status_code == 401
    assert not pool.calls


@pytest.mark.asyncio
async def test_duplicate_auth_and_expired_or_broken_clock_fail_closed():
    async with client() as c:
        h = [("authorization", f"Bearer {WRITER}")] * 2
        assert (await c.get("/v1/operations?idempotency_key=key", headers=h)).status_code == 401
    def broken():
        raise RuntimeError(WRITER)
    for clock in [lambda: NOW + timedelta(hours=1), broken, lambda: NOW.replace(tzinfo=None)]:
        async with client(clock=clock) as c:
            assert (await c.get("/v1/operations?idempotency_key=key", headers=headers())).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", [
    b"{}", b"[]", b"null", b'{"event_id":"x","message":"a"}',
    json.dumps({**EVENT, "message": ""}).encode(),
    json.dumps({**EVENT, "message": "x" * 257}).encode(),
    json.dumps({**EVENT, "message": "\x00"}).encode(),
    json.dumps({**EVENT, "extra": 1}).encode(),
    json.dumps({**EVENT, "message": 1}).encode(),
    b'{"message":"a","message":"b"}', b"\xff", b"[" * 1200,
])
async def test_invalid_payloads_are_sanitized_before_store(raw):
    pool = Pool()
    async with client(pool) as c:
        r = await c.post("/v1/events", content=raw, headers=headers())
        assert r.status_code == 400
        assert r.json() == {"detail": "SSE_INVALID_REQUEST"}
    assert not pool.calls


@pytest.mark.asyncio
async def test_body_size_media_type_and_duplicate_key_headers():
    async with client() as c:
        assert (await c.post("/v1/events", content=b"x" * 4097, headers=headers())).status_code == 413
        assert (await c.post("/v1/events", content=b"x", headers={**headers(), "Content-Type": "text/plain"})).status_code == 415
        assert (await c.post("/v1/events", content=b"x", headers={**headers(), "Content-Encoding": "gzip"})).status_code == 415
        h = list(headers().items()) + [("Idempotency-Key", "second")]
        assert (await c.post("/v1/events", json=EVENT, headers=h)).status_code == 400


@pytest.mark.asyncio
@pytest.mark.parametrize("path,status", [
    ("/v1/operations?bad=key", 400), ("/v1/operations", 400),
    ("/v1/operations?idempotency_key=a&idempotency_key=b", 400),
    ("/v1/operations/not-uuid", 400), (f"/v1/operations/{uuid4()}?x=y", 400),
    (f"/v1/operations/{uuid4()}", 404), ("/v1/operations?idempotency_key=missing", 404),
])
async def test_lookup_invalid_and_absent_is_never_success(path, status):
    async with client() as c:
        assert (await c.get(path, headers=headers(READER))).status_code == status


@pytest.mark.asyncio
async def test_lost_commit_response_is_unknown_then_original_key_recovers():
    pool = Pool()
    pool.fail_commit = True
    async with client(pool) as c:
        response = await c.post("/v1/events", json=EVENT, headers=headers())
        assert response.status_code == 503 and WRITER not in response.text
        pool.fail_commit = False
        found = await c.get("/v1/operations?idempotency_key=original-key", headers=headers(READER))
        assert found.status_code == 200
        pool.fail_read = True
        assert (await c.get("/v1/operations?idempotency_key=original-key", headers=headers())).status_code == 503
    assert len(pool.rows) == 1


@pytest.mark.parametrize("changes", [
    {"writer": SecretStr("short")}, {"reader": SecretStr(WRITER)},
    {"valid_until": NOW.replace(tzinfo=None)},
])
def test_invalid_service_configuration_rejects(changes):
    with pytest.raises(ValueError):
        create_sandbox_event_service(store=PostgresSandboxEventStore(Pool()), tokens=tokens(**changes))


@pytest.mark.asyncio
async def test_store_validates_direct_inputs_and_sanitizes_exceptions():
    with pytest.raises(ValueError):
        PostgresSandboxEventStore(None)
    with pytest.raises(ValueError):
        parse_event(b"x" * 4097)
    store = PostgresSandboxEventStore(Pool())
    for args in [{}, {"key": "bad key"}, {"key": "x", "operation_id": str(uuid4())}]:
        with pytest.raises(ValueError):
            await store.lookup(**args)
    store._pool.fail_read = True
    with pytest.raises(SandboxEventStoreError) as caught:
        await store.register(json.dumps(EVENT).encode(), "key")
    assert caught.value.__context__ is None and WRITER not in str(caught.value)
    with pytest.raises(ValueError):
        create_sandbox_event_service(store=store, tokens=None)


def test_committed_synthetic_sample_roundtrip():
    body = json.loads((Path(__file__).parent / "fixtures" / "sandbox_event_service.json").read_text())
    assert parse_event(json.dumps(body["request"]).encode()).model_dump() == body["request"]
    assert SandboxOperation.model_validate(body["operation"]).model_dump() == body["operation"]
    assert body["operation"]["payload_digest"] == sha256_of_canonical_json(body["request"])
