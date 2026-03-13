#!/usr/bin/env python3
"""One-way migration CLI: convert legacy pickle artifacts to safe JSON format.

Usage
-----
    python -m veritas_os.scripts.migrate_pickle [--scan-dir DIR] [--dry-run]

Security
--------
    pickle deserialization is inherently unsafe (arbitrary code execution).
    This CLI uses ``RestrictedUnpickler`` with a strict class allow-list and
    imposes a maximum file size to reduce risk.  **Run only in an isolated,
    trusted environment** and never against untrusted ``.pkl`` files.

After migration, remove the original ``.pkl`` / ``.joblib`` files.  The
application will refuse to load them at runtime.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import logging
import pickle
import struct
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger("veritas_os.migrate_pickle")

# ---------------------------------------------------------------------------
# Security constants
# ---------------------------------------------------------------------------

# Maximum pickle file size we are willing to process (50 MiB).
MAX_PICKLE_BYTES = 50 * 1024 * 1024

# Classes explicitly allowed during restricted unpickling.
_ALLOWED_MODULES_CLASSES: Dict[str, set] = {
    "builtins": {"dict", "list", "set", "frozenset", "tuple", "bytes", "bytearray"},
    "numpy": {"ndarray", "dtype", "float32", "float64", "int64", "int32"},
    "numpy.core.multiarray": {"scalar", "_reconstruct"},
    "numpy._core.multiarray": {"scalar", "_reconstruct"},
    "collections": {"OrderedDict"},
}

LEGACY_EXTENSIONS = frozenset({".pkl", ".joblib", ".pickle"})


# ---------------------------------------------------------------------------
# Restricted unpickler
# ---------------------------------------------------------------------------

class _RestrictedUnpickler(pickle.Unpickler):
    """An unpickler that only allows a vetted set of safe classes."""

    def find_class(self, module: str, name: str) -> Any:
        allowed = _ALLOWED_MODULES_CLASSES.get(module)
        if allowed is not None and name in allowed:
            return super().find_class(module, name)
        raise pickle.UnpicklingError(
            f"Blocked: {module}.{name} is not in the migration allow-list"
        )


def _restricted_loads(data: bytes) -> Any:
    """Deserialize bytes using the restricted unpickler."""
    return _RestrictedUnpickler(io.BytesIO(data)).load()


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------

def scan_legacy_files(roots: List[Path]) -> List[Path]:
    """Find all ``.pkl`` / ``.joblib`` / ``.pickle`` files under *roots*."""
    found: List[Path] = []
    seen: set = set()
    for root in roots:
        resolved = root.resolve()
        if resolved in seen or not resolved.exists() or not resolved.is_dir():
            continue
        seen.add(resolved)
        for candidate in sorted(resolved.rglob("*")):
            if candidate.is_file() and candidate.suffix.lower() in LEGACY_EXTENSIONS:
                found.append(candidate)
    return found


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------

def _convert_vector_index(pkl_path: Path) -> Optional[Path]:
    """Convert a legacy VectorMemory pickle index to JSON."""
    raw = pkl_path.read_bytes()
    if len(raw) > MAX_PICKLE_BYTES:
        logger.error("File too large (%d bytes), skipping: %s", len(raw), pkl_path)
        return None

    data = _restricted_loads(raw)
    if not isinstance(data, dict):
        logger.error("Unexpected pickle payload type %s in %s", type(data).__name__, pkl_path)
        return None

    documents: list = data.get("documents", [])
    embeddings = data.get("embeddings")

    out: Dict[str, Any] = {
        "documents": documents,
        "embeddings": None,
        "embeddings_shape": None,
        "embeddings_dtype": None,
        "format_version": "2.0",
        "migrated_from": str(pkl_path.name),
    }

    if embeddings is not None:
        arr = np.asarray(embeddings, dtype=np.float32)
        out["embeddings"] = base64.b64encode(arr.tobytes()).decode("ascii")
        out["embeddings_shape"] = list(arr.shape)
        out["embeddings_dtype"] = "float32"

    json_path = pkl_path.with_suffix(".json")
    json_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Converted vector index: %s -> %s", pkl_path, json_path)
    return json_path


def _convert_generic_pickle(pkl_path: Path) -> Optional[Path]:
    """Convert a generic pickle file to JSON (best-effort)."""
    raw = pkl_path.read_bytes()
    if len(raw) > MAX_PICKLE_BYTES:
        logger.error("File too large (%d bytes), skipping: %s", len(raw), pkl_path)
        return None

    data = _restricted_loads(raw)

    # Try to serialize to JSON — numpy arrays need special handling
    def _default(obj: Any) -> Any:
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, bytes):
            return base64.b64encode(obj).decode("ascii")
        raise TypeError(f"Cannot serialize {type(obj).__name__}")

    json_path = pkl_path.with_suffix(".json")
    json_path.write_text(
        json.dumps(data, default=_default, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("Converted generic pickle: %s -> %s", pkl_path, json_path)
    return json_path


def migrate_file(pkl_path: Path, *, dry_run: bool = False) -> Optional[Path]:
    """Migrate a single legacy pickle file to JSON.

    Returns the output JSON path on success, or ``None`` on failure / dry-run.
    """
    if not pkl_path.is_file():
        logger.warning("Not a file, skipping: %s", pkl_path)
        return None

    if pkl_path.suffix.lower() not in LEGACY_EXTENSIONS:
        logger.warning("Not a legacy pickle file, skipping: %s", pkl_path)
        return None

    if dry_run:
        logger.info("[DRY-RUN] Would convert: %s", pkl_path)
        return None

    try:
        # Peek at the pickle to decide strategy
        raw = pkl_path.read_bytes()
        if len(raw) > MAX_PICKLE_BYTES:
            logger.error("File too large (%d bytes > %d max), skipping: %s",
                         len(raw), MAX_PICKLE_BYTES, pkl_path)
            return None

        data = _restricted_loads(raw)

        # Heuristic: if it has "documents" and "embeddings" keys, treat as
        # VectorMemory index.
        if isinstance(data, dict) and "documents" in data:
            return _convert_vector_index(pkl_path)
        else:
            return _convert_generic_pickle(pkl_path)

    except pickle.UnpicklingError as exc:
        logger.error("Restricted unpickle failed for %s: %s", pkl_path, exc)
        return None
    except Exception as exc:
        logger.error("Migration failed for %s: %s", pkl_path, exc)
        return None


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _default_scan_dirs() -> List[Path]:
    """Return the default directories to scan for legacy artifacts."""
    repo_root = Path(__file__).resolve().parents[1]
    dirs = [
        repo_root / "core" / "models",
    ]
    import os
    mem_dir = os.getenv("VERITAS_MEMORY_DIR", "").strip()
    if mem_dir:
        dirs.append(Path(mem_dir))
    return dirs


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Migrate legacy pickle/joblib artifacts to safe JSON format.",
    )
    parser.add_argument(
        "--scan-dir",
        action="append",
        type=Path,
        default=None,
        help="Directory to scan (can be repeated). Defaults to MemoryOS model dirs.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only list files that would be converted; do not write anything.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    scan_dirs = args.scan_dir or _default_scan_dirs()
    legacy_files = scan_legacy_files(scan_dirs)

    if not legacy_files:
        logger.info("No legacy pickle/joblib files found in %s", scan_dirs)
        return 0

    logger.info("Found %d legacy file(s) to migrate:", len(legacy_files))
    for f in legacy_files:
        logger.info("  %s", f)

    converted = 0
    failed = 0
    for pkl_path in legacy_files:
        result = migrate_file(pkl_path, dry_run=args.dry_run)
        if args.dry_run:
            continue
        if result is not None:
            converted += 1
        else:
            failed += 1

    if args.dry_run:
        logger.info("[DRY-RUN] %d file(s) would be converted.", len(legacy_files))
    else:
        logger.info("Migration complete: %d converted, %d failed.", converted, failed)
        if converted > 0:
            logger.info(
                "Remove the original .pkl/.joblib files after verifying the JSON output."
            )

    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
