"""Tests for deterministic local performance metrics harness."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = Path("scripts/benchmarks/run_performance_metrics.py")


def _run_harness(tmp_path: Path, iterations: int) -> dict:
    output = tmp_path / "metrics.json"
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--iterations",
            str(iterations),
            "--output",
            str(output),
        ],
        check=True,
    )
    return json.loads(output.read_text(encoding="utf-8"))


def test_script_exists() -> None:
    assert SCRIPT_PATH.exists()


def test_cli_generates_json(tmp_path: Path) -> None:
    data = _run_harness(tmp_path, iterations=5)
    assert data["schema_version"] == "performance_metrics.v1"
    assert data["metrics"]["mean_ms"] >= 0
    assert data["metrics"]["median_ms"] >= 0
    assert data["metrics"]["p95_ms"] >= 0
    assert data["metrics"]["p99_ms"] >= 0
    assert data["counters"]["success"] == 5
    assert data["counters"]["failure"] == 0
    notes_blob = "\n".join(data["notes"])
    assert "Not a production SLA" in notes_blob


def test_iterations_one_succeeds(tmp_path: Path) -> None:
    data = _run_harness(tmp_path, iterations=1)
    assert data["iterations"] == 1
    assert data["counters"]["success"] == 1
    assert data["counters"]["failure"] == 0


def test_output_has_no_fake_production_claims(tmp_path: Path) -> None:
    data = _run_harness(tmp_path, iterations=3)
    rendered = json.dumps(data, ensure_ascii=False).lower()
    forbidden = ["measured customer", "guaranteed", "certified production"]
    for token in forbidden:
        assert token not in rendered
