"""Partition pytest's full slow-marked collection without omitting test IDs.

Load using: pytest -p scripts.ci.slow_pytest_shard -m slow
Each shard records the full selected universe, its assigned test IDs and the
test IDs that produced pytest reports, for independent post-run verification.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from scripts.ci.select_pytest_shard import load_historical_durations, partition_test_files

DEFAULT_SEED = Path("scripts/ci/pytest-slow-file-durations-py312.json")
_active_config: pytest.Config | None = None


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("slow-ci-sharding")
    group.addoption("--slow-shard-index", type=int, default=None)
    group.addoption("--slow-shard-count", type=int, default=None)
    group.addoption("--slow-shard-durations", type=Path, default=DEFAULT_SEED)


def pytest_configure(config: pytest.Config) -> None:
    global _active_config
    _active_config = config


def pytest_unconfigure(config: pytest.Config) -> None:
    global _active_config
    if _active_config is config:
        _active_config = None


def _relative_path(item: pytest.Item) -> Path:
    try:
        return Path(item.path).resolve().relative_to(Path.cwd().resolve())
    except ValueError as exc:
        raise pytest.UsageError(f"slow test outside checkout: {item.nodeid}") from exc


def pytest_collection_finish(session: pytest.Session) -> None:
    config = session.config
    index = config.getoption("slow_shard_index")
    count = config.getoption("slow_shard_count")
    if index is None and count is None:
        return
    if count is None or index is None or count < 1 or not 1 <= index <= count:
        raise pytest.UsageError("invalid slow shard index/count")
    if config.getoption("markexpr").strip() != "slow":
        raise pytest.UsageError("slow sharding requires exactly '-m slow'")

    items = list(session.items)  # after pytest's own -m slow deselection
    nodeids = [item.nodeid for item in items]
    if not items or len(set(nodeids)) != len(nodeids):
        raise pytest.UsageError("empty or duplicate slow test collection")
    try:
        files = sorted({_relative_path(item) for item in items})
        seed = load_historical_durations(config.getoption("slow_shard_durations"))
        shards = partition_test_files(files, shard_count=count, historical=seed)
    except (OSError, ValueError) as exc:
        raise pytest.UsageError(f"slow shard selection failed: {exc}") from exc

    assigned = set(shards[index - 1])
    kept = [item for item in items if _relative_path(item) in assigned]
    deselected = [item for item in items if _relative_path(item) not in assigned]
    if not kept:
        raise pytest.UsageError(f"slow shard {index} selected zero tests")

    report_dir = Path("test-reports")
    report_dir.mkdir(parents=True, exist_ok=True)
    report = report_dir / "slow-shard-manifest.json"
    manifest = {
        "schema_version": 1,
        "shard_index": index,
        "shard_count": count,
        "full_nodeids": sorted(nodeids),
        "selected_nodeids": sorted(item.nodeid for item in kept),
        "selected_files": sorted(path.as_posix() for path in assigned),
    }
    report.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    config._slow_shard_manifest = report  # type: ignore[attr-defined]
    config._slow_shard_seen = Counter()  # type: ignore[attr-defined]
    session.items[:] = kept
    config.hook.pytest_deselected(items=deselected)


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if _active_config is not None and hasattr(_active_config, "_slow_shard_seen"):
        _active_config._slow_shard_seen[report.nodeid] += 1  # type: ignore[attr-defined]


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    report = getattr(session.config, "_slow_shard_manifest", None)
    if report is None:
        return
    manifest = json.loads(report.read_text(encoding="utf-8"))
    manifest["reported_nodeids"] = sorted(session.config._slow_shard_seen)  # type: ignore[attr-defined]
    report.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
