"""Tests for local Reviewer Evidence Bundle generation."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from scripts.demo.build_reviewer_evidence_bundle import (
    BUNDLE_ID,
    BUNDLE_VERSION,
    REQUIRED_FILENAMES,
    build_reviewer_evidence_bundle,
)

REQUIRED_OUTPUT_FILES = set(REQUIRED_FILENAMES)


def _summary_by_path(summary: dict[str, object]) -> dict[str, dict[str, object]]:
    """Return generated file summaries keyed by relative path."""
    generated_files = summary["generated_files"]
    assert isinstance(generated_files, list)
    return {
        file_entry["path"]: file_entry
        for file_entry in generated_files
        if isinstance(file_entry, dict)
    }


def test_build_reviewer_evidence_bundle_returns_pass_summary(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "reviewer-evidence-packet"

    summary = build_reviewer_evidence_bundle(output_dir=output_dir)

    assert isinstance(summary, dict)
    assert summary["bundle_id"] == BUNDLE_ID
    assert summary["bundle_id"] == "reviewer-evidence-bundle-v1"
    assert summary["bundle_version"] == BUNDLE_VERSION
    assert summary["bundle_version"] == "v1"
    assert summary["local_offline_only"] is True
    assert summary["status"] == "pass"
    assert output_dir.is_dir()
    assert summary["validation_status"] == "pass"
    assert summary["artifact_manifest_verification_status"] == "pass"
    assert summary["step_summary_written"] is True
    assert summary["failure_reasons"] == []


def test_build_reviewer_evidence_bundle_writes_required_files(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "reviewer-evidence-packet"

    summary = build_reviewer_evidence_bundle(output_dir=output_dir)
    generated_by_path = _summary_by_path(summary)

    assert set(generated_by_path) == REQUIRED_OUTPUT_FILES
    for filename in REQUIRED_OUTPUT_FILES:
        assert (output_dir / filename).is_file()
        assert generated_by_path[filename]["exists"] is True
        assert generated_by_path[filename]["required"] is True
        assert generated_by_path[filename]["size_bytes"] > 0


def test_generated_files_use_relative_paths(tmp_path: Path) -> None:
    output_dir = tmp_path / "reviewer-evidence-packet"

    summary = build_reviewer_evidence_bundle(output_dir=output_dir)

    for file_entry in summary["generated_files"]:
        path = Path(file_entry["path"])
        assert not path.is_absolute()
        assert ".." not in path.parts


def test_repeated_bundle_builds_are_deterministic_for_stable_summary_fields(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "reviewer-evidence-packet"

    first_summary = build_reviewer_evidence_bundle(output_dir=output_dir)
    second_summary = build_reviewer_evidence_bundle(output_dir=output_dir)

    assert first_summary == second_summary


def test_cli_exits_zero_and_prints_json_summary(tmp_path: Path) -> None:
    output_dir = tmp_path / "cli-bundle"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/demo/build_reviewer_evidence_bundle.py",
            "--output-dir",
            str(output_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    summary = json.loads(result.stdout)
    assert summary["status"] == "pass"
    assert summary["output_dir"] == str(output_dir)
    assert (output_dir / "reviewer-evidence-step-summary.md").is_file()


def test_custom_output_dir_works(tmp_path: Path) -> None:
    output_dir = tmp_path / "custom" / "bundle"

    summary = build_reviewer_evidence_bundle(output_dir=output_dir)

    assert summary["status"] == "pass"
    assert output_dir.is_dir()
    assert (output_dir / "external-reviewer-quickstart.md").is_file()
    assert (output_dir / "external-reviewer-artifact-index.md").is_file()


def test_no_network_or_environment_dependency_required(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "offline-bundle"
    for env_name in [
        "OPENAI_API_KEY",
        "VERITAS_API_KEY",
        "VERITAS_API_SECRET",
        "VERITAS_ENCRYPTION_KEY",
    ]:
        monkeypatch.delenv(env_name, raising=False)

    summary = build_reviewer_evidence_bundle(output_dir=output_dir)

    assert os.environ.get("OPENAI_API_KEY") is None
    assert summary["status"] == "pass"
    assert summary["local_offline_only"] is True


def test_invalid_output_dir_returns_fail(tmp_path: Path) -> None:
    output_file = tmp_path / "not-a-directory"
    output_file.write_text("not a directory\n", encoding="utf-8")

    summary = build_reviewer_evidence_bundle(output_dir=output_file)

    assert summary["status"] == "fail"
    assert "reviewer_evidence_bundle_output_dir_invalid" in summary["failure_reasons"]


def test_cli_invalid_output_dir_exits_nonzero(tmp_path: Path) -> None:
    output_file = tmp_path / "not-a-directory"
    output_file.write_text("not a directory\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/demo/build_reviewer_evidence_bundle.py",
            "--output-dir",
            str(output_file),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    summary = json.loads(result.stdout)
    assert summary["status"] == "fail"
