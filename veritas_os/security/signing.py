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
import importlib.util
import logging
import os
import stat
from pathlib import Path
from typing import Any, Tuple

from veritas_os.security.hash import sha256_hex

logger = logging.getLogger(__name__)


def _load_crypto_primitives() -> tuple[Any, Any, Any, Any]:
    """Load cryptography primitives lazily for signed TrustLog operations.

    Security:
        Signed TrustLog integrity depends on Ed25519 primitives from
        ``cryptography``. When the package is unavailable, callers receive a
        clear runtime error instead of an import-time crash so non-signed code
        paths can continue to operate in a degraded but observable mode.
    """
    if importlib.util.find_spec("cryptography") is None:
        raise RuntimeError(
            "cryptography is required for signed TrustLog operations"
        )

    exceptions = importlib.import_module("cryptography.exceptions")
    serialization = importlib.import_module(
        "cryptography.hazmat.primitives.serialization"
    )
    ed25519 = importlib.import_module(
        "cryptography.hazmat.primitives.asymmetric.ed25519"
    )
    return (
        exceptions.InvalidSignature,
        serialization,
        ed25519.Ed25519PrivateKey,
        ed25519.Ed25519PublicKey,
    )


def generate_ed25519_keypair() -> Tuple[bytes, bytes]:
    """Generate an Ed25519 key pair as raw bytes.

    Returns:
        Tuple of ``(private_key_raw, public_key_raw)``.
    """
    _, serialization, private_key_cls, _ = _load_crypto_primitives()
    private_key = private_key_cls.generate()
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


def _load_private_key(private_key_path: Path) -> Any:
    _, _, private_key_cls, _ = _load_crypto_primitives()
    _check_private_key_permissions(private_key_path)
    raw = base64.urlsafe_b64decode(private_key_path.read_text(encoding="utf-8"))
    return private_key_cls.from_private_bytes(raw)


def _load_public_key(public_key_path: Path) -> Any:
    _, _, _, public_key_cls = _load_crypto_primitives()
    raw = base64.urlsafe_b64decode(public_key_path.read_text(encoding="utf-8"))
    return public_key_cls.from_public_bytes(raw)


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
    invalid_signature_cls, _, _, _ = _load_crypto_primitives()
    public_key = _load_public_key(public_key_path)
    signature = base64.urlsafe_b64decode(signature_b64)
    try:
        public_key.verify(signature, payload_hash.encode("utf-8"))
    except invalid_signature_cls:
        return False
    return True


def public_key_fingerprint(public_key_path: Path, *, length: int = 16) -> str:
    """Return a short, stable fingerprint for a public signing key.

    The fingerprint is derived from SHA-256 over the raw public-key bytes and is
    intended for lightweight key-id tagging in TrustLog entries.
    """
    raw = base64.urlsafe_b64decode(public_key_path.read_text(encoding="utf-8"))
    return sha256_hex(raw.hex())[:length]
