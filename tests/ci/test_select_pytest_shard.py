"""Regression tests for deterministic CI pytest sharding."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ci.select_pytest_shard import (
    discover_test_files,
    partition_test_files,
)


def test_partition_is_complete_disjoint_and_deterministic(tmp_path: Path) -> None:
    files = []
    historical = {}
    for index, duration in enumerate((50.0, 30.0, 20.0, 10.0, 5.0), start=1):
        path = tmp_path / f"test_{index}.py"
        path.write_text(f"def test_{index}():\n    pass\n", encoding="utf-8")
        files.append(path)
        historical[path.as_posix()] = duration

    first = partition_test_files(files, shard_count=3, historical=historical)
    second = partition_test_files(files, shard_count=3, historical=historical)

    flattened = [path for shard in first for path in shard]
    assert first == second
    assert len(flattened) == len(set(flattened)) == len(files)
    assert set(flattened) == set(files)
    assert all(first)


def test_discovery_matches_pytest_file_patterns(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    expected = {
        tmp_path / "test_alpha.py",
        nested / "beta_test.py",
    }
    for path in expected:
        path.write_text("def test_ok():\n    pass\n", encoding="utf-8")
    (tmp_path / "helper.py").write_text("", encoding="utf-8")

    assert set(discover_test_files([tmp_path])) == expected


def test_partition_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="shard_count"):
        partition_test_files([Path("test_example.py")], shard_count=0, historical={})
    with pytest.raises(ValueError, match="no test files"):
        partition_test_files([], shard_count=1, historical={})
