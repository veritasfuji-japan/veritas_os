# veritas_os/core/kernel_doctor.py
# -*- coding: utf-8 -*-
"""Doctor / process-confinement security utilities.

Extracted from ``kernel.py`` because these helpers are orthogonal to the
decision-making core.  They guard the auto-doctor subprocess launch and
have no coupling to ``decide()`` logic.

Backward compatibility:
- ``kernel.py`` re-exports the symbols that existed at module level
  (``_is_doctor_confinement_profile_active``, ``_is_safe_python_executable``,
  ``_open_doctor_log_fd``) so external callers are unaffected.
"""
from __future__ import annotations

import re
from typing import Optional


def _read_proc_self_status_seccomp() -> Optional[int]:
    """Read Linux seccomp mode from ``/proc/self/status``.

    Returns:
        ``0`` for disabled, ``1`` for strict mode, ``2`` for filter mode,
        or ``None`` when the value cannot be determined.
    """
    from pathlib import Path

    status_path = Path("/proc/self/status")
    if not status_path.exists():
        return None

    try:
        for line in status_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("Seccomp:"):
                _, value = line.split(":", 1)
                return int(value.strip())
    except (OSError, ValueError):
        return None
    return None


def _read_apparmor_profile() -> Optional[str]:
    """Read the current AppArmor profile label on Linux.

    Returns:
        The profile label string, or ``None`` when unavailable.
    """
    from pathlib import Path

    current_path = Path("/proc/self/attr/current")
    if not current_path.exists():
        return None

    try:
        profile = current_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None

    return profile or None


def _is_doctor_confinement_profile_active() -> bool:
    """Return whether process confinement is active for safe auto-doctor.

    Security:
        ``subprocess.Popen`` widens impact when operational settings are wrong.
        Auto-starting doctor is therefore allowed only when at least one runtime
        confinement profile (seccomp or AppArmor) is active.
    """
    seccomp_mode = _read_proc_self_status_seccomp()
    if seccomp_mode is not None and seccomp_mode > 0:
        return True

    apparmor_profile = _read_apparmor_profile()
    if not apparmor_profile:
        return False

    normalized = apparmor_profile.lower()
    return normalized not in {"unconfined", "docker-default (enforce)"}


def _is_safe_python_executable(executable_path: Optional[str]) -> bool:
    """Validate that a Python executable path is safe to launch.

    Args:
        executable_path: Path candidate, usually ``sys.executable``.

    Returns:
        ``True`` when the path points to an executable Python interpreter.

    Security:
        Auto-doctor launches a subprocess. Rejecting missing, non-absolute,
        non-executable, or unexpected binary names reduces command hijacking
        risk when runtime environment variables are tampered with.
    """
    import os

    if not executable_path:
        return False
    if not os.path.isabs(executable_path):
        return False
    if not os.path.isfile(executable_path):
        return False
    if not os.access(executable_path, os.X_OK):
        return False

    executable_name = os.path.basename(executable_path).lower().replace(".exe", "")
    return bool(re.match(r"^(python|pypy)[0-9.]*$", executable_name))


def _open_doctor_log_fd(log_path: str) -> int:
    """Open a doctor log file descriptor with secure defaults.

    The descriptor is opened with restrictive file permissions and validated
    as a regular file. When available, ``O_NOFOLLOW`` is enabled to reduce
    symlink-based redirection risks.

    Args:
        log_path: Absolute file path of the doctor log.

    Returns:
        File descriptor opened in append mode.

    Raises:
        OSError: If the file cannot be opened.
        ValueError: If the opened path is not a regular file.
    """
    import os
    import stat

    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    nofollow_flag = getattr(os, "O_NOFOLLOW", 0)
    if nofollow_flag:
        flags |= nofollow_flag

    fd = os.open(log_path, flags, 0o600)
    st = os.fstat(fd)
    if not stat.S_ISREG(st.st_mode):
        os.close(fd)
        raise ValueError("Doctor log path must point to a regular file")
    return fd


__all__ = [
    "_read_proc_self_status_seccomp",
    "_read_apparmor_profile",
    "_is_doctor_confinement_profile_active",
    "_is_safe_python_executable",
    "_open_doctor_log_fd",
]
