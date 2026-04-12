"""At-rest encryption for TrustLog — **secure-by-default**.

P3-2: Art. 12 — Encryption at rest standardisation (GAP-12).

Encryption is **mandatory** by default.  When no key is configured the
module raises ``EncryptionKeyMissing`` on write so that plaintext can
never be persisted by accident.

Key management:
    * ``VERITAS_ENCRYPTION_KEY``  — Base64-encoded 32-byte key.
    * ``generate_key()``         — Helper to create a new key.
    * ``KeyProvider`` protocol   — Pluggable key retrieval backends
      (env-var, AWS KMS, GCP KMS, HashiCorp Vault).

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
from typing import Optional, Protocol, Tuple, runtime_checkable

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
    """Return the 32-byte master key from the environment, or None.

    Returns ``None`` when the environment variable is not set.
    Raises :class:`EncryptionKeyMissing` when the variable **is** set but
    cannot be decoded to a valid 32-byte key, so that a misconfigured key
    is never silently treated as "no key".
    """
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


def is_encryption_enabled() -> bool:
    """Return True if at-rest encryption is configured."""
    try:
        return _get_key_bytes() is not None
    except EncryptionKeyMissing:
        return False


# ---------------------------------------------------------------------------
# Pluggable KeyProvider interface (KMS migration path)
# ---------------------------------------------------------------------------


@runtime_checkable
class KeyProvider(Protocol):
    """Protocol for pluggable encryption key retrieval backends.

    Implementations provide a migration path from environment-variable
    key management to external KMS/Vault systems.
    """

    provider_name: str

    def get_key_bytes(self) -> Optional[bytes]:
        """Return the 32-byte master encryption key, or None if unavailable.

        Raises:
            EncryptionKeyMissing: If the provider is configured but the key
                cannot be retrieved or is invalid.
        """
        ...

    def is_available(self) -> bool:
        """Return True if this provider is configured and reachable."""
        ...


class EnvKeyProvider:
    """Key provider backed by the ``VERITAS_ENCRYPTION_KEY`` environment variable.

    This is the default provider and preserves full backward compatibility
    with the existing configuration model.
    """

    provider_name = "env"

    def get_key_bytes(self) -> Optional[bytes]:
        """Retrieve key from ``VERITAS_ENCRYPTION_KEY`` environment variable."""
        return _get_key_bytes()

    def is_available(self) -> bool:
        """Return True if the environment variable is set."""
        return bool(os.environ.get("VERITAS_ENCRYPTION_KEY"))


class AwsKmsKeyProvider:
    """Key provider that retrieves data-encryption keys from AWS KMS.

    Uses AWS KMS ``Decrypt`` API to unwrap a data key stored as
    base64 ciphertext in ``VERITAS_KMS_ENCRYPTED_KEY``.

    Environment variables:
        ``VERITAS_KMS_KEY_ID``: AWS KMS key ARN or alias for decryption.
        ``VERITAS_KMS_ENCRYPTED_KEY``: Base64-encoded ciphertext blob of
            the 32-byte data encryption key.

    Security:
        IAM permissions must be scoped to ``kms:Decrypt`` on the specific
        key. Requests are routed via the default boto3 credential chain.
    """

    provider_name = "aws_kms"

    def __init__(
        self,
        kms_key_id: Optional[str] = None,
        encrypted_key_b64: Optional[str] = None,
        kms_client: Optional[object] = None,
    ) -> None:
        self.kms_key_id = (
            kms_key_id or os.getenv("VERITAS_KMS_KEY_ID", "")
        ).strip()
        self.encrypted_key_b64 = (
            encrypted_key_b64 or os.getenv("VERITAS_KMS_ENCRYPTED_KEY", "")
        ).strip()
        self._kms_client = kms_client

    @property
    def kms_client(self) -> object:
        """Lazily construct boto3 KMS client."""
        if self._kms_client is None:
            import importlib

            boto3 = importlib.import_module("boto3")
            self._kms_client = boto3.client("kms")
        return self._kms_client

    def get_key_bytes(self) -> Optional[bytes]:
        """Decrypt the data encryption key via AWS KMS."""
        if not self.encrypted_key_b64 or not self.kms_key_id:
            return None
        try:
            ciphertext = base64.b64decode(self.encrypted_key_b64)
            response = self.kms_client.decrypt(
                CiphertextBlob=ciphertext,
                KeyId=self.kms_key_id,
            )
            key = response["Plaintext"]
            if len(key) != 32:
                raise EncryptionKeyMissing(
                    "AWS KMS decrypted key must be exactly 32 bytes"
                )
            return key
        except EncryptionKeyMissing:
            raise
        except Exception as exc:
            raise EncryptionKeyMissing(
                f"AWS KMS key retrieval failed: {exc}"
            ) from exc

    def is_available(self) -> bool:
        """Return True if KMS key id and encrypted key are configured."""
        return bool(self.kms_key_id and self.encrypted_key_b64)


class GcpKmsKeyProvider:
    """Key provider that retrieves data-encryption keys from Google Cloud KMS.

    Uses GCP KMS ``Decrypt`` API to unwrap a data key stored as
    base64 ciphertext in ``VERITAS_GCP_KMS_ENCRYPTED_KEY``.

    Environment variables:
        ``VERITAS_GCP_KMS_RESOURCE_NAME``: Full resource name of the KMS
            crypto key version (e.g.
            ``projects/p/locations/l/keyRings/r/cryptoKeys/k/cryptoKeyVersions/v``).
        ``VERITAS_GCP_KMS_ENCRYPTED_KEY``: Base64-encoded ciphertext of
            the 32-byte data encryption key.

    Security:
        Service account must have ``cloudkms.cryptoKeyVersions.useToDecrypt``
        permission on the specified key.
    """

    provider_name = "gcp_kms"

    def __init__(
        self,
        resource_name: Optional[str] = None,
        encrypted_key_b64: Optional[str] = None,
        kms_client: Optional[object] = None,
    ) -> None:
        self.resource_name = (
            resource_name or os.getenv("VERITAS_GCP_KMS_RESOURCE_NAME", "")
        ).strip()
        self.encrypted_key_b64 = (
            encrypted_key_b64 or os.getenv("VERITAS_GCP_KMS_ENCRYPTED_KEY", "")
        ).strip()
        self._kms_client = kms_client

    @property
    def kms_client(self) -> object:
        """Lazily construct GCP KMS client."""
        if self._kms_client is None:
            import importlib

            kms_mod = importlib.import_module(
                "google.cloud.kms_v1"
            )
            self._kms_client = kms_mod.KeyManagementServiceClient()
        return self._kms_client

    def get_key_bytes(self) -> Optional[bytes]:
        """Decrypt the data encryption key via GCP KMS."""
        if not self.encrypted_key_b64 or not self.resource_name:
            return None
        try:
            ciphertext = base64.b64decode(self.encrypted_key_b64)
            response = self.kms_client.decrypt(
                request={"name": self.resource_name, "ciphertext": ciphertext}
            )
            key = response.plaintext
            if len(key) != 32:
                raise EncryptionKeyMissing(
                    "GCP KMS decrypted key must be exactly 32 bytes"
                )
            return key
        except EncryptionKeyMissing:
            raise
        except Exception as exc:
            raise EncryptionKeyMissing(
                f"GCP KMS key retrieval failed: {exc}"
            ) from exc

    def is_available(self) -> bool:
        """Return True if GCP KMS resource name and encrypted key are configured."""
        return bool(self.resource_name and self.encrypted_key_b64)


class VaultKeyProvider:
    """Key provider that retrieves encryption keys from HashiCorp Vault.

    Reads a 32-byte key stored as base64 at the configured Vault path
    using the KV v2 secrets engine.

    Environment variables:
        ``VERITAS_VAULT_ADDR``: Vault server address (e.g. ``https://vault:8200``).
        ``VERITAS_VAULT_TOKEN``: Authentication token.
        ``VERITAS_VAULT_SECRET_PATH``: KV v2 secret path
            (e.g. ``secret/data/veritas/encryption``).
        ``VERITAS_VAULT_SECRET_KEY``: Key name within the secret
            (default ``encryption_key``).

    Security:
        Vault token should be scoped to read-only on the specific path.
        Use AppRole, Kubernetes auth, or similar machine identity for
        production instead of static tokens.
    """

    provider_name = "vault"

    def __init__(
        self,
        vault_addr: Optional[str] = None,
        vault_token: Optional[str] = None,
        secret_path: Optional[str] = None,
        secret_key: Optional[str] = None,
        client: Optional[object] = None,
    ) -> None:
        self.vault_addr = (
            vault_addr or os.getenv("VERITAS_VAULT_ADDR", "")
        ).strip()
        self.vault_token = (
            vault_token or os.getenv("VERITAS_VAULT_TOKEN", "")
        ).strip()
        self.secret_path = (
            secret_path or os.getenv("VERITAS_VAULT_SECRET_PATH", "")
        ).strip()
        self.secret_key = (
            secret_key or os.getenv("VERITAS_VAULT_SECRET_KEY", "encryption_key")
        ).strip()
        self._client = client

    @property
    def _vault_client(self) -> object:
        """Lazily construct Vault HVAC client."""
        if self._client is None:
            import importlib

            hvac = importlib.import_module("hvac")
            self._client = hvac.Client(url=self.vault_addr, token=self.vault_token)
        return self._client

    def get_key_bytes(self) -> Optional[bytes]:
        """Retrieve the encryption key from HashiCorp Vault."""
        if not self.vault_addr or not self.secret_path:
            return None
        try:
            response = self._vault_client.secrets.kv.v2.read_secret_version(
                path=self.secret_path,
            )
            data = response["data"]["data"]
            raw_b64 = data.get(self.secret_key, "")
            if not raw_b64:
                return None
            key = base64.b64decode(raw_b64)
            if len(key) != 32:
                raise EncryptionKeyMissing(
                    "Vault key must decode to exactly 32 bytes"
                )
            return key
        except EncryptionKeyMissing:
            raise
        except Exception as exc:
            raise EncryptionKeyMissing(
                f"Vault key retrieval failed: {exc}"
            ) from exc

    def is_available(self) -> bool:
        """Return True if Vault address and secret path are configured."""
        return bool(self.vault_addr and self.secret_path)


# ---------------------------------------------------------------------------
# Key provider registry
# ---------------------------------------------------------------------------

_active_key_provider: Optional[KeyProvider] = None


def set_key_provider(provider: KeyProvider) -> None:
    """Set the active key provider for encryption/decryption operations.

    Args:
        provider: A :class:`KeyProvider` implementation.

    Example::

        set_key_provider(AwsKmsKeyProvider(kms_key_id="alias/veritas"))
    """
    global _active_key_provider
    _active_key_provider = provider
    logger.info("Encryption key provider set to: %s", provider.provider_name)


def get_key_provider() -> KeyProvider:
    """Return the active key provider (defaults to :class:`EnvKeyProvider`)."""
    global _active_key_provider
    if _active_key_provider is None:
        _active_key_provider = EnvKeyProvider()
    return _active_key_provider


def build_key_provider(
    backend: Optional[str] = None,
    **kwargs: object,
) -> KeyProvider:
    """Build a key provider from a backend name string.

    Args:
        backend: Provider name (``env``, ``aws_kms``, ``gcp_kms``,
            ``vault``). Defaults to ``VERITAS_KEY_PROVIDER`` env var
            or ``env``.

    Returns:
        Configured :class:`KeyProvider` instance.

    Raises:
        ValueError: If the backend name is not recognised.
    """
    selected = (
        backend
        if backend is not None
        else os.getenv("VERITAS_KEY_PROVIDER", "env")
    ).strip().lower()

    if selected in {"", "env", "env_var"}:
        return EnvKeyProvider()
    if selected in {"aws_kms", "aws"}:
        return AwsKmsKeyProvider(**kwargs)  # type: ignore[arg-type]
    if selected in {"gcp_kms", "gcp"}:
        return GcpKmsKeyProvider(**kwargs)  # type: ignore[arg-type]
    if selected in {"vault", "hashicorp_vault"}:
        return VaultKeyProvider(**kwargs)  # type: ignore[arg-type]
    raise ValueError(
        f"Unknown key provider backend: {selected!r}. "
        "Supported: env, aws_kms, gcp_kms, vault."
    )


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

    Uses the active :class:`KeyProvider` to retrieve the encryption key.
    Falls back to ``VERITAS_ENCRYPTION_KEY`` env var for backward
    compatibility when no custom provider is configured.

    Raises :class:`EncryptionKeyMissing` when no key is configured
    to enforce secure-by-default (fail-closed).

    Returns ``ENC:`` prefixed base64 ciphertext when a key is available.
    """
    if not isinstance(plaintext, str):
        raise TypeError(f"encrypt() requires a str, got {type(plaintext).__name__}")

    provider = get_key_provider()
    key = provider.get_key_bytes()
    if key is None:
        raise EncryptionKeyMissing(
            "No encryption key available. "
            "TrustLog requires encryption. Configure a KeyProvider or "
            "set VERITAS_ENCRYPTION_KEY, or call generate_key() to create one."
        )

    if _USE_REAL_AES:
        return "ENC:aesgcm:" + _encrypt_aesgcm_raw(plaintext, key)
    return "ENC:hmac-ctr:" + _encrypt_hmac_ctr_raw(plaintext, key)


def decrypt(ciphertext: str) -> str:
    """Decrypt an ``ENC:``-prefixed ciphertext string.

    Uses the active :class:`KeyProvider` to retrieve the decryption key.

    Algorithm dispatch uses the tag between ``ENC:`` and the payload
    (e.g. ``ENC:aesgcm:<b64>``). Legacy tokens without an algorithm tag are
    rejected by default and can be enabled only for migrations via
    ``VERITAS_ENCRYPTION_LEGACY_DECRYPT=1``.

    Returns the original string unchanged if it does not start with ``ENC:``.
    Raises :class:`EncryptionKeyMissing` when the key is required but absent.
    """
    if not ciphertext.startswith("ENC:"):
        return ciphertext

    provider = get_key_provider()
    key = provider.get_key_bytes()
    if key is None:
        raise EncryptionKeyMissing(
            "Cannot decrypt: no encryption key available from provider"
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
