"""Bundle layout and archive helpers for policy compiler artifacts."""

from __future__ import annotations

import hashlib
import tarfile
from pathlib import Path
from typing import Any, Dict, List


def compute_file_sha256(path: Path) -> str:
    """Compute SHA-256 checksum for a generated artifact file."""
    hasher = hashlib.sha256()
    hasher.update(path.read_bytes())
    return hasher.hexdigest()


def collect_bundle_files(bundle_dir: Path) -> List[Dict[str, Any]]:
    """Collect bundle file metadata excluding generated archive files."""
    files: List[Dict[str, Any]] = []
    for file_path in sorted(bundle_dir.rglob("*")):
        if not file_path.is_file():
            continue
        rel = file_path.relative_to(bundle_dir).as_posix()
        if rel.endswith(".tar.gz"):
            continue
        files.append(
            {
                "path": rel,
                "sha256": compute_file_sha256(file_path),
                "size": file_path.stat().st_size,
            }
        )
    return files


def create_bundle_archive(bundle_dir: Path) -> Path:
    """Create deterministic tar.gz archive for distribution."""
    archive_path = bundle_dir.with_suffix(".tar.gz")
    with tarfile.open(archive_path, mode="w:gz") as tar:
        for entry in sorted(bundle_dir.rglob("*")):
            if not entry.is_file() or entry.is_symlink():
                continue
            rel = entry.relative_to(bundle_dir.parent)
            info = tar.gettarinfo(entry, arcname=rel.as_posix())
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            with open(entry, "rb") as fh:
                tar.addfile(info, fh)
    return archive_path
