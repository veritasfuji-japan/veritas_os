#!/usr/bin/env python3
"""Reset non-committed runtime artifacts for a fresh-clone repository state.

Usage:
    python scripts/reset_repo_runtime.py --dry-run
    python scripts/reset_repo_runtime.py --apply
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]

RUNTIME_NAMESPACE_DIRS = (
    "runtime/dev/logs",
    "runtime/dev/state",
    "runtime/dev/datasets",
    "runtime/test/logs",
    "runtime/test/state",
    "runtime/test/datasets",
    "runtime/demo/logs",
    "runtime/demo/state",
    "runtime/demo/datasets",
    "runtime/prod/logs",
    "runtime/prod/state",
    "runtime/prod/datasets",
)

LEGACY_TARGETS = (
    "logs",
    "scripts/logs",
    "datasets/generated",
    "data/runtime",
    "storage",
    "cache",
)

LEGACY_FILE_GLOBS = (
    "trust_log.json",
    "trust_log.jsonl",
    "world_state*.json",
    "value_stats.json",
    "value_core.json",
    "memory.json",
    "persona.json",
    "*.tmp",
)


def _iter_removals() -> Iterable[Path]:
    """Yield runtime artifact paths that should be removed."""
    for rel in RUNTIME_NAMESPACE_DIRS:
        base = REPO_ROOT / rel
        if not base.exists():
            continue
        for child in base.iterdir():
            if child.name == ".gitkeep":
                continue
            yield child

    for rel in LEGACY_TARGETS:
        path = REPO_ROOT / rel
        if path.exists():
            yield path

    for pattern in LEGACY_FILE_GLOBS:
        for path in REPO_ROOT.glob(pattern):
            if path.name == ".gitkeep":
                continue
            yield path


def _remove_path(path: Path) -> None:
    """Remove a file or directory recursively."""
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def _ensure_runtime_layout() -> None:
    """Ensure runtime namespace directories and .gitkeep files exist."""
    for rel in RUNTIME_NAMESPACE_DIRS:
        directory = REPO_ROOT / rel
        directory.mkdir(parents=True, exist_ok=True)
        gitkeep = directory / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.write_text("", encoding="utf-8")


def main() -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Print deletions only")
    mode.add_argument("--apply", action="store_true", help="Apply deletions")
    args = parser.parse_args()

    removals = sorted(set(_iter_removals()))
    print(f"[reset-repo-runtime] repo={REPO_ROOT}")
    if not removals:
        print("[reset-repo-runtime] no runtime artifacts found")
    for path in removals:
        print(f"[reset-repo-runtime] remove: {path.relative_to(REPO_ROOT)}")

    if args.apply:
        for path in removals:
            _remove_path(path)
        _ensure_runtime_layout()
        print("[reset-repo-runtime] applied")
    else:
        print("[reset-repo-runtime] dry-run only")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
