"""Presence checks for Reviewer-Facing Visibility Roadmap v0 docs."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ENGLISH_DEMO_DOC = ROOT / "docs/en/demos/pre_boundary_collapse_demo.md"
JAPANESE_DEMO_DOC = ROOT / "docs/ja/demos/pre_boundary_collapse_demo.md"
REVIEWER_ARTIFACT_INDEX = (
    ROOT / "docs/en/demo/external-reviewer-artifact-index.md"
)
ENGLISH_README = ROOT / "README.md"
JAPANESE_README = ROOT / "README_JP.md"


def _normalize_whitespace(text: str) -> str:
    return " ".join(text.split())


def test_english_demo_documents_reviewer_facing_visibility_roadmap() -> None:
    text = _normalize_whitespace(
        ENGLISH_DEMO_DOC.read_text(encoding="utf-8")
    )

    expected_fragments = [
        "Reviewer-Facing Visibility Roadmap v0",
        (
            "Reviewer-facing visibility should distinguish procedural "
            "admissibility evidence, maneuverability contraction evidence, "
            "and recognizability evidence before any future packet expansion."
        ),
        (
            "This roadmap does not change the Governance Evidence "
            "Packet v0 contract."
        ),
        "Governance Evidence Packet v0",
        "Governance Evidence Packet Contract v0",
        "Procedural Admissibility vs. Maneuverability Observables v0",
        "Governance Recognizability Conditions v0",
        "not certification",
        "not production security",
        "not automatic enforcement",
        "not a psychological inference",
        "not a Governance Evidence Packet v1 implementation",
    ]

    for fragment in expected_fragments:
        assert fragment in text


def test_japanese_demo_documents_reviewer_facing_visibility_roadmap() -> None:
    if not JAPANESE_DEMO_DOC.exists():
        return

    text = _normalize_whitespace(
        JAPANESE_DEMO_DOC.read_text(encoding="utf-8")
    )

    expected_fragments = [
        "Reviewer-Facing Visibility Roadmap v0",
        "docs-only",
        "Governance Evidence Packet v1",
        "procedural admissibility",
        "maneuverability",
        "recognizability",
        "reviewer",
        "certification",
        "production security",
        "automatic enforcement",
    ]

    for fragment in expected_fragments:
        assert fragment in text


def test_reviewer_index_or_readme_references_visibility_roadmap() -> None:
    candidate_paths = [
        REVIEWER_ARTIFACT_INDEX,
        ENGLISH_README,
        JAPANESE_README,
    ]
    combined_text = _normalize_whitespace(
        "\n".join(
            path.read_text(encoding="utf-8")
            for path in candidate_paths
            if path.exists()
        )
    )

    assert "Reviewer-Facing Visibility Roadmap v0" in combined_text
