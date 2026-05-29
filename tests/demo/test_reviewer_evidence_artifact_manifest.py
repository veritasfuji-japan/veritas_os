"""Tests for Reviewer Evidence Packet artifact manifest generation."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from scripts.demo.build_reviewer_evidence_artifact_manifest import (
    ARTIFACT_NAME,
    MANIFEST_ID,
    MANIFEST_VERSION,
    build_reviewer_evidence_artifact_manifest,
    compute_reviewer_evidence_artifact_manifest_hash,
    write_reviewer_evidence_artifact_manifest,
)

REQUIRED_FILENAMES = [
    "reviewer-evidence-packet-validation-report.json",
    "reviewer-evidence-packet-generated.json",
    "reviewer-evidence-packet-golden-fixture.json",
    "reviewer-evidence-packet-schema.json",
]
SHA256_HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _write_complete_artifact_dir(tmp_path: Path) -> Path:
    """Create a deterministic fake reviewer evidence artifact directory."""
    artifact_dir = tmp_path / "reviewer-evidence-packet"
    artifact_dir.mkdir()
    payloads = {
        "reviewer-evidence-packet-validation-report.json": {
            "generated_at": "2026-01-02T03:04:05Z",
            "status": "pass",
        },
        "reviewer-evidence-packet-generated.json": {
            "generated_at": "2026-01-02T03:04:05Z",
            "packet_id": "fake-packet",
        },
        "reviewer-evidence-packet-golden-fixture.json": {"fixture": True},
        "reviewer-evidence-packet-schema.json": {"$schema": "https://json-schema.org"},
    }
    for filename, payload in payloads.items():
        (artifact_dir / filename).write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    (artifact_dir / "external-reviewer-quickstart.md").write_text(
        "# Quickstart\n",
        encoding="utf-8",
    )
    (artifact_dir / "external-reviewer-artifact-index.md").write_text(
        "# Artifact Index\n",
        encoding="utf-8",
    )
    return artifact_dir


def test_build_reviewer_evidence_artifact_manifest_returns_expected_dict(
    tmp_path: Path,
) -> None:
    artifact_dir = _write_complete_artifact_dir(tmp_path)

    manifest = build_reviewer_evidence_artifact_manifest(artifact_dir=artifact_dir)

    assert isinstance(manifest, dict)
    assert manifest["manifest_id"] == MANIFEST_ID
    assert manifest["manifest_id"] == "reviewer-evidence-artifact-manifest-v1"
    assert manifest["manifest_version"] == MANIFEST_VERSION
    assert manifest["manifest_version"] == "v1"
    assert manifest["artifact_name"] == ARTIFACT_NAME
    assert manifest["artifact_name"] == "reviewer-evidence-packet-validation-artifacts"
    assert manifest["generated_at"] == "2026-01-02T03:04:05Z"
    assert manifest["local_offline_only"] is True
    assert manifest["files"]


def test_manifest_contains_required_file_entries(tmp_path: Path) -> None:
    artifact_dir = _write_complete_artifact_dir(tmp_path)

    manifest = build_reviewer_evidence_artifact_manifest(artifact_dir=artifact_dir)
    paths = {file_entry["path"] for file_entry in manifest["files"]}

    for filename in REQUIRED_FILENAMES:
        assert filename in paths


def test_every_manifest_file_entry_has_required_metadata(tmp_path: Path) -> None:
    artifact_dir = _write_complete_artifact_dir(tmp_path)

    manifest = build_reviewer_evidence_artifact_manifest(artifact_dir=artifact_dir)

    for file_entry in manifest["files"]:
        assert set(file_entry) >= {
            "path",
            "role",
            "source",
            "generated",
            "required",
            "sha256",
            "size_bytes",
            "media_type",
            "description",
        }
        assert SHA256_HEX_PATTERN.fullmatch(file_entry["sha256"])
        assert isinstance(file_entry["size_bytes"], int)
        assert file_entry["size_bytes"] >= 0


def test_manifest_aggregate_summary_matches_files(tmp_path: Path) -> None:
    artifact_dir = _write_complete_artifact_dir(tmp_path)

    manifest = build_reviewer_evidence_artifact_manifest(artifact_dir=artifact_dir)
    aggregate_summary = manifest["aggregate_summary"]

    assert aggregate_summary["total_files"] == len(manifest["files"])
    assert aggregate_summary["missing_required_files"] == []
    assert aggregate_summary["local_offline_only"] is True
    assert aggregate_summary["total_size_bytes"] == sum(
        file_entry["size_bytes"] for file_entry in manifest["files"]
    )


def test_manifest_hash_is_deterministic_and_excludes_itself(tmp_path: Path) -> None:
    artifact_dir = _write_complete_artifact_dir(tmp_path)

    first_manifest = build_reviewer_evidence_artifact_manifest(artifact_dir=artifact_dir)
    second_manifest = build_reviewer_evidence_artifact_manifest(artifact_dir=artifact_dir)

    assert first_manifest["manifest_hash"]
    assert len(first_manifest["manifest_hash"]) == 64
    assert SHA256_HEX_PATTERN.fullmatch(first_manifest["manifest_hash"])
    assert (
        compute_reviewer_evidence_artifact_manifest_hash(first_manifest)
        == first_manifest["manifest_hash"]
    )
    assert first_manifest["manifest_hash"] == second_manifest["manifest_hash"]

    changed_manifest = json.loads(json.dumps(first_manifest))
    changed_manifest["files"][0]["role"] = "changed_role"
    assert (
        compute_reviewer_evidence_artifact_manifest_hash(changed_manifest)
        != first_manifest["manifest_hash"]
    )

    recursive_manifest = json.loads(json.dumps(first_manifest))
    recursive_manifest["manifest_hash"] = "0" * 64
    assert (
        compute_reviewer_evidence_artifact_manifest_hash(recursive_manifest)
        == first_manifest["manifest_hash"]
    )


def test_missing_required_file_is_reported_and_not_written(tmp_path: Path) -> None:
    artifact_dir = _write_complete_artifact_dir(tmp_path)
    missing_path = artifact_dir / "reviewer-evidence-packet-schema.json"
    missing_path.unlink()

    manifest = build_reviewer_evidence_artifact_manifest(artifact_dir=artifact_dir)

    assert manifest["aggregate_summary"]["missing_required_files"] == [
        "reviewer-evidence-packet-schema.json"
    ]

    script_path = Path("scripts/demo/build_reviewer_evidence_artifact_manifest.py")
    result = subprocess.run(
        [sys.executable, str(script_path), str(artifact_dir)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "reviewer-evidence-packet-schema.json" in result.stderr


def test_write_manifest_creates_deterministic_json_without_network_or_env(
    tmp_path: Path,
) -> None:
    artifact_dir = _write_complete_artifact_dir(tmp_path)

    manifest = write_reviewer_evidence_artifact_manifest(artifact_dir=artifact_dir)
    output_path = artifact_dir / "reviewer-evidence-artifact-manifest.json"

    assert output_path.is_file()
    written_manifest = json.loads(output_path.read_text(encoding="utf-8"))
    assert written_manifest == manifest
    assert written_manifest["aggregate_summary"]["missing_required_files"] == []
