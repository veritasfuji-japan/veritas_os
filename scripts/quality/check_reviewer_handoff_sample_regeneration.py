#!/usr/bin/env python3
"""Check that reviewer handoff sample reports match CLI regeneration.

The checked-in reviewer handoff validation reports are reviewer-facing sample
artifacts. This guard regenerates those reports through the evidence-bundle CLI
into a temporary directory and compares normalized JSON with the committed
samples so CLI behavior and documented sample outputs cannot drift silently.

Diagnostics are intentionally fixed and artifact-name-only. The checker must not
print raw artifact contents, raw JSON values, raw fingerprints, raw keys,
secrets, local absolute paths, exception text, schema validator messages, or
customer/production data.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO


REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_DIR = REPO_ROOT / "samples/evidence_bundle/key_provenance_review"

REVIEW_RESULT_INPUT = "reviewer-handoff-review-result.json"
MANIFEST_INPUT = "sample-artifact-manifest.json"
REVIEW_RESULT_VALIDATION_REPORT = "reviewer-review-result-validation.json"
REVIEW_RESULT_REPORT_VALIDATION_REPORT = (
    "reviewer-review-result-report-validation.json"
)
HANDOFF_PACKAGE_VALIDATION_REPORT = "reviewer-handoff-package-validation.json"
QUICKSTART_COMMAND_VALIDATION_REPORT = (
    "reviewer-handoff-quickstart-command-validation.json"
)

REGENERATED_REPORTS = (
    REVIEW_RESULT_VALIDATION_REPORT,
    REVIEW_RESULT_REPORT_VALIDATION_REPORT,
    HANDOFF_PACKAGE_VALIDATION_REPORT,
    QUICKSTART_COMMAND_VALIDATION_REPORT,
)


@dataclass(frozen=True)
class RegenerationProblem:
    """A fixed diagnostic for one sample regeneration problem."""

    artifact_name: str
    check: str
    message: str


def _canonical_json(path: Path) -> str | None:
    """Return stable JSON text for comparison, or ``None`` for unsafe input."""
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _run_command(command: list[str]) -> int | None:
    """Run a regeneration command while suppressing raw command output."""
    try:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:  # pragma: no cover - fixed diagnostic safety net.
        return None
    return completed.returncode


def _cli_command(args: list[str]) -> list[str]:
    """Return the module-based CLI invocation used by CI and local checks."""
    return [sys.executable, "-m", "veritas_os.cli.evidence_bundle", *args]


def _script_command(script: str, args: list[str]) -> list[str]:
    """Return a repository script invocation used by regeneration checks."""
    return [sys.executable, script, *args]


def _regenerate_reports(sample_dir: Path, temp_dir: Path) -> list[RegenerationProblem]:
    """Regenerate reviewer handoff reports into ``temp_dir`` using CLI behavior."""
    commands = (
        (
            REVIEW_RESULT_VALIDATION_REPORT,
            _cli_command(
                [
                    "validate-review-result",
                    "--result",
                    str(sample_dir / REVIEW_RESULT_INPUT),
                    "--json",
                    "--output",
                    str(temp_dir / REVIEW_RESULT_VALIDATION_REPORT),
                ]
            ),
        ),
        (
            REVIEW_RESULT_REPORT_VALIDATION_REPORT,
            _cli_command(
                [
                    "validate-review-result-report",
                    "--result",
                    str(temp_dir / REVIEW_RESULT_VALIDATION_REPORT),
                    "--json",
                    "--output",
                    str(temp_dir / REVIEW_RESULT_REPORT_VALIDATION_REPORT),
                ]
            ),
        ),
        (
            HANDOFF_PACKAGE_VALIDATION_REPORT,
            _cli_command(
                [
                    "validate-reviewer-handoff-package",
                    "--manifest",
                    str(sample_dir / MANIFEST_INPUT),
                    "--base-dir",
                    str(sample_dir),
                    "--json",
                    "--output",
                    str(temp_dir / HANDOFF_PACKAGE_VALIDATION_REPORT),
                ]
            ),
        ),
        (
            QUICKSTART_COMMAND_VALIDATION_REPORT,
            _script_command(
                "scripts/quality/check_reviewer_handoff_quickstart_command.py",
                [
                    "--json",
                    "--output",
                    str(temp_dir / QUICKSTART_COMMAND_VALIDATION_REPORT),
                ],
            ),
        ),
    )

    problems: list[RegenerationProblem] = []
    for artifact_name, args in commands:
        exit_code = _run_command(args)
        generated_path = temp_dir / artifact_name
        if exit_code not in (0, 1) or not generated_path.is_file():
            problems.append(
                RegenerationProblem(
                    artifact_name=artifact_name,
                    check="regeneration_command",
                    message="regeneration command did not produce a report",
                )
            )
    return problems


def _compare_reports(sample_dir: Path, temp_dir: Path) -> list[RegenerationProblem]:
    """Compare regenerated and checked-in reports with normalized JSON."""
    problems: list[RegenerationProblem] = []
    for artifact_name in REGENERATED_REPORTS:
        checked_in = _canonical_json(sample_dir / artifact_name)
        regenerated = _canonical_json(temp_dir / artifact_name)
        if checked_in is None:
            problems.append(
                RegenerationProblem(
                    artifact_name=artifact_name,
                    check="checked_in_json",
                    message="checked-in report is not valid JSON",
                )
            )
            continue
        if regenerated is None:
            problems.append(
                RegenerationProblem(
                    artifact_name=artifact_name,
                    check="regenerated_json",
                    message="regenerated report is not valid JSON",
                )
            )
            continue
        if checked_in != regenerated:
            problems.append(
                RegenerationProblem(
                    artifact_name=artifact_name,
                    check="normalized_report_match",
                    message="regenerated report differs from checked-in sample",
                )
            )
    return problems


def collect_regeneration_problems(
    sample_dir: Path = SAMPLE_DIR,
) -> list[RegenerationProblem]:
    """Return deterministic sample regeneration problems for ``sample_dir``."""
    if not sample_dir.is_dir():
        return [
            RegenerationProblem(
                artifact_name="reviewer-handoff-sample",
                check="sample_directory",
                message="sample directory is unavailable",
            )
        ]

    with tempfile.TemporaryDirectory(prefix="reviewer-handoff-regeneration-") as raw:
        temp_dir = Path(raw)
        problems = _regenerate_reports(sample_dir, temp_dir)
        problems.extend(_compare_reports(sample_dir, temp_dir))
    return problems


def run(sample_dir: Path = SAMPLE_DIR, stream: TextIO = sys.stderr) -> int:
    """Run the regeneration check and write fixed diagnostics to ``stream``."""
    problems = collect_regeneration_problems(sample_dir)
    if not problems:
        print("reviewer handoff sample regeneration: PASS", file=stream)
        return 0

    print("reviewer handoff sample regeneration: FAIL", file=stream)
    for problem in problems:
        print(
            f"error [{problem.artifact_name}:{problem.check}]: {problem.message}",
            file=stream,
        )
    return 1


def main() -> int:
    """CLI entry point for reviewer handoff sample regeneration checks."""
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
