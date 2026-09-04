#!/usr/bin/env python3
"""Select a deterministic, duration-balanced pytest file shard."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence


DEFAULT_ROOTS = (Path("veritas_os/tests"), Path("tests"))
DEFAULT_DURATIONS = Path("scripts/ci/pytest-file-durations.json")
MINIMUM_ESTIMATED_SECONDS = 0.1
BYTES_PER_ESTIMATED_SECOND = 100_000


def discover_test_files(roots: Iterable[Path]) -> list[Path]:
    """Return every pytest-discoverable Python test file exactly once."""
    discovered: set[Path] = set()
    for root in roots:
        if not root.is_dir():
            raise ValueError(f"test root does not exist: {root}")
        for path in root.rglob("*.py"):
            if path.match("test_*.py") or path.match("*_test.py"):
                discovered.add(path)
    return sorted(discovered, key=lambda path: path.as_posix())


def load_historical_durations(path: Path) -> dict[str, float]:
    """Load optional per-file durations used only to balance the shards."""
    if not path.is_file():
        raise ValueError(f"duration seed does not exist: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    durations = raw.get("durations_seconds")
    if not isinstance(durations, dict):
        raise ValueError("duration seed must contain a durations_seconds object")

    validated: dict[str, float] = {}
    for file_name, duration in durations.items():
        if not isinstance(file_name, str) or not isinstance(duration, (int, float)):
            raise ValueError("duration entries must map file paths to seconds")
        if duration <= 0:
            raise ValueError(f"duration must be positive: {file_name}")
        validated[file_name] = float(duration)
    return validated


def estimated_duration(path: Path, historical: Mapping[str, float]) -> float:
    """Estimate duration, falling back to a conservative source-size proxy."""
    recorded = historical.get(path.as_posix())
    if recorded is not None:
        return recorded
    return max(
        MINIMUM_ESTIMATED_SECONDS,
        path.stat().st_size / BYTES_PER_ESTIMATED_SECOND,
    )


def partition_test_files(
    files: Sequence[Path],
    *,
    shard_count: int,
    historical: Mapping[str, float],
) -> list[list[Path]]:
    """Greedily balance files using deterministic longest-processing-time order."""
    if shard_count < 1:
        raise ValueError("shard_count must be at least 1")
    if not files:
        raise ValueError("no test files were discovered")

    shards: list[list[Path]] = [[] for _ in range(shard_count)]
    loads = [0.0] * shard_count
    ordered = sorted(
        files,
        key=lambda path: (
            -estimated_duration(path, historical),
            path.as_posix(),
        ),
    )

    for path in ordered:
        shard_index = min(
            range(shard_count),
            key=lambda index: (loads[index], index),
        )
        shards[shard_index].append(path)
        loads[shard_index] += estimated_duration(path, historical)

    for shard in shards:
        shard.sort(key=lambda path: path.as_posix())
    return shards


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shard-index", type=int, required=True, help="1-based shard")
    parser.add_argument("--shard-count", type=int, required=True)
    parser.add_argument(
        "--durations",
        type=Path,
        default=DEFAULT_DURATIONS,
        help="historical per-file duration seed",
    )
    parser.add_argument(
        "roots",
        nargs="*",
        type=Path,
        default=list(DEFAULT_ROOTS),
        help="pytest discovery roots",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not 1 <= args.shard_index <= args.shard_count:
        raise SystemExit("shard-index must be between 1 and shard-count")

    try:
        files = discover_test_files(args.roots)
        durations = load_historical_durations(args.durations)
        shards = partition_test_files(
            files,
            shard_count=args.shard_count,
            historical=durations,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(str(exc)) from exc

    selected = shards[args.shard_index - 1]
    if not selected:
        raise SystemExit(f"shard {args.shard_index} selected no test files")

    for path in selected:
        print(path.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
