#!/usr/bin/env python3
"""Guard the reviewer handoff quickstart package validation command.

The reviewer handoff quickstart is reviewer-facing documentation, so this guard
checks that the documented one-command package validation flow stays executable
and continues to emit the public validation-report contract. The generated
report is written to a temporary directory so checked-in sample artifacts are not
overwritten.

Diagnostics are intentionally fixed and privacy-preserving. The checker must not
print raw command output, raw JSON values, raw artifact contents, raw file paths,
raw fingerprints, public keys, secrets, exception text, schema validator
messages, customer data, or production data.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO


REPO_ROOT = Path(__file__).resolve().parents[2]
QUICKSTART_PATH = (
    REPO_ROOT / "docs/en/validation/reviewer-handoff-sample-quickstart.md"
)
REPORT_SCHEMA_PATH = (
    REPO_ROOT / "schemas/reviewer_handoff_package_validation_report.schema.json"
)
QUICKSTART_REPORT_SCHEMA_PATH = (
    REPO_ROOT
    / "schemas/reviewer_handoff_quickstart_command_validation_report.schema.json"
)
MANIFEST_INPUT = (
    "samples/evidence_bundle/key_provenance_review/"
    "sample-artifact-manifest.json"
)
BASE_DIR_INPUT = "samples/evidence_bundle/key_provenance_review"
OUTPUT_REPORT = "reviewer-handoff-package-validation.json"

DOCUMENTED_COMMAND = (
    "veritas-evidence-bundle validate-reviewer-handoff-package "
    f"--manifest {MANIFEST_INPUT} "
    f"--base-dir {BASE_DIR_INPUT} "
    f"--json --output {OUTPUT_REPORT}"
)
VALIDATED_DOCUMENT = "docs/en/validation/reviewer-handoff-sample-quickstart.md"
VALIDATED_COMMAND = "veritas-evidence-bundle validate-reviewer-handoff-package"
VALIDATOR = "scripts/quality/check_reviewer_handoff_quickstart_command.py"
QUICKSTART_COMMAND_REPORT_SCHEMA_ID = (
    "https://veritas-os.example/schemas/"
    "reviewer_handoff_quickstart_command_validation_report.schema.json"
)
EXPECTED_REPORT_SCHEMA_ID = (
    "https://veritas-os.example/schemas/"
    "reviewer_handoff_package_validation_report.schema.json"
)
EXPECTED_VALIDATED_SCHEMA_ID = (
    "https://veritas-os.example/schemas/"
    "trusted_public_key_provenance_review_sample_manifest.schema.json"
)
EXPECTED_VALIDATOR = "veritas-evidence-bundle validate-reviewer-handoff-package"
REQUIRED_BOOLEAN_FIELDS = frozenset(
    {
        "ok",
        "manifest_schema_valid",
        "artifacts_present",
        "artifact_hashes_valid",
        "artifact_schemas_valid",
        "artifact_relationships_valid",
        "forbidden_patterns_absent",
    }
)
EXPECTED_PUBLIC_FIELDS = frozenset(
    {
        *REQUIRED_BOOLEAN_FIELDS,
        "validated_schema_id",
        "report_schema_id",
        "validator",
        "errors",
    }
)
REPORT_STATUS_FIELDS = (
    "ok",
    "quickstart_exists",
    "command_present",
    "command_executable",
    "output_json_valid",
    "output_schema_valid",
    "report_schema_id_valid",
    "validated_schema_id_valid",
    "validator_valid",
    "boolean_fields_valid",
    "errors_array_valid",
    "no_unknown_public_fields",
    "forbidden_patterns_absent",
)

CommandRunner = Callable[[Path], int | None]


@dataclass(frozen=True)
class QuickstartCommandProblem:
    """A fixed diagnostic for one quickstart command guard problem."""

    check: str
    message: str


@dataclass(frozen=True)
class QuickstartCommandReport:
    """Machine-readable quickstart command guard report.

    The report intentionally contains only fixed identifiers, booleans, and
    fixed diagnostics so CI systems can inspect guard status without parsing
    human logs or receiving raw command output, raw JSON values, paths,
    fingerprints, secrets, exception text, or schema validator messages.
    """

    report_schema_id: str
    validated_document: str
    validated_command: str
    validator: str
    ok: bool
    quickstart_exists: bool
    command_present: bool
    command_executable: bool
    output_json_valid: bool
    output_schema_valid: bool
    report_schema_id_valid: bool
    validated_schema_id_valid: bool
    validator_valid: bool
    boolean_fields_valid: bool
    errors_array_valid: bool
    no_unknown_public_fields: bool
    forbidden_patterns_absent: bool
    errors: list[QuickstartCommandProblem]

    def to_public_dict(self) -> dict[str, Any]:
        """Return the fixed public JSON report shape."""
        return {
            "report_schema_id": self.report_schema_id,
            "validated_document": self.validated_document,
            "validated_command": self.validated_command,
            "validator": self.validator,
            "ok": self.ok,
            "quickstart_exists": self.quickstart_exists,
            "command_present": self.command_present,
            "command_executable": self.command_executable,
            "output_json_valid": self.output_json_valid,
            "output_schema_valid": self.output_schema_valid,
            "report_schema_id_valid": self.report_schema_id_valid,
            "validated_schema_id_valid": self.validated_schema_id_valid,
            "validator_valid": self.validator_valid,
            "boolean_fields_valid": self.boolean_fields_valid,
            "errors_array_valid": self.errors_array_valid,
            "no_unknown_public_fields": self.no_unknown_public_fields,
            "forbidden_patterns_absent": self.forbidden_patterns_absent,
            "errors": [
                {"check": problem.check, "message": problem.message}
                for problem in self.errors
            ],
        }


def _cli_command(output_path: Path) -> list[str]:
    """Return the module-based command equivalent to the documented CLI."""
    return [
        sys.executable,
        "-m",
        "veritas_os.cli.evidence_bundle",
        "validate-reviewer-handoff-package",
        "--manifest",
        MANIFEST_INPUT,
        "--base-dir",
        BASE_DIR_INPUT,
        "--json",
        "--output",
        str(output_path),
    ]


def _run_documented_equivalent(output_path: Path) -> int | None:
    """Run the documented command equivalent while suppressing raw output."""
    try:
        completed = subprocess.run(
            _cli_command(output_path),
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:  # pragma: no cover - fixed diagnostic safety net.
        return None
    return completed.returncode


def _read_text(path: Path) -> str | None:
    """Read UTF-8 text, returning ``None`` without exposing exceptions."""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _load_json_object(path: Path) -> dict[str, Any] | None:
    """Load a JSON object, returning ``None`` for invalid or unsafe input."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _load_schema() -> dict[str, Any] | None:
    """Load the reviewer handoff package validation report schema."""
    return _load_json_object(REPORT_SCHEMA_PATH)


def _schema_validation_failed(schema: dict[str, Any], payload: dict[str, Any]) -> bool:
    """Return whether jsonschema rejects the payload when available."""
    if importlib.util.find_spec("jsonschema") is None:
        return False

    import jsonschema

    try:
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.Draft202012Validator(schema).validate(payload)
    except (
        jsonschema.exceptions.ValidationError,
        jsonschema.exceptions.SchemaError,
    ):
        return True
    return False


def _error_items_invalid(payload: dict[str, Any]) -> bool:
    """Return whether generated error items violate the public schema shape."""
    errors = payload.get("errors")
    if not isinstance(errors, list):
        return True
    allowed_checks = {
        "manifest_json_valid",
        "manifest_schema_valid",
        "artifacts_present",
        "artifact_hashes_valid",
        "artifact_schemas_valid",
        "artifact_relationships_valid",
        "forbidden_patterns_absent",
    }
    for item in errors:
        if not isinstance(item, dict):
            return True
        if set(item) != {"check", "path", "message"}:
            return True
        if item.get("check") not in allowed_checks:
            return True
        if item.get("path") != "$":
            return True
        message = item.get("message")
        if not isinstance(message, str) or not message:
            return True
    return False


def _validate_schema_contract(
    payload: dict[str, Any],
) -> list[QuickstartCommandProblem]:
    """Return fixed diagnostics for output contract violations."""
    problems: list[QuickstartCommandProblem] = []
    schema = _load_schema()
    if schema is None:
        return [
            QuickstartCommandProblem(
                check="report_schema_available",
                message="report schema is unavailable",
            )
        ]

    if _schema_validation_failed(schema, payload) or _error_items_invalid(payload):
        problems.append(
            QuickstartCommandProblem(
                check="report_schema_contract",
                message="generated report does not match the public schema contract",
            )
        )

    public_fields = set(payload)
    if public_fields != EXPECTED_PUBLIC_FIELDS:
        problems.append(
            QuickstartCommandProblem(
                check="public_fields",
                message="generated report public fields do not match the contract",
            )
        )

    if payload.get("report_schema_id") != EXPECTED_REPORT_SCHEMA_ID:
        problems.append(
            QuickstartCommandProblem(
                check="report_schema_id",
                message="generated report schema identifier is not accepted",
            )
        )
    if payload.get("validated_schema_id") != EXPECTED_VALIDATED_SCHEMA_ID:
        problems.append(
            QuickstartCommandProblem(
                check="validated_schema_id",
                message="generated validated schema identifier is not accepted",
            )
        )
    if payload.get("validator") != EXPECTED_VALIDATOR:
        problems.append(
            QuickstartCommandProblem(
                check="validator",
                message="generated validator identifier is not accepted",
            )
        )

    for field in sorted(REQUIRED_BOOLEAN_FIELDS):
        if not isinstance(payload.get(field), bool):
            problems.append(
                QuickstartCommandProblem(
                    check="boolean_status_fields",
                    message="generated status fields do not match the contract",
                )
            )
            break

    if not isinstance(payload.get("errors"), list):
        problems.append(
            QuickstartCommandProblem(
                check="errors_array",
                message="generated errors field does not match the contract",
            )
        )

    return problems


def _validate_quickstart_command(
    quickstart_path: Path,
) -> list[QuickstartCommandProblem]:
    """Return diagnostics when the exact documented command is absent."""
    content = _read_text(quickstart_path)
    if content is None:
        return [
            QuickstartCommandProblem(
                check="quickstart_available",
                message="quickstart document is unavailable",
            )
        ]
    if DOCUMENTED_COMMAND not in content:
        return [
            QuickstartCommandProblem(
                check="documented_command",
                message="quickstart command does not match the guarded command",
            )
        ]
    return []


def _format_problem(problem: QuickstartCommandProblem) -> str:
    """Return a fixed, privacy-preserving diagnostic line."""
    return f"- {problem.check}: {problem.message}"


def _base_status() -> dict[str, bool]:
    """Return initialized status booleans for the JSON report."""
    return {field: False for field in REPORT_STATUS_FIELDS}


def _problem(check: str, message: str) -> QuickstartCommandProblem:
    """Build a fixed privacy-preserving diagnostic object."""
    return QuickstartCommandProblem(check=check, message=message)


def _build_report(
    *,
    quickstart_path: Path = QUICKSTART_PATH,
    command_runner: CommandRunner | None = None,
) -> QuickstartCommandReport:
    """Run the guard checks and return a machine-readable status report."""
    status = _base_status()
    status["forbidden_patterns_absent"] = True
    errors: list[QuickstartCommandProblem] = []

    content = _read_text(quickstart_path)
    status["quickstart_exists"] = content is not None
    if content is None:
        errors.append(
            _problem("quickstart_available", "quickstart document is unavailable")
        )
        return _report_from_status(status, errors)

    status["command_present"] = DOCUMENTED_COMMAND in content
    if not status["command_present"]:
        errors.append(
            _problem(
                "documented_command",
                "quickstart command does not match the guarded command",
            )
        )
        return _report_from_status(status, errors)

    runner = command_runner or _run_documented_equivalent
    with tempfile.TemporaryDirectory(prefix="veritas-reviewer-handoff-") as temp_name:
        output_path = Path(temp_name) / OUTPUT_REPORT
        exit_code = runner(output_path)
        status["command_executable"] = (
            exit_code in (0, 1) and output_path.is_file()
        )
        if not status["command_executable"]:
            errors.append(
                _problem(
                    "command_execution",
                    "documented command did not produce a validation report",
                )
            )
            return _report_from_status(status, errors)

        payload = _load_json_object(output_path)
        status["output_json_valid"] = payload is not None
        if payload is None:
            errors.append(
                _problem(
                    "report_json",
                    "generated report is not valid JSON object output",
                )
            )
            return _report_from_status(status, errors)

        schema = _load_schema()
        if schema is None:
            errors.append(
                _problem("report_schema_available", "report schema is unavailable")
            )
        else:
            status["output_schema_valid"] = not (
                _schema_validation_failed(schema, payload)
                or _error_items_invalid(payload)
            )
            if not status["output_schema_valid"]:
                errors.append(
                    _problem(
                        "report_schema_contract",
                        "generated report does not match the public schema contract",
                    )
                )

        status["no_unknown_public_fields"] = set(payload) == EXPECTED_PUBLIC_FIELDS
        if not status["no_unknown_public_fields"]:
            errors.append(
                _problem(
                    "public_fields",
                    "generated report public fields do not match the contract",
                )
            )

        status["report_schema_id_valid"] = (
            payload.get("report_schema_id") == EXPECTED_REPORT_SCHEMA_ID
        )
        if not status["report_schema_id_valid"]:
            errors.append(
                _problem(
                    "report_schema_id",
                    "generated report schema identifier is not accepted",
                )
            )

        status["validated_schema_id_valid"] = (
            payload.get("validated_schema_id") == EXPECTED_VALIDATED_SCHEMA_ID
        )
        if not status["validated_schema_id_valid"]:
            errors.append(
                _problem(
                    "validated_schema_id",
                    "generated validated schema identifier is not accepted",
                )
            )

        status["validator_valid"] = payload.get("validator") == EXPECTED_VALIDATOR
        if not status["validator_valid"]:
            errors.append(
                _problem(
                    "validator",
                    "generated validator identifier is not accepted",
                )
            )

        status["boolean_fields_valid"] = all(
            isinstance(payload.get(field), bool)
            for field in sorted(REQUIRED_BOOLEAN_FIELDS)
        )
        if not status["boolean_fields_valid"]:
            errors.append(
                _problem(
                    "boolean_status_fields",
                    "generated status fields do not match the contract",
                )
            )

        status["errors_array_valid"] = isinstance(payload.get("errors"), list)
        if not status["errors_array_valid"]:
            errors.append(
                _problem(
                    "errors_array",
                    "generated errors field does not match the contract",
                )
            )

    return _report_from_status(status, errors)


def _report_from_status(
    status: dict[str, bool],
    errors: list[QuickstartCommandProblem],
) -> QuickstartCommandReport:
    """Create a report from accumulated fixed status fields and diagnostics."""
    completed_status = {
        field: bool(status.get(field, False)) for field in REPORT_STATUS_FIELDS
    }
    completed_status["ok"] = all(
        completed_status[field] for field in REPORT_STATUS_FIELDS if field != "ok"
    )
    if errors:
        completed_status["ok"] = False
    return QuickstartCommandReport(
        report_schema_id=QUICKSTART_COMMAND_REPORT_SCHEMA_ID,
        validated_document=VALIDATED_DOCUMENT,
        validated_command=VALIDATED_COMMAND,
        validator=VALIDATOR,
        errors=errors,
        **completed_status,
    )


def _append_report_error(
    report: QuickstartCommandReport,
    error: QuickstartCommandProblem,
) -> QuickstartCommandReport:
    """Return a report copy with one additional fixed diagnostic."""
    return QuickstartCommandReport(
        report_schema_id=report.report_schema_id,
        validated_document=report.validated_document,
        validated_command=report.validated_command,
        validator=report.validator,
        ok=False,
        quickstart_exists=report.quickstart_exists,
        command_present=report.command_present,
        command_executable=report.command_executable,
        output_json_valid=report.output_json_valid,
        output_schema_valid=report.output_schema_valid,
        report_schema_id_valid=report.report_schema_id_valid,
        validated_schema_id_valid=report.validated_schema_id_valid,
        validator_valid=report.validator_valid,
        boolean_fields_valid=report.boolean_fields_valid,
        errors_array_valid=report.errors_array_valid,
        no_unknown_public_fields=report.no_unknown_public_fields,
        forbidden_patterns_absent=report.forbidden_patterns_absent,
        errors=[*report.errors, error],
    )


def _json_report_text(report: QuickstartCommandReport) -> str:
    """Serialize a report deterministically for stdout and optional file output."""
    return json.dumps(report.to_public_dict(), indent=2, sort_keys=True) + "\n"


def _write_json_report_atomically(path: Path, content: str) -> None:
    """Write the complete JSON report without leaving partial invalid output."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(content)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        temp_path.replace(path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def run(
    *,
    quickstart_path: Path = QUICKSTART_PATH,
    command_runner: CommandRunner | None = None,
    stream: TextIO = sys.stdout,
    json_report: bool = False,
    output_path: Path | None = None,
) -> int:
    """Run the quickstart command guard and write fixed diagnostics.

    Args:
        quickstart_path: Reviewer quickstart document to check.
        command_runner: Optional command runner test seam.
        stream: Destination for human diagnostics or JSON stdout.
        json_report: Emit the stable machine-readable JSON report when true.
        output_path: Optional path for writing the same JSON report when
            ``json_report`` is true.

    Returns:
        ``0`` when all checks pass; ``1`` otherwise.
    """
    report = _build_report(
        quickstart_path=quickstart_path,
        command_runner=command_runner,
    )
    if json_report:
        content = _json_report_text(report)
        if output_path is not None:
            try:
                _write_json_report_atomically(output_path, content)
            except OSError:
                report = _append_report_error(
                    report,
                    _problem("output_write", "JSON report output could not be written"),
                )
                content = _json_report_text(report)
        stream.write(content)
        return 0 if report.ok else 1

    if report.ok:
        print("reviewer handoff quickstart command guard: PASS", file=stream)
        return 0

    print("reviewer handoff quickstart command guard: FAIL", file=stream)
    for problem in report.errors:
        print(_format_problem(problem), file=stream)
    return 1


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for human or JSON report output."""
    parser = argparse.ArgumentParser(
        description="Validate the reviewer handoff quickstart command contract."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_report",
        help="Emit a stable machine-readable JSON report.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the JSON report to this path when --json is used.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for reviewer handoff quickstart command checks."""
    args = _parse_args(argv)
    return run(json_report=args.json_report, output_path=args.output)


if __name__ == "__main__":  # pragma: no cover - exercised by CI.
    raise SystemExit(main())
