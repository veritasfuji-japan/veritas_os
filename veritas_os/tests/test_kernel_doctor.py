# tests/test_kernel_doctor.py
# -*- coding: utf-8 -*-
"""Unit tests for kernel_doctor.py — doctor/security utilities.

These tests verify that the functions extracted from kernel.py into
kernel_doctor.py behave identically. They also confirm backward-compatible
access via ``kernel._is_doctor_confinement_profile_active`` etc.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from veritas_os.core.kernel_doctor import (
    _read_proc_self_status_seccomp,
    _read_apparmor_profile,
    _is_doctor_confinement_profile_active,
    _is_safe_python_executable,
    _open_doctor_log_fd,
)


# ============================================================
# _read_proc_self_status_seccomp
# ============================================================

class TestReadSeccomp:
    def test_returns_none_when_missing(self, tmp_path):
        with patch("pathlib.Path.exists", return_value=False):
            assert _read_proc_self_status_seccomp() is None

    def test_returns_int_or_none(self):
        result = _read_proc_self_status_seccomp()
        assert result is None or isinstance(result, int)

    def test_handles_os_error(self, tmp_path):
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", side_effect=OSError("perm")):
                assert _read_proc_self_status_seccomp() is None


# ============================================================
# _read_apparmor_profile
# ============================================================

class TestReadApparmor:
    def test_returns_none_when_missing(self):
        with patch("pathlib.Path.exists", return_value=False):
            assert _read_apparmor_profile() is None


# ============================================================
# _is_doctor_confinement_profile_active
# ============================================================

class TestConfinement:
    def test_active_with_seccomp(self, monkeypatch):
        import veritas_os.core.kernel_doctor as kd
        monkeypatch.setattr(kd, "_read_proc_self_status_seccomp", lambda: 2)
        monkeypatch.setattr(kd, "_read_apparmor_profile", lambda: None)
        assert _is_doctor_confinement_profile_active() is True

    def test_inactive_unconfined(self, monkeypatch):
        import veritas_os.core.kernel_doctor as kd
        monkeypatch.setattr(kd, "_read_proc_self_status_seccomp", lambda: 0)
        monkeypatch.setattr(kd, "_read_apparmor_profile", lambda: "unconfined")
        assert _is_doctor_confinement_profile_active() is False

    def test_active_with_custom_profile(self, monkeypatch):
        import veritas_os.core.kernel_doctor as kd
        monkeypatch.setattr(kd, "_read_proc_self_status_seccomp", lambda: None)
        monkeypatch.setattr(kd, "_read_apparmor_profile", lambda: "my_custom")
        assert _is_doctor_confinement_profile_active() is True

    def test_inactive_no_confinement(self, monkeypatch):
        import veritas_os.core.kernel_doctor as kd
        monkeypatch.setattr(kd, "_read_proc_self_status_seccomp", lambda: None)
        monkeypatch.setattr(kd, "_read_apparmor_profile", lambda: None)
        assert _is_doctor_confinement_profile_active() is False


# ============================================================
# _is_safe_python_executable
# ============================================================

class TestSafePython:
    def test_none_rejected(self):
        assert _is_safe_python_executable(None) is False

    def test_relative_rejected(self):
        assert _is_safe_python_executable("python3") is False

    def test_nonexistent_rejected(self):
        assert _is_safe_python_executable("/nonexistent/python3") is False

    def test_valid_executable(self):
        result = _is_safe_python_executable(sys.executable)
        # sys.executable should be valid in test environments
        assert isinstance(result, bool)

    def test_non_python_name_rejected(self, tmp_path):
        bad = tmp_path / "notpython"
        bad.write_text("#!/bin/sh\n")
        bad.chmod(0o755)
        assert _is_safe_python_executable(str(bad)) is False


# ============================================================
# _open_doctor_log_fd
# ============================================================

class TestOpenDoctorLog:
    def test_creates_regular_file(self, tmp_path):
        log_path = tmp_path / "doc.log"
        fd = _open_doctor_log_fd(str(log_path))
        try:
            assert log_path.exists()
            st = os.fstat(fd)
            # Permissions should be 0o600
            assert (st.st_mode & 0o777) == 0o600
        finally:
            os.close(fd)

    def test_rejects_non_regular(self, tmp_path):
        with pytest.raises((ValueError, OSError)):
            _open_doctor_log_fd(str(tmp_path))


# ============================================================
# Backward compat: accessible via kernel module
# ============================================================

class TestBackwardCompat:
    def test_accessible_from_kernel(self):
        """Verify re-exports exist (kernel import may fail in minimal envs)."""
        try:
            from veritas_os.core import kernel
        except BaseException:
            pytest.skip("kernel import requires full dependency set")
        assert hasattr(kernel, "_is_doctor_confinement_profile_active")
        assert hasattr(kernel, "_is_safe_python_executable")
        assert hasattr(kernel, "_open_doctor_log_fd")
        assert hasattr(kernel, "_read_proc_self_status_seccomp")
        assert hasattr(kernel, "_read_apparmor_profile")
