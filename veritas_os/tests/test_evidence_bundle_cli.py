"""Tests for evidence bundle CLI and financial sample fixture."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pytest

from veritas_os.audit import trustlog_signed


SCHEMA_PATH = Path("schemas/evidence_bundle_verification_result.schema.json")
VALIDATION_REPORT_SCHEMA_PATH = Path(
    "schemas/evidence_bundle_validation_report.schema.json"
)
REPORT_SCHEMA_ID = (
    "https://veritas-os.example/schemas/"
    "evidence_bundle_validation_report.schema.json"
)
VALIDATED_SCHEMA_ID = (
    "https://veritas-os.example/schemas/"
    "evidence_bundle_verification_result.schema.json"
)
VALIDATOR = "veritas-evidence-bundle validate-result"
VALIDATION_REPORT_METADATA = {
    "report_schema_id": REPORT_SCHEMA_ID,
    "validated_schema_id": VALIDATED_SCHEMA_ID,
    "validator": VALIDATOR,
}
CONTRACT_JSON_FIELDS = {
    "ok",
    "tampered",
    "hash_integrity_ok",
    "signature_status",
    "signature_verified",
    "authenticity_ok",
    "authenticity_failure",
    "public_key_fingerprint_sha256",
    "errors",
    "warnings",
}


def _load_verification_result_schema() -> dict[str, Any]:
    """Load the Evidence Bundle verification result JSON Schema."""
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _load_validation_report_schema() -> dict[str, Any]:
    """Load the validate-result JSON validation report Schema."""
    return json.loads(VALIDATION_REPORT_SCHEMA_PATH.read_text(encoding="utf-8"))


def _assert_validation_report_schema(output: dict[str, Any]) -> None:
    """Assert validate-result --json output matches its report Schema."""
    import jsonschema

    schema = _load_validation_report_schema()
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(output)


def _assert_validation_report_metadata(output: dict[str, Any]) -> None:
    """Assert validate-result reports include self-describing metadata."""
    assert output["report_schema_id"] == REPORT_SCHEMA_ID
    assert output["validated_schema_id"] == VALIDATED_SCHEMA_ID
    assert output["validator"] == VALIDATOR


def _assert_contract_fields(output: dict[str, Any]) -> None:
    """Assert reviewer-facing JSON contract fields are present and schema-valid."""
    import jsonschema

    assert CONTRACT_JSON_FIELDS.issubset(output.keys())
    assert isinstance(output["ok"], bool)
    assert isinstance(output["tampered"], bool)
    assert isinstance(output["hash_integrity_ok"], bool)
    assert isinstance(output["signature_status"], str)
    assert isinstance(output["signature_verified"], bool)
    assert isinstance(output["authenticity_ok"], bool)
    assert output["authenticity_failure"] is None or isinstance(
        output["authenticity_failure"],
        str,
    )
    assert output["public_key_fingerprint_sha256"] is None or isinstance(
        output["public_key_fingerprint_sha256"],
        str,
    )
    assert isinstance(output["errors"], list)
    assert isinstance(output["warnings"], list)

    schema = _load_verification_result_schema()
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(output)


def test_evidence_bundle_validation_report_schema_contract() -> None:
    """JSON Schema pins validate-result --json validation report fields."""
    schema = _load_validation_report_schema()

    assert set(schema["required"]) == {
        "ok",
        "schema_valid",
        "result_path",
        "report_schema_id",
        "validated_schema_id",
        "validator",
        "errors",
    }
    assert schema["properties"]["ok"]["type"] == "boolean"
    assert schema["properties"]["schema_valid"]["type"] == "boolean"
    assert schema["properties"]["result_path"]["type"] == "string"
    assert schema["properties"]["report_schema_id"]["type"] == "string"
    assert schema["properties"]["validated_schema_id"]["type"] == "string"
    assert schema["properties"]["validator"]["type"] == "string"
    error_schema = schema["properties"]["errors"]["items"]
    assert set(error_schema["required"]) == {"path", "message"}
    assert error_schema["properties"]["path"]["type"] == "string"
    assert error_schema["properties"]["message"]["type"] == "string"
    description = schema["description"]
    assert (
        "machine-readable report emitted by "
        "veritas-evidence-bundle validate-result --json"
    ) in description
    assert "validates the validation report shape only" in description
    assert "report_schema_id identifies the schema" in description
    assert (
        "validated_schema_id identifies the saved verification result schema"
        in description
    )
    assert "metadata for interpretation" in description
    assert "does not re-run cryptographic verification" in description
    assert "does not re-run file/hash integrity checks" in description
    assert "does not establish trusted key provenance" in description
    assert "not regulatory certification" in description

    _assert_validation_report_schema(
        {
            "ok": False,
            "schema_valid": False,
            "result_path": "verification-result.json",
            **VALIDATION_REPORT_METADATA,
            "errors": [
                {
                    "path": "$['signature_status']",
                    "message": "'verified' is not one of allowed values",
                }
            ],
        }
    )


def test_evidence_bundle_verification_result_schema_contract() -> None:
    """JSON Schema pins required reviewer-facing verification fields."""
    schema = _load_verification_result_schema()

    assert set(schema["required"]) == CONTRACT_JSON_FIELDS
    assert schema["properties"]["signature_status"]["enum"] == [
        "pass",
        "fail",
        "missing",
        "not_verified",
    ]
    assert schema["properties"]["authenticity_failure"]["enum"] == [
        None,
        "signature_not_verified",
        "signature_verification_failed",
        "signature_verification_error",
        "signature_missing",
    ]
    assert "Hash integrity is not authenticity" in (
        schema["properties"]["hash_integrity_ok"]["description"]
    )
    assert "trusted Ed25519 public key" in (
        schema["properties"]["signature_verified"]["description"]
    )
    fingerprint_description = (
        schema["properties"]["public_key_fingerprint_sha256"]["description"]
    )
    assert "public key material used for verification" in fingerprint_description
    assert "does not by itself establish trust" in fingerprint_description
    assert "out-of-band reviewer/operator trust channel" in fingerprint_description
    assert schema["properties"]["public_key_fingerprint_sha256"]["pattern"] == (
        "^[0-9a-f]{64}$"
    )
    assert "not regulatory certification" in schema["description"]


def test_evidence_bundle_cli_generate_and_verify(tmp_path, monkeypatch) -> None:
    """CLI can generate and verify a decision evidence bundle."""
    log_path = tmp_path / "trustlog.jsonl"
    private_key = tmp_path / "keys" / "priv.key"
    public_key = tmp_path / "keys" / "pub.key"

    monkeypatch.setattr(trustlog_signed, "SIGNED_TRUSTLOG_JSONL", log_path)
    monkeypatch.setattr(trustlog_signed, "PRIVATE_KEY_PATH", private_key)
    monkeypatch.setattr(trustlog_signed, "PUBLIC_KEY_PATH", public_key)

    trustlog_signed.append_signed_decision(
        {
            "request_id": "fin-wire-2026-0001",
            "gate_decision": "human_review_required",
            "business_decision": "REVIEW_REQUIRED",
            "next_action": "ROUTE_TO_HUMAN_REVIEW",
            "required_evidence": [
                "kyc_verification",
                "source_of_funds_attestation",
                "aml_screening_receipt",
            ],
            "human_review_required": True,
        }
    )

    from veritas_os.cli.evidence_bundle import main

    out_dir = tmp_path / "bundles"
    exit_code = main(
        [
            "generate",
            "--bundle-type",
            "decision",
            "--witness-ledger",
            str(log_path),
            "--output-dir",
            str(out_dir),
            "--request-id",
            "fin-wire-2026-0001",
            "--json",
        ]
    )
    assert exit_code == 0

    generated_dirs = list(out_dir.glob("veritas_bundle_decision_*"))
    assert generated_dirs
    bundle_dir = generated_dirs[0]

    verify_exit = main(["verify", "--bundle-dir", str(bundle_dir), "--json"])
    assert verify_exit == 0


def test_generated_ui_delivery_hook_requires_manifest_signature(
    tmp_path,
    monkeypatch,
) -> None:
    """Generated reviewer handoff uses strict Ed25519 manifest verification."""
    from veritas_os.audit.evidence_bundle import generate_evidence_bundle

    log_path = tmp_path / "trustlog.jsonl"
    private_key = tmp_path / "keys" / "priv.key"
    public_key = tmp_path / "keys" / "pub.key"

    monkeypatch.setattr(trustlog_signed, "SIGNED_TRUSTLOG_JSONL", log_path)
    monkeypatch.setattr(trustlog_signed, "PRIVATE_KEY_PATH", private_key)
    monkeypatch.setattr(trustlog_signed, "PUBLIC_KEY_PATH", public_key)
    trustlog_signed.append_signed_decision(
        {"request_id": "ui-hook-bundle", "decision": "allow"}
    )

    result = generate_evidence_bundle(
        bundle_type="decision",
        witness_ledger_path=log_path,
        output_dir=tmp_path / "bundles",
        request_ids=["ui-hook-bundle"],
    )
    bundle_dir = Path(result["bundle_dir"])
    hook = json.loads(
        (bundle_dir / "ui_delivery_hook.json").read_text(encoding="utf-8")
    )

    assert "--public-key" in hook["verify_command"]
    assert "--require-signature" in hook["verify_command"]
    assert hook["requires_trusted_public_key"] is True
    assert {"secure", "prod"}.issubset(hook["signature_required_in_postures"])
    assert hook["verification_scope"] == [
        "file_hash_integrity",
        "manifest_signature_authenticity",
    ]

    readme = (bundle_dir / "README.txt").read_text(encoding="utf-8")
    assert "reviewer/operator trust channel" in readme
    assert "do not trust a public key only because it is included" in readme


def test_financial_bundle_sample_fixture_exists() -> None:
    """Repository includes a representative financial decision bundle sample."""
    fixture_path = Path(
        "veritas_os/benchmarks/evidence/fixtures/financial_template_bundle_sample.json"
    )
    assert fixture_path.exists()

    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.1.0"
    decision_record = payload["decision_record"]
    assert decision_record["decision_payload"]["gate_decision"] == "human_review_required"
    assert decision_record["decision_payload"]["business_decision"] == "REVIEW_REQUIRED"
    assert decision_record["decision_payload"]["human_review_required"] is True


def test_evidence_bundle_decision_record_canonicalizes_gate_decision(
    tmp_path,
) -> None:
    """Decision record decision semantics should use canonical public values."""
    log_path = tmp_path / "trustlog.jsonl"
    log_entry = {
        "decision_id": "dec-fin-wire-2026-0002",
        "timestamp": "2026-04-18T00:00:00Z",
        "previous_hash": None,
        "payload_hash": "dummy",
        "full_payload_hash": "dummy-full",
        "signature": "dummy-signature",
        "decision_payload": {
            "request_id": "fin-wire-2026-0002",
            "gate_decision": "allow",
            "business_decision": "allow",
            "next_action": "needs_human_review",
            "required_evidence": [],
            "human_review_required": False,
        },
    }
    log_path.write_text(json.dumps(log_entry) + "\n", encoding="utf-8")

    from veritas_os.cli.evidence_bundle import main

    out_dir = tmp_path / "bundles"
    exit_code = main(
        [
            "generate",
            "--bundle-type",
            "decision",
            "--witness-ledger",
            str(log_path),
            "--output-dir",
            str(out_dir),
            "--request-id",
            "fin-wire-2026-0002",
            "--json",
        ]
    )
    assert exit_code == 0
    bundle_dir = next(out_dir.glob("veritas_bundle_decision_*"))
    decision_record = json.loads((bundle_dir / "decision_record.json").read_text(encoding="utf-8"))
    assert decision_record["gate_decision"] == "proceed"
    assert decision_record["business_decision"] == "APPROVE"
    assert decision_record["next_action"] == "PREPARE_HUMAN_REVIEW_PACKET"


def _signed_bundle(tmp_path, monkeypatch):
    """Create a signed decision evidence bundle and its verification keys."""
    from veritas_os.audit.evidence_bundle import generate_evidence_bundle
    from veritas_os.security.signing import sign_payload_hash, store_keypair

    log_path = tmp_path / "trustlog.jsonl"
    trustlog_private_key = tmp_path / "trustlog_keys" / "priv.key"
    trustlog_public_key = tmp_path / "trustlog_keys" / "pub.key"
    manifest_private_key = tmp_path / "manifest_keys" / "priv.key"
    manifest_public_key = tmp_path / "manifest_keys" / "pub.key"

    monkeypatch.setattr(trustlog_signed, "SIGNED_TRUSTLOG_JSONL", log_path)
    monkeypatch.setattr(trustlog_signed, "PRIVATE_KEY_PATH", trustlog_private_key)
    monkeypatch.setattr(trustlog_signed, "PUBLIC_KEY_PATH", trustlog_public_key)
    store_keypair(manifest_private_key, manifest_public_key)
    trustlog_signed.append_signed_decision(
        {"request_id": "signed-cli-bundle", "decision": "allow"}
    )
    result = generate_evidence_bundle(
        bundle_type="decision",
        witness_ledger_path=log_path,
        output_dir=tmp_path / "bundles",
        signer_fn=lambda payload_hash: sign_payload_hash(
            payload_hash,
            manifest_private_key,
        ),
        signer_metadata={"type": "ed25519-file-test"},
    )
    return Path(result["bundle_dir"]), manifest_private_key, manifest_public_key


def test_evidence_bundle_cli_verify_signed_manifest_with_public_key(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    """Correct Ed25519 manifest signature and public key pass verification."""
    from veritas_os.cli.evidence_bundle import main

    monkeypatch.setenv("VERITAS_POSTURE", "dev")
    bundle_dir, _private_key, public_key = _signed_bundle(tmp_path, monkeypatch)

    exit_code = main(
        [
            "verify",
            "--bundle-dir",
            str(bundle_dir),
            "--public-key",
            str(public_key),
            "--require-signature",
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "File/hash integrity: PASS" in output
    assert "Manifest signature: PASS" in output


def test_evidence_bundle_cli_strict_success_json_contract(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    """Strict --json success exposes stable reviewer-facing fields."""
    from veritas_os.cli.evidence_bundle import main

    monkeypatch.setenv("VERITAS_POSTURE", "dev")
    bundle_dir, _private_key, public_key = _signed_bundle(tmp_path, monkeypatch)

    exit_code = main(
        [
            "verify",
            "--bundle-dir",
            str(bundle_dir),
            "--public-key",
            str(public_key),
            "--require-signature",
            "--json",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    _assert_contract_fields(output)
    assert output["ok"] is True
    assert output["tampered"] is False
    assert output["hash_integrity_ok"] is True
    assert output["signature_status"] == "pass"
    assert output["signature_verified"] is True
    assert output["authenticity_ok"] is True
    assert output["authenticity_failure"] is None
    assert re.fullmatch(
        r"[0-9a-f]{64}",
        output["public_key_fingerprint_sha256"],
    )
    assert output["public_key_fingerprint_sha256"] == hashlib.sha256(
        public_key.read_bytes()
    ).hexdigest()
    assert output["errors"] == []


def _assert_written_result_matches_stdout(
    output_path: Path,
    stdout: str,
) -> dict[str, Any]:
    """Assert saved verification JSON exactly mirrors stdout and schema."""
    assert output_path.read_text(encoding="utf-8") == stdout
    output = json.loads(stdout)
    _assert_contract_fields(output)
    return output


def test_evidence_bundle_cli_strict_success_json_output_file(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    """Strict success --json result can be saved as reviewer evidence."""
    from veritas_os.cli.evidence_bundle import main

    monkeypatch.setenv("VERITAS_POSTURE", "dev")
    bundle_dir, _private_key, public_key = _signed_bundle(tmp_path, monkeypatch)
    output_path = tmp_path / "review" / "strict-success-result.json"

    exit_code = main(
        [
            "verify",
            "--bundle-dir",
            str(bundle_dir),
            "--public-key",
            str(public_key),
            "--require-signature",
            "--json",
            "--output",
            str(output_path),
        ]
    )
    output = _assert_written_result_matches_stdout(
        output_path,
        capsys.readouterr().out,
    )

    assert exit_code == 0
    assert output["ok"] is True
    assert output["signature_status"] == "pass"
    assert output["signature_verified"] is True
    assert output["public_key_fingerprint_sha256"] == hashlib.sha256(
        public_key.read_bytes()
    ).hexdigest()


def test_evidence_bundle_cli_missing_public_key_json_output_file(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    """Strict missing-key --json failure can be saved as audit evidence."""
    from veritas_os.cli.evidence_bundle import main

    monkeypatch.setenv("VERITAS_POSTURE", "dev")
    bundle_dir, _private_key, _public_key = _signed_bundle(tmp_path, monkeypatch)
    output_path = tmp_path / "missing-key-result.json"

    exit_code = main(
        [
            "verify",
            "--bundle-dir",
            str(bundle_dir),
            "--require-signature",
            "--json",
            "--output",
            str(output_path),
        ]
    )
    output = _assert_written_result_matches_stdout(
        output_path,
        capsys.readouterr().out,
    )

    assert exit_code == 1
    assert output["ok"] is False
    assert output["signature_status"] == "not_verified"
    assert output["authenticity_failure"] == "signature_not_verified"
    assert output["public_key_fingerprint_sha256"] is None


def test_evidence_bundle_cli_wrong_key_json_output_file(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    """Strict wrong-key --json failure can be saved as audit evidence."""
    from veritas_os.cli.evidence_bundle import main
    from veritas_os.security.signing import store_keypair

    monkeypatch.setenv("VERITAS_POSTURE", "dev")
    bundle_dir, _private_key, _public_key = _signed_bundle(tmp_path, monkeypatch)
    wrong_private_key = tmp_path / "wrong_output_keys" / "priv.key"
    wrong_public_key = tmp_path / "wrong_output_keys" / "pub.key"
    store_keypair(wrong_private_key, wrong_public_key)
    output_path = tmp_path / "wrong-key-result.json"

    exit_code = main(
        [
            "verify",
            "--bundle-dir",
            str(bundle_dir),
            "--public-key",
            str(wrong_public_key),
            "--require-signature",
            "--json",
            "--output",
            str(output_path),
        ]
    )
    output = _assert_written_result_matches_stdout(
        output_path,
        capsys.readouterr().out,
    )

    assert exit_code == 1
    assert output["ok"] is False
    assert output["signature_status"] == "fail"
    assert output["authenticity_failure"] == "signature_verification_failed"
    assert output["public_key_fingerprint_sha256"] == hashlib.sha256(
        wrong_public_key.read_bytes()
    ).hexdigest()


def test_evidence_bundle_cli_output_requires_json(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    """--output is reserved for JSON verification results."""
    from veritas_os.cli.evidence_bundle import main

    monkeypatch.setenv("VERITAS_POSTURE", "dev")
    bundle_dir, _private_key, public_key = _signed_bundle(tmp_path, monkeypatch)

    with pytest.raises(SystemExit) as excinfo:
        main(
            [
                "verify",
                "--bundle-dir",
                str(bundle_dir),
                "--public-key",
                str(public_key),
                "--require-signature",
                "--output",
                str(tmp_path / "result.json"),
            ]
        )

    assert excinfo.value.code == 2
    assert "verify --output requires --json" in capsys.readouterr().err


def test_evidence_bundle_cli_output_write_failure_is_clear(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    """A result write failure exits non-zero with a clear stderr message."""
    from veritas_os.cli.evidence_bundle import main

    monkeypatch.setenv("VERITAS_POSTURE", "dev")
    bundle_dir, _private_key, public_key = _signed_bundle(tmp_path, monkeypatch)
    output_path = tmp_path / "existing-directory"
    output_path.mkdir()

    exit_code = main(
        [
            "verify",
            "--bundle-dir",
            str(bundle_dir),
            "--public-key",
            str(public_key),
            "--require-signature",
            "--json",
            "--output",
            str(output_path),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert "failed to write verification result" in captured.err


def test_evidence_bundle_cli_verify_tampered_manifest_signature_fails(
    tmp_path,
    monkeypatch,
) -> None:
    """Tampering manifest_signature causes strict CLI verification to fail."""
    from veritas_os.cli.evidence_bundle import main

    monkeypatch.setenv("VERITAS_POSTURE", "dev")
    bundle_dir, _private_key, public_key = _signed_bundle(tmp_path, monkeypatch)
    manifest_path = bundle_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["manifest_signature"] = base64.urlsafe_b64encode(
        b"\x00" * 64
    ).decode("ascii")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "verify",
            "--bundle-dir",
            str(bundle_dir),
            "--public-key",
            str(public_key),
            "--require-signature",
        ]
    )

    assert exit_code == 1


def test_verify_bundle_signature_failure_reports_authenticity_failure(
    tmp_path,
    monkeypatch,
) -> None:
    """A validly encoded wrong Ed25519 signature is classified as verification failure."""
    from veritas_os.audit.verify_bundle import verify_evidence_bundle
    from veritas_os.security.signing import verify_payload_signature

    bundle_dir, _private_key, public_key = _signed_bundle(tmp_path, monkeypatch)
    manifest_path = bundle_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["manifest_signature"] = base64.urlsafe_b64encode(
        b"\x00" * 64
    ).decode("ascii")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    result = verify_evidence_bundle(
        bundle_dir,
        verify_signature_fn=lambda payload_hash, signature_b64: (
            verify_payload_signature(payload_hash, signature_b64, public_key)
        ),
        require_signature=True,
    )

    assert result["ok"] is False
    assert result["hash_integrity_ok"] is True
    assert result["authenticity_ok"] is False
    assert result["authenticity_failure"] == "signature_verification_failed"


def test_verify_bundle_malformed_signature_reports_authenticity_error(
    tmp_path,
    monkeypatch,
) -> None:
    """Malformed manifest_signature is classified separately from signature mismatch."""
    from veritas_os.audit.verify_bundle import verify_evidence_bundle
    from veritas_os.security.signing import verify_payload_signature

    bundle_dir, _private_key, public_key = _signed_bundle(tmp_path, monkeypatch)
    manifest_path = bundle_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["manifest_signature"] = "not base64 ???"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    result = verify_evidence_bundle(
        bundle_dir,
        verify_signature_fn=lambda payload_hash, signature_b64: (
            verify_payload_signature(payload_hash, signature_b64, public_key)
        ),
        require_signature=True,
    )

    assert result["ok"] is False
    assert result["hash_integrity_ok"] is True
    assert result["authenticity_ok"] is False
    assert result["authenticity_failure"] == "signature_verification_error"


def test_evidence_bundle_cli_missing_public_key_json_contract(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    """Strict --json reports missing trusted public key without hash failure."""
    from veritas_os.cli.evidence_bundle import main

    monkeypatch.setenv("VERITAS_POSTURE", "dev")
    bundle_dir, _private_key, _public_key = _signed_bundle(tmp_path, monkeypatch)

    exit_code = main(
        [
            "verify",
            "--bundle-dir",
            str(bundle_dir),
            "--require-signature",
            "--json",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    _assert_contract_fields(output)
    assert output["ok"] is False
    assert output["tampered"] is True
    assert output["hash_integrity_ok"] is True
    assert output["signature_status"] == "not_verified"
    assert output["signature_verified"] is False
    assert output["authenticity_ok"] is False
    assert output["authenticity_failure"] == "signature_not_verified"
    assert output["public_key_fingerprint_sha256"] is None
    assert any("No trusted public key supplied" in e for e in output["errors"])


def test_evidence_bundle_cli_require_signature_without_public_key_fails(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    """Strict reviewer verification fails when no trusted key is supplied."""
    from veritas_os.cli.evidence_bundle import main

    monkeypatch.setenv("VERITAS_POSTURE", "dev")
    bundle_dir, _private_key, _public_key = _signed_bundle(tmp_path, monkeypatch)

    exit_code = main(
        [
            "verify",
            "--bundle-dir",
            str(bundle_dir),
            "--require-signature",
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "File/hash integrity: PASS" in output
    assert "Manifest signature: NOT VERIFIED" in output
    assert "No trusted public key supplied" in output


def test_evidence_bundle_cli_verify_manifest_signed_by_wrong_key_fails(
    tmp_path,
    monkeypatch,
) -> None:
    """A manifest signature made by another key fails authenticity checks."""
    from veritas_os.cli.evidence_bundle import main
    from veritas_os.security.signing import store_keypair

    monkeypatch.setenv("VERITAS_POSTURE", "dev")
    bundle_dir, _private_key, _public_key = _signed_bundle(tmp_path, monkeypatch)
    wrong_private_key = tmp_path / "wrong_keys" / "priv.key"
    wrong_public_key = tmp_path / "wrong_keys" / "pub.key"
    store_keypair(wrong_private_key, wrong_public_key)

    exit_code = main(
        [
            "verify",
            "--bundle-dir",
            str(bundle_dir),
            "--public-key",
            str(wrong_public_key),
            "--require-signature",
        ]
    )

    assert exit_code == 1


def test_evidence_bundle_cli_wrong_key_json_contract(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    """Strict --json reports wrong trusted key as authenticity failure."""
    from veritas_os.cli.evidence_bundle import main
    from veritas_os.security.signing import store_keypair

    monkeypatch.setenv("VERITAS_POSTURE", "dev")
    bundle_dir, _private_key, _public_key = _signed_bundle(tmp_path, monkeypatch)
    wrong_private_key = tmp_path / "wrong_json_keys" / "priv.key"
    wrong_public_key = tmp_path / "wrong_json_keys" / "pub.key"
    store_keypair(wrong_private_key, wrong_public_key)

    exit_code = main(
        [
            "verify",
            "--bundle-dir",
            str(bundle_dir),
            "--public-key",
            str(wrong_public_key),
            "--require-signature",
            "--json",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    _assert_contract_fields(output)
    assert output["ok"] is False
    assert output["tampered"] is True
    assert output["hash_integrity_ok"] is True
    assert output["signature_status"] == "fail"
    assert output["signature_verified"] is False
    assert output["authenticity_ok"] is False
    assert output["authenticity_failure"] == "signature_verification_failed"
    assert output["public_key_fingerprint_sha256"] == hashlib.sha256(
        wrong_public_key.read_bytes()
    ).hexdigest()
    assert "Manifest signature verification failed" in output["errors"]


def test_evidence_bundle_cli_malformed_signature_json_contract(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    """Strict --json distinguishes malformed signatures from wrong keys."""
    from veritas_os.cli.evidence_bundle import main

    monkeypatch.setenv("VERITAS_POSTURE", "dev")
    bundle_dir, _private_key, public_key = _signed_bundle(tmp_path, monkeypatch)
    manifest_path = bundle_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["manifest_signature"] = "not base64 ???"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "verify",
            "--bundle-dir",
            str(bundle_dir),
            "--public-key",
            str(public_key),
            "--require-signature",
            "--json",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    _assert_contract_fields(output)
    assert output["ok"] is False
    assert output["tampered"] is True
    assert output["hash_integrity_ok"] is True
    assert output["signature_status"] == "fail"
    assert output["signature_verified"] is False
    assert output["authenticity_ok"] is False
    assert output["authenticity_failure"] == "signature_verification_error"
    assert any(
        error.startswith("Manifest signature verification error")
        for error in output["errors"]
    )


def test_evidence_bundle_cli_require_signature_rejects_unsigned_bundle(
    tmp_path,
    monkeypatch,
) -> None:
    """--require-signature fails closed when a bundle has no manifest signature."""
    from veritas_os.audit.evidence_bundle import generate_evidence_bundle
    from veritas_os.cli.evidence_bundle import main

    monkeypatch.setenv("VERITAS_POSTURE", "dev")
    log_path = tmp_path / "trustlog.jsonl"
    private_key = tmp_path / "keys" / "priv.key"
    public_key = tmp_path / "keys" / "pub.key"
    monkeypatch.setattr(trustlog_signed, "SIGNED_TRUSTLOG_JSONL", log_path)
    monkeypatch.setattr(trustlog_signed, "PRIVATE_KEY_PATH", private_key)
    monkeypatch.setattr(trustlog_signed, "PUBLIC_KEY_PATH", public_key)
    trustlog_signed.append_signed_decision({"request_id": "unsigned", "decision": "allow"})
    result = generate_evidence_bundle(
        bundle_type="decision",
        witness_ledger_path=log_path,
        output_dir=tmp_path / "bundles",
    )

    exit_code = main(
        [
            "verify",
            "--bundle-dir",
            result["bundle_dir"],
            "--require-signature",
        ]
    )

    assert exit_code == 1


@pytest.mark.parametrize("posture", ["secure", "prod"])
def test_evidence_bundle_cli_secure_or_prod_posture_rejects_unsigned_bundle(
    tmp_path,
    monkeypatch,
    posture,
) -> None:
    """VERITAS_POSTURE=secure/prod requires manifest signature verification."""
    from veritas_os.audit.evidence_bundle import generate_evidence_bundle
    from veritas_os.cli.evidence_bundle import main

    monkeypatch.setenv("VERITAS_POSTURE", posture)
    log_path = tmp_path / "trustlog.jsonl"
    private_key = tmp_path / "keys" / "priv.key"
    public_key = tmp_path / "keys" / "pub.key"
    monkeypatch.setattr(trustlog_signed, "SIGNED_TRUSTLOG_JSONL", log_path)
    monkeypatch.setattr(trustlog_signed, "PRIVATE_KEY_PATH", private_key)
    monkeypatch.setattr(trustlog_signed, "PUBLIC_KEY_PATH", public_key)
    trustlog_signed.append_signed_decision({"request_id": "secure-unsigned"})
    result = generate_evidence_bundle(
        bundle_type="decision",
        witness_ledger_path=log_path,
        output_dir=tmp_path / "bundles",
    )

    exit_code = main(["verify", "--bundle-dir", result["bundle_dir"]])

    assert exit_code == 1


def test_evidence_bundle_cli_secure_unsigned_json_contract(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    """Secure posture --json reports unsigned bundles as authenticity failures."""
    from veritas_os.audit.evidence_bundle import generate_evidence_bundle
    from veritas_os.cli.evidence_bundle import main

    monkeypatch.setenv("VERITAS_POSTURE", "secure")
    log_path = tmp_path / "trustlog.jsonl"
    private_key = tmp_path / "keys" / "priv.key"
    public_key = tmp_path / "keys" / "pub.key"
    monkeypatch.setattr(trustlog_signed, "SIGNED_TRUSTLOG_JSONL", log_path)
    monkeypatch.setattr(trustlog_signed, "PRIVATE_KEY_PATH", private_key)
    monkeypatch.setattr(trustlog_signed, "PUBLIC_KEY_PATH", public_key)
    trustlog_signed.append_signed_decision({"request_id": "secure-json-unsigned"})
    result = generate_evidence_bundle(
        bundle_type="decision",
        witness_ledger_path=log_path,
        output_dir=tmp_path / "bundles",
    )

    exit_code = main(["verify", "--bundle-dir", result["bundle_dir"], "--json"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    _assert_contract_fields(output)
    assert output["ok"] is False
    assert output["tampered"] is True
    assert output["hash_integrity_ok"] is True
    assert output["signature_status"] == "missing"
    assert output["signature_verified"] is False
    assert output["authenticity_ok"] is False
    assert output["authenticity_failure"] == "signature_missing"
    assert output["public_key_fingerprint_sha256"] is None
    assert "Manifest signature missing" in output["errors"]


def test_evidence_bundle_cli_dev_without_public_key_warns_and_reports_json(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    """dev posture may skip authenticity checks but reports an explicit warning."""
    from veritas_os.cli.evidence_bundle import main

    monkeypatch.setenv("VERITAS_POSTURE", "dev")
    bundle_dir, _private_key, _public_key = _signed_bundle(tmp_path, monkeypatch)

    exit_code = main(
        [
            "verify",
            "--bundle-dir",
            str(bundle_dir),
            "--json",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["signature_verified"] is False
    assert output["signature_status"] == "not_verified"
    assert output["public_key_fingerprint_sha256"] is None
    assert any("authenticity was not verified" in w for w in output["warnings"])


def test_verify_bundle_signed_manifest_without_verifier_warns(
    tmp_path,
    monkeypatch,
) -> None:
    """verify_evidence_bundle does not silently skip present manifest signatures."""
    from veritas_os.audit.verify_bundle import verify_evidence_bundle

    bundle_dir, _private_key, _public_key = _signed_bundle(tmp_path, monkeypatch)

    result = verify_evidence_bundle(bundle_dir)

    assert result["ok"] is True
    assert result["signature_verified"] is False
    assert result["signature_status"] == "not_verified"
    assert any("no signature verifier" in w for w in result["warnings"])


def _valid_verification_result_payload() -> dict[str, Any]:
    """Return a minimal schema-valid saved verification result payload."""
    return {
        "ok": True,
        "tampered": False,
        "hash_integrity_ok": True,
        "signature_status": "pass",
        "signature_verified": True,
        "authenticity_ok": True,
        "authenticity_failure": None,
        "public_key_fingerprint_sha256": "a" * 64,
        "errors": [],
        "warnings": [],
    }


def _write_result_payload(path: Path, payload: dict[str, Any]) -> None:
    """Write a saved verification result fixture as UTF-8 JSON."""
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_evidence_bundle_cli_validate_result_valid_saved_result_passes(
    tmp_path,
    capsys,
) -> None:
    """validate-result accepts a saved verification result that matches schema."""
    from veritas_os.cli.evidence_bundle import main

    result_path = tmp_path / "valid-result.json"
    _write_result_payload(result_path, _valid_verification_result_payload())

    exit_code = main(["validate-result", "--result", str(result_path)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert output == "Evidence bundle verification result schema: PASS\n"


def test_evidence_bundle_cli_validate_result_missing_required_field_fails(
    tmp_path,
    capsys,
) -> None:
    """validate-result reports the missing required contract field."""
    from veritas_os.cli.evidence_bundle import main

    result_path = tmp_path / "missing-field-result.json"
    payload = _valid_verification_result_payload()
    del payload["signature_verified"]
    _write_result_payload(result_path, payload)

    exit_code = main(["validate-result", "--result", str(result_path)])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Evidence bundle verification result schema: FAIL" in output
    assert "'signature_verified' is a required property" in output


def test_evidence_bundle_cli_validate_result_invalid_signature_status_fails(
    tmp_path,
    capsys,
) -> None:
    """validate-result reports invalid signature_status enum values."""
    from veritas_os.cli.evidence_bundle import main

    result_path = tmp_path / "invalid-status-result.json"
    payload = _valid_verification_result_payload()
    payload["signature_status"] = "verified"
    _write_result_payload(result_path, payload)

    exit_code = main(["validate-result", "--result", str(result_path)])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Evidence bundle verification result schema: FAIL" in output
    assert "$['signature_status']" in output
    assert "'verified' is not one of" in output


def test_evidence_bundle_cli_validate_result_invalid_fingerprint_pattern_fails(
    tmp_path,
    capsys,
) -> None:
    """validate-result reports invalid public_key_fingerprint_sha256 patterns."""
    from veritas_os.cli.evidence_bundle import main

    result_path = tmp_path / "invalid-fingerprint-result.json"
    payload = _valid_verification_result_payload()
    payload["public_key_fingerprint_sha256"] = "A" * 64
    _write_result_payload(result_path, payload)

    exit_code = main(["validate-result", "--result", str(result_path)])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Evidence bundle verification result schema: FAIL" in output
    assert "$['public_key_fingerprint_sha256']" in output
    assert "does not match '^[0-9a-f]{64}$'" in output


def test_evidence_bundle_cli_validate_result_malformed_json_fails_clearly(
    tmp_path,
    capsys,
) -> None:
    """validate-result reports malformed JSON before schema validation."""
    from veritas_os.cli.evidence_bundle import main

    result_path = tmp_path / "malformed-result.json"
    result_path.write_text('{"ok": true,', encoding="utf-8")

    exit_code = main(["validate-result", "--result", str(result_path)])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Evidence bundle verification result schema: FAIL" in output
    assert "malformed JSON: line 1" in output


def test_evidence_bundle_cli_validate_result_valid_saved_result_json_passes(
    tmp_path,
    capsys,
) -> None:
    """validate-result --json emits a machine-readable success report."""
    from veritas_os.cli.evidence_bundle import main

    result_path = tmp_path / "valid-result.json"
    _write_result_payload(result_path, _valid_verification_result_payload())

    exit_code = main(["validate-result", "--result", str(result_path), "--json"])
    output = json.loads(capsys.readouterr().out)

    _assert_validation_report_schema(output)
    _assert_validation_report_metadata(output)
    assert exit_code == 0
    assert output == {
        "ok": True,
        "schema_valid": True,
        "result_path": str(result_path),
        **VALIDATION_REPORT_METADATA,
        "errors": [],
    }


def test_evidence_bundle_cli_validate_result_missing_required_field_json_fails(
    tmp_path,
    capsys,
) -> None:
    """validate-result --json reports missing required fields structurally."""
    from veritas_os.cli.evidence_bundle import main

    result_path = tmp_path / "missing-field-result.json"
    payload = _valid_verification_result_payload()
    del payload["signature_verified"]
    _write_result_payload(result_path, payload)

    exit_code = main(["validate-result", "--result", str(result_path), "--json"])
    output = json.loads(capsys.readouterr().out)

    _assert_validation_report_schema(output)
    _assert_validation_report_metadata(output)
    assert exit_code == 1
    assert output["ok"] is False
    assert output["schema_valid"] is False
    assert output["result_path"] == str(result_path)
    assert output["errors"] == [
        {
            "path": "$",
            "message": "'signature_verified' is a required property",
        }
    ]


def test_evidence_bundle_cli_validate_result_invalid_signature_status_json_fails(
    tmp_path,
    capsys,
) -> None:
    """validate-result --json reports invalid signature_status paths."""
    from veritas_os.cli.evidence_bundle import main

    result_path = tmp_path / "invalid-status-result.json"
    payload = _valid_verification_result_payload()
    payload["signature_status"] = "verified"
    _write_result_payload(result_path, payload)

    exit_code = main(["validate-result", "--result", str(result_path), "--json"])
    output = json.loads(capsys.readouterr().out)

    _assert_validation_report_schema(output)
    _assert_validation_report_metadata(output)
    assert exit_code == 1
    assert output["ok"] is False
    assert output["schema_valid"] is False
    assert output["errors"][0]["path"] == "$['signature_status']"
    assert "'verified' is not one of" in output["errors"][0]["message"]


def test_evidence_bundle_cli_validate_result_invalid_fingerprint_json_fails(
    tmp_path,
    capsys,
) -> None:
    """validate-result --json reports invalid fingerprint paths."""
    from veritas_os.cli.evidence_bundle import main

    result_path = tmp_path / "invalid-fingerprint-result.json"
    payload = _valid_verification_result_payload()
    payload["public_key_fingerprint_sha256"] = "A" * 64
    _write_result_payload(result_path, payload)

    exit_code = main(["validate-result", "--result", str(result_path), "--json"])
    output = json.loads(capsys.readouterr().out)

    _assert_validation_report_schema(output)
    _assert_validation_report_metadata(output)
    assert exit_code == 1
    assert output["ok"] is False
    assert output["schema_valid"] is False
    assert output["errors"][0]["path"] == "$['public_key_fingerprint_sha256']"
    assert "does not match '^[0-9a-f]{64}$'" in output["errors"][0]["message"]


def test_evidence_bundle_cli_validate_result_malformed_json_json_fails(
    tmp_path,
    capsys,
) -> None:
    """validate-result --json reports malformed JSON as structured output."""
    from veritas_os.cli.evidence_bundle import main

    result_path = tmp_path / "malformed-result.json"
    result_path.write_text('{"ok": true,', encoding="utf-8")

    exit_code = main(["validate-result", "--result", str(result_path), "--json"])
    output = json.loads(capsys.readouterr().out)

    _assert_validation_report_schema(output)
    _assert_validation_report_metadata(output)
    assert exit_code == 1
    assert output == {
        "ok": False,
        "schema_valid": False,
        "result_path": str(result_path),
        **VALIDATION_REPORT_METADATA,
        "errors": [
            {
                "path": "$",
                "message": (
                    "malformed JSON: line 1, column 13: "
                    "Expecting property name enclosed in double quotes"
                ),
            }
        ],
    }


def _assert_validation_report_matches_stdout(
    output_path: Path,
    stdout: str,
) -> dict[str, Any]:
    """Assert saved validate-result report bytes match stdout exactly."""
    saved = output_path.read_text(encoding="utf-8")
    assert saved == stdout
    return json.loads(stdout)


def test_evidence_bundle_cli_validate_result_json_output_valid_matches_stdout(
    tmp_path,
    capsys,
) -> None:
    """validate-result --json --output saves the success report exactly."""
    from veritas_os.cli.evidence_bundle import main

    result_path = tmp_path / "valid-result.json"
    output_path = tmp_path / "reports" / "validation.json"
    _write_result_payload(result_path, _valid_verification_result_payload())

    exit_code = main(
        [
            "validate-result",
            "--result",
            str(result_path),
            "--json",
            "--output",
            str(output_path),
        ]
    )
    output = _assert_validation_report_matches_stdout(
        output_path,
        capsys.readouterr().out,
    )

    _assert_validation_report_schema(output)
    _assert_validation_report_metadata(output)
    assert exit_code == 0
    assert output == {
        "ok": True,
        "schema_valid": True,
        "result_path": str(result_path),
        **VALIDATION_REPORT_METADATA,
        "errors": [],
    }


def test_evidence_bundle_cli_validate_result_json_output_invalid_matches_stdout(
    tmp_path,
    capsys,
) -> None:
    """validate-result --json --output saves signature_status failures."""
    from veritas_os.cli.evidence_bundle import main

    result_path = tmp_path / "invalid-status-result.json"
    output_path = tmp_path / "validation" / "invalid-status.json"
    payload = _valid_verification_result_payload()
    payload["signature_status"] = "verified"
    _write_result_payload(result_path, payload)

    exit_code = main(
        [
            "validate-result",
            "--result",
            str(result_path),
            "--json",
            "--output",
            str(output_path),
        ]
    )
    output = _assert_validation_report_matches_stdout(
        output_path,
        capsys.readouterr().out,
    )

    _assert_validation_report_schema(output)
    _assert_validation_report_metadata(output)
    assert exit_code == 1
    assert output["ok"] is False
    assert output["schema_valid"] is False
    assert output["errors"][0]["path"] == "$['signature_status']"
    assert "'verified' is not one of" in output["errors"][0]["message"]


def test_evidence_bundle_cli_validate_result_json_output_malformed_matches_stdout(
    tmp_path,
    capsys,
) -> None:
    """validate-result --json --output saves malformed JSON reports."""
    from veritas_os.cli.evidence_bundle import main

    result_path = tmp_path / "malformed-result.json"
    output_path = tmp_path / "validation" / "malformed.json"
    result_path.write_text('{"ok": true,', encoding="utf-8")

    exit_code = main(
        [
            "validate-result",
            "--result",
            str(result_path),
            "--json",
            "--output",
            str(output_path),
        ]
    )
    output = _assert_validation_report_matches_stdout(
        output_path,
        capsys.readouterr().out,
    )

    _assert_validation_report_schema(output)
    _assert_validation_report_metadata(output)
    assert exit_code == 1
    assert output["ok"] is False
    assert output["schema_valid"] is False
    assert output["errors"][0]["path"] == "$"
    assert "malformed JSON: line 1" in output["errors"][0]["message"]


def test_evidence_bundle_cli_validate_result_output_requires_json(
    tmp_path,
    capsys,
) -> None:
    """validate-result --output without --json fails clearly."""
    from veritas_os.cli.evidence_bundle import main

    result_path = tmp_path / "valid-result.json"
    _write_result_payload(result_path, _valid_verification_result_payload())

    with pytest.raises(SystemExit) as excinfo:
        main(
            [
                "validate-result",
                "--result",
                str(result_path),
                "--output",
                str(tmp_path / "validation.json"),
            ]
        )

    assert excinfo.value.code == 2
    assert "validate-result --output requires --json" in capsys.readouterr().err


def test_evidence_bundle_cli_validate_result_output_write_failure_is_clear(
    tmp_path,
    capsys,
) -> None:
    """validate-result write failures exit non-zero with clear stderr."""
    from veritas_os.cli.evidence_bundle import main

    result_path = tmp_path / "valid-result.json"
    output_path = tmp_path / "existing-directory"
    _write_result_payload(result_path, _valid_verification_result_payload())
    output_path.mkdir()

    exit_code = main(
        [
            "validate-result",
            "--result",
            str(result_path),
            "--json",
            "--output",
            str(output_path),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert "failed to write validation report" in captured.err
