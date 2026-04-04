"""Ed25519 cryptographic signing for policy bundles.

This module provides key generation, signing, and verification using
Ed25519 public-key cryptography.  When keys are unavailable the caller
falls back to SHA-256 integrity checks automatically.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from pathlib import Path
from typing import Tuple

logger = logging.getLogger(__name__)

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
        Ed25519PublicKey,
    )
    from cryptography.hazmat.primitives import serialization
    from cryptography.exceptions import InvalidSignature

    _HAS_CRYPTO = True
except ImportError:  # pragma: no cover – optional dependency
    _HAS_CRYPTO = False

SIGNING_ALGORITHM = "ed25519"


# ---------------------------------------------------------------------------
# Key management helpers
# ---------------------------------------------------------------------------

def generate_keypair() -> Tuple[bytes, bytes]:
    """Generate an Ed25519 key pair.

    Returns:
        Tuple of ``(private_key_pem, public_key_pem)`` in PEM encoding.

    Raises:
        RuntimeError: If the ``cryptography`` library is not installed.
    """
    if not _HAS_CRYPTO:
        raise RuntimeError(
            "cryptography library is required for Ed25519 signing "
            "(pip install cryptography)"
        )
    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


def _load_private_key(pem: bytes) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("provided PEM is not an Ed25519 private key")
    return key


def _load_public_key(pem: bytes) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(pem)
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("provided PEM is not an Ed25519 public key")
    return key


# ---------------------------------------------------------------------------
# Sign / verify
# ---------------------------------------------------------------------------

def sign_manifest(manifest_bytes: bytes, private_key_pem: bytes) -> str:
    """Sign *manifest_bytes* with an Ed25519 private key.

    Returns:
        Base64-encoded signature string.

    Raises:
        RuntimeError: If the ``cryptography`` library is not installed.
        ValueError:   If the key is not a valid Ed25519 private key.
    """
    if not _HAS_CRYPTO:
        raise RuntimeError(
            "cryptography library is required for Ed25519 signing"
        )
    private_key = _load_private_key(private_key_pem)
    signature = private_key.sign(manifest_bytes)
    return base64.b64encode(signature).decode("ascii")


def verify_manifest_ed25519(
    manifest_bytes: bytes,
    signature_b64: str,
    public_key_pem: bytes,
) -> bool:
    """Verify an Ed25519 signature on *manifest_bytes*.

    Returns:
        ``True`` if the signature is valid, ``False`` otherwise.
    """
    if not _HAS_CRYPTO:
        logger.warning("cryptography library not available; cannot verify Ed25519 signature")
        return False
    try:
        public_key = _load_public_key(public_key_pem)
        raw_sig = base64.b64decode(signature_b64)
        public_key.verify(raw_sig, manifest_bytes)
        return True
    except (InvalidSignature, Exception) as exc:
        logger.warning("Ed25519 signature verification failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Legacy SHA-256 helpers (backward compatibility)
# ---------------------------------------------------------------------------

def sha256_manifest_hex(manifest_bytes: bytes) -> str:
    """Compute SHA-256 hex digest of manifest payload (legacy mode)."""
    return hashlib.sha256(manifest_bytes).hexdigest()


def verify_manifest_sha256(manifest_path: Path) -> bool:
    """Legacy SHA-256 hash-integrity check for bundles without Ed25519 keys."""
    sig_path = manifest_path.parent / "manifest.sig"
    if not manifest_path.exists() or not sig_path.exists():
        return False
    expected = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    observed = sig_path.read_text(encoding="utf-8").strip()
    return hmac.compare_digest(expected, observed)
