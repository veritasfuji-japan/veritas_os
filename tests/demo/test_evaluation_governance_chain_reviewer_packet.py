"""Tests for generating Reviewer Evidence Packets from offline chains."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from scripts.demo import (
    generate_reviewer_evidence_packet_from_evaluation_governance_chain as helper,
)

EXAMPLE_DIR = Path(
    "docs/en/demo/examples/evaluation-governance-offline-chain-v1"
)
CHAIN_MANIFEST_PATH = EXAMPLE_DIR / "generated/chain-manifest.generated.example.json"
SCRIPT_PATH = Path(
    "scripts/demo/"
    "generate_reviewer_evidence_packet_from_evaluation_governance_chain.py"
)
SCHEMA_PATH = Path("docs/en/demo/schemas/reviewer-evidence-packet-v1.schema.json")
REQUIRED_ARTIFACT_TYPES = {
    "evaluation_receipt",
    "manifest_change_receipt",
    "outcome_delta_attribution",
    "evaluation_drift_detection",
    "trajectory_admissibility_monitor",
    "legitimacy_impact_review",
}
REQUIRED_ATTACHMENT_FIELDS = {
    "artifact_type",
    "artifact_ref",
    "artifact_hash",
    "schema_ref",
    "required_for_review",
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonschema_module() -> Any | None:
    if importlib.util.find_spec("jsonschema") is None:
        return None

    import jsonschema

    return jsonschema


def _validate_packet(packet: dict[str, Any]) -> None:
    helper.validate_reviewer_packet(packet)
    jsonschema = _jsonschema_module()
    if jsonschema is not None:
        validator = jsonschema.Draft202012Validator(_load_json(SCHEMA_PATH))
        validator.validate(packet)


def test_helper_imports_cleanly() -> None:
    assert callable(helper.load_json)
    assert callable(helper.canonical_json_hash)
    assert callable(helper.map_artifact_type)
    assert callable(helper.schema_ref_for_artifact_type)
    assert callable(helper.build_evaluation_governance_artifacts)
    assert callable(helper.validate_reviewer_packet)
    assert callable(helper.generate_reviewer_evidence_packet_from_chain)


def test_generate_packet_from_checked_in_chain_manifest() -> None:
    chain_manifest = helper.load_json(CHAIN_MANIFEST_PATH)

    packet = helper.generate_reviewer_evidence_packet_from_chain(
        chain_manifest,
        EXAMPLE_DIR,
    )

    _validate_packet(packet)
    artifacts = packet.get("evaluation_governance_artifacts")
    assert isinstance(artifacts, list)
    assert artifacts

    artifact_types = {artifact["artifact_type"] for artifact in artifacts}
    assert REQUIRED_ARTIFACT_TYPES <= artifact_types
    for artifact in artifacts:
        assert REQUIRED_ATTACHMENT_FIELDS <= set(artifact)
        assert artifact["required_for_review"] is False


def test_cli_writes_packet_to_output_path(tmp_path: Path) -> None:
    output_path = tmp_path / "reviewer-evidence-packet.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--chain-manifest",
            str(CHAIN_MANIFEST_PATH),
            "--artifact-base-dir",
            str(EXAMPLE_DIR),
            "--output",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "Generated Reviewer Evidence Packet" in completed.stdout
    assert output_path.is_file()

    packet = _load_json(output_path)
    _validate_packet(packet)
    assert packet["evaluation_governance_artifacts"]


def test_unsupported_artifact_type_fails_clearly(tmp_path: Path) -> None:
    chain_manifest = {
        "schema_version": "evaluation-governance-offline-chain-manifest-v1",
        "chain_id": "unsupported-artifact-type-test",
        "issued_at": "2026-01-01T00:00:00Z",
        "non_runtime": True,
        "non_enforcing": True,
        "artifacts": [
            {
                "artifact_type": "unsafe_unknown_artifact",
                "artifact_ref": "unsafe-unknown-artifact.example.json",
                "artifact_hash": "0" * 64,
            }
        ],
    }

    with pytest.raises(ValueError, match="unsupported.*artifact_type"):
        helper.generate_reviewer_evidence_packet_from_chain(
            chain_manifest,
            tmp_path,
        )
