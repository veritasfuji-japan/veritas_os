"""Fail-closed synthetic checks for the full slow-shard aggregation gate."""

import json
from pathlib import Path

import pytest

from scripts.ci.validate_pytest_slow_shards import verify_shards


def _write_shards(root: Path, *, count: int = 4) -> None:
    full = [f"tests/test_sample_{index}.py::test_case" for index in range(1, count + 1)]
    for index in range(1, count + 1):
        directory = root / f"pytest-slow-py312-shard-{index}"
        directory.mkdir(parents=True)
        manifest = {
            "schema_version": 1,
            "shard_index": index,
            "shard_count": count,
            "full_nodeids": full,
            "selected_nodeids": [full[index - 1]],
            "reported_nodeids": [full[index - 1]],
            "selected_files": [f"tests/test_sample_{index}.py"],
        }
        (directory / "slow-shard-manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        xml = (
            '<testsuites><testsuite tests="1" failures="0" errors="0">'
            f'<testcase classname="tests.sample_{index}" '
            f'name="test_case" time="0.1"/></testsuite></testsuites>'
        )
        (directory / "pytest-slow.xml").write_text(xml, encoding="utf-8")


def _manifest(root: Path, index: int) -> tuple[Path, dict]:
    path = root / f"pytest-slow-py312-shard-{index}" / "slow-shard-manifest.json"
    return path, json.loads(path.read_text(encoding="utf-8"))


def test_accepts_complete_disjoint_slow_shard_evidence(tmp_path: Path) -> None:
    _write_shards(tmp_path)
    assert verify_shards(tmp_path, shard_count=4, min_cases=4) == (4, 0)


def test_rejects_missing_artifact(tmp_path: Path) -> None:
    _write_shards(tmp_path)
    import shutil
    shutil.rmtree(tmp_path / "pytest-slow-py312-shard-4")
    with pytest.raises(ValueError, match="incomplete"):
        verify_shards(tmp_path, shard_count=4, min_cases=4)


def test_rejects_duplicate_or_missing_node_id(tmp_path: Path) -> None:
    _write_shards(tmp_path)
    path, data = _manifest(tmp_path, 2)
    data["selected_nodeids"] = ["tests/test_sample_1.py::test_case"]
    data["reported_nodeids"] = data["selected_nodeids"]
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="missing or duplicated"):
        verify_shards(tmp_path, shard_count=4, min_cases=4)


def test_rejects_unstable_full_collection(tmp_path: Path) -> None:
    _write_shards(tmp_path)
    path, data = _manifest(tmp_path, 2)
    data["full_nodeids"] = data["full_nodeids"][:-1]
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="full slow collections differ"):
        verify_shards(tmp_path, shard_count=4, min_cases=4)


def test_rejects_unreported_test(tmp_path: Path) -> None:
    _write_shards(tmp_path)
    path, data = _manifest(tmp_path, 3)
    data["reported_nodeids"] = ["tests/unexpected.py::test_wrong"]
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="selected vs executed"):
        verify_shards(tmp_path, shard_count=4, min_cases=4)


def test_rejects_missing_junit_case(tmp_path: Path) -> None:
    _write_shards(tmp_path)
    path = tmp_path / "pytest-slow-py312-shard-3" / "pytest-slow.xml"
    path.write_text("<testsuites/>", encoding="utf-8")
    with pytest.raises(ValueError, match="no testcases"):
        verify_shards(tmp_path, shard_count=4, min_cases=4)


def test_rejects_silent_suite_shrink(tmp_path: Path) -> None:
    _write_shards(tmp_path)
    with pytest.raises(ValueError, match="fell below minimum"):
        verify_shards(tmp_path, shard_count=4, min_cases=948)
