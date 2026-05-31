"""String-presence checks for Intervention Actionability Map v0 contract docs."""

from __future__ import annotations

from pathlib import Path


SCHEMA_PATH = Path(
    "docs/en/demo/schemas/intervention-actionability-map-v0.schema.json"
)
FIXTURE_PATH = Path("docs/en/demo/fixtures/intervention-actionability-map-v0.json")
README_PATH = Path("README.md")
README_JP_PATH = Path("README_JP.md")
EN_DEMO_PATH = Path("docs/en/demos/pre_boundary_collapse_demo.md")
JA_DEMO_PATH = Path("docs/ja/demos/pre_boundary_collapse_demo.md")
ARTIFACT_INDEX_PATH = Path("docs/en/demo/external-reviewer-artifact-index.md")

SCHEMA_FILE_NAME = "intervention-actionability-map-v0.schema.json"
FIXTURE_FILE_NAME = "intervention-actionability-map-v0.json"
NON_CLAIM_TERMS = [
    "automatic enforcement",
    "automatic blocking",
    "automatic escalation",
    "scoring",
    "production decisioning",
    "certification",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_intervention_actionability_map_contract_files_exist() -> None:
    assert SCHEMA_PATH.exists()
    assert FIXTURE_PATH.exists()


def test_readmes_reference_intervention_actionability_map_contract() -> None:
    for path in (README_PATH, README_JP_PATH):
        content = _read(path)
        assert SCHEMA_FILE_NAME in content
        assert FIXTURE_FILE_NAME in content


def test_demo_docs_reference_intervention_actionability_map_contract() -> None:
    for path in (EN_DEMO_PATH, JA_DEMO_PATH):
        content = _read(path)
        assert SCHEMA_FILE_NAME in content
        assert FIXTURE_FILE_NAME in content


def test_external_reviewer_artifact_index_references_contract() -> None:
    content = _read(ARTIFACT_INDEX_PATH)

    assert SCHEMA_FILE_NAME in content
    assert FIXTURE_FILE_NAME in content


def test_docs_preserve_non_enforcement_and_non_certification_language() -> None:
    content = "\n".join(
        _read(path) for path in (README_PATH, README_JP_PATH, EN_DEMO_PATH, JA_DEMO_PATH)
    ).lower()

    for term in NON_CLAIM_TERMS:
        assert term in content
