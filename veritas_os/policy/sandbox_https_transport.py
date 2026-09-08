"""Opt-in sandbox HTTPS sender; no listener, deployment or default credentials.

Only the owning executor may configure this transport. Request models are not
capabilities. TLS authenticates the configured DNS identity through reviewed CA
roots, not the truth of an operation. Responses never confirm external effect.
"""

from __future__ import annotations

import asyncio
import json
import re
import ssl
from typing import Callable

from pydantic import SecretBytes

from veritas_os.policy.sandbox_action_binding import _unique_object
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
            request = SandboxDispatchRequest.model_validate(request.model_dump())
            if request.endpoint_url != self._endpoint:
                raise ValueError("endpoint")
            body = request.payload_json.encode("utf-8")
            event = parse_event(body)
            if (request.payload_digest != sha256_of_canonical_json(event.model_dump())
                    or request.payload_json != canonical_json_dumps(event.model_dump())):
                raise ValueError("payload")
            key = validate_key(request.idempotency_key)
            # All non-secret work is performed before the final one-use callback.
            prefix = (
                f"POST /v1/events HTTP/1.1\r\nHost: {self._host}\r\n"
                f"Idempotency-Key: {key}\r\nContent-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\nConnection: close\r\nAuthorization: Bearer "
            ).encode("ascii")
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
                return await _read_observation(reader, request, event.event_id)
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
    reader: asyncio.StreamReader, request: SandboxDispatchRequest, event_id: str,
) -> SandboxHTTPObservation:
    """Accept only bounded Content-Length HTTP/1.1 JSON from the fixed service.

    Chunked, encoded, duplicate-header, interim and malformed responses remain
    unknown. This deliberately narrow client does not follow response locations.
    """
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
    if status == 409:
        return "HTTP_409_CONFLICT"
    if status == 503:
        return "HTTP_503_UNKNOWN"
    if status not in {200, 201}:
        return "HTTP_RESPONSE_UNKNOWN"
    if headers.get(b"content-type", b"").split(b";")[0].lower() != b"application/json":
        raise ValueError("type")
    operation = SandboxOperation.model_validate(
        json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object),
    )
    validate_uuid(operation.operation_id)
    if (operation.idempotency_key != request.idempotency_key
            or operation.event_id != event_id or operation.payload_digest != request.payload_digest):
        raise ValueError("binding")
    return "HTTP_201_MATCHING_ACK" if status == 201 else "HTTP_200_MATCHING_ACK"
