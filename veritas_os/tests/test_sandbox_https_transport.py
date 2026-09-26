"""Synthetic stream tests only: no DNS, TLS handshake or external effect."""

import asyncio
import hashlib
import json
import ssl

import pytest
from pydantic import SecretBytes

from veritas_os.policy import sandbox_https_transport as module
from veritas_os.policy.sandbox_bind_execution import SandboxDispatchRequest
from veritas_os.policy.bind_execution_capability import (
    BindExecutionCapabilityError,
    ImmutableFinalDispatch,
    PermitBinding,
    _mint_bound_execution_permit,
    canonical_headers,
    runtime_implementation_identity,
)
from veritas_os.security.hash import canonical_json_dumps, sha256_of_canonical_json

ENDPOINT = "https://sandbox.example.test/v1/events"
EVENT = {"event_id": "11111111-1111-4111-8111-111111111111", "message": "synthetic"}
TOKEN = b"synthetic-test-token-never-a-live-credential"


def request():
    return SandboxDispatchRequest(
        endpoint_url=ENDPOINT, payload_json=canonical_json_dumps(EVENT),
        payload_digest=sha256_of_canonical_json(EVENT), idempotency_key="original-key",
        attempt_id="attempt",
    )


async def authorized_send(transport, req, take):
    body = req.payload_json.encode()
    runtime = runtime_implementation_identity(transport)
    identity = hashlib.sha256(body + req.endpoint_url.encode()).hexdigest()
    dispatch = ImmutableFinalDispatch(
        effect_boundary_id="native-v2-sandbox-action",
        dispatch_kind="ACTION",
        method="POST",
        canonical_endpoint=req.endpoint_url,
        canonical_bound_headers=canonical_headers({
            "content-type": "application/json", "idempotency-key": req.idempotency_key,
        }),
        body_bytes=body,
        body_digest=req.payload_digest,
        request_identity=identity,
        idempotency_identity=req.idempotency_key,
        credential_reference_digest="reference",
        credential_scope_digest="scope",
        authorization_consumption_id="consumption",
        runtime_implementation_identity=runtime,
    )
    binding = PermitBinding(
        coverage_entry_id="bcb-v1-native-v2-sandbox-action",
        operation_id=req.attempt_id,
        action_class="sandbox.event.register.v1",
        dispatch_kind="ACTION",
        execution_intent_hash="intent",
        authorization_id="authorization",
        authorization_hash="hash",
        authorization_consumption_id="consumption",
        target_identity=req.endpoint_url,
        runtime_implementation_identity=runtime,
        effect_boundary_id=dispatch.effect_boundary_id,
        endpoint_identity=dispatch.canonical_endpoint,
        credential_reference_digest=dispatch.credential_reference_digest,
        credential_scope_digest=dispatch.credential_scope_digest,
        request_body_digest=dispatch.body_digest,
        request_identity=dispatch.request_identity,
        idempotency_identity=dispatch.idempotency_identity,
    )
    return await transport.send_once(
        req,
        take_material=take,
        permit=_mint_bound_execution_permit(binding),
        permit_binding=binding,
        final_dispatch=dispatch,
    )


def response(status=201, **changes):
    operation = dict(operation_id="22222222-2222-4222-8222-222222222222",
                     event_id=EVENT["event_id"], payload_digest=request().payload_digest,
                     idempotency_key="original-key", state="PERSISTED")
    operation.update(changes)
    body = json.dumps(operation).encode()
    return (f"HTTP/1.1 {status} Test\r\nContent-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n\r\n").encode() + body


class Writer:
    def __init__(self):
        self.writes = []
        self.transport = self
        self.aborted = False

    def write(self, wire):
        self.writes.append(wire)

    async def drain(self):
        pass

    def abort(self):
        self.aborted = True


def setup(monkeypatch, raw):
    writer, calls, taken = Writer(), [], []

    async def connect(host, port, **kwargs):
        calls.append((host, port, kwargs))
        reader = asyncio.StreamReader(limit=8192)
        reader.feed_data(raw)
        reader.feed_eof()
        return reader, writer

    def take():
        assert len(calls) == 1 and not writer.writes
        taken.append(True)
        return SecretBytes(TOKEN)

    monkeypatch.setattr(module.asyncio, "open_connection", connect)
    return writer, calls, taken, take


@pytest.mark.asyncio
@pytest.mark.parametrize("status,expected", [
    (201, "HTTP_201_MATCHING_ACK"), (200, "HTTP_200_MATCHING_ACK"),
    (409, "HTTP_409_CONFLICT"), (503, "HTTP_503_UNKNOWN"),
    (302, "HTTP_RESPONSE_UNKNOWN"), (401, "HTTP_RESPONSE_UNKNOWN"),
    (500, "HTTP_RESPONSE_UNKNOWN"),
])
async def test_single_exact_post_and_observations(monkeypatch, status, expected):
    writer, calls, taken, take = setup(monkeypatch, response(status))
    result = await authorized_send(
        module.SandboxHTTPSTransport(endpoint_url=ENDPOINT), request(), take
    )
    assert result == expected
    assert len(writer.writes) == len(calls) == len(taken) == 1
    wire = writer.writes[0]
    assert wire.endswith(request().payload_json.encode())
    assert b"Authorization: Bearer " + TOKEN + b"\r\n" in wire
    assert b"Idempotency-Key: original-key\r\n" in wire
    assert calls[0][:2] == ("sandbox.example.test", 443)
    tls = calls[0][2]["ssl"]
    assert tls.check_hostname and tls.verify_mode == ssl.CERT_REQUIRED
    assert calls[0][2]["server_hostname"] == "sandbox.example.test"
    assert writer.aborted


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [
    ("event_id", "other"), ("operation_id", "invalid"), ("payload_digest", "0" * 64),
    ("idempotency_key", "substituted"), ("state", "SUCCESS"), ("secret", "untrusted"),
])
async def test_mismatched_response_is_unknown(monkeypatch, field, value):
    writer, calls, taken, take = setup(monkeypatch, response(**{field: value}))
    with pytest.raises(module.SandboxHTTPTransportError) as caught:
        await authorized_send(
            module.SandboxHTTPSTransport(endpoint_url=ENDPOINT), request(), take
        )
    assert caught.value.__context__ is None
    assert len(calls) == len(writer.writes) == 1 and writer.aborted


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", [
    b"garbage\r\n\r\n", b"HTTP/1.1 201 OK\r\nContent-Length: 9999\r\n\r\n",
    response().replace(b"Content-Type:", b"Content-Length: 0\r\nContent-Type:"),
    response().replace(b"Content-Type:", b"Transfer-Encoding: chunked\r\nContent-Type:"),
    response().replace(b"application/json", b"text/plain"), response()[:-5],
    b"x" * 9000 + b"\r\n\r\n",
])
async def test_malformed_bounded_response_no_retry(monkeypatch, raw):
    writer, calls, taken, take = setup(monkeypatch, raw)
    with pytest.raises(module.SandboxHTTPTransportError):
        await authorized_send(
            module.SandboxHTTPSTransport(endpoint_url=ENDPOINT), request(), take
        )
    assert len(calls) == 1 and writer.aborted


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["tls", "late", "cancel", "token", "endpoint", "digest", "key"])
async def test_failure_prevents_write(monkeypatch, mode):
    writer, calls, taken, take = setup(monkeypatch, response())
    req = request()
    if mode in {"tls", "cancel"}:
        async def fail(*args, **kwargs):
            if mode == "cancel":
                raise asyncio.CancelledError(TOKEN.decode())
            raise ssl.SSLError(TOKEN.decode())
        monkeypatch.setattr(module.asyncio, "open_connection", fail)
    elif mode == "late":
        def take():
            raise ValueError("send window exceeded")
    elif mode == "token":
        def take():
            return SecretBytes(TOKEN + b"\r\nInjected: true")
    else:
        updates = {"endpoint": {"endpoint_url": "https://other.test/v1/events"},
                   "digest": {"payload_digest": "0" * 64},
                   "key": {"idempotency_key": "bad\r\nkey"}}
        req = req.model_copy(update=updates[mode])
    if mode == "cancel":
        error = asyncio.CancelledError
    elif mode in {"digest", "key"}:
        error = BindExecutionCapabilityError
    else:
        error = module.SandboxHTTPTransportError
    with pytest.raises(error) as caught:
        await authorized_send(
            module.SandboxHTTPSTransport(endpoint_url=ENDPOINT), req, take
        )
    assert not writer.writes
    if mode in {"digest", "key"}:
        assert calls == []
    assert TOKEN.decode() not in str(caught.value) and caught.value.__context__ is None


@pytest.mark.parametrize("url", ["http://sandbox.test/v1/events", "https://sandbox.test/other",
                                      "https://user@sandbox.test/v1/events", "https://127.0.0.1/v1/events"])
def test_invalid_configuration(url):
    with pytest.raises(module.SandboxHTTPTransportError):
        module.SandboxHTTPSTransport(endpoint_url=url)


@pytest.mark.asyncio
async def test_timeout_after_write_does_not_retry(monkeypatch):
    writer, calls, taken, take = setup(monkeypatch, response())

    async def stall():
        await asyncio.Event().wait()

    writer.drain = stall
    monkeypatch.setattr(module, "REQUEST_TIMEOUT_SECONDS", 0.01)
    with pytest.raises(module.SandboxHTTPTransportError):
        await authorized_send(
            module.SandboxHTTPSTransport(endpoint_url=ENDPOINT), request(), take
        )
    assert len(writer.writes) == len(calls) == 1 and writer.aborted


@pytest.mark.asyncio
async def test_exact_transport_can_model_observation_loss_after_send(monkeypatch):
    writer, calls, taken, take = setup(monkeypatch, response())
    transport = module.SandboxHTTPSTransport(
        endpoint_url=ENDPOINT,
        _discard_response_after_observation=True,
    )
    with pytest.raises(module.SandboxHTTPTransportError):
        await authorized_send(transport, request(), take)
    assert transport.last_observation == "HTTP_201_MATCHING_ACK"
    assert transport.send_calls == 1
    assert len(writer.writes) == len(calls) == len(taken) == 1


@pytest.mark.asyncio
async def test_missing_persisted_state_is_not_inferred(monkeypatch):
    raw = response()
    header, body = raw.split(b"\r\n\r\n", 1)
    payload = json.loads(body)
    payload.pop("state")
    body = json.dumps(payload).encode()
    raw = (f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
           f"Content-Length: {len(body)}\r\n\r\n").encode() + body
    writer, calls, taken, take = setup(monkeypatch, raw)
    with pytest.raises(module.SandboxHTTPTransportError):
        await authorized_send(
            module.SandboxHTTPSTransport(endpoint_url=ENDPOINT), request(), take
        )
