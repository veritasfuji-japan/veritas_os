"""Tests for optional local hash verification in reviewer demo validator."""

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
SCRIPT_PATH = Path(
    "scripts/demo/validate_evaluation_governance_reviewer_demo.py"
)
SHA256_SHAPED_BUT_INVALID = "f" * 64


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


def test_validate_reviewer_demo_with_local_hashes_succeeds(
    tmp_path: Path,
) -> None:
    demo_dir = _generate_demo(tmp_path)

    result = validator.validate_reviewer_demo(
        demo_dir,
        verify_local_hashes=True,
        artifact_base_dir=EXAMPLE_INPUT_DIR,
    )

    assert result.local_hash_checks_total > 0
    assert result.local_hash_checks_passed > 0
    assert result.local_hash_failures == ()


def test_validator_cli_reports_local_hash_success(tmp_path: Path) -> None:
    demo_dir = _generate_demo(tmp_path)

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--demo-dir",
            str(demo_dir),
            "--artifact-base-dir",
            str(EXAMPLE_INPUT_DIR),
            "--verify-local-hashes",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "PASS local hash consistency" in completed.stdout


def test_validator_local_hash_mismatch_fails_clearly(tmp_path: Path) -> None:
    demo_dir = _generate_demo(tmp_path)
    summary_path = demo_dir / "demo-summary.generated.example.json"
    summary = _load_json(summary_path)
    summary["generated_artifacts"][0]["artifact_hash"] = SHA256_SHAPED_BUT_INVALID
    _write_json(summary_path, summary)

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--demo-dir",
            str(demo_dir),
            "--artifact-base-dir",
            str(EXAMPLE_INPUT_DIR),
            "--verify-local-hashes",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "hash mismatch" in completed.stderr
    assert "expected hash" in completed.stderr
    assert "actual hash" in completed.stderr
    assert "demo-summary.generated.example.json" in completed.stderr


def test_reviewer_packet_external_ref_is_skipped_not_dereferenced(
    tmp_path: Path,
) -> None:
    demo_dir = _generate_demo(tmp_path)
    packet_path = demo_dir / "reviewer-evidence-packet.generated.example.json"
    packet = _load_json(packet_path)
    packet["evaluation_governance_artifacts"][0]["artifact_ref"] = (
        "https://example.invalid/nonlocal-artifact.json"
    )
    packet["evaluation_governance_artifacts"][0]["artifact_hash"] = "0" * 64
    _write_json(packet_path, packet)

    summary_path = demo_dir / "demo-summary.generated.example.json"
    summary = _load_json(summary_path)
    for artifact in summary["generated_artifacts"]:
        if artifact["artifact_ref"] == "reviewer-evidence-packet.generated.example.json":
            artifact["artifact_hash"] = runner.canonical_json_hash(packet)
    _write_json(summary_path, summary)

    result = validator.validate_reviewer_demo(
        demo_dir,
        verify_local_hashes=True,
        artifact_base_dir=EXAMPLE_INPUT_DIR,
    )

    assert result.local_hash_checks_skipped >= 1
    assert result.local_hash_failures == ()


def test_demo_summary_missing_local_artifact_fails(tmp_path: Path) -> None:
    demo_dir = _generate_demo(tmp_path)
    summary_path = demo_dir / "demo-summary.generated.example.json"
    summary = _load_json(summary_path)
    summary["generated_artifacts"][0]["artifact_ref"] = "missing-local.json"
    summary["generated_artifacts"][0]["artifact_hash"] = "0" * 64
    _write_json(summary_path, summary)

    with pytest.raises(validator.ReviewerDemoValidationError) as exc_info:
        validator.validate_reviewer_demo(
            demo_dir,
            verify_local_hashes=True,
            artifact_base_dir=EXAMPLE_INPUT_DIR,
        )

    assert exc_info.value.check == "local hash consistency"
    assert "missing local artifact" in exc_info.value.message
