"""Tests for release proof summary generation."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def _load_module():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "generate_release_readiness_report.py"
    )
    spec = spec_from_file_location("generate_release_readiness_report", module_path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


release_readiness_report = _load_module()


def test_summarize_check_classes_counts_pass_fail() -> None:
    """Check-class summary should aggregate pass/fail counts per class."""
    results = [
        {"label": "runtime-pickle-ban", "passed": True},
        {"label": "bare-except-ban", "passed": False},
        {"label": "responsibility-boundaries", "passed": True},
        {"label": "deployment-env-defaults", "passed": True},
    ]

    summary_rows = release_readiness_report.summarize_check_classes(results)
    rows_by_name = {row["class_name"]: row for row in summary_rows}

    assert rows_by_name["security"]["pass"] == 1
    assert rows_by_name["security"]["fail"] == 1
    assert rows_by_name["architecture"]["pass"] == 1
    assert rows_by_name["quality"]["pass"] == 1


def test_render_release_proof_summary_contains_assurance_boundary() -> None:
    """Rendered proof summary should include conservative assurance wording."""
    report = {
        "release_ref": "v2.2.0",
        "release_sha": "1234567890abcdef",
        "generated_at": "2026-04-24T00:00:00+00:00",
        "summary": {"governance_ready": True},
        "checks": [
            {
                "label": "runtime-pickle-ban",
                "passed": True,
                "blocking": True,
            },
            {
                "label": "operational-docs-consistency",
                "passed": False,
                "blocking": False,
            },
        ],
    }

    rendered = release_readiness_report.render_release_proof_summary(report)

    assert "Release Proof Summary" in rendered
    assert "| security | 1 | 0 | 0 |" in rendered
    assert "| documentation | 0 | 1 | 0 |" in rendered
    assert "internal assurance artifact" in rendered
    assert "not an external certification" in rendered
