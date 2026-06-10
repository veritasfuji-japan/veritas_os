"""Tests for trusted public key provenance CLI validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest


FINGERPRINT = "a" * 64
MISMATCHED_FINGERPRINT = "b" * 64
REPORT_SCHEMA_ID = (
    "https://veritas-os.example/schemas/"
    "trusted_public_key_provenance_validation_report.schema.json"
)
REPORT_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "schemas"
    / "trusted_public_key_provenance_validation_report.schema.json"
)


def _valid_receipt_payload() -> dict[str, Any]:
    """Return a schema-valid Trusted Public Key Provenance Receipt."""
    return {
        "receipt_type": "trusted_public_key_provenance",
        "algorithm": "Ed25519",
        "public_key_fingerprint_sha256": FINGERPRINT,
        "trust_channel": "reviewer_vault",
        "received_at": "2026-06-09T00:00:00Z",
        "approved_by": "external-reviewer@example.com",
        "approval_reference": "vault://trusted/veritas/evidence-key",
        "notes": "Key fingerprint confirmed through reviewer vault record.",
        "bundle_internal_key_used": False,
    }


def _valid_verification_result_payload() -> dict[str, Any]:
    """Return a schema-valid strict authenticity verification result."""
    return {
        "ok": True,
        "tampered": False,
        "hash_integrity_ok": True,
        "signature_status": "pass",
        "signature_verified": True,
        "authenticity_ok": True,
        "authenticity_failure": None,
        "public_key_fingerprint_sha256": FINGERPRINT,
        "errors": [],
        "warnings": [],
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write a compact UTF-8 JSON fixture."""
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_valid_inputs(tmp_path: Path) -> tuple[Path, Path]:
    """Write valid receipt and verification result fixtures."""
    receipt_path = tmp_path / "trusted-public-key-provenance.json"
    verification_result_path = tmp_path / "verification-result.json"
    _write_json(receipt_path, _valid_receipt_payload())
    _write_json(verification_result_path, _valid_verification_result_payload())
    return receipt_path, verification_result_path



def _report_schema_validator() -> jsonschema.Draft202012Validator:
    """Return the validate-key-provenance report schema validator."""
    schema = json.loads(REPORT_SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


def _assert_report_matches_schema(report: dict[str, Any]) -> None:
    """Assert a validate-key-provenance JSON report matches its schema."""
    _report_schema_validator().validate(report)
    assert report["report_schema_id"] == REPORT_SCHEMA_ID


def _run_json_report(
    tmp_path: Path,
    capsys,
    *,
    receipt_payload: dict[str, Any] | None = None,
    verification_result_payload: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any], str, Path, Path]:
    """Run validate-key-provenance --json against supplied fixtures."""
    from veritas_os.cli.evidence_bundle import main

    receipt_path, verification_result_path = _write_valid_inputs(tmp_path)
    if receipt_payload is not None:
        _write_json(receipt_path, receipt_payload)
    if verification_result_payload is not None:
        _write_json(verification_result_path, verification_result_payload)

    exit_code = main(
        [
            "validate-key-provenance",
            "--receipt",
            str(receipt_path),
            "--verification-result",
            str(verification_result_path),
            "--json",
        ]
    )
    output_text = capsys.readouterr().out
    return (
        exit_code,
        json.loads(output_text),
        output_text,
        receipt_path,
        verification_result_path,
    )


def _assert_report_hides_raw_inputs(
    output_text: str,
    receipt_path: Path,
    verification_result_path: Path,
) -> None:
    """Assert public reports omit raw fingerprints, paths, and internals."""
    assert FINGERPRINT not in output_text
    assert MISMATCHED_FINGERPRINT not in output_text
    assert str(receipt_path) not in output_text
    assert str(verification_result_path) not in output_text
    assert "No such file" not in output_text
    assert "Errno" not in output_text
    assert "Traceback" not in output_text
    assert "ValidationError" not in output_text
    assert "is a required property" not in output_text
    assert "is not one of" not in output_text
    assert "value does not satisfy schema at this path" not in output_text


def test_validate_key_provenance_valid_inputs_pass(tmp_path, capsys) -> None:
    """Valid receipt and strict result with matching fingerprint pass."""
    from veritas_os.cli.evidence_bundle import main

    receipt_path, verification_result_path = _write_valid_inputs(tmp_path)

    exit_code = main(
        [
            "validate-key-provenance",
            "--receipt",
            str(receipt_path),
            "--verification-result",
            str(verification_result_path),
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Trusted public key provenance validation: PASS" in output
    assert "Receipt schema: PASS" in output
    assert "Verification result schema: PASS" in output
    assert "Fingerprint correlation: PASS" in output
    assert "Bundle-internal key used: PASS" in output
    assert "Strict authenticity result: PASS" in output
    assert FINGERPRINT not in output
    assert str(receipt_path) not in output
    assert str(verification_result_path) not in output


def test_validate_key_provenance_fingerprint_mismatch_fails(tmp_path, capsys) -> None:
    """Fingerprint mismatch fails correlation without hiding schema success."""
    from veritas_os.cli.evidence_bundle import main

    receipt_path, verification_result_path = _write_valid_inputs(tmp_path)
    verification_result = _valid_verification_result_payload()
    verification_result["public_key_fingerprint_sha256"] = MISMATCHED_FINGERPRINT
    _write_json(verification_result_path, verification_result)

    exit_code = main(
        [
            "validate-key-provenance",
            "--receipt",
            str(receipt_path),
            "--verification-result",
            str(verification_result_path),
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Trusted public key provenance validation: FAIL" in output
    assert "Receipt schema: PASS" in output
    assert "Verification result schema: PASS" in output
    assert "Fingerprint correlation: FAIL" in output
    assert FINGERPRINT not in output
    assert MISMATCHED_FINGERPRINT not in output
    assert str(receipt_path) not in output
    assert str(verification_result_path) not in output


def test_validate_key_provenance_receipt_schema_invalid_fails(tmp_path, capsys) -> None:
    """Receipt schema failures are reported as validation failures."""
    from veritas_os.cli.evidence_bundle import main

    receipt_path, verification_result_path = _write_valid_inputs(tmp_path)
    receipt = _valid_receipt_payload()
    receipt.pop("approved_by")
    _write_json(receipt_path, receipt)

    exit_code = main(
        [
            "validate-key-provenance",
            "--receipt",
            str(receipt_path),
            "--verification-result",
            str(verification_result_path),
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Receipt schema: FAIL" in output
    assert "receipt does not satisfy schema" in output
    assert "value does not satisfy schema at this path" not in output
    assert "'approved_by' is a required property" not in output
    assert str(receipt_path) not in output


def test_validate_key_provenance_verification_result_schema_invalid_fails(
    tmp_path,
    capsys,
) -> None:
    """Verification result schema failures are reported as validation failures."""
    from veritas_os.cli.evidence_bundle import main

    receipt_path, verification_result_path = _write_valid_inputs(tmp_path)
    verification_result = _valid_verification_result_payload()
    verification_result["signature_status"] = "verified"
    _write_json(verification_result_path, verification_result)

    exit_code = main(
        [
            "validate-key-provenance",
            "--receipt",
            str(receipt_path),
            "--verification-result",
            str(verification_result_path),
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Verification result schema: FAIL" in output
    assert "verification result does not satisfy schema" in output
    assert "value does not satisfy schema at this path" not in output
    assert "'verified' is not one of" not in output
    assert str(verification_result_path) not in output


def test_validate_key_provenance_bundle_internal_key_used_true_fails(
    tmp_path,
    capsys,
) -> None:
    """A receipt based on bundle-internal key material is rejected."""
    from veritas_os.cli.evidence_bundle import main

    receipt_path, verification_result_path = _write_valid_inputs(tmp_path)
    receipt = _valid_receipt_payload()
    receipt["bundle_internal_key_used"] = True
    _write_json(receipt_path, receipt)

    exit_code = main(
        [
            "validate-key-provenance",
            "--receipt",
            str(receipt_path),
            "--verification-result",
            str(verification_result_path),
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Bundle-internal key used: FAIL" in output
    assert "receipt bundle_internal_key_used must be false" in output


def test_validate_key_provenance_authenticity_false_fails(tmp_path, capsys) -> None:
    """Strict authenticity must be true in the verification result."""
    from veritas_os.cli.evidence_bundle import main

    receipt_path, verification_result_path = _write_valid_inputs(tmp_path)
    verification_result = _valid_verification_result_payload()
    verification_result["ok"] = False
    verification_result["authenticity_ok"] = False
    verification_result["authenticity_failure"] = "signature_verification_failed"
    _write_json(verification_result_path, verification_result)

    exit_code = main(
        [
            "validate-key-provenance",
            "--receipt",
            str(receipt_path),
            "--verification-result",
            str(verification_result_path),
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Strict authenticity result: FAIL" in output


def test_validate_key_provenance_json_output_stable_fields(tmp_path, capsys) -> None:
    """--json output contains stable provenance validation fields."""
    from veritas_os.cli.evidence_bundle import main

    receipt_path, verification_result_path = _write_valid_inputs(tmp_path)

    exit_code = main(
        [
            "validate-key-provenance",
            "--receipt",
            str(receipt_path),
            "--verification-result",
            str(verification_result_path),
            "--json",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["ok"] is True
    _assert_report_matches_schema(output)
    assert output["receipt_schema_valid"] is True
    assert output["verification_result_schema_valid"] is True
    assert output["fingerprint_correlation_ok"] is True
    assert output["bundle_internal_key_used_ok"] is True
    assert output["strict_authenticity_ok"] is True
    assert output["receipt_path_provided"] is True
    assert output["verification_result_path_provided"] is True
    assert "receipt_path" not in output
    assert "verification_result_path" not in output
    assert output["receipt_public_key_fingerprint_present"] is True
    assert output["verification_result_public_key_fingerprint_present"] is True
    assert "receipt_public_key_fingerprint_sha256" not in output
    assert "verification_result_public_key_fingerprint_sha256" not in output
    output_json = json.dumps(output)
    assert FINGERPRINT not in output_json
    assert str(receipt_path) not in output_json
    assert str(verification_result_path) not in output_json
    assert output["errors"] == []


def test_validate_key_provenance_json_invalid_schema_uses_fixed_errors(
    tmp_path,
    capsys,
) -> None:
    """--json schema failures expose only fixed public diagnostics."""
    from veritas_os.cli.evidence_bundle import main

    receipt_path, verification_result_path = _write_valid_inputs(tmp_path)
    receipt = _valid_receipt_payload()
    receipt.pop("approved_by")
    _write_json(receipt_path, receipt)
    verification_result = _valid_verification_result_payload()
    verification_result["signature_status"] = "verified"
    _write_json(verification_result_path, verification_result)

    exit_code = main(
        [
            "validate-key-provenance",
            "--receipt",
            str(receipt_path),
            "--verification-result",
            str(verification_result_path),
            "--json",
        ]
    )
    output_text = capsys.readouterr().out
    output = json.loads(output_text)
    messages = {error["message"] for error in output["errors"]}

    assert exit_code == 1
    assert output["receipt_schema_valid"] is False
    assert output["verification_result_schema_valid"] is False
    assert "receipt does not satisfy schema" in messages
    assert "verification result does not satisfy schema" in messages
    assert "'approved_by' is a required property" not in output_text
    assert "'verified' is not one of" not in output_text
    assert "value does not satisfy schema at this path" not in output_text
    assert FINGERPRINT not in output_text
    assert str(receipt_path) not in output_text
    assert str(verification_result_path) not in output_text


def test_validate_key_provenance_json_missing_file_hides_exception_text(
    tmp_path,
    capsys,
) -> None:
    """--json missing-file failures do not expose paths or exception text."""
    from veritas_os.cli.evidence_bundle import main

    receipt_path = tmp_path / "missing-secret-receipt.json"
    verification_result_path = tmp_path / "verification-result.json"
    _write_json(verification_result_path, _valid_verification_result_payload())

    exit_code = main(
        [
            "validate-key-provenance",
            "--receipt",
            str(receipt_path),
            "--verification-result",
            str(verification_result_path),
            "--json",
        ]
    )
    output_text = capsys.readouterr().out
    output = json.loads(output_text)

    assert exit_code == 1
    assert output["receipt_schema_valid"] is False
    assert output["receipt_path_provided"] is True
    assert "receipt does not satisfy schema" in {
        error["message"] for error in output["errors"]
    }
    assert str(receipt_path) not in output_text
    assert str(verification_result_path) not in output_text
    assert "No such file" not in output_text
    assert "Errno" not in output_text


def test_validate_key_provenance_json_output_file_matches_stdout(
    tmp_path,
    capsys,
) -> None:
    """--json --output saves the exact stdout JSON report."""
    from veritas_os.cli.evidence_bundle import main

    receipt_path, verification_result_path = _write_valid_inputs(tmp_path)
    output_path = tmp_path / "reports" / "key-provenance-validation.json"

    exit_code = main(
        [
            "validate-key-provenance",
            "--receipt",
            str(receipt_path),
            "--verification-result",
            str(verification_result_path),
            "--json",
            "--output",
            str(output_path),
        ]
    )
    stdout = capsys.readouterr().out

    assert exit_code == 0
    assert output_path.read_text(encoding="utf-8") == stdout
    saved_report = json.loads(stdout)
    assert saved_report["ok"] is True
    _assert_report_matches_schema(saved_report)
    assert str(output_path) not in stdout


def test_validate_key_provenance_json_success_validates_against_schema(
    tmp_path,
    capsys,
) -> None:
    """Successful --json report validates against the report schema."""
    exit_code, report, output_text, receipt_path, result_path = _run_json_report(
        tmp_path,
        capsys,
    )

    assert exit_code == 0
    _assert_report_matches_schema(report)
    _assert_report_hides_raw_inputs(output_text, receipt_path, result_path)


def test_validate_key_provenance_json_fingerprint_mismatch_validates_schema(
    tmp_path,
    capsys,
) -> None:
    """Fingerprint mismatch --json report validates against the schema."""
    verification_result = _valid_verification_result_payload()
    verification_result["public_key_fingerprint_sha256"] = MISMATCHED_FINGERPRINT

    exit_code, report, output_text, receipt_path, result_path = _run_json_report(
        tmp_path,
        capsys,
        verification_result_payload=verification_result,
    )

    assert exit_code == 1
    assert report["fingerprint_correlation_ok"] is False
    _assert_report_matches_schema(report)
    _assert_report_hides_raw_inputs(output_text, receipt_path, result_path)


def test_validate_key_provenance_json_receipt_schema_failure_validates_schema(
    tmp_path,
    capsys,
) -> None:
    """Receipt schema failure --json report validates against the schema."""
    receipt = _valid_receipt_payload()
    receipt.pop("approved_by")

    exit_code, report, output_text, receipt_path, result_path = _run_json_report(
        tmp_path,
        capsys,
        receipt_payload=receipt,
    )

    assert exit_code == 1
    assert report["receipt_schema_valid"] is False
    _assert_report_matches_schema(report)
    _assert_report_hides_raw_inputs(output_text, receipt_path, result_path)


def test_validate_key_provenance_json_result_schema_failure_validates_schema(
    tmp_path,
    capsys,
) -> None:
    """Verification-result schema failure report validates against schema."""
    verification_result = _valid_verification_result_payload()
    verification_result["signature_status"] = "verified"

    exit_code, report, output_text, receipt_path, result_path = _run_json_report(
        tmp_path,
        capsys,
        verification_result_payload=verification_result,
    )

    assert exit_code == 1
    assert report["verification_result_schema_valid"] is False
    _assert_report_matches_schema(report)
    _assert_report_hides_raw_inputs(output_text, receipt_path, result_path)


def test_validate_key_provenance_json_bundle_internal_key_failure_validates_schema(
    tmp_path,
    capsys,
) -> None:
    """bundle_internal_key_used true report validates against schema."""
    receipt = _valid_receipt_payload()
    receipt["bundle_internal_key_used"] = True

    exit_code, report, output_text, receipt_path, result_path = _run_json_report(
        tmp_path,
        capsys,
        receipt_payload=receipt,
    )

    assert exit_code == 1
    assert report["bundle_internal_key_used_ok"] is False
    _assert_report_matches_schema(report)
    _assert_report_hides_raw_inputs(output_text, receipt_path, result_path)


def test_validate_key_provenance_json_strict_authenticity_failure_validates_schema(
    tmp_path,
    capsys,
) -> None:
    """Strict authenticity failure report validates against schema."""
    verification_result = _valid_verification_result_payload()
    verification_result["ok"] = False
    verification_result["authenticity_ok"] = False
    verification_result["authenticity_failure"] = "signature_verification_failed"

    exit_code, report, output_text, receipt_path, result_path = _run_json_report(
        tmp_path,
        capsys,
        verification_result_payload=verification_result,
    )

    assert exit_code == 1
    assert report["strict_authenticity_ok"] is False
    _assert_report_matches_schema(report)
    _assert_report_hides_raw_inputs(output_text, receipt_path, result_path)


def test_validate_key_provenance_output_without_json_fails_clearly(
    tmp_path,
    capsys,
) -> None:
    """--output without --json fails before running validation."""
    from veritas_os.cli.evidence_bundle import main

    receipt_path, verification_result_path = _write_valid_inputs(tmp_path)

    with pytest.raises(SystemExit) as excinfo:
        main(
            [
                "validate-key-provenance",
                "--receipt",
                str(receipt_path),
                "--verification-result",
                str(verification_result_path),
                "--output",
                str(tmp_path / "report.json"),
            ]
        )

    assert excinfo.value.code == 2
    stderr = capsys.readouterr().err
    assert "validate-key-provenance --output requires --json" in stderr


def test_validate_key_provenance_output_write_failure_is_clear(
    tmp_path,
    capsys,
) -> None:
    """--json --output write failures exit non-zero with clear stderr."""
    from veritas_os.cli.evidence_bundle import main

    receipt_path, verification_result_path = _write_valid_inputs(tmp_path)
    output_path = tmp_path / "existing-directory"
    output_path.mkdir()

    exit_code = main(
        [
            "validate-key-provenance",
            "--receipt",
            str(receipt_path),
            "--verification-result",
            str(verification_result_path),
            "--json",
            "--output",
            str(output_path),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert captured.err.strip() == (
        "error: failed to write key provenance validation report"
    )
    assert str(output_path) not in captured.err
