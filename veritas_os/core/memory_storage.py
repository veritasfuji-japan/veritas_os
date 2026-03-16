# veritas_os/core/memory_storage.py
"""
File I/O, locking, and JSON serialization for MemoryOS.

Provides:
- locked_memory() context manager for multi-process file locking
- Pickle artifact scanning and security guards
- Storage path configuration
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional
from contextlib import contextmanager
import os
import time
import logging

from .config import capability_cfg, emit_capability_manifest

logger = logging.getLogger(__name__)

PICKLE_MIGRATION_GUIDE_PATH = "docs/operations/MEMORY_PICKLE_MIGRATION.md"

# OS 判定
IS_WIN = os.name == "nt"

if not IS_WIN and capability_cfg.enable_memory_posix_file_lock:
    import fcntl  # type: ignore
else:
    fcntl = None  # type: ignore

if capability_cfg.emit_manifest_on_import:
    emit_capability_manifest(
        component="memory_storage",
        manifest={
            "posix_file_lock": bool(not IS_WIN and fcntl is not None),
        },
    )


def _emit_legacy_pickle_runtime_blocked(path: Path, artifact_name: str) -> None:
    """Log a security error for legacy pickle artifacts blocked at runtime.

    Pickle/joblib deserialization is permanently removed due to arbitrary code
    execution (RCE) risk.  Use the offline migration CLI to convert legacy
    artifacts:  ``python -m veritas_os.scripts.migrate_pickle``
    """
    logger.error(
        "[SECURITY] Legacy %s pickle detected at %s. "
        "Runtime pickle/joblib loading is permanently disabled (RCE risk). "
        "Migrate artifacts offline: python -m veritas_os.scripts.migrate_pickle  "
        "See %s for details.",
        artifact_name,
        path,
        PICKLE_MIGRATION_GUIDE_PATH,
    )


def _warn_for_legacy_pickle_artifacts(scan_roots: List[Path]) -> None:
    """Emit security warnings when legacy pickle artifacts are present.

    This runtime guardrail does not deserialize any pickle payloads.
    It scans recursively under known MemoryOS runtime directories and emits
    migration guidance so operators can remove risky artifacts.
    """
    checked_roots = set()
    for raw_root in scan_roots:
        root = raw_root.resolve(strict=False)
        if root in checked_roots or not root.exists() or not root.is_dir():
            continue
        checked_roots.add(root)

        for candidate in root.rglob("*"):
            if not candidate.is_file():
                continue

            if candidate.suffix.lower() not in {".pkl", ".joblib", ".pickle"}:
                continue

            _emit_legacy_pickle_runtime_blocked(
                path=candidate,
                artifact_name="runtime artifact",
            )


@contextmanager
def locked_memory(path: Path, timeout: float = 5.0) -> Any:
    """
    memory.json 用のシンプルな排他ロック。
    """
    start = time.time()
    lockfile: Optional[Path] = None
    fh = None

    if not IS_WIN and fcntl is not None:
        # POSIX: fcntl によるファイルロック
        path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(path, "a+", encoding="utf-8")
        while True:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)  # type: ignore
                break
            except BlockingIOError:
                if time.time() - start > timeout:
                    fh.close()
                    raise TimeoutError(f"failed to acquire lock for {path}")
                time.sleep(0.02)
        try:
            yield
        finally:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)  # type: ignore
            except Exception as e:
                logger.error("[MemoryOS] unlock failed: %s", e)
            fh.close()
    else:
        # Windows or 非POSIX: .lock ファイルで排他
        lockfile = path.with_suffix(path.suffix + ".lock")
        _STALE_LOCK_AGE_SECONDS = 300  # 5 minutes
        backoff = 0.01
        while True:
            try:
                fd = os.open(str(lockfile), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                break
            except FileExistsError:
                # Stale lock detection: remove lockfile older than threshold
                try:
                    lock_age = time.time() - os.path.getmtime(str(lockfile))
                    if lock_age > _STALE_LOCK_AGE_SECONDS:
                        logger.warning(
                            "[MemoryOS] Removing stale lockfile (age=%.0fs): %s",
                            lock_age, lockfile,
                        )
                        lockfile.unlink(missing_ok=True)
                        continue
                except OSError as e:
                    logger.debug(
                        "[MemoryOS] lockfile mtime check failed: %s (%s)",
                        lockfile,
                        e,
                    )
                if time.time() - start > timeout:
                    raise TimeoutError(f"failed to acquire lock for {path}")
                time.sleep(backoff)
                backoff = min(backoff * 2.0, 0.32)
        try:
            yield
        finally:
            try:
                # Use missing_ok=True to avoid TOCTOU race condition
                # (file could be deleted between exists() check and unlink())
                lockfile.unlink(missing_ok=True)
            except Exception as e:
                logger.error("[MemoryOS] lockfile cleanup failed: %s", e)
