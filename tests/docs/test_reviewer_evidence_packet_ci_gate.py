"""Tests for Reviewer Evidence Packet CI gate references."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = ROOT / ".github/workflows/reviewer-evidence-packet-validation.yml"
WORKFLOW_REFERENCE = ".github/workflows/reviewer-evidence-packet-validation.yml"
VALIDATOR_REFERENCE = "scripts/demo/validate_reviewer_evidence_packet.py"
ARTIFACT_NAME = "reviewer-evidence-packet-validation-artifacts"
VALIDATION_REPORT_ARTIFACT = "reviewer-evidence-packet-validation-report.json"
GENERATED_PACKET_ARTIFACT = "reviewer-evidence-packet-generated.json"
GOLDEN_FIXTURE_ARTIFACT = "reviewer-evidence-packet-golden-fixture.json"
SCHEMA_ARTIFACT = "reviewer-evidence-packet-schema.json"


def _read_repo_file(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_reviewer_evidence_packet_validation_workflow_exists() -> None:
    assert WORKFLOW_PATH.exists()


def test_reviewer_evidence_packet_validation_workflow_runs_validator() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert VALIDATOR_REFERENCE in workflow
    assert "continue-on-error" not in workflow


def test_reviewer_evidence_packet_workflow_uploads_artifacts() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "actions/upload-artifact" in workflow
    assert ARTIFACT_NAME in workflow


def test_reviewer_evidence_packet_workflow_writes_artifact_files() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert VALIDATION_REPORT_ARTIFACT in workflow
    assert GENERATED_PACKET_ARTIFACT in workflow
    assert GOLDEN_FIXTURE_ARTIFACT in workflow
    assert SCHEMA_ARTIFACT in workflow


def test_validation_report_docs_reference_workflow_path() -> None:
    docs = _read_repo_file(
        "docs/en/demo/reviewer-evidence-packet-validation-report.md"
    )

    assert WORKFLOW_REFERENCE in docs


def test_validation_report_docs_reference_ci_artifacts() -> None:
    docs = _read_repo_file(
        "docs/en/demo/reviewer-evidence-packet-validation-report.md"
    )

    assert ARTIFACT_NAME in docs


def test_quickstart_mentions_ci_validation() -> None:
    quickstart = _read_repo_file(
        "docs/en/demo/external-reviewer-quickstart.md"
    )

    assert "Reviewer Evidence Packet Validation workflow" in quickstart
    assert "continuously checked" in quickstart


def test_quickstart_mentions_ci_artifacts() -> None:
    quickstart = _read_repo_file(
        "docs/en/demo/external-reviewer-quickstart.md"
    )

    assert ARTIFACT_NAME in quickstart


def test_artifact_index_references_workflow_path() -> None:
    artifact_index = _read_repo_file(
        "docs/en/demo/external-reviewer-artifact-index.md"
    )

    assert WORKFLOW_REFERENCE in artifact_index


def test_artifact_index_references_ci_artifacts() -> None:
    artifact_index = _read_repo_file(
        "docs/en/demo/external-reviewer-artifact-index.md"
    )

    assert ARTIFACT_NAME in artifact_index


def test_readmes_reference_workflow_path() -> None:
    for readme_path in ["README.md", "README_JP.md"]:
        readme = _read_repo_file(readme_path)
        assert WORKFLOW_REFERENCE in readme


def test_readmes_reference_ci_artifacts() -> None:
    for readme_path in ["README.md", "README_JP.md"]:
        readme = _read_repo_file(readme_path)
        assert ARTIFACT_NAME in readme
