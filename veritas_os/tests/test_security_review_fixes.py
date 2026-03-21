"""Tests for security fixes: path traversal sanitization and signing permission check."""

from __future__ import annotations

import importlib
import os
import stat
from pathlib import Path

import pytest


# ================================================================
# 1. Path traversal sanitization — _safe_filename_id
# ================================================================

class TestSafeFilenameIdPipeline:
    """Verify pipeline._safe_filename_id strips path traversal characters."""

    def test_normal_hex_id_unchanged(self):
        from veritas_os.core.pipeline import _safe_filename_id
        assert _safe_filename_id("abc123def456") == "abc123def456"

    def test_path_traversal_stripped(self):
        from veritas_os.core.pipeline import _safe_filename_id
        result = _safe_filename_id("../../etc/passwd")
        assert "/" not in result
        assert ".." not in result

    def test_slashes_replaced(self):
        from veritas_os.core.pipeline import _safe_filename_id
        result = _safe_filename_id("foo/bar\\baz")
        assert "/" not in result
        assert "\\" not in result

    def test_hyphens_and_underscores_kept(self):
        from veritas_os.core.pipeline import _safe_filename_id
        assert _safe_filename_id("my-id_123") == "my-id_123"

    def test_long_id_truncated(self):
        from veritas_os.core.pipeline import _safe_filename_id
        long_id = "a" * 200
        result = _safe_filename_id(long_id)
        assert len(result) <= 128

    def test_empty_string(self):
        from veritas_os.core.pipeline import _safe_filename_id
        result = _safe_filename_id("")
        assert isinstance(result, str)


class TestSafeFilenameIdReplay:
    """Verify replay_engine._safe_filename_id strips path traversal characters."""

    def test_path_traversal_stripped(self):
        from veritas_os.replay.replay_engine import _safe_filename_id
        result = _safe_filename_id("../../etc/shadow")
        assert "/" not in result
        assert ".." not in result

    def test_replay_file_name_sanitized(self):
        from veritas_os.replay.replay_engine import _replay_file_name
        name = _replay_file_name("../../etc/passwd")
        assert "/" not in name
        assert name.startswith("replay_")
        assert name.endswith(".json")


class TestSafeFilenameIdCompliance:
    """Verify report_engine._safe_filename_id strips path traversal characters."""

    def test_path_traversal_stripped(self):
        from veritas_os.compliance.report_engine import _safe_filename_id
        result = _safe_filename_id("../../etc/shadow")
        assert "/" not in result
        assert ".." not in result


# ================================================================
# 2. signing.py — PermissionError must propagate, not be caught by OSError
# ================================================================

class TestSigningPermissionCheck:
    """Verify that _check_private_key_permissions raises PermissionError for unsafe perms."""

    def test_unsafe_permissions_raise(self, tmp_path):
        from veritas_os.security.signing import _check_private_key_permissions
        key_file = tmp_path / "test.key"
        key_file.write_text("fake-key-data")
        # Make file group-readable (unsafe)
        os.chmod(key_file, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP)

        with pytest.raises(PermissionError, match="unsafe permissions"):
            _check_private_key_permissions(key_file)

    def test_safe_permissions_pass(self, tmp_path):
        from veritas_os.security.signing import _check_private_key_permissions
        key_file = tmp_path / "test.key"
        key_file.write_text("fake-key-data")
        os.chmod(key_file, stat.S_IRUSR | stat.S_IWUSR)  # 0o600

        # Should not raise
        _check_private_key_permissions(key_file)

    def test_world_readable_raises(self, tmp_path):
        from veritas_os.security.signing import _check_private_key_permissions
        key_file = tmp_path / "test.key"
        key_file.write_text("fake-key-data")
        os.chmod(key_file, stat.S_IRUSR | stat.S_IWUSR | stat.S_IROTH)

        with pytest.raises(PermissionError, match="unsafe permissions"):
            _check_private_key_permissions(key_file)

    def test_oserror_on_stat_is_warning_only(self, tmp_path):
        """OSError from stat (e.g. file not found) should warn, not raise."""
        from veritas_os.security.signing import _check_private_key_permissions
        missing = tmp_path / "nonexistent.key"

        # Should not raise (just logs warning)
        _check_private_key_permissions(missing)

    def test_generate_keypair_raises_runtime_error_without_cryptography(
        self,
        monkeypatch,
    ):
        """Missing cryptography must fail at call time, not module import time."""
        import veritas_os.security.signing as signing

        monkeypatch.setattr(
            signing.importlib.util,
            "find_spec",
            lambda name: None if name == "cryptography" else object(),
        )

        with pytest.raises(RuntimeError, match="cryptography is required"):
            signing.generate_ed25519_keypair()
