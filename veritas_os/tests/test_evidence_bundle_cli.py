"""Tests for evidence bundle CLI and financial sample fixture."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from veritas_os.audit import trustlog_signed


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
