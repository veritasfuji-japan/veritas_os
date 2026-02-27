"""Ed25519 signing helpers for TrustLog signed audit entries."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Tuple

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
    """Persist a new Ed25519 key pair to disk in URL-safe base64 form."""
    private_raw, public_raw = generate_ed25519_keypair()
    private_key_path.parent.mkdir(parents=True, exist_ok=True)
    public_key_path.parent.mkdir(parents=True, exist_ok=True)

    private_key_path.write_text(
        base64.urlsafe_b64encode(private_raw).decode("ascii"),
        encoding="utf-8",
    )
    public_key_path.write_text(
        base64.urlsafe_b64encode(public_raw).decode("ascii"),
        encoding="utf-8",
    )
    return private_key_path, public_key_path


def _load_private_key(private_key_path: Path) -> Ed25519PrivateKey:
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
