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

import importlib.util
import json
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

CommandRunner = Callable[[Path], int | None]


@dataclass(frozen=True)
class QuickstartCommandProblem:
    """A fixed diagnostic for one quickstart command guard problem."""

    check: str
    message: str


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


def run(
    *,
    quickstart_path: Path = QUICKSTART_PATH,
    command_runner: CommandRunner | None = None,
    stream: TextIO = sys.stdout,
) -> int:
    """Run the quickstart command guard and write fixed diagnostics."""
    problems = _validate_quickstart_command(quickstart_path)
    if problems:
        print("reviewer handoff quickstart command guard: FAIL", file=stream)
        for problem in problems:
            print(_format_problem(problem), file=stream)
        return 1

    runner = command_runner or _run_documented_equivalent
    with tempfile.TemporaryDirectory(prefix="veritas-reviewer-handoff-") as temp_name:
        output_path = Path(temp_name) / OUTPUT_REPORT
        exit_code = runner(output_path)
        if exit_code not in (0, 1) or not output_path.is_file():
            problems.append(
                QuickstartCommandProblem(
                    check="command_execution",
                    message="documented command did not produce a validation report",
                )
            )
        else:
            payload = _load_json_object(output_path)
            if payload is None:
                problems.append(
                    QuickstartCommandProblem(
                        check="report_json",
                        message="generated report is not valid JSON object output",
                    )
                )
            else:
                problems.extend(_validate_schema_contract(payload))

    if not problems:
        print("reviewer handoff quickstart command guard: PASS", file=stream)
        return 0

    print("reviewer handoff quickstart command guard: FAIL", file=stream)
    for problem in problems:
        print(_format_problem(problem), file=stream)
    return 1


def main() -> int:
    """CLI entry point for reviewer handoff quickstart command checks."""
    return run()


if __name__ == "__main__":  # pragma: no cover - exercised by CI.
    raise SystemExit(main())
