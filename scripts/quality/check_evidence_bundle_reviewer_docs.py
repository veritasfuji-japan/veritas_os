#!/usr/bin/env python3
"""Validate Evidence Bundle reviewer verification documentation links.

This guard keeps the external reviewer path for Evidence Bundle verification
intact. It verifies that required reviewer-facing documents exist, that the
main review-readiness entry points link to the verification materials, and that
safety boundary language remains present before documentation edits reach CI.
"""

from __future__ import annotations

import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
VALIDATION_DIR = REPO_ROOT / "docs/en/validation"

REQUIRED_DOCS = (
    VALIDATION_DIR / "evidence-bundle-reviewer-checklist.md",
    VALIDATION_DIR / "evidence-bundle-signature-verification.md",
    VALIDATION_DIR / "sample-evidence-bundle-verification-output.md",
    VALIDATION_DIR / "trusted-public-key-provenance.md",
    VALIDATION_DIR / "reviewer-key-provenance-walkthrough.md",
    VALIDATION_DIR / "external-audit-readiness.md",
    VALIDATION_DIR / "technical-proof-pack.md",
    VALIDATION_DIR / "third-party-review-readiness.md",
)

REVIEWER_VERIFICATION_LINKS = (
    "evidence-bundle-reviewer-checklist.md",
    "evidence-bundle-signature-verification.md",
    "sample-evidence-bundle-verification-output.md",
    "trusted-public-key-provenance.md",
    "reviewer-key-provenance-walkthrough.md",
    "external-audit-readiness.md",
)

LINK_SOURCE_PATHS = (
    VALIDATION_DIR / "technical-proof-pack.md",
    VALIDATION_DIR / "third-party-review-readiness.md",
)

README_ENTRYPOINT_PATHS = (
    REPO_ROOT / "README.md",
    REPO_ROOT / "docs/en/README.md",
)

README_VERIFICATION_LINKS = (
    "evidence-bundle-reviewer-checklist.md",
    "evidence-bundle-signature-verification.md",
    "sample-evidence-bundle-verification-output.md",
    "reviewer-key-provenance-walkthrough.md",
)

SAFETY_BOUNDARY_PHRASES = (
    "reviewer-facing verification support",
    "not regulatory certification",
    "not completed third-party audit approval",
    (
        "trusted public keys must come from an out-of-band "
        "reviewer/operator trust channel"
    ),
)

VERIFICATION_CONCEPTS = (
    "file/hash integrity",
    "manifest authenticity",
    "Ed25519",
    "trusted public key",
    "Reviewer Evidence Packet",
    "matching fingerprints support correlation, not standalone trust",
)

BOUNDARY_SOURCE_PATHS = (
    VALIDATION_DIR / "technical-proof-pack.md",
    VALIDATION_DIR / "third-party-review-readiness.md",
)

WHITESPACE_PATTERN = re.compile(r"\s+")


def _relative(path: pathlib.Path) -> str:
    """Return a repository-relative path for readable diagnostics."""
    return str(path.relative_to(REPO_ROOT))


def _read_existing_documents(paths: tuple[pathlib.Path, ...]) -> dict[pathlib.Path, str]:
    """Read the existing files from ``paths`` using UTF-8."""
    return {
        path: path.read_text(encoding="utf-8")
        for path in paths
        if path.exists()
    }


def _normalize_text(text: str) -> str:
    """Normalize case and whitespace so wrapped Markdown still matches."""
    return WHITESPACE_PATTERN.sub(" ", text.lower()).strip()


def collect_missing_files(paths: tuple[pathlib.Path, ...]) -> list[str]:
    """Return diagnostics for required documentation files that are absent."""
    return [f"Missing file: {_relative(path)}" for path in paths if not path.exists()]


def collect_missing_links(
    documents: dict[pathlib.Path, str],
    source_paths: tuple[pathlib.Path, ...],
    required_links: tuple[str, ...],
) -> list[str]:
    """Return diagnostics for links missing from required source documents."""
    problems = []
    for path in source_paths:
        content = documents.get(path)
        if content is None:
            continue
        for link in required_links:
            if link not in content:
                problems.append(f"{_relative(path)}: missing link: {link}")
    return problems


def collect_missing_readme_entrypoint(
    documents: dict[pathlib.Path, str],
    readme_paths: tuple[pathlib.Path, ...],
    verification_links: tuple[str, ...],
) -> list[str]:
    """Return a diagnostic when no README links to verification materials."""
    for path in readme_paths:
        content = documents.get(path)
        if content is None:
            continue
        if any(link in content for link in verification_links):
            return []

    readmes = ", ".join(_relative(path) for path in readme_paths)
    links = ", ".join(verification_links)
    return [
        f"{readmes}: missing reachable Evidence Bundle verification docs link "
        f"(expected one of: {links})"
    ]


def collect_missing_boundary_phrases(
    documents: dict[pathlib.Path, str],
    source_paths: tuple[pathlib.Path, ...],
    required_phrases: tuple[str, ...],
) -> list[str]:
    """Return diagnostics for safety boundary phrases missing from all sources."""
    normalized_sources = {
        path: _normalize_text(documents.get(path, "")) for path in source_paths
    }
    combined = "\n".join(normalized_sources.values())
    problems = []
    for phrase in required_phrases:
        if _normalize_text(phrase) not in combined:
            sources = ", ".join(_relative(path) for path in source_paths)
            problems.append(
                f"{sources}: missing required safety boundary phrase: {phrase}"
            )
    return problems


def collect_missing_concepts(
    documents: dict[pathlib.Path, str],
    required_concepts: tuple[str, ...],
) -> list[str]:
    """Return diagnostics for verification concepts missing from all docs."""
    combined = "\n".join(documents.values())
    normalized_combined = _normalize_text(combined)
    problems = []
    for concept in required_concepts:
        if _normalize_text(concept) not in normalized_combined:
            problems.append(
                "Evidence Bundle reviewer docs: missing required concept: "
                f"{concept}"
            )
    return problems


def validate_evidence_bundle_reviewer_docs() -> list[str]:
    """Validate the Evidence Bundle external reviewer documentation path."""
    paths_to_read = tuple(
        dict.fromkeys(REQUIRED_DOCS + README_ENTRYPOINT_PATHS).keys()
    )
    documents = _read_existing_documents(paths_to_read)

    problems = []
    problems.extend(collect_missing_files(REQUIRED_DOCS))
    problems.extend(
        collect_missing_links(
            documents,
            LINK_SOURCE_PATHS,
            REVIEWER_VERIFICATION_LINKS,
        )
    )
    problems.extend(
        collect_missing_readme_entrypoint(
            documents,
            README_ENTRYPOINT_PATHS,
            README_VERIFICATION_LINKS,
        )
    )
    problems.extend(
        collect_missing_boundary_phrases(
            documents,
            BOUNDARY_SOURCE_PATHS,
            SAFETY_BOUNDARY_PHRASES,
        )
    )
    problems.extend(collect_missing_concepts(documents, VERIFICATION_CONCEPTS))
    return problems


def main() -> int:
    """Run the Evidence Bundle reviewer documentation consistency check."""
    problems = validate_evidence_bundle_reviewer_docs()
    if not problems:
        print("Evidence Bundle reviewer documentation checks passed.")
        return 0

    print("[DOCS] Evidence Bundle reviewer documentation path is incomplete:")
    for problem in problems:
        print(f"- {problem}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
