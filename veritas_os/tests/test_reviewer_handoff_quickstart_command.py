"""Tests for the reviewer handoff quickstart command guard."""

from __future__ import annotations

import importlib.util
import io
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

from scripts.quality.check_reviewer_handoff_quickstart_command import (
    DOCUMENTED_COMMAND,
    EXPECTED_VALIDATED_SCHEMA_ID,
    EXPECTED_VALIDATOR,
    OUTPUT_REPORT,
    QUICKSTART_PATH,
    REQUIRED_BOOLEAN_FIELDS,
    _cli_command,
    run,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_REPORT = (
    REPO_ROOT
    / "samples/evidence_bundle/key_provenance_review"
    / "reviewer-handoff-package-validation.json"
)


def _load_sample_report() -> dict[str, Any]:
    """Load the checked-in package validation report as a baseline."""
    payload = json.loads(SAMPLE_REPORT.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write deterministic JSON for fake command output."""
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _quickstart_copy(tmp_path: Path) -> Path:
    """Copy the quickstart to a temporary editable path."""
    quickstart_path = tmp_path / "quickstart.md"
    shutil.copyfile(QUICKSTART_PATH, quickstart_path)
    return quickstart_path


def _run_guard(
    quickstart_path: Path,
    payload: dict[str, Any] | None = None,
) -> tuple[int, str]:
    """Run the guard with a fake command runner and capture diagnostics."""
    stream = io.StringIO()

    def fake_runner(output_path: Path) -> int:
        _write_json(output_path, payload or _load_sample_report())
        return 0

    code = run(
        quickstart_path=quickstart_path,
        command_runner=fake_runner,
        stream=stream,
    )
    return code, stream.getvalue()


def test_quickstart_command_guard_uses_module_cli_invocation(tmp_path: Path) -> None:
    """The executable guard invokes the CLI through the Python module."""
    output_path = tmp_path / OUTPUT_REPORT
    command = _cli_command(output_path)

    assert command[:3] == [sys.executable, "-m", "veritas_os.cli.evidence_bundle"]
    assert command[3:5] == ["validate-reviewer-handoff-package", "--manifest"]
    assert command[-2:] == ["--output", str(output_path)]


def test_quickstart_command_guard_accepts_current_quickstart() -> None:
    """The current reviewer quickstart command is executable and contract-valid."""
    if importlib.util.find_spec("jsonschema") is None:
        pytest.skip("jsonschema is required by the evidence-bundle CLI")
    stream = io.StringIO()
    code = run(stream=stream)

    assert code == 0
    assert "PASS" in stream.getvalue()


def test_quickstart_command_guard_rejects_missing_command(tmp_path: Path) -> None:
    """A quickstart without the guarded command fails before execution."""
    quickstart_path = tmp_path / "quickstart.md"
    quickstart_path.write_text(
        "# Quickstart\n\nNo guarded command here.\n",
        encoding="utf-8",
    )

    code, output = _run_guard(quickstart_path)

    assert code == 1
    assert "documented_command" in output


def test_quickstart_command_guard_rejects_changed_command_path(
    tmp_path: Path,
) -> None:
    """Changing the documented manifest path fails the exact command guard."""
    quickstart_path = _quickstart_copy(tmp_path)
    content = quickstart_path.read_text(encoding="utf-8")
    quickstart_path.write_text(
        content.replace(
            "samples/evidence_bundle/key_provenance_review/"
            "sample-artifact-manifest.json",
            "samples/evidence_bundle/key_provenance_review/changed-manifest.json",
        ),
        encoding="utf-8",
    )

    code, output = _run_guard(quickstart_path)

    assert code == 1
    assert "documented_command" in output


def test_quickstart_command_guard_rejects_missing_report_schema_id(
    tmp_path: Path,
) -> None:
    """Generated output without report_schema_id fails the contract guard."""
    payload = _load_sample_report()
    payload.pop("report_schema_id")

    code, output = _run_guard(_quickstart_copy(tmp_path), payload)

    assert code == 1
    assert "report_schema_id" in output


def test_quickstart_command_guard_rejects_wrong_validator(tmp_path: Path) -> None:
    """Generated output with a wrong validator identifier fails."""
    payload = _load_sample_report()
    payload["validator"] = "placeholder-validator"

    code, output = _run_guard(_quickstart_copy(tmp_path), payload)

    assert code == 1
    assert "validator" in output
    assert EXPECTED_VALIDATOR not in output


def test_quickstart_command_guard_rejects_wrong_validated_schema_id(
    tmp_path: Path,
) -> None:
    """Generated output with a wrong validated schema identifier fails."""
    payload = _load_sample_report()
    payload["validated_schema_id"] = "https://veritas-os.example/schemas/changed.json"

    code, output = _run_guard(_quickstart_copy(tmp_path), payload)

    assert code == 1
    assert "validated_schema_id" in output
    assert EXPECTED_VALIDATED_SCHEMA_ID not in output


def test_quickstart_command_guard_rejects_non_boolean_status_fields(
    tmp_path: Path,
) -> None:
    """Generated output with non-boolean status fields fails."""
    payload = _load_sample_report()
    for field in REQUIRED_BOOLEAN_FIELDS:
        payload[field] = "true"
        break

    code, output = _run_guard(_quickstart_copy(tmp_path), payload)

    assert code == 1
    assert "boolean_status_fields" in output


def test_quickstart_command_guard_rejects_unknown_public_field(
    tmp_path: Path,
) -> None:
    """Generated output with an unknown public field fails."""
    payload = _load_sample_report()
    payload["unexpected_public_field"] = True

    code, output = _run_guard(_quickstart_copy(tmp_path), payload)

    assert code == 1
    assert "public_fields" in output
    assert "unexpected_public_field" not in output


def test_quickstart_command_guard_rejects_non_array_errors(
    tmp_path: Path,
) -> None:
    """Generated output with a non-array errors field fails."""
    payload = _load_sample_report()
    payload["errors"] = {"message": "placeholder"}

    code, output = _run_guard(_quickstart_copy(tmp_path), payload)

    assert code == 1
    assert "errors_array" in output


def test_quickstart_command_guard_diagnostics_do_not_leak_raw_values(
    tmp_path: Path,
) -> None:
    """Failure diagnostics omit raw output, paths, secrets, and validator text."""
    quickstart_path = _quickstart_copy(tmp_path)
    payload = _load_sample_report()
    leak_markers = (
        "raw-command-stdout-customer-production-data",
        "raw-command-stderr-secret-value",
        "raw-json-value-customer-production-data",
        "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        "-----BEGIN PUBLIC KEY-----",
        "/tmp/veritas/local/absolute/path",
        "Traceback",
        "ValidationError",
        "schema validator says secret detail",
        "customer data",
        "production data",
    )
    payload["validator"] = leak_markers[2]
    payload["errors"] = [
        {"check": "manifest_json_valid", "path": "$", "message": marker}
        for marker in leak_markers[3:]
    ]

    code, output = _run_guard(quickstart_path, payload)

    assert code == 1
    for marker in leak_markers:
        assert marker not in output
    assert str(tmp_path) not in output
    assert DOCUMENTED_COMMAND not in output
