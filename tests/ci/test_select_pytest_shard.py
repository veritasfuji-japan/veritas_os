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


def test_py312_junit_seed_is_valid_and_balances_measured_heavy_files() -> None:
    """Keep the pinned, independently reviewable Py3.12 seed deterministic."""
    from math import isfinite

    from scripts.ci.select_pytest_shard import load_historical_durations

    path = Path("scripts/ci/pytest-file-durations-py312.json")
    durations = load_historical_durations(path)

    assert len(durations) >= 80
    assert all(isfinite(duration) and duration >= 1.0 for duration in durations.values())
    assert all(Path(name).is_file() for name in durations)

    files = [Path(name) for name in durations]
    shards = partition_test_files(
        files,
        shard_count=8,
        historical=durations,
        avoid_duplicate_test_basenames=True,
    )
    flattened = [file for shard in shards for file in shard]
    assert all(shards)
    assert len(flattened) == len(set(flattened)) == len(files)
    assert set(flattened) == set(files)

    predicted_loads = [
        sum(durations[file.as_posix()] for file in shard) for shard in shards
    ]
    # The heaviest indivisible test file is ~1115s; tolerate up to 1200s
    # for the current, pinned measured seed. This is NOT a runtime claim.
    assert max(predicted_loads) <= 1200.0


def test_opt_in_separates_same_named_test_modules_deterministically(tmp_path: Path) -> None:
    """Avoid pytest's import file mismatch without changing test coverage."""
    demo = tmp_path / "demo"
    governance = tmp_path / "governance"
    demo.mkdir()
    governance.mkdir()
    a = demo / "test_human_approval_alternatives_evidence.py"
    b = governance / "test_human_approval_alternatives_evidence.py"
    heavy = tmp_path / "test_heavy.py"
    medium = tmp_path / "test_medium.py"
    files = [a, b, heavy, medium]
    for file in files:
        file.write_text("def test_ok(): pass\\n", encoding="utf-8")
    historical = {
        a.as_posix(): 1.0,
        b.as_posix(): 1.0,
        heavy.as_posix(): 100.0,
        medium.as_posix(): 90.0,
    }

    baseline = partition_test_files(files, shard_count=2, historical=historical)
    assert any(a in shard and b in shard for shard in baseline)

    safe = partition_test_files(
        files, shard_count=2, historical=historical,
        avoid_duplicate_test_basenames=True,
    )
    assert safe == partition_test_files(
        files, shard_count=2, historical=historical,
        avoid_duplicate_test_basenames=True,
    )
    assert set().union(*(set(shard) for shard in safe)) == set(files)
    assert all(len({path.name for path in shard}) == len(shard) for shard in safe)
    assert all(safe)


def test_opt_in_fails_closed_when_duplicate_count_exceeds_shards(tmp_path: Path) -> None:
    files = []
    for index in range(3):
        directory = tmp_path / f"root_{index}"
        directory.mkdir()
        file = directory / "test_same_name.py"
        file.write_text("def test_ok(): pass\\n", encoding="utf-8")
        files.append(file)

    with pytest.raises(ValueError, match="duplicate test filename"):
        partition_test_files(
            files, shard_count=2,
            historical={file.as_posix(): 1.0 for file in files},
            avoid_duplicate_test_basenames=True,
        )


def test_real_human_approval_module_collision_is_separated() -> None:
    modules = [
        Path("tests/demo/test_human_approval_alternatives_evidence.py"),
        Path("tests/governance/test_human_approval_alternatives_evidence.py"),
    ]
    assert all(file.is_file() for file in modules)
    shards = partition_test_files(
        modules, shard_count=2, historical={},
        avoid_duplicate_test_basenames=True,
    )
    assert all(len(shard) == 1 for shard in shards)


def test_current_py312_corpus_is_complete_and_import_collision_free() -> None:
    """Exercise the actual multi-root corpus, not only synthetic fixtures."""
    from scripts.ci.select_pytest_shard import DEFAULT_ROOTS, load_historical_durations

    files = discover_test_files(DEFAULT_ROOTS)
    durations = load_historical_durations(
        Path("scripts/ci/pytest-file-durations-py312.json")
    )
    shards = partition_test_files(
        files,
        shard_count=8,
        historical=durations,
        avoid_duplicate_test_basenames=True,
    )
    flattened = [file for shard in shards for file in shard]
    assert len(flattened) == len(set(flattened)) == len(files)
    assert set(flattened) == set(files)
    assert all(shards)
    assert all(len({file.name for file in shard}) == len(shard) for shard in shards)
