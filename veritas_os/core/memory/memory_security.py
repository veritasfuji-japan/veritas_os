"""Security guard helpers for MemoryOS runtime artifact handling."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Iterable, Optional, Set

logger = logging.getLogger(__name__)

PICKLE_MIGRATION_GUIDE_PATH = "docs/operations/MEMORY_PICKLE_MIGRATION.md"


def is_explicitly_enabled(env_key: str) -> bool:
    """Return ``True`` when an env var is explicitly set to a truthy value."""
    value = os.getenv(env_key)
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}



def should_fail_fast_legacy_pickle_guard(profile: Optional[str] = None) -> bool:
    """Return whether legacy pickle detection should stop startup immediately."""
    resolved_profile = profile if profile is not None else os.getenv("VERITAS_ENV", "")
    normalized_profile = resolved_profile.strip().lower()
    return normalized_profile in {"prod", "production", "stg", "staging"}


def emit_legacy_pickle_runtime_blocked(path: Path, artifact_name: str) -> None:
    """Emit a runtime security warning for blocked legacy pickle artifacts."""
    logger.error(
        "[SECURITY] Legacy %s pickle detected at %s. "
        "Runtime pickle/joblib loading is permanently disabled (RCE risk). "
        "Migrate artifacts offline: python -m veritas_os.scripts.migrate_pickle  "
        "See %s for details.",
        artifact_name,
        path,
        PICKLE_MIGRATION_GUIDE_PATH,
    )


def warn_for_legacy_pickle_artifacts(scan_roots: Iterable[Path]) -> None:
    """Scan directories and report legacy pickle artifacts without deserializing.

    In operational profiles (``VERITAS_ENV`` = prod/production/stg/staging),
    detections are treated as fatal and raise ``RuntimeError`` to fail fast.
    """
    checked_roots: Set[Path] = set()
    findings: list[Path] = []

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
            findings.append(candidate)
            emit_legacy_pickle_runtime_blocked(
                path=candidate,
                artifact_name="runtime artifact",
            )

    if findings and should_fail_fast_legacy_pickle_guard():
        raise RuntimeError(
            "[SECURITY] Legacy runtime pickle artifacts detected in operational "
            "profile. Refusing startup due to RCE risk."
        )
