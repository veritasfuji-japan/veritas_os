# -*- coding: utf-8 -*-
"""Checks for newly added decision semantics / taxonomy documentation links."""

from __future__ import annotations

import re
from pathlib import Path

DOC_FILES = [
    Path("README.md"),
    Path("docs/en/README.md"),
    Path("docs/ja/README.md"),
]


def _extract_markdown_links(content: str) -> list[str]:
    """Extract relative markdown links from markdown content."""
    return re.findall(r"\[[^\]]+\]\(([^)]+)\)", content)


def test_decision_semantics_docs_exist() -> None:
    """Core semantics docs should exist in EN/JA."""
    assert Path("docs/en/architecture/decision-semantics.md").exists()
    assert Path("docs/ja/architecture/decision-semantics.md").exists()
    assert Path("docs/en/governance/required-evidence-taxonomy.md").exists()
    assert Path("docs/ja/governance/required-evidence-taxonomy.md").exists()


def test_decision_semantics_doc_declares_runtime_source_of_truth() -> None:
    """EN semantics doc should reference canonical backend source-of-truth constants."""
    content = Path("docs/en/architecture/decision-semantics.md").read_text(
        encoding="utf-8"
    )
    assert "veritas_os/core/decision_semantics.py" in content
    assert "CANONICAL_GATE_DECISION_VALUES" in content
    assert "LEGACY_GATE_DECISION_ALIASES" in content
    assert "FORBIDDEN_GATE_BUSINESS_COMBINATIONS" in content


def test_decision_semantics_doc_freeze_wording_and_legacy_matrix_present() -> None:
    """EN semantics doc should declare freeze policy and legacy alias matrix."""
    content = Path("docs/en/architecture/decision-semantics.md").read_text(
        encoding="utf-8"
    )
    assert "frozen public contract" in content
    assert "legacy alias compatibility matrix" in content.lower()
    assert "`allow` MUST NOT be reintroduced as public canonical label." in content
    assert "proceed" in content and "not business approval" in content


def test_readme_links_to_new_decision_docs() -> None:
    """README hubs should route to the new semantics/taxonomy docs."""
    for path in DOC_FILES:
        content = path.read_text(encoding="utf-8")
        assert "decision-semantics" in content
        assert "required-evidence-taxonomy" in content


def test_new_doc_links_resolve() -> None:
    """Relative links from modified doc hubs should resolve on disk."""
    for path in DOC_FILES:
        content = path.read_text(encoding="utf-8")
        links = _extract_markdown_links(content)
        for link in links:
            if link.startswith(("http://", "https://", "#", "mailto:")):
                continue
            candidate = (path.parent / link).resolve()
            assert candidate.exists(), f"Broken link in {path}: {link} -> {candidate}"
