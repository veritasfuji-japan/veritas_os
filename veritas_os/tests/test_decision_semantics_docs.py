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
