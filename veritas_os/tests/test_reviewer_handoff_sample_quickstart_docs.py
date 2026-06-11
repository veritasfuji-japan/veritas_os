"""Tests for the reviewer handoff sample quickstart documentation."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from scripts.quality.check_evidence_bundle_reviewer_docs import (
    HANDOFF_SAFETY_PATTERNS,
    QUICKSTART_REQUIRED_ARTIFACTS,
    QUICKSTART_REQUIRED_PHRASES,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
QUICKSTART_PATH = (
    REPO_ROOT / "docs/en/validation/reviewer-handoff-sample-quickstart.md"
)
DOCS_GUARD_PATH = REPO_ROOT / "scripts/quality/check_evidence_bundle_reviewer_docs.py"

REQUIRED_SAMPLE_COMMAND = (
    "veritas-evidence-bundle validate-reviewer-handoff-package --manifest "
    "samples/evidence_bundle/key_provenance_review/"
    "sample-artifact-manifest.json --base-dir "
    "samples/evidence_bundle/key_provenance_review --json --output "
    "reviewer-handoff-package-validation.json"
)

ADDITIONAL_FORBIDDEN_PATTERNS = {
    "real public key": (
        re.compile(r"-----BEGIN PUBLIC KEY-----"),
        re.compile(r"-----BEGIN CERTIFICATE-----"),
    ),
    "real fingerprint": (re.compile(r"(?i)\b[0-9a-f]{64}\b"),),
    "local absolute path": (
        re.compile(r"(?<![A-Za-z0-9])(?:/(?:Users|home|tmp|var|workspace)/)"),
        re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:\\"),
    ),
    "customer or production data": (
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        re.compile(r"\b(?:\d{4}[ -]){3}\d{4}\b"),
        re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
        re.compile(r"\bcustomer[_ -]?(?!data\b)[A-Za-z0-9-]{4,}\b", re.I),
    ),
}


def _quickstart_text() -> str:
    """Return the reviewer handoff sample quickstart text."""
    return QUICKSTART_PATH.read_text(encoding="utf-8")


def test_docs_consistency_guard_accepts_reviewer_handoff_quickstart() -> None:
    """The docs consistency guard protects the quickstart from orphaning."""
    completed = subprocess.run(
        [sys.executable, str(DOCS_GUARD_PATH)],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_quickstart_contains_required_artifacts_and_command() -> None:
    """The quickstart lists the complete sample chain and package command."""
    text = _quickstart_text()

    for artifact in QUICKSTART_REQUIRED_ARTIFACTS:
        assert artifact in text
    assert REQUIRED_SAMPLE_COMMAND in text


def test_quickstart_contains_required_boundary_phrases() -> None:
    """The quickstart keeps non-trust, non-certification, and audit boundaries."""
    normalized_text = " ".join(_quickstart_text().lower().split())

    for phrase in QUICKSTART_REQUIRED_PHRASES:
        assert " ".join(phrase.lower().split()) in normalized_text


def test_quickstart_avoids_sensitive_or_raw_diagnostic_content() -> None:
    """The quickstart remains placeholder-only and reviewer-safe."""
    text = _quickstart_text()
    all_patterns = {
        **HANDOFF_SAFETY_PATTERNS,
        **ADDITIONAL_FORBIDDEN_PATTERNS,
    }

    for label, patterns in all_patterns.items():
        assert not any(pattern.search(text) for pattern in patterns), label
