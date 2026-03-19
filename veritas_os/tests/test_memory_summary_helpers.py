"""Tests for extracted MemoryOS planner summary helpers."""

from __future__ import annotations

from veritas_os.core import memory_summary_helpers


def test_build_planner_summary_returns_empty_message_for_no_hits() -> None:
    """The planner summary should keep the existing no-hit fallback string."""
    result = memory_summary_helpers.build_planner_summary([])

    assert "見つかりませんでした" in result


def test_build_planner_summary_formats_tags_and_timestamp() -> None:
    """Formatted summaries should expose stable timestamp and tag labels."""
    episodic = [
        {
            "text": "important note",
            "tags": ["ops", "p1"],
            "ts": 1,
        }
    ]

    result = memory_summary_helpers.build_planner_summary(episodic)

    assert "MemoryOS 要約" in result
    assert "1970-01-01T00:00:01Z" in result
    assert "tags=['ops', 'p1']" in result
    assert "important note" in result


def test_build_planner_summary_truncates_long_text_and_handles_bad_timestamp() -> None:
    """Long text and invalid timestamps should preserve the legacy formatting contract."""
    episodic = [{"text": "x" * 130, "ts": "bad"}]

    result = memory_summary_helpers.build_planner_summary(episodic)

    assert "unknown" in result
    assert ("x" * 117) + "..." in result
