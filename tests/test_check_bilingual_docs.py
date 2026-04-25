"""Tests for bilingual documentation consistency checks."""

from scripts.quality.check_bilingual_docs import (
    _is_external_url_only_line,
    _is_long_url_or_generated_badge,
    run,
)


def test_bilingual_docs_checks_pass() -> None:
    """Repository documentation entrypoints should satisfy bilingual checks."""
    assert run() == []


def test_badge_url_is_ignored_for_length_check() -> None:
    """Shields badge URLs should be ignored by markdown readability guard."""
    line = (
        "[![CI](https://img.shields.io/badge/ci-passing-brightgreen.svg)]"
        "(https://github.com/example/repo/actions)"
    )
    assert _is_long_url_or_generated_badge(line) is True


def test_non_badge_url_is_not_auto_ignored() -> None:
    """Normal URLs should not be ignored unless line length is excessive."""
    line = "Reference: https://example.com/docs/ja/guide"
    assert _is_long_url_or_generated_badge(line) is False


def test_external_url_only_line_is_ignored() -> None:
    """A single external URL line should be exempted from long-line checks."""
    line = "https://example.com/docs/ja/very/long/path"
    assert _is_external_url_only_line(line) is True
