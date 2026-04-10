"""Ed25519 signing helpers for TrustLog signed audit entries.

Security notes — private key storage
-------------------------------------
``store_keypair`` writes the private key as URL-safe Base64 to a local file.
The key material is **not encrypted at rest**.  This design is intentional for
simplicity in single-host deployments, but operators should be aware of the
following risk and mitigations:

Risk:
    If an attacker gains read access to the private key file (e.g., via path
    traversal, symlink attack, or file-system backup exposure), they can forge
    TrustLog signatures and invalidate the audit trail's integrity guarantee.

Mitigations applied here:
    - Files are created with mode ``0o600`` (owner-read/write only).
    - ``_load_private_key`` checks that the key file is not world-readable
      and raises ``PermissionError`` when unsafe permissions are detected.

Recommended additional hardening for production:
    - Store the private key in a secrets manager (HashiCorp Vault, AWS Secrets
      Manager, GCP Secret Manager) or an HSM/KMS.
    - Mount the key file from a tmpfs/memory-backed volume.
    - Rotate keys periodically and re-sign historical log entries.
"""

from __future__ import annotations

import base64
import importlib
import logging
import os
import stat
from pathlib import Path
from typing import Optional, Protocol, Tuple

from veritas_os.security.hash import sha256_hex

logger = logging.getLogger(__name__)

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


def generate_ed25519_keypair() -> Tuple[bytes, bytes]:
    """Generate an Ed25519 key pair as raw bytes.

    Returns:
        Tuple of ``(private_key_raw, public_key_raw)``.
    """
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    private_raw = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return private_raw, public_raw


def store_keypair(private_key_path: Path, public_key_path: Path) -> Tuple[Path, Path]:
    """Persist a new Ed25519 key pair to disk in URL-safe base64 form.

    Security:
        The private key file is written with mode ``0o600`` so that only the
        owning process account can read it.  See the module-level docstring for
        production hardening recommendations.
    """
    private_raw, public_raw = generate_ed25519_keypair()
    private_key_path.parent.mkdir(parents=True, exist_ok=True)
    public_key_path.parent.mkdir(parents=True, exist_ok=True)

    # Write with restrictive permissions: owner read/write only.
    fd = os.open(str(private_key_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, base64.urlsafe_b64encode(private_raw))
    finally:
        os.close(fd)

    public_key_path.write_text(
        base64.urlsafe_b64encode(public_raw).decode("ascii"),
        encoding="utf-8",
    )
    return private_key_path, public_key_path


def _check_private_key_permissions(private_key_path: Path) -> None:
    """Warn (or raise) when the private key file has unsafe permissions.

    Security:
        A world-readable private key file undermines the audit trail integrity
        guarantee. This check runs at load time so misconfigurations are caught
        early rather than silently tolerated.

    Raises:
        PermissionError: When the file is readable by group or others.
    """
    try:
        file_stat = private_key_path.stat()
        mode = stat.S_IMODE(file_stat.st_mode)
        if mode & (stat.S_IRGRP | stat.S_IROTH):
            raise PermissionError(
                f"Private key file {private_key_path} has unsafe permissions "
                f"({oct(mode)}). Expected 0o600 (owner-read/write only). "
                "An attacker with file-system read access could forge TrustLog signatures."
            )
    except PermissionError:
        raise
    except OSError as exc:
        logger.warning("Could not stat private key file %s: %s", private_key_path, exc)


def _load_private_key(private_key_path: Path) -> Ed25519PrivateKey:
    _check_private_key_permissions(private_key_path)
    raw = base64.urlsafe_b64decode(private_key_path.read_text(encoding="utf-8"))
    return Ed25519PrivateKey.from_private_bytes(raw)


def _load_public_key(public_key_path: Path) -> Ed25519PublicKey:
    raw = base64.urlsafe_b64decode(public_key_path.read_text(encoding="utf-8"))
    return Ed25519PublicKey.from_public_bytes(raw)


def sign_payload_hash(payload_hash: str, private_key_path: Path) -> str:
    """Sign a SHA-256 payload hash string with Ed25519 and return base64."""
    private_key = _load_private_key(private_key_path)
    signature = private_key.sign(payload_hash.encode("utf-8"))
    return base64.urlsafe_b64encode(signature).decode("ascii")


def verify_payload_signature(
    payload_hash: str,
    signature_b64: str,
    public_key_path: Path,
) -> bool:
    """Verify an Ed25519 signature over a payload hash string."""
    public_key = _load_public_key(public_key_path)
    signature = base64.urlsafe_b64decode(signature_b64)
    try:
        public_key.verify(signature, payload_hash.encode("utf-8"))
    except InvalidSignature:
        return False
    return True


def public_key_fingerprint(public_key_path: Path, *, length: int = 16) -> str:
    """Return a short, stable fingerprint for a public signing key.

    The fingerprint is derived from SHA-256 over the raw public-key bytes and is
    intended for lightweight key-id tagging in TrustLog entries.
    """
    raw = base64.urlsafe_b64decode(public_key_path.read_text(encoding="utf-8"))
    return sha256_hex(raw.hex())[:length]


class Signer(Protocol):
    """Pluggable signer protocol for TrustLog signatures."""

    signer_type: str

    def sign_payload_hash(self, payload_hash: str) -> str:
        """Sign a canonical payload hash and return URL-safe Base64 signature."""

    def verify_payload_signature(self, payload_hash: str, signature_b64: str) -> bool:
        """Verify signature over a payload hash."""

    def signer_key_id(self) -> str:
        """Return a stable signer identity (KMS key id or local key fingerprint)."""


class FileEd25519Signer:
    """Ed25519 signer backed by local key files."""

    signer_type = "file_ed25519"

    def __init__(self, private_key_path: Path, public_key_path: Path) -> None:
        self.private_key_path = private_key_path
        self.public_key_path = public_key_path

    def ensure_key_material(self) -> None:
        """Create local signing keypair on first use."""
        if self.private_key_path.exists() and self.public_key_path.exists():
            return
        store_keypair(self.private_key_path, self.public_key_path)

    def sign_payload_hash(self, payload_hash: str) -> str:
        return sign_payload_hash(payload_hash, self.private_key_path)

    def verify_payload_signature(self, payload_hash: str, signature_b64: str) -> bool:
        return verify_payload_signature(
            payload_hash=payload_hash,
            signature_b64=signature_b64,
            public_key_path=self.public_key_path,
        )

    def signer_key_id(self) -> str:
        return public_key_fingerprint(self.public_key_path)


class AwsKmsEd25519Signer:
    """Ed25519 signer backed by AWS KMS asymmetric keys.

    Security warning:
        This signer performs a network call to AWS KMS for signing operations.
        Ensure IAM permissions are scoped to the specific key and that requests
        are routed over trusted channels.
    """

    signer_type = "aws_kms_ed25519"

    def __init__(
        self,
        kms_key_id: str,
        kms_client: Optional[object] = None,
    ) -> None:
        if not kms_key_id.strip():
            raise ValueError("VERITAS_TRUSTLOG_KMS_KEY_ID is required for aws_kms backend")
        self.kms_key_id = kms_key_id.strip()
        self._kms_client = kms_client
        self._public_key: Optional[Ed25519PublicKey] = None

    @property
    def kms_client(self) -> object:
        """Lazily construct boto3 KMS client."""
        if self._kms_client is None:
            boto3 = importlib.import_module("boto3")
            self._kms_client = boto3.client("kms")
        return self._kms_client

    def _load_public_key(self) -> Ed25519PublicKey:
        if self._public_key is not None:
            return self._public_key
        response = self.kms_client.get_public_key(KeyId=self.kms_key_id)
        public_key_der = response["PublicKey"]
        loaded = serialization.load_der_public_key(public_key_der)
        if not isinstance(loaded, Ed25519PublicKey):
            raise ValueError("KMS key is not Ed25519")
        self._public_key = loaded
        return self._public_key

    def sign_payload_hash(self, payload_hash: str) -> str:
        response = self.kms_client.sign(
            KeyId=self.kms_key_id,
            Message=payload_hash.encode("utf-8"),
            MessageType="RAW",
            SigningAlgorithm="EDDSA",
        )
        signature: bytes = response["Signature"]
        return base64.urlsafe_b64encode(signature).decode("ascii")

    def verify_payload_signature(self, payload_hash: str, signature_b64: str) -> bool:
        try:
            signature = base64.urlsafe_b64decode(signature_b64)
            public_key = self._load_public_key()
            public_key.verify(signature, payload_hash.encode("utf-8"))
        except (InvalidSignature, ValueError, TypeError):
            return False
        return True

    def signer_key_id(self) -> str:
        return self.kms_key_id


def build_trustlog_signer(
    *,
    private_key_path: Path,
    public_key_path: Path,
    ensure_local_keys: bool = False,
) -> Signer:
    """Build TrustLog signer from backend environment variables."""
    backend = os.getenv("VERITAS_TRUSTLOG_SIGNER_BACKEND", "file").strip().lower()
    if backend in {"", "file"}:
        signer = FileEd25519Signer(private_key_path=private_key_path, public_key_path=public_key_path)
        if ensure_local_keys:
            signer.ensure_key_material()
        return signer
    if backend == "aws_kms":
        kms_key_id = os.getenv("VERITAS_TRUSTLOG_KMS_KEY_ID", "")
        return AwsKmsEd25519Signer(kms_key_id=kms_key_id)
    raise ValueError(
        "Unsupported VERITAS_TRUSTLOG_SIGNER_BACKEND. Expected 'file' or 'aws_kms'."
    )
