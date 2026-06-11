"""Validate reviewer handoff sample regeneration coverage."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.quality import check_reviewer_handoff_sample_regeneration as regen


def test_regeneration_covers_quickstart_command_report() -> None:
    """The drift guard compares the checked-in quickstart command report."""
    assert "reviewer-handoff-quickstart-command-validation.json" in (
        regen.REGENERATED_REPORTS
    )


def test_regeneration_compare_catches_quickstart_command_report_drift(
    tmp_path: Path,
) -> None:
    """Normalized JSON drift is reported for the quickstart command report."""
    sample_dir = tmp_path / "sample"
    temp_dir = tmp_path / "generated"
    sample_dir.mkdir()
    temp_dir.mkdir()

    for artifact_name in regen.REGENERATED_REPORTS:
        payload = {"ok": True, "artifact": artifact_name}
        (sample_dir / artifact_name).write_text(
            json.dumps(payload, sort_keys=True),
            encoding="utf-8",
        )
        (temp_dir / artifact_name).write_text(
            json.dumps(payload, sort_keys=True),
            encoding="utf-8",
        )

    quickstart_report = "reviewer-handoff-quickstart-command-validation.json"
    (temp_dir / quickstart_report).write_text(
        json.dumps({"ok": False, "artifact": quickstart_report}, sort_keys=True),
        encoding="utf-8",
    )

    problems = regen._compare_reports(sample_dir, temp_dir)

    assert any(
        problem.artifact_name == quickstart_report
        and problem.check == "normalized_report_match"
        for problem in problems
    )
