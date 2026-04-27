"""Tests for bilingual documentation consistency checks."""

from scripts.quality import check_bilingual_docs


def test_bilingual_docs_checks_pass() -> None:
    """Repository documentation entrypoints should satisfy bilingual checks."""
    assert check_bilingual_docs.run() == []


def test_markdown_compression_guard_detects_overlong_line() -> None:
    """Compression guard should flag excessive non-fenced line length."""
    temp = check_bilingual_docs.REPO_ROOT / "tmp_bilingual_guard.md"
    temp.write_text(
        "x" * (check_bilingual_docs.MARKDOWN_LINE_HARD_LIMIT + 1),
        encoding="utf-8",
    )

    errors: list[str] = []
    check_bilingual_docs._check_markdown_compression_guard(temp, errors)
    temp.unlink()

    assert errors
    assert ("exceeds" in errors[0]) or ("likely compressed" in errors[0])


def test_markdown_compression_guard_ignores_long_fenced_line() -> None:
    """Compression guard should ignore long lines inside fenced code blocks."""
    temp = check_bilingual_docs.REPO_ROOT / "tmp_bilingual_guard_fenced.md"
    temp.write_text(
        "```\n"
        + "x" * (check_bilingual_docs.MARKDOWN_LINE_HARD_LIMIT + 5)
        + "\n```\n",
        encoding="utf-8",
    )

    errors: list[str] = []
    check_bilingual_docs._check_markdown_compression_guard(temp, errors)
    temp.unlink()

    assert errors == []
