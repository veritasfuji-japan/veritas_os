# veritas_os/core/atomic_io.py
# Atomic file write utilities for crash-safe persistence
"""
Atomic file write utilities.

Implements the "write to temp file + fsync + atomic rename" pattern
to prevent data corruption on crashes or power failures.

Usage:
    from veritas_os.core.atomic_io import atomic_write_json, atomic_write_text

    # For JSON files
    atomic_write_json(path, data, indent=2)

    # For text files (e.g., JSONL lines)
    atomic_write_text(path, content)

    # For numpy arrays
    atomic_write_npz(path, **arrays)
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Union

# Optional numpy support
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    np = None  # type: ignore
    HAS_NUMPY = False


def _ensure_parent_dir(path: Path) -> None:
    """Ensure the parent directory exists."""
    path.parent.mkdir(parents=True, exist_ok=True)


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    """
    Atomically write bytes to a file.

    Process:
    1. Write to a temporary file in the same directory
    2. fsync to ensure data is flushed to disk
    3. Atomically rename temp file to target path

    The temp file is created in the same directory to ensure
    os.replace() works (same filesystem requirement).
    """
    _ensure_parent_dir(path)

    # Create temp file in the same directory for atomic rename
    fd, tmp_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp"
    )
    try:
        # Write data
        os.write(fd, data)
        # Flush to disk
        os.fsync(fd)
        os.close(fd)
        fd = -1  # Mark as closed

        # Atomic rename (POSIX guarantees atomicity)
        os.replace(tmp_path, path)
        
        # ★ 修正 (M-1): ディレクトリの fsync を追加
        # ext4 data=ordered (デフォルト) では、rename後にディレクトリをfsyncしないと
        # クラッシュ時にrenameが失われる可能性がある
        try:
            dir_fd = os.open(str(path.parent), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except (OSError, AttributeError):
            # Windows や一部のファイルシステムでは失敗する可能性がある
            # その場合は無視して続行（ベストエフォート）
            pass
    except Exception:
        # Clean up temp file on failure
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def atomic_write_text(
    path: Union[str, Path],
    content: str,
    encoding: str = "utf-8",
) -> None:
    """
    Atomically write text content to a file.

    Args:
        path: Target file path
        content: Text content to write
        encoding: Text encoding (default: utf-8)
    """
    path = Path(path)
    data = content.encode(encoding)
    _atomic_write_bytes(path, data)


def atomic_write_json(
    path: Union[str, Path],
    data: Any,
    *,
    indent: int | None = 2,
    ensure_ascii: bool = False,
    sort_keys: bool = False,
) -> None:
    """
    Atomically write JSON data to a file.

    Args:
        path: Target file path
        data: JSON-serializable data
        indent: JSON indentation (default: 2, None for compact)
        ensure_ascii: Escape non-ASCII characters (default: False)
        sort_keys: Sort dictionary keys (default: False)
    """
    path = Path(path)
    content = json.dumps(
        data,
        indent=indent,
        ensure_ascii=ensure_ascii,
        sort_keys=sort_keys,
    )
    # Add trailing newline for POSIX compliance
    if not content.endswith("\n"):
        content += "\n"
    atomic_write_text(path, content)


def atomic_write_npz(
    path: Union[str, Path],
    **arrays: Any,
) -> None:
    """
    Atomically write numpy arrays to an .npz file.

    Args:
        path: Target .npz file path
        **arrays: Named arrays to save (e.g., vecs=vecs, ids=ids)

    Raises:
        ImportError: If numpy is not available
    """
    if not HAS_NUMPY:
        raise ImportError("numpy is required for atomic_write_npz")

    path = Path(path)
    _ensure_parent_dir(path)

    # Create temp file in the same directory
    fd, tmp_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp.npz"
    )
    try:
        os.close(fd)  # np.savez needs to open it itself
        fd = -1

        # Save to temp file
        np.savez(tmp_path, **arrays)

        # Atomic rename
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def atomic_append_line(
    path: Union[str, Path],
    line: str,
    encoding: str = "utf-8",
) -> None:
    """
    Append a line to a file with fsync for durability.

    Note: Appends are generally safe on POSIX systems, but this function
    ensures the data is fsynced to disk before returning.

    For truly atomic append-or-create, use atomic_write_text with full content.

    Args:
        path: Target file path
        line: Line to append (newline will be added if missing)
        encoding: Text encoding (default: utf-8)
    """
    path = Path(path)
    _ensure_parent_dir(path)

    if not line.endswith("\n"):
        line += "\n"

    # Open in append mode with line buffering
    fd = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_APPEND,
        0o644
    )
    try:
        os.write(fd, line.encode(encoding))
        os.fsync(fd)
    finally:
        os.close(fd)


__all__ = [
    "atomic_write_text",
    "atomic_write_json",
    "atomic_write_npz",
    "atomic_append_line",
]
