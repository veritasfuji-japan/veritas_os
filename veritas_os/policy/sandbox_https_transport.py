"""Opt-in sandbox HTTPS sender; no listener, deployment or default credentials.

Only the owning executor may configure this transport. Request models are not
capabilities. TLS authenticates the configured DNS identity through reviewed CA
roots, not the truth of an operation. Responses never confirm external effect.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import ssl
from typing import Callable

from pydantic import SecretBytes

from veritas_os.policy.sandbox_action_binding import _unique_object
from veritas_os.policy.bind_coverage_registry import match_frozen_runtime_boundary
from veritas_os.policy.bind_execution_capability import (
    ImmutableFinalDispatch, PermitBinding, canonical_headers,
    consume_bound_execution_permit, runtime_implementation_identity,
)
from veritas_os.policy.sandbox_bind_execution import (
    SandboxDispatchRequest, SandboxHTTPObservation,
)
from veritas_os.policy.sandbox_event_store import (
    SandboxOperation, parse_event, validate_key, validate_uuid,
)
from veritas_os.security.hash import canonical_json_dumps, sha256_of_canonical_json

REQUEST_TIMEOUT_SECONDS = 5


class SandboxHTTPTransportError(ValueError):
    """Sanitized failure; the caller must retain durable uncertainty."""


class SandboxHTTPSTransport:
    """One fresh TLS connection per call, one POST, no redirects/proxies/retries.

    The endpoint is independently supplied by the executor, never a response or
    request-selected destination. ca_pem is reviewed CA configuration, not an
    arbitrary SSLContext that could disable verification. None uses system roots.
    Production use still requires section 9 deployment approval and TLS tests.
    """

    def __init__(self, *, endpoint_url: str, ca_pem: str | None = None) -> None:
        if type(endpoint_url) is not str or not re.fullmatch(
            r"https://(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
            r"[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?/v1/events", endpoint_url,
        ):
            raise SandboxHTTPTransportError("SHT_ENDPOINT_INVALID")
        self._endpoint = endpoint_url
        self._host = endpoint_url[len("https://"):-len("/v1/events")]
        self._tls = ssl.create_default_context(cadata=ca_pem)
        self._tls.minimum_version = ssl.TLSVersion.TLSv1_2
        self._tls.set_alpn_protocols(["http/1.1"])

    async def send_once(
        self, request: SandboxDispatchRequest, *, take_material: Callable[[], SecretBytes],
        permit: object | None = None,
        permit_binding: PermitBinding | None = None,
        final_dispatch: ImmutableFinalDispatch | None = None,
    ) -> SandboxHTTPObservation:
        """Take material after TLS, then write without any intervening await.

        Five seconds includes DNS, TLS, write and bounded response read. Unsupported
        HTTP framing stays unknown. The response body and exception never escape.
        Closing drops references; it does not guarantee Python memory erasure.
        """
        writer = None
        token = material = wire = None
        cancelled = False
        try:
            # Freeze and validate every caller-provided semantic before consuming
            # authority. No request field is read below the consume call.
            frozen_request = SandboxDispatchRequest.model_validate(request.model_dump())
            if (
                type(permit_binding) is not PermitBinding
                or type(final_dispatch) is not ImmutableFinalDispatch
                or final_dispatch.runtime_implementation_identity
                != runtime_implementation_identity(self)
            ):
                raise ValueError("capability")
            match_frozen_runtime_boundary(
                self,
                effect_boundary_id="native-v2-sandbox-action",
                dispatch_kind="ACTION",
            )
            body = final_dispatch.body_bytes
            event = parse_event(body)
            key = validate_key(final_dispatch.idempotency_identity)
            expected_headers = canonical_headers({
                "content-type": "application/json",
                "idempotency-key": key,
            })
            expected_request_identity = hashlib.sha256(
                b"sandbox-dispatch-v1\x00"
                + final_dispatch.canonical_endpoint.encode("utf-8")
                + b"\x00"
                + body
                + b"\x00"
                + key.encode("utf-8")
            ).hexdigest()
            if (
                final_dispatch.effect_boundary_id != "native-v2-sandbox-action"
                or final_dispatch.dispatch_kind != "ACTION"
                or final_dispatch.method != "POST"
                or final_dispatch.canonical_endpoint != self._endpoint
                or final_dispatch.canonical_bound_headers != expected_headers
                or final_dispatch.request_identity != expected_request_identity
                or frozen_request.endpoint_url != final_dispatch.canonical_endpoint
                or frozen_request.payload_json.encode("utf-8") != body
                or frozen_request.payload_digest != final_dispatch.body_digest
                or frozen_request.idempotency_key != key
            ):
                raise ValueError("endpoint")
            if (
                final_dispatch.body_digest
                != sha256_of_canonical_json(event.model_dump())
                or body != canonical_json_dumps(event.model_dump()).encode("utf-8")
            ):
                raise ValueError("payload")
            prefix = (
                f"POST /v1/events HTTP/1.1\r\nHost: {self._host}\r\n"
                f"Idempotency-Key: {key}\r\nContent-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\nConnection: close\r\nAuthorization: Bearer "
            ).encode("ascii")
            event_id = event.event_id
            response_payload_digest = final_dispatch.body_digest
            response_idempotency_key = key
            consume_bound_execution_permit(permit, permit_binding, final_dispatch)
            async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                reader, writer = await asyncio.open_connection(
                    self._host, 443, ssl=self._tls, server_hostname=self._host,
                    limit=8192, ssl_handshake_timeout=5,
                )
                material = take_material()
                token = material.get_secret_value()
                if not 32 <= len(token) <= 4096 or not re.fullmatch(rb"[A-Za-z0-9._~+/-]+=*", token):
                    raise ValueError("material")
                wire = prefix + token + b"\r\n\r\n" + body
                writer.write(wire)
                token = material = wire = None
                await writer.drain()
                return await _read_observation(
                    reader,
                    idempotency_key=response_idempotency_key,
                    payload_digest=response_payload_digest,
                    event_id=event_id,
                )
        except asyncio.CancelledError:
            cancelled = True
        except Exception:
            pass
        finally:
            token = material = wire = None
            if writer is not None:
                # Abort without awaiting an untrusted peer's TLS close-notify.
                try:
                    writer.transport.abort()
                except Exception:
                    pass
        if cancelled:
            raise asyncio.CancelledError()
        raise SandboxHTTPTransportError("SHT_FAILED_OR_UNKNOWN")


async def _read_observation(
    reader: asyncio.StreamReader,
    *,
    idempotency_key: str,
    payload_digest: str,
    event_id: str,
) -> SandboxHTTPObservation:
    """Accept only bounded Content-Length HTTP/1.1 JSON from the fixed service.

    Chunked, encoded, duplicate-header, interim and malformed responses remain
    unknown. This deliberately narrow client does not follow response locations.
    """
    status, headers, raw = await _read_bounded_response(reader)
    if status == 409:
        return "HTTP_409_CONFLICT"
    if status == 503:
        return "HTTP_503_UNKNOWN"
    if status not in {200, 201}:
        return "HTTP_RESPONSE_UNKNOWN"
    operation = _parse_operation(headers, raw)
    if (
        operation.idempotency_key != idempotency_key
        or operation.event_id != event_id
        or operation.payload_digest != payload_digest
    ):
        raise ValueError("binding")
    return "HTTP_201_MATCHING_ACK" if status == 201 else "HTTP_200_MATCHING_ACK"


async def _read_bounded_response(reader: asyncio.StreamReader) -> tuple[int, dict[bytes, bytes], bytes]:
    """Bound HTTP framing only; callers independently interpret and bind content."""
    head = await reader.readuntil(b"\r\n\r\n")
    if len(head) > 8192:
        raise ValueError("headers")
    lines = head[:-4].split(b"\r\n")
    if not re.fullmatch(rb"HTTP/1\.1 [0-9]{3} [\x20-\x7e]*", lines[0]):
        raise ValueError("status")
    status = int(lines[0].split(b" ")[1])
    headers = {}
    for line in lines[1:]:
        name, value = line.split(b":", 1)
        if not re.fullmatch(rb"[A-Za-z0-9-]+", name) or name.lower() in headers:
            raise ValueError("header")
        headers[name.lower()] = value.strip()
    length = headers.get(b"content-length", b"")
    if (not re.fullmatch(rb"[0-9]{1,4}", length) or int(length) > 4096
            or b"transfer-encoding" in headers or b"content-encoding" in headers):
        raise ValueError("framing")
    raw = await reader.readexactly(int(length))
    return status, headers, raw


def _parse_operation(headers: dict[bytes, bytes], raw: bytes) -> SandboxOperation:
    """Parse service shape only, never authority or independent effect evidence."""
    if headers.get(b"content-type", b"").split(b";")[0].lower() != b"application/json":
        raise ValueError("type")
    payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    if type(payload) is not dict or set(payload) != {
        "operation_id", "idempotency_key", "event_id", "payload_digest", "state",
    }:
        raise ValueError("operation fields")
    operation = SandboxOperation.model_validate(payload)
    validate_uuid(operation.operation_id)
    return operation
