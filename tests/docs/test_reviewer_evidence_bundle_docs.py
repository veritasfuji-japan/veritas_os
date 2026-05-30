"""Documentation reference tests for Reviewer Evidence Bundle v1."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUNDLE_SCRIPT = "scripts/demo/build_reviewer_evidence_bundle.py"
BUNDLE_DOC = "docs/en/demo/reviewer-evidence-bundle.md"
EXPECTED_OUTPUT_FILES = [
    "reviewer-evidence-packet-validation-report.json",
    "reviewer-evidence-packet-generated.json",
    "reviewer-evidence-packet-golden-fixture.json",
    "reviewer-evidence-packet-schema.json",
    "reviewer-evidence-artifact-manifest.json",
    "reviewer-evidence-artifact-manifest-verification-report.json",
    "reviewer-evidence-step-summary.md",
    "external-reviewer-quickstart.md",
    "external-reviewer-artifact-index.md",
]


def _read_repo_file(relative_path: str) -> str:
    """Read a repository file as UTF-8 text."""
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_readmes_reference_bundle_builder() -> None:
    for readme_path in ["README.md", "README_JP.md"]:
        readme = _read_repo_file(readme_path)
        assert BUNDLE_SCRIPT in readme
        assert BUNDLE_DOC in readme


def test_quickstart_references_bundle_builder() -> None:
    quickstart = _read_repo_file("docs/en/demo/external-reviewer-quickstart.md")

    assert BUNDLE_SCRIPT in quickstart
    assert "Local bundle generation" in quickstart


def test_artifact_index_references_bundle_builder_and_docs() -> None:
    artifact_index = _read_repo_file("docs/en/demo/external-reviewer-artifact-index.md")

    assert BUNDLE_SCRIPT in artifact_index
    assert BUNDLE_DOC in artifact_index


def test_reviewer_evidence_bundle_docs_exist_and_explain_boundary() -> None:
    bundle_doc_path = ROOT / BUNDLE_DOC

    assert bundle_doc_path.is_file()
    bundle_doc = bundle_doc_path.read_text(encoding="utf-8")
    assert "local/offline" in bundle_doc
    assert "no live network calls" in bundle_doc
    assert "requires no credentials" in bundle_doc
    assert "not proof of live production deployment" in bundle_doc


def test_reviewer_evidence_bundle_docs_list_expected_output_files() -> None:
    bundle_doc = _read_repo_file(BUNDLE_DOC)

    for filename in EXPECTED_OUTPUT_FILES:
        assert filename in bundle_doc
