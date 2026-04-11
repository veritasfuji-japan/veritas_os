"""RFC 3161 TSA anchor backend for TrustLog transparency anchoring.

This module extends the existing ``AnchorBackend`` protocol with an RFC 3161
Time-Stamp Authority (TSA) backend.  The TSA backend sends the TrustLog chain
head digest to an external TSA service and stores the resulting timestamp
receipt as proof of existence at a specific point in time.

Design rationale — TSA over blockchain:
    RFC 3161 is a well-established, IETF-standardized timestamping protocol
    supported by all major Certificate Authorities.  It provides legally
    recognized third-party anchoring without the operational complexity,
    cost, or environmental concerns of blockchain-based approaches.

Environment variables:
    VERITAS_TRUSTLOG_ANCHOR_BACKEND=tsa
    VERITAS_TRUSTLOG_TSA_URL=https://freetsa.org/tsr  (or any RFC 3161 endpoint)
    VERITAS_TRUSTLOG_TSA_TIMEOUT_SECONDS=10
    VERITAS_TRUSTLOG_TSA_CA_BUNDLE=/path/to/tsa-ca-bundle.pem  (optional)
    VERITAS_TRUSTLOG_TSA_AUTH_HEADER=Bearer <token>  (optional)
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import struct
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx

from veritas_os.audit.trustlog_signed import AnchorReceipt

_logger = logging.getLogger(__name__)

# ── Defaults ──────────────────────────────────────────────────────────────
_DEFAULT_TSA_TIMEOUT_SECONDS = 10
_TSA_CONTENT_TYPE = "application/timestamp-query"
_TSA_ACCEPT = "application/timestamp-reply"

# ── ASN.1 / DER helpers (minimal, dependency-free) ────────────────────────
# We build a minimal RFC 3161 TimeStampReq without a full ASN.1 library.
# Structure: SEQUENCE { version INTEGER(1), messageImprint MessageImprint,
#                       nonce INTEGER, certReq BOOLEAN(TRUE) }
# MessageImprint: SEQUENCE { hashAlgorithm AlgorithmIdentifier, hashedMessage OCTET STRING }

# OID for SHA-256: 2.16.840.1.101.3.4.2.1
_SHA256_OID_DER = bytes([
    0x30, 0x0D,  # SEQUENCE (13 bytes)
    0x06, 0x09,  # OID (9 bytes)
    0x60, 0x86, 0x48, 0x01, 0x65, 0x03, 0x04, 0x02, 0x01,
    0x05, 0x00,  # NULL parameters
])


def _der_length(length: int) -> bytes:
    """Encode ASN.1 DER length bytes."""
    if length < 0x80:
        return bytes([length])
    if length < 0x100:
        return bytes([0x81, length])
    if length < 0x10000:
        return bytes([0x82, (length >> 8) & 0xFF, length & 0xFF])
    raise ValueError(f"DER length too large: {length}")


def _der_sequence(content: bytes) -> bytes:
    """Wrap content in an ASN.1 SEQUENCE tag."""
    return b"\x30" + _der_length(len(content)) + content


def _der_integer(value: int) -> bytes:
    """Encode a non-negative integer as ASN.1 DER INTEGER."""
    if value == 0:
        return b"\x02\x01\x00"
    raw = value.to_bytes((value.bit_length() + 8) // 8, byteorder="big", signed=False)
    # Ensure leading 0 if high bit set
    if raw[0] & 0x80:
        raw = b"\x00" + raw
    return b"\x02" + _der_length(len(raw)) + raw


def _der_octet_string(data: bytes) -> bytes:
    """Encode bytes as ASN.1 OCTET STRING."""
    return b"\x04" + _der_length(len(data)) + data


def _der_boolean_true() -> bytes:
    """ASN.1 DER BOOLEAN TRUE."""
    return b"\x01\x01\xff"


def build_timestamp_request(digest: bytes, *, nonce: Optional[int] = None) -> bytes:
    """Build a minimal RFC 3161 TimeStampReq DER for SHA-256 digest.

    Args:
        digest: 32-byte SHA-256 hash to timestamp.
        nonce: Optional nonce for replay protection.  Generated if None.

    Returns:
        DER-encoded TimeStampReq bytes.
    """
    if len(digest) != 32:
        raise ValueError(f"Expected 32-byte SHA-256 digest, got {len(digest)}")

    if nonce is None:
        nonce = int.from_bytes(os.urandom(8), byteorder="big")

    # MessageImprint = SEQUENCE { algorithm, hashedMessage }
    message_imprint = _der_sequence(_SHA256_OID_DER + _der_octet_string(digest))

    # TimeStampReq = SEQUENCE { version, messageImprint, nonce, certReq }
    version = _der_integer(1)
    nonce_der = _der_integer(nonce)
    cert_req = _der_boolean_true()

    return _der_sequence(version + message_imprint + nonce_der + cert_req)


def parse_tsa_response(response_der: bytes) -> Dict[str, Any]:
    """Parse a minimal subset of RFC 3161 TimeStampResp for receipt storage.

    We intentionally keep this lightweight — the goal is to store the raw
    receipt for future full ASN.1 verification by auditors using OpenSSL or
    a dedicated TSA verification tool.

    Returns:
        Dict with ``status``, ``receipt_b64``, ``receipt_hash``, and basic
        extracted metadata when possible.
    """
    result: Dict[str, Any] = {
        "raw_receipt_b64": base64.b64encode(response_der).decode("ascii"),
        "receipt_hash": hashlib.sha256(response_der).hexdigest(),
        "receipt_size_bytes": len(response_der),
    }

    # Minimal DER parsing to extract status
    try:
        if len(response_der) < 5:
            result["status_code"] = "parse_error"
            result["status_text"] = "response too short"
            return result

        # TimeStampResp ::= SEQUENCE { status PKIStatusInfo, timeStampToken ... }
        # PKIStatusInfo ::= SEQUENCE { status PKIStatus, ... }
        # PKIStatus ::= INTEGER
        # 0 = granted, 1 = grantedWithMods, 2 = rejection, ...
        idx = 0
        if response_der[idx] != 0x30:  # outer SEQUENCE
            result["status_code"] = "parse_error"
            result["status_text"] = "not a SEQUENCE"
            return result

        idx += 1
        idx, _ = _parse_der_length(response_der, idx)

        # PKIStatusInfo SEQUENCE
        if response_der[idx] != 0x30:
            result["status_code"] = "parse_error"
            result["status_text"] = "missing PKIStatusInfo"
            return result

        idx += 1
        idx, _ = _parse_der_length(response_der, idx)

        # PKIStatus INTEGER
        if response_der[idx] != 0x02:
            result["status_code"] = "parse_error"
            result["status_text"] = "missing PKIStatus INTEGER"
            return result

        idx += 1
        int_len = response_der[idx]
        idx += 1
        status_val = int.from_bytes(response_der[idx:idx + int_len], byteorder="big")
        status_names = {0: "granted", 1: "granted_with_mods", 2: "rejection",
                        3: "waiting", 4: "revocation_warning", 5: "revocation_notification"}
        result["status_code"] = status_val
        result["status_text"] = status_names.get(status_val, f"unknown({status_val})")

    except (IndexError, ValueError, struct.error) as exc:
        result["status_code"] = "parse_error"
        result["status_text"] = f"DER parse failed: {exc}"

    return result


def _parse_der_length(data: bytes, idx: int) -> tuple[int, int]:
    """Parse DER length and return (new_idx, length)."""
    byte = data[idx]
    if byte < 0x80:
        return idx + 1, byte
    num_bytes = byte & 0x7F
    length = int.from_bytes(data[idx + 1:idx + 1 + num_bytes], byteorder="big")
    return idx + 1 + num_bytes, length


class TsaAnchorBackend:
    """RFC 3161 Time-Stamp Authority anchor backend.

    Sends the TrustLog chain head digest to a TSA endpoint and stores the
    resulting timestamp receipt in the witness entry for third-party
    verification.
    """

    backend_name = "tsa"

    def __init__(
        self,
        *,
        tsa_url: str,
        timeout_seconds: float = _DEFAULT_TSA_TIMEOUT_SECONDS,
        ca_bundle: Optional[str] = None,
        auth_header: Optional[str] = None,
    ) -> None:
        if not tsa_url:
            raise ValueError("VERITAS_TRUSTLOG_TSA_URL is required for TSA backend")
        self._tsa_url = tsa_url
        self._timeout = timeout_seconds
        self._ca_bundle = ca_bundle
        self._auth_header = auth_header

    def anchor(self, *, entry_hash: str, anchored_at: str) -> AnchorReceipt:
        """Send chain hash to TSA and return structured receipt."""
        digest = bytes.fromhex(entry_hash)
        nonce = int.from_bytes(os.urandom(8), byteorder="big")
        tsq = build_timestamp_request(digest, nonce=nonce)

        headers: Dict[str, str] = {
            "Content-Type": _TSA_CONTENT_TYPE,
            "Accept": _TSA_ACCEPT,
        }
        if self._auth_header:
            headers["Authorization"] = self._auth_header

        verify: Any = self._ca_bundle if self._ca_bundle else True

        receipt_id = _uuid7()
        try:
            resp = httpx.post(
                self._tsa_url,
                content=tsq,
                headers=headers,
                timeout=self._timeout,
                verify=verify,
            )
            resp.raise_for_status()
        except httpx.TimeoutException as exc:
            _logger.warning("TSA request timed out: %s", exc)
            return AnchorReceipt(
                backend=self.backend_name,
                status="failed",
                anchored_hash=entry_hash,
                anchored_at=anchored_at,
                receipt_id=receipt_id,
                receipt_location=self._tsa_url,
                receipt_payload_hash=None,
                external_timestamp=None,
                details={
                    "configured": True,
                    "ok": False,
                    "error": f"TimeoutException: {exc}",
                    "tsa_url": self._tsa_url,
                },
            )
        except httpx.HTTPStatusError as exc:
            _logger.warning("TSA returned HTTP %d: %s", exc.response.status_code, exc)
            return AnchorReceipt(
                backend=self.backend_name,
                status="failed",
                anchored_hash=entry_hash,
                anchored_at=anchored_at,
                receipt_id=receipt_id,
                receipt_location=self._tsa_url,
                receipt_payload_hash=None,
                external_timestamp=None,
                details={
                    "configured": True,
                    "ok": False,
                    "error": f"HTTP {exc.response.status_code}",
                    "tsa_url": self._tsa_url,
                },
            )
        except httpx.HTTPError as exc:
            _logger.warning("TSA request failed: %s: %s", exc.__class__.__name__, exc)
            return AnchorReceipt(
                backend=self.backend_name,
                status="failed",
                anchored_hash=entry_hash,
                anchored_at=anchored_at,
                receipt_id=receipt_id,
                receipt_location=self._tsa_url,
                receipt_payload_hash=None,
                external_timestamp=None,
                details={
                    "configured": True,
                    "ok": False,
                    "error": f"{exc.__class__.__name__}: {exc}",
                    "tsa_url": self._tsa_url,
                },
            )

        tsa_result = parse_tsa_response(resp.content)
        receipt_payload_hash = tsa_result.get("receipt_hash")
        external_timestamp = anchored_at  # TSA reply itself is the proof

        status_code = tsa_result.get("status_code")
        if status_code in (0, 1):
            status = "anchored"
            ok = True
        else:
            status = "failed"
            ok = False
            _logger.warning(
                "TSA response status: %s (%s)",
                tsa_result.get("status_text"),
                status_code,
            )

        return AnchorReceipt(
            backend=self.backend_name,
            status=status,
            anchored_hash=entry_hash,
            anchored_at=anchored_at,
            receipt_id=receipt_id,
            receipt_location=self._tsa_url,
            receipt_payload_hash=receipt_payload_hash,
            external_timestamp=external_timestamp,
            details={
                "configured": True,
                "ok": ok,
                "tsa_url": self._tsa_url,
                "status_code": tsa_result.get("status_code"),
                "status_text": tsa_result.get("status_text"),
                "receipt_size_bytes": tsa_result.get("receipt_size_bytes"),
                "raw_receipt_b64": tsa_result.get("raw_receipt_b64"),
                "nonce": nonce,
            },
        )


def build_tsa_anchor_backend() -> TsaAnchorBackend:
    """Factory: build TSA backend from environment variables."""
    tsa_url = os.getenv("VERITAS_TRUSTLOG_TSA_URL", "").strip()
    timeout_str = os.getenv("VERITAS_TRUSTLOG_TSA_TIMEOUT_SECONDS", "").strip()
    ca_bundle = os.getenv("VERITAS_TRUSTLOG_TSA_CA_BUNDLE", "").strip() or None
    auth_header = os.getenv("VERITAS_TRUSTLOG_TSA_AUTH_HEADER", "").strip() or None

    timeout = _DEFAULT_TSA_TIMEOUT_SECONDS
    if timeout_str:
        try:
            timeout = float(timeout_str)
        except ValueError:
            _logger.warning("Invalid VERITAS_TRUSTLOG_TSA_TIMEOUT_SECONDS: %s", timeout_str)

    return TsaAnchorBackend(
        tsa_url=tsa_url,
        timeout_seconds=timeout,
        ca_bundle=ca_bundle,
        auth_header=auth_header,
    )


def _uuid7() -> str:
    """Generate a UUIDv7-compatible identifier."""
    unix_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    rand_a = uuid.uuid4().int & ((1 << 12) - 1)
    rand_b = uuid.uuid4().int & ((1 << 62) - 1)
    value = (unix_ms & ((1 << 48) - 1)) << 80
    value |= 0x7 << 76
    value |= rand_a << 64
    value |= 0x2 << 62
    value |= rand_b
    return str(uuid.UUID(int=value))
