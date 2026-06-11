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
    EXPECTED_REPORT_SCHEMA_ID,
    EXPECTED_VALIDATED_SCHEMA_ID,
    EXPECTED_VALIDATOR,
    OUTPUT_REPORT,
    QUICKSTART_PATH,
    QUICKSTART_REPORT_SCHEMA_PATH,
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


def _run_guard_json(
    quickstart_path: Path,
    payload: dict[str, Any] | None = None,
    *,
    exit_code: int | None = 0,
    write_output: bool = True,
    output_path: Path | None = None,
) -> tuple[int, dict[str, Any], str]:
    """Run the guard in JSON mode with a fake command runner."""
    stream = io.StringIO()

    def fake_runner(command_output_path: Path) -> int | None:
        if write_output:
            _write_json(command_output_path, payload or _load_sample_report())
        return exit_code

    code = run(
        quickstart_path=quickstart_path,
        command_runner=fake_runner,
        stream=stream,
        json_report=True,
        output_path=output_path,
    )
    raw_output = stream.getvalue()
    report = json.loads(raw_output)
    assert isinstance(report, dict)
    return code, report, raw_output


def _assert_json_report_schema_valid(report: dict[str, Any]) -> None:
    """Validate a command guard JSON report against its public schema."""
    if importlib.util.find_spec("jsonschema") is None:
        pytest.skip("jsonschema is required for schema validation")

    import jsonschema

    schema = json.loads(QUICKSTART_REPORT_SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(report)


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


def test_quickstart_command_guard_json_emits_valid_json(tmp_path: Path) -> None:
    """The JSON report mode emits parseable command guard status JSON."""
    code, report, raw_output = _run_guard_json(_quickstart_copy(tmp_path))

    assert code == 0
    assert json.loads(raw_output) == report
    assert report["report_schema_id"].endswith(
        "reviewer_handoff_quickstart_command_validation_report.schema.json"
    )


def test_quickstart_command_guard_json_validates_against_schema(
    tmp_path: Path,
) -> None:
    """The JSON report mode conforms to its machine-readable schema."""
    _, report, _ = _run_guard_json(_quickstart_copy(tmp_path))

    _assert_json_report_schema_valid(report)


def test_quickstart_command_guard_json_output_matches_stdout(
    tmp_path: Path,
) -> None:
    """The --json --output report matches stdout after JSON normalization."""
    output_path = tmp_path / "guard-report.json"

    _, report, raw_output = _run_guard_json(
        _quickstart_copy(tmp_path),
        output_path=output_path,
    )

    file_report = json.loads(output_path.read_text(encoding="utf-8"))
    assert file_report == report
    assert json.loads(raw_output) == file_report


def test_quickstart_command_guard_json_success_report_ok_true(
    tmp_path: Path,
) -> None:
    """A valid quickstart command and output contract produces ok true."""
    code, report, _ = _run_guard_json(_quickstart_copy(tmp_path))

    assert code == 0
    assert report["ok"] is True
    assert report["errors"] == []


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


def test_quickstart_command_guard_json_missing_command_ok_false(
    tmp_path: Path,
) -> None:
    """A missing quickstart command produces a fixed ok false JSON report."""
    quickstart_path = tmp_path / "quickstart.md"
    quickstart_path.write_text("# Quickstart\n", encoding="utf-8")

    code, report, _ = _run_guard_json(quickstart_path)

    assert code == 1
    assert report["ok"] is False
    assert report["quickstart_exists"] is True
    assert report["command_present"] is False
    assert report["errors"] == [
        {
            "check": "documented_command",
            "message": "quickstart command does not match the guarded command",
        }
    ]


def test_quickstart_command_guard_json_execution_failure_ok_false(
    tmp_path: Path,
) -> None:
    """Command execution failures produce ok false with fixed diagnostics."""
    code, report, output = _run_guard_json(
        _quickstart_copy(tmp_path),
        exit_code=2,
        write_output=False,
    )

    assert code == 1
    assert report["ok"] is False
    assert report["command_executable"] is False
    assert report["errors"] == [
        {
            "check": "command_execution",
            "message": "documented command did not produce a validation report",
        }
    ]
    assert "exit_code" not in output


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


def test_quickstart_command_guard_json_wrong_report_schema_id_ok_false(
    tmp_path: Path,
) -> None:
    """Generated output with a wrong report_schema_id fails JSON mode."""
    payload = _load_sample_report()
    payload["report_schema_id"] = "https://veritas-os.example/schemas/changed.json"

    code, report, output = _run_guard_json(_quickstart_copy(tmp_path), payload)

    assert code == 1
    assert report["ok"] is False
    assert report["report_schema_id_valid"] is False
    assert {error["check"] for error in report["errors"]} >= {
        "report_schema_id",
        "report_schema_contract",
    }
    assert EXPECTED_REPORT_SCHEMA_ID not in output
    assert "changed.json" not in output


def test_quickstart_command_guard_rejects_wrong_validator(tmp_path: Path) -> None:
    """Generated output with a wrong validator identifier fails."""
    payload = _load_sample_report()
    payload["validator"] = "placeholder-validator"

    code, output = _run_guard(_quickstart_copy(tmp_path), payload)

    assert code == 1
    assert "validator" in output
    assert EXPECTED_VALIDATOR not in output


def test_quickstart_command_guard_json_wrong_validator_ok_false(
    tmp_path: Path,
) -> None:
    """Generated output with a wrong validator identifier fails JSON mode."""
    payload = _load_sample_report()
    payload["validator"] = "placeholder-validator"

    code, report, output = _run_guard_json(_quickstart_copy(tmp_path), payload)

    assert code == 1
    assert report["ok"] is False
    assert report["validator_valid"] is False
    assert {error["check"] for error in report["errors"]} >= {
        "validator",
        "report_schema_contract",
    }
    assert EXPECTED_VALIDATOR not in output
    assert "placeholder-validator" not in output


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


def test_quickstart_command_guard_json_non_boolean_status_ok_false(
    tmp_path: Path,
) -> None:
    """Generated output with non-boolean status fields fails JSON mode."""
    payload = _load_sample_report()
    payload["ok"] = "true"

    code, report, output = _run_guard_json(_quickstart_copy(tmp_path), payload)

    assert code == 1
    assert report["ok"] is False
    assert report["boolean_fields_valid"] is False
    assert {error["check"] for error in report["errors"]} >= {
        "boolean_status_fields",
        "report_schema_contract",
    }
    assert '"true"' not in output


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


def test_quickstart_command_guard_json_unknown_public_field_ok_false(
    tmp_path: Path,
) -> None:
    """Generated output with an unknown public field fails JSON mode."""
    payload = _load_sample_report()
    payload["unexpected_public_field"] = True

    code, report, output = _run_guard_json(_quickstart_copy(tmp_path), payload)

    assert code == 1
    assert report["ok"] is False
    assert report["no_unknown_public_fields"] is False
    assert {error["check"] for error in report["errors"]} >= {
        "public_fields",
        "report_schema_contract",
    }
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


def test_quickstart_command_guard_json_errors_not_array_ok_false(
    tmp_path: Path,
) -> None:
    """Generated output with a non-array errors field fails JSON mode."""
    payload = _load_sample_report()
    payload["errors"] = {"message": "placeholder"}

    code, report, output = _run_guard_json(_quickstart_copy(tmp_path), payload)

    assert code == 1
    assert report["ok"] is False
    assert report["errors_array_valid"] is False
    assert {error["check"] for error in report["errors"]} >= {
        "errors_array",
        "report_schema_contract",
    }
    assert "placeholder" not in output


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


def test_quickstart_command_guard_json_diagnostics_do_not_leak_raw_values(
    tmp_path: Path,
) -> None:
    """JSON diagnostics omit raw output, paths, secrets, and validator text."""
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

    code, report, output = _run_guard_json(quickstart_path, payload)

    assert code == 1
    assert report["ok"] is False
    assert report["forbidden_patterns_absent"] is True
    for marker in leak_markers:
        assert marker not in output
    assert str(tmp_path) not in output
    assert DOCUMENTED_COMMAND not in output
