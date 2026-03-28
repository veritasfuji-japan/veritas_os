#!/usr/bin/env python3
"""Reset repository runtime artifacts to a fresh-clone state.

This script removes local runtime outputs (logs, caches, generated datasets,
runtime state) while preserving directory placeholders such as ``.gitkeep``.

Examples:
    python scripts/reset_repo_runtime.py --dry-run
    python scripts/reset_repo_runtime.py --apply
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Iterable, List

REPO_ROOT = Path(__file__).resolve().parents[1]

RUNTIME_DIRS: tuple[str, ...] = (
    "runtime",
    "logs",
    "scripts/logs",
    "datasets/generated",
    "data/runtime",
    "storage",
    "cache",
)

RUNTIME_FILE_GLOBS: tuple[str, ...] = ("*.log", "*.tmp", "*.jsonl", "*.sqlite", "*.db")

RUNTIME_FILE_SEARCH_DIRS: tuple[str, ...] = (
    "runtime",
    "logs",
    "scripts/logs",
    "data/runtime",
    "datasets/generated",
    "storage",
    "cache",
)

SKIP_DIRS: tuple[str, ...] = (
    ".git",
    "node_modules",
    ".venv",
    "venv",
)


def _iter_deletion_targets() -> List[Path]:
    """Collect candidate runtime paths that should be cleaned."""
    targets: List[Path] = []

    for rel in RUNTIME_DIRS:
        root = REPO_ROOT / rel
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_dir() or path.name == ".gitkeep":
                continue
            targets.append(path)

    for rel_dir in RUNTIME_FILE_SEARCH_DIRS:
        search_root = REPO_ROOT / rel_dir
        if not search_root.exists():
            continue
        for pattern in RUNTIME_FILE_GLOBS:
            for path in search_root.rglob(pattern):
                if not path.is_file():
                    continue
                if any(skip in path.parts for skip in SKIP_DIRS):
                    continue
                if path.name == ".gitkeep":
                    continue
                targets.append(path)

    unique = sorted({p.resolve() for p in targets if p.exists()})
    return unique


def _delete_paths(paths: Iterable[Path], *, apply: bool) -> None:
    """Delete or report paths depending on apply mode."""
    path_list = list(paths)
    mode_label = "DELETE" if apply else "DRY-RUN"
    removed = 0
    for path in path_list:
        rel = path.relative_to(REPO_ROOT)
        print(f"[{mode_label}] {rel}")
        if not apply:
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)
        removed += 1

    print(f"\nTotal targets: {len(path_list)}")
    if apply:
        print(f"Removed: {removed}")


def _ensure_gitkeep() -> None:
    """Ensure runtime namespaces exist with .gitkeep placeholders."""
    for namespace in ("dev", "test", "demo", "prod"):
        directory = REPO_ROOT / "runtime" / namespace
        directory.mkdir(parents=True, exist_ok=True)
        gitkeep = directory / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.write_text("", encoding="utf-8")


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Preview deletion targets.")
    mode.add_argument("--apply", action="store_true", help="Delete runtime artifacts.")
    args = parser.parse_args()

    targets = _iter_deletion_targets()
    _delete_paths(targets, apply=args.apply)

    if args.apply:
        _ensure_gitkeep()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
