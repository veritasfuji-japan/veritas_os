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
QUICKSTART_PATH = VALIDATION_DIR / "reviewer-handoff-sample-quickstart.md"
SAMPLE_README_PATH = (
    REPO_ROOT / "samples/evidence_bundle/key_provenance_review/README.md"
)

REQUIRED_DOCS = (
    VALIDATION_DIR / "evidence-bundle-reviewer-checklist.md",
    VALIDATION_DIR / "evidence-bundle-signature-verification.md",
    VALIDATION_DIR / "sample-evidence-bundle-verification-output.md",
    VALIDATION_DIR / "trusted-public-key-provenance.md",
    VALIDATION_DIR / "reviewer-key-provenance-walkthrough.md",
    VALIDATION_DIR / "reviewer-handoff-guide.md",
    QUICKSTART_PATH,
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
    "reviewer-handoff-guide.md",
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
    "reviewer-handoff-guide.md",
)

HANDOFF_LINK_SOURCE_PATHS = (
    REPO_ROOT / "README.md",
    REPO_ROOT / "README_JP.md",
    REPO_ROOT / "docs/en/technical-proof-pack.md",
    VALIDATION_DIR / "reviewer-key-provenance-walkthrough.md",
    VALIDATION_DIR / "evidence-bundle-reviewer-checklist.md",
    VALIDATION_DIR / "trusted-public-key-provenance.md",
    SAMPLE_README_PATH,
    VALIDATION_DIR / "third-party-review-readiness.md",
    VALIDATION_DIR / "technical-proof-pack.md",
)

QUICKSTART_LINK_SOURCE_PATHS = (
    REPO_ROOT / "README.md",
    REPO_ROOT / "README_JP.md",
    VALIDATION_DIR / "reviewer-handoff-guide.md",
    VALIDATION_DIR / "reviewer-key-provenance-walkthrough.md",
    VALIDATION_DIR / "evidence-bundle-reviewer-checklist.md",
    VALIDATION_DIR / "trusted-public-key-provenance.md",
    SAMPLE_README_PATH,
)

HANDOFF_REQUIRED_ARTIFACTS = (
    "Evidence Bundle",
    "verification-result.json",
    "trusted-public-key-provenance.json",
    "key-provenance-validation.json",
    "key-provenance-result-validation.json",
    "reviewer-evidence-packet.json",
    "sample-artifact-manifest.json",
    "reviewer-handoff-package-validation.json",
)

QUICKSTART_REQUIRED_ARTIFACTS = (
    "verification-result.json",
    "trusted-public-key-provenance.json",
    "key-provenance-validation.json",
    "key-provenance-result-validation.json",
    "reviewer-evidence-packet.json",
    "reviewer-handoff-review-result.json",
    "reviewer-review-result-validation.json",
    "reviewer-review-result-report-validation.json",
    "reviewer-handoff-package-validation.json",
    "sample-artifact-manifest.json",
    "README.md",
)

QUICKSTART_REQUIRED_PHRASES = (
    "validate-reviewer-handoff-package",
    "deterministic regeneration check",
    "out-of-band public key trust",
    (
        "reviewer handoff sample package validates sample structure and "
        "validation status only"
    ),
    "does not create trust",
    "does not replace out-of-band public key trust",
    "does not prove regulatory certification",
    "not completed third-party audit approval",
    "does not establish cryptographic truth by itself",
    "sample hashes support sample integrity only",
    "matching fingerprints support correlation only, not standalone trust",
    "validation reports record validation status only",
)

HANDOFF_BOUNDARY_PHRASES = (
    "do not create trust by themselves",
    "do not replace out-of-band public key trust",
    "do not prove regulatory certification",
    "not completed third-party audit approval",
    "matching fingerprints support correlation, not standalone trust",
    "sample artifact hashes prove sample integrity only, not production evidence authenticity",
    "Reviewer Evidence Packets reference artifacts; they do not prove trust alone",
)

HANDOFF_SAFETY_PATTERNS = {
    "raw private key": (
        re.compile(r"-----BEGIN (?:OPENSSH |RSA |EC |DSA )?PRIVATE KEY-----"),
        re.compile(r"-----BEGIN ENCRYPTED PRIVATE KEY-----"),
    ),
    "real secret or credential": (
        re.compile(r"AKIA[0-9A-Z]{16}"),
        re.compile(r"ASIA[0-9A-Z]{16}"),
        re.compile(r"sk_live_[0-9A-Za-z]{12,}"),
        re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}"),
        re.compile(r"ghp_[0-9A-Za-z]{20,}"),
        re.compile(r"github_pat_[0-9A-Za-z_]{20,}"),
        re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
        re.compile(
            r"(?i)\b(?:api[_-]?key|access[_-]?token|password|secret)\b"
            r"\s*[:=]\s*['\"]?(?!sample|example|placeholder|synthetic)"
            r"[A-Za-z0-9_./+=-]{8,}"
        ),
    ),
    "absolute local path": (
        re.compile(r"(?<![A-Za-z0-9])(?:/(?:Users|home|tmp|var|workspace)/)"),
        re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:\\"),
    ),
    "exception traceback or raw exception text": (
        re.compile(r"Traceback \(most recent call last\)"),
        re.compile(r"\b(?:FileNotFoundError|PermissionError|RuntimeError):"),
        re.compile(r"\b(?:Exception|ValidationError):"),
        re.compile(r"jsonschema\.exceptions"),
    ),
    "raw schema validator message": (
        re.compile(r"\bis not of type\b"),
        re.compile(r"\bis a required property\b"),
        re.compile(r"Additional properties are not allowed"),
        re.compile(r"Failed validating"),
        re.compile(r"\bdoes not match\b"),
    ),
    "real fingerprint": (
        re.compile(r"(?i)\b[0-9a-f]{64}\b"),
    ),
    "obvious production or customer data": (
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        re.compile(r"\b(?:\d{4}[ -]){3}\d{4}\b"),
        re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
        re.compile(r"\bcustomer[_ -]?(?!data\b)[A-Za-z0-9-]{4,}\b", re.I),
    ),
}

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


def collect_handoff_document_problems(documents: dict[pathlib.Path, str]) -> list[str]:
    """Return diagnostics for reviewer handoff guide content and safety."""
    handoff_path = VALIDATION_DIR / "reviewer-handoff-guide.md"
    content = documents.get(handoff_path, "")
    normalized_content = _normalize_text(content)
    problems = []

    for artifact in HANDOFF_REQUIRED_ARTIFACTS:
        if artifact not in content:
            problems.append(
                f"{_relative(handoff_path)}: missing expected artifact: {artifact}"
            )

    for phrase in HANDOFF_BOUNDARY_PHRASES:
        if _normalize_text(phrase) not in normalized_content:
            problems.append(
                f"{_relative(handoff_path)}: missing required boundary phrase: "
                f"{phrase}"
            )

    for label, patterns in HANDOFF_SAFETY_PATTERNS.items():
        for pattern in patterns:
            if pattern.search(content):
                problems.append(
                    f"{_relative(handoff_path)}: contains forbidden {label} pattern"
                )
                break

    return problems


def collect_quickstart_document_problems(
    documents: dict[pathlib.Path, str],
) -> list[str]:
    """Return diagnostics for reviewer handoff sample quickstart content."""
    content = documents.get(QUICKSTART_PATH, "")
    normalized_content = _normalize_text(content)
    problems = []

    for artifact in QUICKSTART_REQUIRED_ARTIFACTS:
        if artifact not in content:
            problems.append(
                f"{_relative(QUICKSTART_PATH)}: missing expected artifact: "
                f"{artifact}"
            )

    for phrase in QUICKSTART_REQUIRED_PHRASES:
        if _normalize_text(phrase) not in normalized_content:
            problems.append(
                f"{_relative(QUICKSTART_PATH)}: missing required phrase: "
                f"{phrase}"
            )

    for label, patterns in HANDOFF_SAFETY_PATTERNS.items():
        for pattern in patterns:
            if pattern.search(content):
                problems.append(
                    f"{_relative(QUICKSTART_PATH)}: contains forbidden "
                    f"{label} pattern"
                )
                break

    return problems


def validate_evidence_bundle_reviewer_docs() -> list[str]:
    """Validate the Evidence Bundle external reviewer documentation path."""
    paths_to_read = tuple(
        dict.fromkeys(
            REQUIRED_DOCS + README_ENTRYPOINT_PATHS + HANDOFF_LINK_SOURCE_PATHS
            + QUICKSTART_LINK_SOURCE_PATHS
        ).keys()
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
        collect_missing_links(
            documents,
            HANDOFF_LINK_SOURCE_PATHS,
            ("reviewer-handoff-guide.md",),
        )
    )
    problems.extend(
        collect_missing_links(
            documents,
            QUICKSTART_LINK_SOURCE_PATHS,
            ("reviewer-handoff-sample-quickstart.md",),
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
    problems.extend(collect_handoff_document_problems(documents))
    problems.extend(collect_quickstart_document_problems(documents))
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
