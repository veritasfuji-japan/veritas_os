"""Tests for scripts/bench_summary.py output helpers."""

from __future__ import annotations

from veritas_os.scripts import bench_summary


def test_build_decision_status_counter_preserves_duplicates() -> None:
    """Repeated statuses should remain counted in benchmark summaries."""
    rows = [
        {"decision_status": "pass"},
        {"decision_status": "pass"},
        {"decision_status": "review"},
        {"decision_status": None},
        {},
    ]

    result = bench_summary._build_decision_status_counter(rows)

    assert result["pass"] == 2
    assert result["review"] == 1
