"""Tests for the Evaluation Governance reviewer demo validator."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from scripts.demo import run_evaluation_governance_reviewer_demo as runner
from scripts.demo import (
    validate_evaluation_governance_reviewer_demo as validator,
)

EXAMPLE_INPUT_DIR = Path(
    "docs/en/demo/examples/evaluation-governance-offline-chain-v1"
)
CHECKED_IN_GENERATED_DIR = Path(
    "docs/en/demo/examples/evaluation-governance-reviewer-demo-v1/generated"
)
SCRIPT_PATH = Path(
    "scripts/demo/validate_evaluation_governance_reviewer_demo.py"
)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        f"{json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)}\n",
        encoding="utf-8",
    )


def _generate_demo(tmp_path: Path) -> Path:
    runner.run_reviewer_demo(EXAMPLE_INPUT_DIR, tmp_path)
    return tmp_path


def test_validator_imports_cleanly() -> None:
    assert callable(validator.load_json)
    assert callable(validator.validate_schema_if_available)
    assert callable(validator.validate_sha256_shape)
    assert callable(validator.validate_expected_files)
    assert callable(validator.validate_chain_manifest)
    assert callable(validator.validate_demo_summary)
    assert callable(validator.validate_reviewer_packet_attachments)
    assert callable(validator.validate_reviewer_demo)
    assert callable(validator.main)


def test_validate_reviewer_demo_generated_output(tmp_path: Path) -> None:
    demo_dir = _generate_demo(tmp_path)

    result = validator.validate_reviewer_demo(demo_dir)

    assert result.expected_files_count == len(validator.EXPECTED_FILE_NAMES)
    assert result.schema_validated_count == len(
        validator.SCHEMA_FILE_NAMES_BY_ARTIFACT
    )
    assert result.reviewer_attachment_count >= len(
        validator.EXPECTED_ATTACHMENT_TYPES
    )


def test_validate_reviewer_demo_checked_in_generated_examples() -> None:
    result = validator.validate_reviewer_demo(CHECKED_IN_GENERATED_DIR)

    assert result.expected_files_count == len(validator.EXPECTED_FILE_NAMES)
    assert result.reviewer_attachment_count >= len(
        validator.EXPECTED_ATTACHMENT_TYPES
    )


def test_validator_cli_reports_success(tmp_path: Path) -> None:
    demo_dir = _generate_demo(tmp_path)

    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--demo-dir", str(demo_dir)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "PASS expected files present" in completed.stdout
    assert "PASS reviewer evidence packet attachments" in completed.stdout
    assert "Validated reviewer demo output:" in completed.stdout


def test_validator_fails_with_clear_error_for_missing_file(tmp_path: Path) -> None:
    demo_dir = _generate_demo(tmp_path)
    missing_path = demo_dir / "demo-summary.generated.example.json"
    missing_path.unlink()

    with pytest.raises(validator.ReviewerDemoValidationError) as exc_info:
        validator.validate_reviewer_demo(demo_dir)

    assert exc_info.value.check == "expected files present"
    assert "demo-summary.generated.example.json" in exc_info.value.message


def test_validator_fails_for_invalid_chain_manifest_sha(tmp_path: Path) -> None:
    demo_dir = _generate_demo(tmp_path)
    manifest_path = demo_dir / "chain-manifest.generated.example.json"
    manifest = _load_json(manifest_path)
    manifest["artifacts"][0]["artifact_hash"] = "not-a-sha256"
    _write_json(manifest_path, manifest)

    with pytest.raises(validator.ReviewerDemoValidationError) as exc_info:
        validator.validate_reviewer_demo(demo_dir)

    assert exc_info.value.check == "sha256 shape"
    assert "artifact_hash" in exc_info.value.message


def test_validator_cli_fails_for_invalid_reviewer_packet_sha(
    tmp_path: Path,
) -> None:
    demo_dir = _generate_demo(tmp_path)
    packet_path = demo_dir / "reviewer-evidence-packet.generated.example.json"
    packet = _load_json(packet_path)
    packet["evaluation_governance_artifacts"][0]["artifact_hash"] = "bad"
    _write_json(packet_path, packet)

    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--demo-dir", str(demo_dir)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "FAIL" in completed.stderr
    assert "artifact_hash" in completed.stderr
