"""At-rest encryption for TrustLog — **secure-by-default**.

P3-2: Art. 12 — Encryption at rest standardisation (GAP-12).

Encryption is **mandatory** by default.  When no key is configured the
module raises ``EncryptionKeyMissing`` on write so that plaintext can
never be persisted by accident.

Key management:
    * ``VERITAS_ENCRYPTION_KEY``  — Base64-encoded 32-byte key.
    * ``generate_key()``         — Helper to create a new key.

Cipher:
    HMAC-SHA256 CTR-mode stream cipher with HMAC-SHA256 authentication.
    This is a pure-Python implementation that does not require the
    ``cryptography`` package.  For production deployments, install
    ``cryptography`` and the module will prefer real AES-256-GCM.

    * IV: 16 random bytes (unique per message)
    * Keystream: HMAC-SHA256(enc_key, IV || counter) per 32-byte block
    * Authentication: HMAC-SHA256(hmac_key, IV || ciphertext)

Security notes:
    * The key **must** be stored securely (vault / KMS / env-injected secret).
    * Do **not** commit the key to source control.
    * Without the key, ciphertext is unrecoverable.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import secrets
import struct
from typing import Optional

logger = logging.getLogger(__name__)

_AES_BLOCK = 16
_IV_SIZE = 16
_HMAC_SIZE = 32
_KEY_HALF = 16
_STREAM_BLOCK = 32  # SHA-256 output size


class EncryptionKeyMissing(RuntimeError):
    """Raised when encryption is required but no key is configured."""


class DecryptionError(RuntimeError):
    """Raised when decryption fails (fail-closed principle)."""


# ---------------------------------------------------------------------------
# Optional real AES backend
# ---------------------------------------------------------------------------

_USE_REAL_AES = False
AESGCM = None  # type: ignore[assignment]
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # type: ignore[import-untyped]

    _USE_REAL_AES = True
except BaseException:  # noqa: BLE001
    # Catches ImportError, broken native bindings (pyo3 panics), etc.
    _USE_REAL_AES = False

# ---------------------------------------------------------------------------
# Key helpers
# ---------------------------------------------------------------------------


def generate_key() -> str:
    """Generate a new 32-byte encryption key, returned as URL-safe base64."""
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")


def _get_key_bytes() -> Optional[bytes]:
    """Return the 32-byte master key from the environment, or None."""
    raw = os.environ.get("VERITAS_ENCRYPTION_KEY")
    if not raw:
        return None
    try:
        key = base64.b64decode(raw.encode("ascii"), altchars=b"-_", validate=True)
        if len(key) != 32:
            logger.warning(
                "VERITAS_ENCRYPTION_KEY must decode to 32 bytes; got %d — encryption disabled",
                len(key),
            )
            return None
        return key
    except (ValueError, TypeError, UnicodeEncodeError):
        logger.warning("VERITAS_ENCRYPTION_KEY is not valid base64 — encryption disabled")
        return None


def is_encryption_enabled() -> bool:
    """Return True if at-rest encryption is configured."""
    return _get_key_bytes() is not None


# ---------------------------------------------------------------------------
# Pure-Python HMAC-CTR stream cipher
# ---------------------------------------------------------------------------


def _hmac_ctr_keystream(enc_key: bytes, iv: bytes, length: int) -> bytes:
    """Generate *length* bytes of keystream using HMAC-SHA256 in CTR mode."""
    stream = b""
    counter = 0
    while len(stream) < length:
        block_input = iv + struct.pack(">Q", counter)
        stream += hmac.new(enc_key, block_input, hashlib.sha256).digest()
        counter += 1
    return stream[:length]


def _xor_bytes(a: bytes, b: bytes) -> bytes:
    """XOR two byte strings of equal length."""
    return bytes(x ^ y for x, y in zip(a, b, strict=True))


# ---------------------------------------------------------------------------
# Encrypt / Decrypt
# ---------------------------------------------------------------------------


def encrypt(plaintext: str) -> str:
    """Encrypt a plaintext string.

    Raises :class:`EncryptionKeyMissing` when no key is configured
    to enforce secure-by-default (fail-closed).

    Returns ``ENC:`` prefixed base64 ciphertext when a key is available.
    """
    if not isinstance(plaintext, str):
        raise TypeError(f"encrypt() requires a str, got {type(plaintext).__name__}")

    key = _get_key_bytes()
    if key is None:
        raise EncryptionKeyMissing(
            "VERITAS_ENCRYPTION_KEY is not set. "
            "TrustLog requires encryption. Set the environment variable or "
            "call generate_key() to create one."
        )

    if _USE_REAL_AES:
        return _encrypt_aesgcm(plaintext, key)
    return _encrypt_hmac_ctr(plaintext, key)


def decrypt(ciphertext: str) -> str:
    """Decrypt an ``ENC:``-prefixed ciphertext string.

    Returns the original string unchanged if it does not start with ``ENC:``.
    Raises :class:`EncryptionKeyMissing` when the key is required but absent.
    """
    if not ciphertext.startswith("ENC:"):
        return ciphertext

    key = _get_key_bytes()
    if key is None:
        raise EncryptionKeyMissing(
            "Cannot decrypt: VERITAS_ENCRYPTION_KEY not set"
        )

    try:
        if _USE_REAL_AES:
            return _decrypt_aesgcm(ciphertext, key)
        return _decrypt_hmac_ctr(ciphertext, key)
    except (ValueError, TypeError, KeyError) as exc:
        raise DecryptionError(
            f"Decryption failed for malformed ciphertext: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# HMAC-CTR backend (pure Python, no external deps)
# ---------------------------------------------------------------------------


def _encrypt_hmac_ctr(plaintext: str, key: bytes) -> str:
    enc_key = key[:_KEY_HALF]
    hmac_key = key[_KEY_HALF:]
    iv = secrets.token_bytes(_IV_SIZE)
    data = plaintext.encode("utf-8")

    keystream = _hmac_ctr_keystream(enc_key, iv, len(data))
    ciphertext = _xor_bytes(data, keystream)

    payload = iv + ciphertext
    tag = hmac.new(hmac_key, payload, hashlib.sha256).digest()

    return "ENC:" + base64.urlsafe_b64encode(tag + payload).decode("ascii")


def _decrypt_hmac_ctr(token: str, key: bytes) -> str:
    hmac_key = key[_KEY_HALF:]
    enc_key = key[:_KEY_HALF]

    raw = base64.urlsafe_b64decode(token[4:])
    if len(raw) < _HMAC_SIZE + _IV_SIZE + 1:
        raise ValueError("ciphertext too short")

    tag = raw[:_HMAC_SIZE]
    payload = raw[_HMAC_SIZE:]

    expected_tag = hmac.new(hmac_key, payload, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected_tag):
        raise ValueError("HMAC verification failed — data may be tampered")

    iv = payload[:_IV_SIZE]
    ciphertext = payload[_IV_SIZE:]

    keystream = _hmac_ctr_keystream(enc_key, iv, len(ciphertext))
    plaintext_bytes = _xor_bytes(ciphertext, keystream)

    return plaintext_bytes.decode("utf-8")


# ---------------------------------------------------------------------------
# AES-GCM backend (when cryptography package is installed)
# ---------------------------------------------------------------------------


def _encrypt_aesgcm(plaintext: str, key: bytes) -> str:
    nonce = secrets.token_bytes(12)
    aes = AESGCM(key)
    ct = aes.encrypt(nonce, plaintext.encode("utf-8"), None)
    return "ENC:" + base64.urlsafe_b64encode(nonce + ct).decode("ascii")


def _decrypt_aesgcm(token: str, key: bytes) -> str:
    raw = base64.urlsafe_b64decode(token[4:])
    if len(raw) < 13:
        raise ValueError("ciphertext too short for AES-GCM")
    nonce = raw[:12]
    ct = raw[12:]
    aes = AESGCM(key)
    try:
        return aes.decrypt(nonce, ct, None).decode("utf-8")
    except Exception as exc:
        # cryptography raises InvalidTag on tampered data
        raise ValueError(f"AES-GCM decryption failed — data may be tampered: {exc}") from exc


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


def get_encryption_status() -> dict:
    """Return current encryption configuration status."""
    enabled = is_encryption_enabled()
    backend = "AES-256-GCM" if _USE_REAL_AES else "HMAC-SHA256 CTR-mode"
    return {
        "encryption_enabled": enabled,
        "algorithm": backend if enabled else "none",
        "key_configured": enabled,
        "secure_by_default": True,
        "eu_ai_act_article": "Art. 12",
        "note": (
            f"At-rest encryption is active ({backend})."
            if enabled
            else (
                "VERITAS_ENCRYPTION_KEY is NOT configured. "
                "TrustLog writes will fail until a key is set."
            )
        ),
    }
