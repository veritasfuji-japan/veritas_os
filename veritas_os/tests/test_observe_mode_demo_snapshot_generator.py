"""Tests for dev-only Observe Mode demo snapshot generator script."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


GENERATOR_CLI_PATH = Path("scripts/generate_observe_mode_demo_snapshot.py")
CHECKER_CLI_PATH = Path("scripts/check_governance_observation.py")


def _run_generator(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GENERATOR_CLI_PATH), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _run_checker(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER_CLI_PATH), str(path)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_stdout_generation_returns_valid_json() -> None:
    result = _run_generator()

    assert result.returncode == 0
    payload = json.loads(result.stdout)

    assert payload["sample_kind"] == "dev_only_observe_mode_demo"
    observation = payload["governance_layer_snapshot"]["governance_observation"]
    assert observation["policy_mode"] == "observe"
    assert observation["environment"] == "development"
    assert observation["would_have_blocked"] is True
    assert observation["effective_outcome"] == "proceed"
    assert observation["observed_outcome"] == "block"


def test_generated_stdout_passes_cli_checker(tmp_path: Path) -> None:
    generated_file = tmp_path / "generated_snapshot.json"

    generate_result = _run_generator()
    assert generate_result.returncode == 0
    generated_file.write_text(generate_result.stdout, encoding="utf-8")

    check_result = _run_checker(generated_file)
    output = check_result.stdout + check_result.stderr

    assert check_result.returncode == 0
    assert "valid" in output
    assert "issues: 0" in output


def test_out_writes_file_and_passes_cli_checker(tmp_path: Path) -> None:
    output_file = tmp_path / "observe_snapshot.json"

    result = _run_generator("--out", str(output_file))

    assert result.returncode == 0
    assert output_file.exists()

    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert payload["sample_kind"] == "dev_only_observe_mode_demo"

    check_result = _run_checker(output_file)
    output = check_result.stdout + check_result.stderr

    assert check_result.returncode == 0
    assert "valid" in output
    assert "issues: 0" in output
