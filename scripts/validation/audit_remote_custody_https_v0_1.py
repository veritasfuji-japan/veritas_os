"""Fail-closed, read-only HTTPS lookup of separately operated audit-custody pins.

Transport authentication derives from an operator-supplied CA bundle and an
exact expected hostname, NEVER from a database row, checkpoint or receipt.
A private-key-holder's signature is verified independently by the existing
v0.1 custody verifier. No HTTP proxy, redirect, or fallback to local pins.

The remote endpoint and signer must actually be operated outside the DB
administrator's trust domain to establish operational independence. Local
loopback tests DO NOT prove that deployment property.
"""
from __future__ import annotations

import asyncio
import hmac
import http.client
import json
from pathlib import Path
import re
import ssl
from typing import Any
from urllib.parse import urlsplit

from scripts.validation.audit_checkpoint_signed_custody_v0_1 import (
    check_registry_against_signed_reference,
)

_FORMAT = "veritas.audit-custody-remote-head/0.1"
_SCOPE = "LOCAL_AUDIT_OBSERVATION_ONLY"
_PATH = "/v1/audit/checkpoints/latest"
_MAX_BYTES = 2048
_SHA = re.compile(r"^[0-9a-f]{64}$")
_HOST = re.compile(r"^[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?$")
_KEYS = {
    "format_version", "scope", "signer_public_key_hex",
    "latest_receipt_sha256", "sequence",
}


def _valid_head(value: Any) -> bool:
    """No unknown trust fields and no coercion of numeric sequence."""
    return (
        isinstance(value, dict)
        and set(value) == _KEYS
        and value["format_version"] == _FORMAT
        and value["scope"] == _SCOPE
        and isinstance(value["signer_public_key_hex"], str)
        and bool(_SHA.fullmatch(value["signer_public_key_hex"]))
        and isinstance(value["latest_receipt_sha256"], str)
        and bool(_SHA.fullmatch(value["latest_receipt_sha256"]))
        and type(value["sequence"]) is int
        and 1 <= value["sequence"] <= 1_000_000_000
    )


def _parse_url(endpoint: str, expected_hostname: str) -> tuple[str, int] | None:
    if (
        not isinstance(endpoint, str)
        or not isinstance(expected_hostname, str)
        or not _HOST.fullmatch(expected_hostname)
        or any(ord(c) <= 32 or ord(c) == 127 or c == "\\" for c in endpoint)
    ):
        return None
    try:
        u = urlsplit(endpoint)
        if (
            u.scheme != "https"
            or u.hostname != expected_hostname
            or u.username is not None or u.password is not None
            or u.query or u.fragment or u.path != _PATH
            or not u.netloc or u.hostname is None
        ):
            return None
        port = u.port or 443
        if not 1 <= port <= 65535:
            return None
    except ValueError:
        return None
    return u.hostname, port


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DUPLICATE_ANCHOR_KEY")
        result[key] = value
    return result


def _reject_json_constant(_: str) -> None:
    raise ValueError("NONFINITE_JSON")


def _fetch_blocking(
    *, host: str, port: int, ca_bundle: Path, timeout_seconds: float,
) -> Any:
    """http.client avoids environment proxies and never follows redirects."""
    context = ssl.create_default_context(cafile=str(ca_bundle))
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    conn = http.client.HTTPSConnection(
        host=host, port=port, context=context, timeout=timeout_seconds,
    )
    try:
        conn.request(
            "GET", _PATH,
            headers={"Accept": "application/json", "Connection": "close"},
        )
        reply = conn.getresponse()
        if reply.status != 200:
            raise OSError("REMOTE_HTTP_NOT_OK")
        content_type = reply.getheader("Content-Type", "")
        if content_type.split(";", 1)[0].strip().lower() != "application/json":
            raise ValueError("ANCHOR_CONTENT_TYPE")
        if reply.getheader("Content-Encoding"):
            raise ValueError("ANCHOR_COMPRESSION_UNSUPPORTED")
        body = reply.read(_MAX_BYTES + 1)
        if not body or len(body) > _MAX_BYTES:
            raise ValueError("ANCHOR_SIZE")
        return json.loads(
            body.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    finally:
        conn.close()


async def fetch_https_anchor(
    *, endpoint: str, expected_hostname: str, ca_bundle: Path,
    timeout_seconds: float = 5.0,
) -> tuple[str, dict[str, Any] | None]:
    """Return an *authenticated transport observation*, not a custody proof."""
    target = _parse_url(endpoint, expected_hostname)
    if target is None or not isinstance(ca_bundle, Path):
        return "REMOTE_ENDPOINT_INVALID", None
    if type(timeout_seconds) not in (int, float) or not 0.1 <= timeout_seconds <= 10:
        return "REMOTE_ENDPOINT_INVALID", None
    try:
        value = await asyncio.to_thread(
            _fetch_blocking, host=target[0], port=target[1],
            ca_bundle=ca_bundle, timeout_seconds=timeout_seconds,
        )
    except (OSError, ssl.SSLError, ValueError, TimeoutError, UnicodeError, http.client.HTTPException):
        return "REMOTE_ANCHOR_UNAVAILABLE", None
    if not _valid_head(value):
        return "REMOTE_ANCHOR_INVALID", None
    return "REMOTE_ANCHOR_OBSERVED", value


async def verify_registry_against_https_custody(
    *, reference: Any, receipt: Any,
    endpoint: str, expected_hostname: str, ca_bundle: Path,
    trusted_signer_public_key_hex: str, minimum_sequence: int,
) -> str:
    """Never query the registry if the remote transport/head is inconsistent.

    The supplied key and minimum sequence MUST be independently controlled
    by the verifier, NOT taken from the retrieved anchor itself.
    """
    if (
        not isinstance(trusted_signer_public_key_hex, str)
        or not _SHA.fullmatch(trusted_signer_public_key_hex)
        or type(minimum_sequence) is not int
        or not 1 <= minimum_sequence <= 1_000_000_000
    ):
        return "EXTERNAL_TRUST_REQUIRED"
    state, remote = await fetch_https_anchor(
        endpoint=endpoint,
        expected_hostname=expected_hostname,
        ca_bundle=ca_bundle,
    )
    if state != "REMOTE_ANCHOR_OBSERVED" or remote is None:
        return state
    if not hmac.compare_digest(
        remote["signer_public_key_hex"], trusted_signer_public_key_hex,
    ):
        return "REMOTE_SIGNER_PIN_MISMATCH"
    if remote["sequence"] < minimum_sequence:
        return "REMOTE_HEAD_SEQUENCE_ROLLBACK"
    if not isinstance(receipt, dict) or receipt.get("sequence") != remote["sequence"]:
        return "REMOTE_RECEIPT_SEQUENCE_MISMATCH"
    return await check_registry_against_signed_reference(
        reference=reference, receipt=receipt,
        trusted_public_key_hex=trusted_signer_public_key_hex,
        expected_head_sha256=remote["latest_receipt_sha256"],
    )
