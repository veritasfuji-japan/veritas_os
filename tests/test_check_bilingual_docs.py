"""Tests for bilingual documentation consistency checks."""

from scripts.check_bilingual_docs import run_checks


def test_bilingual_docs_checks_pass() -> None:
    """Repository documentation entrypoints should satisfy bilingual checks."""
    assert run_checks() == []
