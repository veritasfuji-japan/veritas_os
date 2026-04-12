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
import importlib
import logging
import os
import secrets
import struct
from typing import Optional, Protocol, Tuple

logger = logging.getLogger(__name__)

_AES_BLOCK = 16
_IV_SIZE = 16
_HMAC_SIZE = 32
_AESGCM_NONCE_SIZE = 12
# Derive two independent 32-byte subkeys from the 32-byte master key
# via HMAC-SHA256 so that both encryption and authentication use 256-bit keys.
_HMAC_CTR_ENC_INFO = b"veritas-hmac-ctr-enc"
_HMAC_CTR_MAC_INFO = b"veritas-hmac-ctr-mac"


def _derive_hmac_ctr_keys(master: bytes) -> tuple[bytes, bytes]:
    """Derive 256-bit enc_key and hmac_key from a 32-byte master key."""
    enc_key = hmac.new(master, _HMAC_CTR_ENC_INFO, hashlib.sha256).digest()
    hmac_key = hmac.new(master, _HMAC_CTR_MAC_INFO, hashlib.sha256).digest()
    return enc_key, hmac_key
_STREAM_BLOCK = 32  # SHA-256 output size
_LEGACY_DECRYPT_ENV = "VERITAS_ENCRYPTION_LEGACY_DECRYPT"
_ENCRYPTION_PROVIDER_ENV = "VERITAS_ENCRYPTION_KEY_PROVIDER"
_ALLOW_ENV_FALLBACK_ENV = "VERITAS_ENCRYPTION_ALLOW_ENV_FALLBACK"


class EncryptionKeyProvider(Protocol):
    """Provider interface for retrieving the 32-byte at-rest encryption key."""

    provider_name: str

    def load_key(self) -> Optional[bytes]:
        """Return key bytes, or ``None`` when the key is intentionally absent."""


def _is_truthy(raw: str) -> bool:
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class EnvEncryptionKeyProvider:
    """Load encryption key from ``VERITAS_ENCRYPTION_KEY`` for legacy compatibility."""

    provider_name = "env"

    def load_key(self) -> Optional[bytes]:
        raw = os.environ.get("VERITAS_ENCRYPTION_KEY")
        if not raw:
            return None
        try:
            key = base64.b64decode(raw.encode("ascii"), altchars=b"-_", validate=True)
        except (ValueError, TypeError, UnicodeEncodeError) as exc:
            raise EncryptionKeyMissing(
                "VERITAS_ENCRYPTION_KEY is set but contains invalid base64 encoding"
            ) from exc
        if len(key) != 32:
            raise EncryptionKeyMissing(
                "VERITAS_ENCRYPTION_KEY must decode to exactly 32 bytes"
            )
        return key


class AwsKmsEncryptionKeyProvider:
    """Retrieve a data key by decrypting KMS ciphertext (AWS KMS envelope path)."""

    provider_name = "aws_kms"

    def __init__(self, kms_client: Optional[object] = None) -> None:
        self._kms_client = kms_client

    @property
    def kms_client(self) -> object:
        if self._kms_client is None:
            boto3 = importlib.import_module("boto3")
            self._kms_client = boto3.client("kms")
        return self._kms_client

    def load_key(self) -> Optional[bytes]:
        blob_b64 = (os.getenv("VERITAS_ENCRYPTION_AWS_KMS_CIPHERTEXT_B64") or "").strip()
        if not blob_b64:
            return None
        try:
            blob = _decode_urlsafe_b64(blob_b64)
        except ValueError as exc:
            raise EncryptionKeyMissing(
                "VERITAS_ENCRYPTION_AWS_KMS_CIPHERTEXT_B64 must be valid base64"
            ) from exc
        decrypt_kwargs = {"CiphertextBlob": blob}
        kms_key_id = (os.getenv("VERITAS_ENCRYPTION_AWS_KMS_KEY_ID") or "").strip()
        if kms_key_id:
            decrypt_kwargs["KeyId"] = kms_key_id
        response = self.kms_client.decrypt(**decrypt_kwargs)
        key = response.get("Plaintext", b"")
        if not isinstance(key, (bytes, bytearray)) or len(key) != 32:
            raise EncryptionKeyMissing("AWS KMS decrypt did not return a 32-byte key")
        return bytes(key)


class GcpKmsEncryptionKeyProvider:
    """Retrieve a data key by decrypting KMS ciphertext (GCP Cloud KMS path)."""

    provider_name = "gcp_kms"

    def __init__(self, kms_client: Optional[object] = None) -> None:
        self._kms_client = kms_client

    @property
    def kms_client(self) -> object:
        if self._kms_client is None:
            kms_mod = importlib.import_module("google.cloud.kms_v1")
            self._kms_client = kms_mod.KeyManagementServiceClient()
        return self._kms_client

    def load_key(self) -> Optional[bytes]:
        key_name = (os.getenv("VERITAS_ENCRYPTION_GCP_KMS_KEY_NAME") or "").strip()
        blob_b64 = (os.getenv("VERITAS_ENCRYPTION_GCP_KMS_CIPHERTEXT_B64") or "").strip()
        if not key_name or not blob_b64:
            return None
        try:
            blob = _decode_urlsafe_b64(blob_b64)
        except ValueError as exc:
            raise EncryptionKeyMissing(
                "VERITAS_ENCRYPTION_GCP_KMS_CIPHERTEXT_B64 must be valid base64"
            ) from exc
        response = self.kms_client.decrypt(request={"name": key_name, "ciphertext": blob})
        key = getattr(response, "plaintext", b"")
        if not isinstance(key, (bytes, bytearray)) or len(key) != 32:
            raise EncryptionKeyMissing("GCP KMS decrypt did not return a 32-byte key")
        return bytes(key)


class VaultTransitEncryptionKeyProvider:
    """Retrieve encryption key material from Vault KV path during migration."""

    provider_name = "vault"

    def __init__(self, vault_client: Optional[object] = None) -> None:
        self._vault_client = vault_client

    @property
    def vault_client(self) -> object:
        if self._vault_client is None:
            hvac = importlib.import_module("hvac")
            url = os.getenv("VERITAS_ENCRYPTION_VAULT_ADDR")
            token = os.getenv("VERITAS_ENCRYPTION_VAULT_TOKEN")
            self._vault_client = hvac.Client(url=url, token=token)
        return self._vault_client

    def load_key(self) -> Optional[bytes]:
        mount_point = (os.getenv("VERITAS_ENCRYPTION_VAULT_KV_MOUNT") or "secret").strip()
        secret_path = (os.getenv("VERITAS_ENCRYPTION_VAULT_SECRET_PATH") or "").strip()
        secret_field = (os.getenv("VERITAS_ENCRYPTION_VAULT_SECRET_FIELD") or "key_b64").strip()
        if not secret_path:
            return None
        response = self.vault_client.secrets.kv.v2.read_secret_version(
            path=secret_path,
            mount_point=mount_point,
        )
        data = response.get("data", {}).get("data", {})
        raw_value = data.get(secret_field, "")
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise EncryptionKeyMissing(
                "Vault secret missing encryption key value in configured field"
            )
        try:
            key = base64.b64decode(raw_value.encode("ascii"), altchars=b"-_", validate=True)
        except (ValueError, TypeError, UnicodeEncodeError) as exc:
            raise EncryptionKeyMissing("Vault encryption key must be valid base64") from exc
        if len(key) != 32:
            raise EncryptionKeyMissing("Vault encryption key must decode to exactly 32 bytes")
        return key


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


def _build_key_provider(provider: str) -> EncryptionKeyProvider:
    normalized = provider.strip().lower()
    if normalized in {"", "env", "legacy_env"}:
        return EnvEncryptionKeyProvider()
    if normalized in {"aws_kms", "aws-kms"}:
        return AwsKmsEncryptionKeyProvider()
    if normalized in {"gcp_kms", "gcp-kms"}:
        return GcpKmsEncryptionKeyProvider()
    if normalized in {"vault", "vault_kv"}:
        return VaultTransitEncryptionKeyProvider()
    raise EncryptionKeyMissing(
        f"Unsupported encryption key provider: {provider!r}. "
        "Expected one of env/aws_kms/gcp_kms/vault."
    )


def _get_key_bytes() -> Optional[bytes]:
    """Return the 32-byte master key from configured key provider.

    Migration path:
        ``VERITAS_ENCRYPTION_KEY_PROVIDER`` defaults to ``env`` for backward
        compatibility. To migrate from direct env-key management to KMS/Vault,
        set the provider to ``aws_kms``, ``gcp_kms``, or ``vault``.
        During migration you can temporarily allow fallback to env key with:
        ``VERITAS_ENCRYPTION_ALLOW_ENV_FALLBACK=1``.
    """
    provider_name = os.getenv(_ENCRYPTION_PROVIDER_ENV, "env")
    provider = _build_key_provider(provider_name)
    key = provider.load_key()
    if key is not None:
        return key

    allow_fallback = _is_truthy(os.getenv(_ALLOW_ENV_FALLBACK_ENV, ""))
    if provider.provider_name != "env" and allow_fallback:
        logger.warning(
            "%s enabled: falling back to legacy VERITAS_ENCRYPTION_KEY; "
            "disable fallback after KMS/Vault cutover.",
            _ALLOW_ENV_FALLBACK_ENV,
        )
        return EnvEncryptionKeyProvider().load_key()
    return None


def is_encryption_enabled() -> bool:
    """Return True if at-rest encryption is configured."""
    try:
        return _get_key_bytes() is not None
    except EncryptionKeyMissing:
        return False


def _decode_urlsafe_b64(payload: str) -> bytes:
    """Decode URL-safe base64 with strict validation."""
    if not payload:
        raise ValueError("empty ciphertext payload")
    try:
        return base64.b64decode(
            payload.encode("ascii"),
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, TypeError, UnicodeEncodeError) as exc:
        raise ValueError("invalid base64 payload") from exc


def _legacy_decrypt_enabled() -> bool:
    """Return whether legacy ``ENC:<payload>`` token decryption is allowed."""
    raw = (os.environ.get(_LEGACY_DECRYPT_ENV) or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _split_encrypted_token(token: str) -> Tuple[str, str]:
    """Parse ``ENC:<algorithm>:<base64>`` with explicit fail-closed checks.

    Legacy ``ENC:<base64>`` tokens are rejected by default and can be enabled
    only via ``VERITAS_ENCRYPTION_LEGACY_DECRYPT=1`` during migration.
    """
    if not token.startswith("ENC:"):
        raise ValueError("missing ENC prefix")
    after_prefix = token[4:]
    if not after_prefix:
        raise ValueError("missing encrypted envelope")

    first_sep = after_prefix.find(":")
    if first_sep == -1:
        if _legacy_decrypt_enabled():
            logger.warning(
                "Legacy ENC payload accepted due to %s=1; migrate to ENC:<algorithm>:<payload>",
                _LEGACY_DECRYPT_ENV,
            )
            algorithm = "aesgcm" if _USE_REAL_AES else "hmac-ctr"
            return algorithm, after_prefix
        raise ValueError("legacy encrypted envelope not accepted")

    algorithm = after_prefix[:first_sep]
    payload = after_prefix[first_sep + 1:]
    if algorithm not in {"aesgcm", "hmac-ctr"}:
        raise ValueError("unsupported encryption algorithm marker")
    if not payload:
        raise ValueError("missing encrypted payload")
    return algorithm, payload


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
        return "ENC:aesgcm:" + _encrypt_aesgcm_raw(plaintext, key)
    return "ENC:hmac-ctr:" + _encrypt_hmac_ctr_raw(plaintext, key)


def decrypt(ciphertext: str) -> str:
    """Decrypt an ``ENC:``-prefixed ciphertext string.

    Algorithm dispatch uses the tag between ``ENC:`` and the payload
    (e.g. ``ENC:aesgcm:<b64>``). Legacy tokens without an algorithm tag are
    rejected by default and can be enabled only for migrations via
    ``VERITAS_ENCRYPTION_LEGACY_DECRYPT=1``.

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
        algorithm, payload = _split_encrypted_token(ciphertext)
        if algorithm == "aesgcm":
            return _decrypt_aesgcm_raw(payload, key)
        if algorithm == "hmac-ctr":
            return _decrypt_hmac_ctr_raw(payload, key)
        raise ValueError("unsupported encryption algorithm marker")
    except (ValueError, TypeError, KeyError) as exc:
        raise DecryptionError(f"Decryption failed: {exc}") from exc


# ---------------------------------------------------------------------------
# HMAC-CTR backend (pure Python, no external deps)
# ---------------------------------------------------------------------------


def _encrypt_hmac_ctr_raw(plaintext: str, key: bytes) -> str:
    """Return base64-encoded HMAC-CTR ciphertext (no ENC: prefix)."""
    enc_key, hmac_key = _derive_hmac_ctr_keys(key)
    iv = secrets.token_bytes(_IV_SIZE)
    data = plaintext.encode("utf-8")

    keystream = _hmac_ctr_keystream(enc_key, iv, len(data))
    ciphertext = _xor_bytes(data, keystream)

    payload = iv + ciphertext
    tag = hmac.new(hmac_key, payload, hashlib.sha256).digest()

    return base64.urlsafe_b64encode(tag + payload).decode("ascii")


def _decrypt_hmac_ctr_raw(b64_payload: str, key: bytes) -> str:
    """Decrypt base64-encoded HMAC-CTR ciphertext (no ENC: prefix)."""
    enc_key, hmac_key = _derive_hmac_ctr_keys(key)

    raw = _decode_urlsafe_b64(b64_payload)
    # HMAC tag + IV is the minimum valid ciphertext (empty plaintext produces
    # zero ciphertext bytes, but the HMAC and IV are always present).
    if len(raw) < _HMAC_SIZE + _IV_SIZE:
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


def _encrypt_aesgcm_raw(plaintext: str, key: bytes) -> str:
    """Return base64-encoded AES-GCM ciphertext (no ENC: prefix)."""
    nonce = secrets.token_bytes(12)
    aes = AESGCM(key)
    ct = aes.encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.urlsafe_b64encode(nonce + ct).decode("ascii")


def _decrypt_aesgcm_raw(b64_payload: str, key: bytes) -> str:
    """Decrypt base64-encoded AES-GCM ciphertext (no ENC: prefix)."""
    raw = _decode_urlsafe_b64(b64_payload)
    if len(raw) < _AESGCM_NONCE_SIZE + 1:
        raise ValueError("ciphertext too short for AES-GCM")
    nonce = raw[:_AESGCM_NONCE_SIZE]
    ct = raw[_AESGCM_NONCE_SIZE:]
    aes = AESGCM(key)
    try:
        return aes.decrypt(nonce, ct, None).decode("utf-8")
    except Exception as exc:
        raise ValueError("AES-GCM decryption failed — data may be tampered") from exc


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


def get_encryption_status() -> dict:
    """Return current encryption configuration status."""
    enabled = is_encryption_enabled()
    backend = "AES-256-GCM" if _USE_REAL_AES else "HMAC-SHA256 CTR-mode"
    provider = os.getenv(_ENCRYPTION_PROVIDER_ENV, "env").strip().lower() or "env"
    return {
        "encryption_enabled": enabled,
        "algorithm": backend if enabled else "none",
        "key_provider": provider,
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
