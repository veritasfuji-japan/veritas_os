"""Dry-run contract tests for staged readiness Makefile targets."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_make_dry_run(target: str) -> str:
    """Run `make -n` for a target and return combined process output."""
    if shutil.which("make") is None:
        pytest.skip("make is not available in this environment")

    result = subprocess.run(
        ["make", "-n", target],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    combined_output = result.stdout + result.stderr
    assert result.returncode == 0, combined_output
    return combined_output


def _mentions_make_command(text: str, target: str) -> bool:
    """Return whether text references `make <target>` as an exact command."""
    pattern = rf"(?<![\w-])make\s+{re.escape(target)}(?![\w-])"
    return re.search(pattern, text) is not None


def _makefile_logical_lines(text: str) -> list[str]:
    """Join Makefile backslash-continued logical lines."""
    logical_lines: list[str] = []
    current = ""

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if line.endswith("\\"):
            current += line[:-1] + " "
            continue
        logical_lines.append(current + line)
        current = ""

    if current:
        logical_lines.append(current)

    return logical_lines


def _phony_tokens(makefile_text: str) -> set[str]:
    """Return tokens declared across all .PHONY logical lines."""
    tokens: set[str] = set()
    for line in _makefile_logical_lines(makefile_text):
        stripped = line.strip()
        if stripped.startswith(".PHONY:"):
            tokens.update(stripped.split()[1:])
    return tokens


def test_validate_staged_report_dry_run_keeps_no_subreport_path() -> None:
    """Existing staged report target must remain the no-subreport path."""
    output = _run_make_dry_run("validate-staged-report")

    assert "scripts/generate_staged_readiness_report.py" in output
    assert "--output release-artifacts/staged-readiness-report.json" in output
    assert "--text-output release-artifacts/staged-readiness-report.txt" in output

    assert "--compose-report" not in output
    assert "--live-report" not in output
    assert "compose_validation.sh" not in output
    assert "live_provider_validation.sh" not in output


def test_validate_staged_report_with_subreports_dry_run_attaches_subreports() -> None:
    """Subreport target must generate and attach compose/live JSON reports."""
    output = _run_make_dry_run("validate-staged-report-with-subreports")

    compose_cmd = (
        "scripts/compose_validation.sh "
        "--json-report=release-artifacts/compose-validation-report.json"
    )
    live_cmd = (
        "scripts/live_provider_validation.sh "
        "--json-report=release-artifacts/live-provider-report.json"
    )
    generator_cmd = "scripts/generate_staged_readiness_report.py"

    assert compose_cmd in output
    assert live_cmd in output
    assert generator_cmd in output

    compose_index = output.index(compose_cmd)
    live_index = output.index(live_cmd)
    generator_index = output.index(generator_cmd)

    assert compose_index < live_index < generator_index
    assert "--compose-report release-artifacts/compose-validation-report.json" in output
    assert "--live-report release-artifacts/live-provider-report.json" in output
    assert "--output release-artifacts/staged-readiness-report.json" in output
    assert "--text-output release-artifacts/staged-readiness-report.txt" in output


def test_staged_readiness_make_targets_are_phony() -> None:
    """Makefile should mark both staged readiness targets as phony."""
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    phony_tokens = _phony_tokens(makefile)

    assert phony_tokens, "No .PHONY declarations found in Makefile"
    assert "validate-staged-report" in phony_tokens
    assert "validate-staged-report-with-subreports" in phony_tokens


def test_docs_reference_staged_readiness_make_targets() -> None:
    """Docs should reference both staged readiness Make targets by name."""
    docs = [
        REPO_ROOT / "docs/en/operations/operational-readiness-runbook.md",
        REPO_ROOT / "docs/en/validation/production-validation.md",
        REPO_ROOT / "docs/ja/validation/production-validation.md",
    ]

    for path in docs:
        text = path.read_text(encoding="utf-8")
        assert _mentions_make_command(text, "validate-staged-report")
        assert _mentions_make_command(text, "validate-staged-report-with-subreports")
