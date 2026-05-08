"""Hardening tests for file-backed Ed25519 private-key loading."""

from __future__ import annotations

import base64
import os
from pathlib import Path

import pytest

from veritas_os.security import signing


def _write_private_key_file(
    path: Path,
    raw_private_key: bytes,
    mode: int = 0o600,
) -> None:
    path.write_text(
        base64.urlsafe_b64encode(raw_private_key).decode("ascii"),
        encoding="utf-8",
    )
    path.chmod(mode)


@pytest.mark.skipif(not hasattr(os, "O_NOFOLLOW"), reason="O_NOFOLLOW not available")
def test_load_private_key_rejects_symlink(tmp_path: Path) -> None:
    private_raw, _ = signing.generate_ed25519_keypair()
    real_key = tmp_path / "real.key"
    _write_private_key_file(real_key, private_raw, mode=0o600)

    symlink_key = tmp_path / "symlink.key"
    symlink_key.symlink_to(real_key)

    with pytest.raises(OSError):
        signing._load_private_key(symlink_key)


def test_load_private_key_rejects_unsafe_permissions(tmp_path: Path) -> None:
    private_raw, _ = signing.generate_ed25519_keypair()
    private_key_path = tmp_path / "private_unsafe.key"
    _write_private_key_file(private_key_path, private_raw, mode=0o644)

    with pytest.raises(PermissionError, match="unsafe permissions"):
        signing._load_private_key(private_key_path)


def test_load_private_key_rejects_non_regular_file(tmp_path: Path) -> None:
    with pytest.raises(PermissionError, match="regular file"):
        signing._load_private_key(tmp_path)


def test_private_key_open_flags_include_optional_hardening_flags() -> None:
    flags = signing._private_key_open_flags()
    if hasattr(os, "O_CLOEXEC"):
        assert flags & os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        assert flags & os.O_NOFOLLOW


def test_file_backed_signing_flow_remains_valid(tmp_path: Path) -> None:
    private_key_path = tmp_path / "private.key"
    public_key_path = tmp_path / "public.key"
    signing.store_keypair(private_key_path, public_key_path)

    loaded_private_key = signing._load_private_key(private_key_path)
    assert loaded_private_key is not None

    payload_hash = "a" * 64
    signature = signing.sign_payload_hash(payload_hash, private_key_path)
    assert signing.verify_payload_signature(payload_hash, signature, public_key_path)
