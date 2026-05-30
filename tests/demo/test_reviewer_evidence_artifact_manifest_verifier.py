"""Tests for Reviewer Evidence Artifact Manifest verifier v1."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from scripts.demo.build_reviewer_evidence_artifact_manifest import (
    compute_reviewer_evidence_artifact_manifest_hash,
    write_reviewer_evidence_artifact_manifest,
)
from scripts.demo.verify_reviewer_evidence_artifact_manifest import (
    ARTIFACT_NAME,
    VERIFIER_ID,
    VERIFIER_VERSION,
    verify_reviewer_evidence_artifact_manifest,
)

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts/demo/verify_reviewer_evidence_artifact_manifest.py"
REQUIRED_RESULT_FIELDS = {
    "path",
    "role",
    "required",
    "exists",
    "expected_sha256",
    "actual_sha256",
    "sha256_matches",
    "expected_size_bytes",
    "actual_size_bytes",
    "size_matches",
    "status",
}


def _write_fixture_files(artifact_dir: Path) -> None:
    """Write deterministic fake reviewer evidence artifact files."""
    payloads = {
        "reviewer-evidence-packet-validation-report.json": {
            "generated_at": "2026-01-01T00:00:00Z",
            "status": "pass",
        },
        "reviewer-evidence-packet-generated.json": {"packet": "generated"},
        "reviewer-evidence-packet-golden-fixture.json": {"packet": "golden"},
        "reviewer-evidence-packet-schema.json": {"type": "object"},
        "external-reviewer-quickstart.md": "# Quickstart\n",
        "external-reviewer-artifact-index.md": "# Artifact Index\n",
    }
    artifact_dir.mkdir(parents=True, exist_ok=True)
    for relative_path, payload in payloads.items():
        path = artifact_dir / relative_path
        if isinstance(payload, str):
            path.write_text(payload, encoding="utf-8")
        else:
            path.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )


def _valid_artifact_dir(tmp_path: Path) -> Path:
    """Build a deterministic valid fake artifact directory."""
    artifact_dir = tmp_path / "artifact"
    _write_fixture_files(artifact_dir)
    write_reviewer_evidence_artifact_manifest(artifact_dir=artifact_dir)
    return artifact_dir


def _read_manifest(artifact_dir: Path) -> dict[str, Any]:
    """Read the fake artifact manifest."""
    return json.loads(
        (artifact_dir / "reviewer-evidence-artifact-manifest.json").read_text(
            encoding="utf-8"
        )
    )


def _write_manifest(artifact_dir: Path, manifest: dict[str, Any]) -> None:
    """Write a fake artifact manifest."""
    (artifact_dir / "reviewer-evidence-artifact-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _rewrite_manifest_with_hash(
    artifact_dir: Path,
    manifest: dict[str, Any],
) -> None:
    """Recompute and write the fake artifact manifest hash."""
    manifest["manifest_hash"] = compute_reviewer_evidence_artifact_manifest_hash(
        manifest
    )
    _write_manifest(artifact_dir, manifest)


def test_verify_reviewer_evidence_artifact_manifest_returns_dict(
    tmp_path: Path,
) -> None:
    artifact_dir = _valid_artifact_dir(tmp_path)

    report = verify_reviewer_evidence_artifact_manifest(artifact_dir=artifact_dir)

    assert isinstance(report, dict)


def test_verifier_identity_fields(tmp_path: Path) -> None:
    artifact_dir = _valid_artifact_dir(tmp_path)

    report = verify_reviewer_evidence_artifact_manifest(artifact_dir=artifact_dir)

    assert report["verifier_id"] == VERIFIER_ID
    assert report["verifier_version"] == VERIFIER_VERSION
    assert report["artifact_name"] == ARTIFACT_NAME
    assert report["local_offline_only"] is True


def test_complete_valid_artifact_directory_passes(tmp_path: Path) -> None:
    artifact_dir = _valid_artifact_dir(tmp_path)

    report = verify_reviewer_evidence_artifact_manifest(artifact_dir=artifact_dir)

    assert report["status"] == "pass"
    assert report["checks"]["manifest_hash_recomputes"] is True
    assert report["checks"]["required_files_present"] is True
    assert report["checks"]["file_hashes_match"] is True
    assert report["checks"]["file_sizes_match"] is True


def test_every_file_result_has_expected_fields(tmp_path: Path) -> None:
    artifact_dir = _valid_artifact_dir(tmp_path)

    report = verify_reviewer_evidence_artifact_manifest(artifact_dir=artifact_dir)

    assert report["file_results"]
    for file_result in report["file_results"]:
        assert REQUIRED_RESULT_FIELDS == set(file_result)


def test_missing_manifest_fails(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifact"
    artifact_dir.mkdir()

    report = verify_reviewer_evidence_artifact_manifest(artifact_dir=artifact_dir)

    assert report["status"] == "fail"
    assert "artifact_manifest_missing" in report["failure_reasons"]


def test_invalid_json_manifest_fails(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifact"
    artifact_dir.mkdir()
    (artifact_dir / "reviewer-evidence-artifact-manifest.json").write_text(
        "{not-json",
        encoding="utf-8",
    )

    report = verify_reviewer_evidence_artifact_manifest(artifact_dir=artifact_dir)

    assert report["status"] == "fail"
    assert "artifact_manifest_json_unparseable" in report["failure_reasons"]


def test_missing_required_file_fails(tmp_path: Path) -> None:
    artifact_dir = _valid_artifact_dir(tmp_path)
    (artifact_dir / "reviewer-evidence-packet-generated.json").unlink()

    report = verify_reviewer_evidence_artifact_manifest(artifact_dir=artifact_dir)

    assert report["status"] == "fail"
    assert "artifact_manifest_required_file_missing" in report["failure_reasons"]


def test_tampered_file_content_fails(tmp_path: Path) -> None:
    artifact_dir = _valid_artifact_dir(tmp_path)
    (artifact_dir / "reviewer-evidence-packet-generated.json").write_text(
        '{"packet":"tampered"}\n',
        encoding="utf-8",
    )

    report = verify_reviewer_evidence_artifact_manifest(artifact_dir=artifact_dir)

    assert report["status"] == "fail"
    assert "artifact_manifest_file_hash_mismatch" in report["failure_reasons"]


def test_changed_file_size_fails(tmp_path: Path) -> None:
    artifact_dir = _valid_artifact_dir(tmp_path)
    (artifact_dir / "reviewer-evidence-packet-schema.json").write_text(
        '{"type":"object","extra":true}\n',
        encoding="utf-8",
    )

    report = verify_reviewer_evidence_artifact_manifest(artifact_dir=artifact_dir)

    assert report["status"] == "fail"
    assert "artifact_manifest_file_size_mismatch" in report["failure_reasons"]


def test_invalid_artifact_name_fails(tmp_path: Path) -> None:
    artifact_dir = _valid_artifact_dir(tmp_path)
    manifest = _read_manifest(artifact_dir)
    manifest["artifact_name"] = "wrong-artifact"
    _rewrite_manifest_with_hash(artifact_dir, manifest)

    report = verify_reviewer_evidence_artifact_manifest(artifact_dir=artifact_dir)

    assert report["status"] == "fail"
    assert "artifact_manifest_artifact_name_invalid" in report["failure_reasons"]


def test_invalid_local_offline_only_fails(tmp_path: Path) -> None:
    artifact_dir = _valid_artifact_dir(tmp_path)
    manifest = _read_manifest(artifact_dir)
    manifest["local_offline_only"] = False
    _rewrite_manifest_with_hash(artifact_dir, manifest)

    report = verify_reviewer_evidence_artifact_manifest(artifact_dir=artifact_dir)

    assert report["status"] == "fail"
    assert "artifact_manifest_local_offline_only_invalid" in report[
        "failure_reasons"
    ]


def test_invalid_manifest_hash_fails(tmp_path: Path) -> None:
    artifact_dir = _valid_artifact_dir(tmp_path)
    manifest = _read_manifest(artifact_dir)
    manifest["manifest_hash"] = "0" * 64
    _write_manifest(artifact_dir, manifest)

    report = verify_reviewer_evidence_artifact_manifest(artifact_dir=artifact_dir)

    assert report["status"] == "fail"
    assert "artifact_manifest_hash_mismatch" in report["failure_reasons"]


def test_verifier_output_is_deterministic_across_repeated_calls(
    tmp_path: Path,
) -> None:
    artifact_dir = _valid_artifact_dir(tmp_path)

    first = verify_reviewer_evidence_artifact_manifest(artifact_dir=artifact_dir)
    second = verify_reviewer_evidence_artifact_manifest(artifact_dir=artifact_dir)

    assert first == second


def test_cli_exits_zero_for_valid_fixture_dir(tmp_path: Path) -> None:
    artifact_dir = _valid_artifact_dir(tmp_path)

    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(artifact_dir)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert json.loads(result.stdout)["status"] == "pass"


def test_cli_exits_nonzero_for_missing_required_file(tmp_path: Path) -> None:
    artifact_dir = _valid_artifact_dir(tmp_path)
    (artifact_dir / "reviewer-evidence-packet-generated.json").unlink()

    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(artifact_dir)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert json.loads(result.stdout)["status"] == "fail"


def test_no_network_or_environment_dependency_is_required(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    artifact_dir = _valid_artifact_dir(tmp_path)
    for key in list(os.environ):
        if "TOKEN" in key or "KEY" in key or "SECRET" in key:
            monkeypatch.delenv(key, raising=False)

    report = verify_reviewer_evidence_artifact_manifest(artifact_dir=artifact_dir)

    assert report["status"] == "pass"
    assert report["local_offline_only"] is True
