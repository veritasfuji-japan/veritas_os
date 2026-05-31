"""String-presence checks for Governance Evidence Packet v0 contract docs."""

from __future__ import annotations

from pathlib import Path


SCHEMA_PATH = Path(
    "docs/en/demo/schemas/governance-evidence-packet-v0.schema.json"
)
FIXTURE_PATH = Path(
    "docs/en/demo/fixtures/governance-evidence-packet-v0.json"
)
README_PATH = Path("README.md")
EN_DEMO_PATH = Path("docs/en/demos/pre_boundary_collapse_demo.md")
JA_DEMO_PATH = Path("docs/ja/demos/pre_boundary_collapse_demo.md")
ARTIFACT_INDEX_PATH = Path(
    "docs/en/demo/external-reviewer-artifact-index.md"
)

SCHEMA_FILE_NAME = "governance-evidence-packet-v0.schema.json"
FIXTURE_FILE_NAME = "governance-evidence-packet-v0.json"
CONTRACT_TEST_PATH = (
    "frontend/app/api/veritas/v1/report/governance/"
    "governance-evidence-packet-contract.test.ts"
)
EN_DEMO_TERMS = [
    "Governance Evidence Packet v0",
    "deterministic representative reviewer packet",
    "not claim certification",
    "not automatic enforcement",
    "not production security",
]
JA_DEMO_TERMS = [
    "Governance Evidence Packet v0",
    "deterministic representative reviewer packet",
    "certification",
    "automatic enforcement",
    "production security",
]
NON_CLAIM_TERMS = [
    "not certification",
    "not production security guarantee",
    "not automatic enforcement",
    "not scoring model",
    "not legal conclusion",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_governance_evidence_packet_contract_files_exist() -> None:
    assert SCHEMA_PATH.exists()
    assert FIXTURE_PATH.exists()


def test_demo_docs_reference_governance_evidence_packet_contract() -> None:
    en_content = _read(EN_DEMO_PATH)
    ja_content = _read(JA_DEMO_PATH)

    for term in EN_DEMO_TERMS:
        assert term in en_content

    for term in JA_DEMO_TERMS:
        assert term in ja_content


def test_readme_or_external_reviewer_index_references_contract_artifacts() -> None:
    content = "\n".join([_read(README_PATH), _read(ARTIFACT_INDEX_PATH)])

    assert SCHEMA_FILE_NAME in content
    assert FIXTURE_FILE_NAME in content
    assert CONTRACT_TEST_PATH in content


def test_reviewer_docs_preserve_governance_evidence_packet_non_claims() -> None:
    content = "\n".join(
        _read(path) for path in (README_PATH, EN_DEMO_PATH, JA_DEMO_PATH)
    ).lower()

    for term in NON_CLAIM_TERMS:
        assert term in content
