"""Tests for trusted public key provenance CLI validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


FINGERPRINT = "a" * 64
MISMATCHED_FINGERPRINT = "b" * 64


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
    assert str(receipt_path) not in output
    assert str(verification_result_path) not in output
    assert FINGERPRINT not in output


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
    assert str(receipt_path) not in output
    assert str(verification_result_path) not in output
    assert FINGERPRINT not in output
    assert MISMATCHED_FINGERPRINT not in output


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
    assert "value does not satisfy schema at this path" in output
    assert "'approved_by' is a required property" not in output


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
    assert "value does not satisfy schema at this path" in output
    assert "'verified' is not one of" not in output


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
    assert str(receipt_path) not in output_json
    assert str(verification_result_path) not in output_json
    assert FINGERPRINT not in output_json
    assert output["errors"] == []


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
    saved = output_path.read_text(encoding="utf-8")
    assert saved == stdout
    assert json.loads(stdout)["ok"] is True
    assert str(receipt_path) not in stdout
    assert str(verification_result_path) not in stdout
    assert str(output_path) not in stdout
    assert str(output_path) not in saved


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
    assert "failed to write key provenance validation report" in captured.err
    assert str(output_path) not in captured.err
