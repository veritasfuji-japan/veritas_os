"""Focused tests for positive certification wording guard behavior."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.quality.check_operational_docs_consistency import (
    FORBIDDEN_POSITIVE_CERTIFICATION_PHRASES,
    _find_forbidden_positive_certification_phrases,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_positive_certification_phrases_are_reported(tmp_path: Path) -> None:
    """Every forbidden positive phrase should be reported exactly once."""
    for phrase in FORBIDDEN_POSITIVE_CERTIFICATION_PHRASES:
        filename = phrase.replace(" ", "_").lower().replace("/", "_")
        path = tmp_path / f"{filename}.md"
        path.write_text(f"This doc says: {phrase}.", encoding="utf-8")

        problems = _find_forbidden_positive_certification_phrases(path)

        assert len(problems) == 1
        assert "forbidden over-certification wording" in problems[0]
        assert phrase in problems[0]


def test_positive_certification_phrases_are_case_insensitive(
    tmp_path: Path,
) -> None:
    """Forbidden phrases should be detected regardless of case."""
    path = tmp_path / "case.md"
    path.write_text("this says RELEASE CERTIFICATION for production", encoding="utf-8")

    problems = _find_forbidden_positive_certification_phrases(path)

    assert any("Release certification" in problem for problem in problems)


def test_non_certification_boundary_language_is_allowed(tmp_path: Path) -> None:
    """Boundary/disclaimer wording must stay allowed by the guard."""
    path = tmp_path / "allowed-boundary.md"
    allowed_text = """
This document is not third-party certification.
This is not full production certification.
The report is evidence for release review, not production certification.
The matrix documents non-certification boundaries.
Status: Prepared / Not certified.
"""
    path.write_text(allowed_text, encoding="utf-8")

    problems = _find_forbidden_positive_certification_phrases(path)

    assert problems == []


def test_missing_file_reports_missing_file(tmp_path: Path) -> None:
    """Missing files should return the expected diagnostic."""
    missing_path = tmp_path / "missing.md"

    problems = _find_forbidden_positive_certification_phrases(missing_path)

    assert problems == [f"Missing file: {missing_path}"]


def test_operational_docs_consistency_script_runs_successfully() -> None:
    """Checker script should execute successfully against current docs."""
    result = subprocess.run(
        [sys.executable, "scripts/quality/check_operational_docs_consistency.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "Operational documentation consistency checks passed." in output
