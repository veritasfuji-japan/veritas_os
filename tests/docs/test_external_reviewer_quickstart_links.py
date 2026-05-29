"""Tests for external reviewer quickstart documentation links."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
QUICKSTART_PATH = ROOT / "docs/en/demo/external-reviewer-quickstart.md"
ARTIFACT_INDEX_PATH = ROOT / "docs/en/demo/external-reviewer-artifact-index.md"


def _read_repo_file(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_external_reviewer_docs_exist() -> None:
    assert QUICKSTART_PATH.exists()
    assert ARTIFACT_INDEX_PATH.exists()


def test_quickstart_references_core_artifacts() -> None:
    quickstart = QUICKSTART_PATH.read_text(encoding="utf-8")

    for expected_path in [
        "scripts/demo/validate_reviewer_evidence_packet.py",
        "scripts/demo/export_reviewer_evidence_packet.py",
        (
            "docs/en/demo/fixtures/"
            "reviewer-evidence-packet-saas-permission-change-v1.json"
        ),
        "docs/en/demo/schemas/reviewer-evidence-packet-v1.schema.json",
    ]:
        assert expected_path in quickstart


def test_artifact_index_references_reviewer_artifacts() -> None:
    artifact_index = ARTIFACT_INDEX_PATH.read_text(encoding="utf-8")

    for expected_path in [
        "scripts/demo/saas_permission_change_governed_demo.py",
        "scripts/demo/export_reviewer_evidence_packet.py",
        "scripts/demo/validate_reviewer_evidence_packet.py",
        (
            "docs/en/demo/fixtures/"
            "reviewer-evidence-packet-saas-permission-change-v1.json"
        ),
        "docs/en/demo/schemas/reviewer-evidence-packet-v1.schema.json",
        "docs/en/architecture/outcome-receipt.md",
        "docs/en/architecture/evidence-chain-manifest.md",
        "docs/en/architecture/evidence-chain-verifier.md",
        "docs/en/architecture/bind-coverage-registry.md",
    ]:
        assert expected_path in artifact_index


def test_readmes_reference_external_reviewer_quickstart() -> None:
    for readme_path in ["README.md", "README_JP.md"]:
        readme = _read_repo_file(readme_path)
        assert "external-reviewer-quickstart.md" in readme
