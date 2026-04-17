"""Tests for External Audit Readiness Pack.

Covers:
    - TSA anchor backend (success, timeout, error, malformed receipt)
    - TSA receipt storage in witness entries
    - Verifier TSA receipt validation
    - Standalone CLI (happy path, failure path, JSON output, exit codes)
    - Evidence Bundle generation (decision, incident, release)
    - Evidence Bundle verification and tamper detection
    - Legacy TrustLog entry compatibility
    - Secure/prod posture integration
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from veritas_os.audit import trustlog_signed
from veritas_os.audit.trustlog_verify import verify_witness_ledger


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def _trustlog_env(monkeypatch, tmp_path):
    """Standard TrustLog test environment."""
    log_path = tmp_path / "trustlog.jsonl"
    private_key = tmp_path / "keys" / "priv.key"
    public_key = tmp_path / "keys" / "pub.key"

    monkeypatch.setattr(trustlog_signed, "SIGNED_TRUSTLOG_JSONL", log_path)
    monkeypatch.setattr(trustlog_signed, "PRIVATE_KEY_PATH", private_key)
    monkeypatch.setattr(trustlog_signed, "PUBLIC_KEY_PATH", public_key)
    monkeypatch.setenv("VERITAS_TRUSTLOG_ANCHOR_BACKEND", "noop")
    return {
        "log_path": log_path,
        "private_key": private_key,
        "public_key": public_key,
        "tmp_path": tmp_path,
    }


def _make_fake_tsa_response(status_code: int = 0) -> bytes:
    """Build a minimal fake RFC 3161 TimeStampResp DER for testing."""
    # PKIStatus INTEGER (status_code)
    if status_code < 0x80:
        status_int = b"\x02\x01" + bytes([status_code])
    else:
        status_int = b"\x02\x02\x00" + bytes([status_code])

    # PKIStatusInfo SEQUENCE { PKIStatus }
    status_info = b"\x30" + bytes([len(status_int)]) + status_int

    # Fake token content (just some random bytes for testing)
    fake_token = b"\x30\x03\x02\x01\x01"  # minimal SEQUENCE

    # TimeStampResp SEQUENCE { PKIStatusInfo, TimeStampToken }
    content = status_info + fake_token
    outer = b"\x30" + bytes([len(content)]) + content

    return outer


# ── Goal A: TSA Anchor Backend ────────────────────────────────────────────

class TestTsaAnchorBackend:
    """Tests for RFC 3161 TSA anchor backend."""

    def test_tsa_backend_success(self):
        """TSA backend returns anchored receipt on HTTP 200 with granted status."""
        from veritas_os.audit.anchor_backends import TsaAnchorBackend

        fake_response = _make_fake_tsa_response(status_code=0)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = fake_response
        mock_resp.raise_for_status = MagicMock()

        with patch("veritas_os.audit.anchor_backends.httpx.post", return_value=mock_resp):
            backend = TsaAnchorBackend(tsa_url="https://tsa.example.com/tsr")
            entry_hash = hashlib.sha256(b"test_entry").hexdigest()
            receipt = backend.anchor(entry_hash=entry_hash, anchored_at="2024-01-01T00:00:00Z")

        assert receipt.backend == "tsa"
        assert receipt.status == "anchored"
        assert receipt.anchored_hash == entry_hash
        assert receipt.receipt_location == "https://tsa.example.com/tsr"
        assert receipt.receipt_payload_hash is not None
        assert receipt.external_timestamp is not None
        assert receipt.details["ok"] is True
        assert receipt.details["status_code"] == 0
        assert receipt.details["status_text"] == "granted"
        assert receipt.details["raw_receipt_b64"]

    def test_tsa_backend_timeout(self):
        """TSA backend returns failed receipt on timeout."""
        import httpx as _httpx
        from veritas_os.audit.anchor_backends import TsaAnchorBackend

        with patch(
            "veritas_os.audit.anchor_backends.httpx.post",
            side_effect=_httpx.TimeoutException("timeout"),
        ):
            backend = TsaAnchorBackend(tsa_url="https://tsa.example.com/tsr", timeout_seconds=1)
            receipt = backend.anchor(
                entry_hash=hashlib.sha256(b"test").hexdigest(),
                anchored_at="2024-01-01T00:00:00Z",
            )

        assert receipt.status == "failed"
        assert receipt.details["ok"] is False
        assert "TimeoutException" in receipt.details["error"]

    def test_tsa_backend_http_error(self):
        """TSA backend returns failed receipt on HTTP 500."""
        import httpx as _httpx
        from veritas_os.audit.anchor_backends import TsaAnchorBackend

        mock_resp = MagicMock()
        mock_resp.status_code = 500

        with patch(
            "veritas_os.audit.anchor_backends.httpx.post",
            side_effect=_httpx.HTTPStatusError(
                "Server Error",
                request=MagicMock(),
                response=mock_resp,
            ),
        ):
            backend = TsaAnchorBackend(tsa_url="https://tsa.example.com/tsr")
            receipt = backend.anchor(
                entry_hash=hashlib.sha256(b"test").hexdigest(),
                anchored_at="2024-01-01T00:00:00Z",
            )

        assert receipt.status == "failed"
        assert receipt.details["ok"] is False
        assert "HTTP 500" in receipt.details["error"]

    def test_tsa_backend_malformed_receipt(self):
        """TSA backend handles malformed DER response gracefully."""
        from veritas_os.audit.anchor_backends import TsaAnchorBackend

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"\x00\x01\x02"  # garbage DER
        mock_resp.raise_for_status = MagicMock()

        with patch("veritas_os.audit.anchor_backends.httpx.post", return_value=mock_resp):
            backend = TsaAnchorBackend(tsa_url="https://tsa.example.com/tsr")
            receipt = backend.anchor(
                entry_hash=hashlib.sha256(b"test").hexdigest(),
                anchored_at="2024-01-01T00:00:00Z",
            )

        # Malformed DER should result in parse_error, but receipt is still stored
        assert receipt.backend == "tsa"
        assert receipt.receipt_payload_hash is not None  # hash of raw bytes

    def test_tsa_backend_rejection_status(self):
        """TSA backend returns failed when TSA response status is 'rejection'."""
        from veritas_os.audit.anchor_backends import TsaAnchorBackend

        fake_response = _make_fake_tsa_response(status_code=2)  # rejection
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = fake_response
        mock_resp.raise_for_status = MagicMock()

        with patch("veritas_os.audit.anchor_backends.httpx.post", return_value=mock_resp):
            backend = TsaAnchorBackend(tsa_url="https://tsa.example.com/tsr")
            receipt = backend.anchor(
                entry_hash=hashlib.sha256(b"test").hexdigest(),
                anchored_at="2024-01-01T00:00:00Z",
            )

        assert receipt.status == "failed"
        assert receipt.details["status_text"] == "rejection"

    def test_tsa_backend_missing_url_raises(self):
        """TSA backend raises ValueError when URL is empty."""
        from veritas_os.audit.anchor_backends import TsaAnchorBackend

        with pytest.raises(ValueError, match="VERITAS_TRUSTLOG_TSA_URL"):
            TsaAnchorBackend(tsa_url="")


class TestTsaWitnessIntegration:
    """Tests for TSA receipt storage in witness entries."""

    def test_witness_entry_stores_tsa_anchor_receipt(self, monkeypatch, tmp_path):
        """Witness entry includes TSA anchor receipt when backend=tsa."""
        log_path = tmp_path / "trustlog.jsonl"
        private_key = tmp_path / "keys" / "priv.key"
        public_key = tmp_path / "keys" / "pub.key"

        monkeypatch.setattr(trustlog_signed, "SIGNED_TRUSTLOG_JSONL", log_path)
        monkeypatch.setattr(trustlog_signed, "PRIVATE_KEY_PATH", private_key)
        monkeypatch.setattr(trustlog_signed, "PUBLIC_KEY_PATH", public_key)
        monkeypatch.setenv("VERITAS_TRUSTLOG_ANCHOR_BACKEND", "tsa")
        monkeypatch.setenv("VERITAS_TRUSTLOG_TSA_URL", "https://tsa.example.com/tsr")

        fake_response = _make_fake_tsa_response(status_code=0)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = fake_response
        mock_resp.raise_for_status = MagicMock()

        with patch("veritas_os.audit.anchor_backends.httpx.post", return_value=mock_resp):
            entry = trustlog_signed.append_signed_decision(
                {"request_id": "r-tsa", "decision": "allow"}
            )

        assert entry["anchor_backend"] == "tsa"
        assert entry["anchor_status"] == "anchored"
        receipt = entry["anchor_receipt"]
        assert receipt["backend"] == "tsa"
        assert receipt["status"] == "anchored"
        assert receipt["receipt_payload_hash"]
        assert receipt["external_timestamp"]
        assert receipt["details"]["raw_receipt_b64"]


class TestTsaDerHelpers:
    """Tests for DER encoding/parsing helpers."""

    def test_build_timestamp_request(self):
        """Verify TimeStampReq DER structure."""
        from veritas_os.audit.anchor_backends import build_timestamp_request

        digest = hashlib.sha256(b"hello").digest()
        tsq = build_timestamp_request(digest, nonce=12345)

        # Should start with SEQUENCE tag
        assert tsq[0] == 0x30
        # Should be valid DER
        assert len(tsq) > 50

    def test_build_timestamp_request_invalid_digest(self):
        """Verify rejection of non-32-byte digest."""
        from veritas_os.audit.anchor_backends import build_timestamp_request

        with pytest.raises(ValueError, match="32-byte"):
            build_timestamp_request(b"short")

    def test_parse_tsa_response_granted(self):
        """Parse a minimal granted TSA response."""
        from veritas_os.audit.anchor_backends import parse_tsa_response

        resp = _make_fake_tsa_response(status_code=0)
        result = parse_tsa_response(resp)

        assert result["status_code"] == 0
        assert result["status_text"] == "granted"
        assert result["raw_receipt_b64"]
        assert result["receipt_hash"]

    def test_parse_tsa_response_rejection(self):
        """Parse a rejection TSA response."""
        from veritas_os.audit.anchor_backends import parse_tsa_response

        resp = _make_fake_tsa_response(status_code=2)
        result = parse_tsa_response(resp)

        assert result["status_code"] == 2
        assert result["status_text"] == "rejection"

    def test_parse_tsa_response_garbage(self):
        """Gracefully handle garbage input."""
        from veritas_os.audit.anchor_backends import parse_tsa_response

        result = parse_tsa_response(b"\x00\x01")
        assert result["status_code"] == "parse_error"


# ── Goal A: TSA Verifier Integration ──────────────────────────────────────

class TestTsaVerification:
    """Tests for TSA receipt verification in the unified verifier."""

    def test_verifier_validates_tsa_receipt(self, _trustlog_env, monkeypatch):
        """Verifier accepts valid TSA-anchored entries."""
        env = _trustlog_env

        # Create a witness entry with TSA anchor
        monkeypatch.setenv("VERITAS_TRUSTLOG_ANCHOR_BACKEND", "tsa")
        monkeypatch.setenv("VERITAS_TRUSTLOG_TSA_URL", "https://tsa.example.com/tsr")

        fake_response = _make_fake_tsa_response(status_code=0)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = fake_response
        mock_resp.raise_for_status = MagicMock()

        with patch("veritas_os.audit.anchor_backends.httpx.post", return_value=mock_resp):
            trustlog_signed.append_signed_decision(
                {"request_id": "r-verify-tsa", "decision": "allow"}
            )

        result = trustlog_signed.verify_trustlog_chain(path=env["log_path"])
        assert result["ok"] is True

    def test_verifier_detects_tampered_tsa_receipt(self):
        """Verifier detects tampered TSA receipt hash."""
        from veritas_os.audit.trustlog_verify import _verify_tsa_receipt_details

        entry = {
            "anchor_backend": "tsa",
            "anchor_status": "anchored",
            "anchor_receipt": {
                "backend": "tsa",
                "status": "anchored",
                "anchored_hash": hashlib.sha256(b"test").hexdigest(),
                "anchored_at": "2024-01-01T00:00:00Z",
                "receipt_id": "test-receipt-id",
                "receipt_payload_hash": "0000000000000000000000000000000000000000000000000000000000000000",
                "external_timestamp": "2024-01-01T00:00:00Z",
                "details": {
                    "raw_receipt_b64": base64.b64encode(b"tampered").decode(),
                    "status_code": 0,
                },
            },
        }

        error = _verify_tsa_receipt_details(entry)
        assert error == "tsa_receipt_hash_mismatch"

    def test_verifier_passes_non_tsa_entries(self):
        """TSA verification is a no-op for non-TSA anchor backends."""
        from veritas_os.audit.trustlog_verify import _verify_tsa_receipt_details

        entry = {"anchor_backend": "local", "anchor_status": "anchored"}
        assert _verify_tsa_receipt_details(entry) is None

    def test_verifier_detects_missing_raw_receipt(self):
        """Verifier catches missing raw receipt in TSA entries."""
        from veritas_os.audit.trustlog_verify import _verify_tsa_receipt_details

        entry = {
            "anchor_backend": "tsa",
            "anchor_status": "anchored",
            "anchor_receipt": {
                "backend": "tsa",
                "status": "anchored",
                "anchored_hash": hashlib.sha256(b"test").hexdigest(),
                "anchored_at": "2024-01-01T00:00:00Z",
                "receipt_id": "test-id",
                "receipt_payload_hash": None,
                "external_timestamp": None,
                "details": {},  # missing raw_receipt_b64
            },
        }

        error = _verify_tsa_receipt_details(entry)
        assert error == "tsa_receipt_missing_raw"


# ── Goal B: Standalone CLI ────────────────────────────────────────────────

class TestStandaloneCli:
    """Tests for standalone TrustLog verifier CLI."""

    def test_cli_happy_path_witness_only(self, _trustlog_env):
        """CLI verifies witness ledger successfully."""
        env = _trustlog_env

        trustlog_signed.append_signed_decision(
            {"request_id": "r-cli", "decision": "allow"}
        )

        from veritas_os.cli.verify_trustlog import main
        exit_code = main(["--witness-ledger", str(env["log_path"]), "--json"])
        assert exit_code == 0

    def test_cli_json_output_schema(self, _trustlog_env, capsys):
        """CLI JSON output has expected structure."""
        env = _trustlog_env

        trustlog_signed.append_signed_decision(
            {"request_id": "r-json", "decision": "allow"}
        )

        from veritas_os.cli.verify_trustlog import main
        exit_code = main(["--witness-ledger", str(env["log_path"]), "--json"])
        assert exit_code == 0

        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert "ok" in result
        assert "errors" in result
        assert "notes" in result
        assert result["ok"] is True

    def test_cli_failure_path_missing_file(self, tmp_path):
        """CLI returns exit code 2 for missing file."""
        from veritas_os.cli.verify_trustlog import main

        missing = tmp_path / "nonexistent.jsonl"
        exit_code = main(["--witness-ledger", str(missing)])
        assert exit_code == 2

    def test_cli_failure_path_no_args(self):
        """CLI returns exit code 2 when no ledger specified."""
        from veritas_os.cli.verify_trustlog import main
        exit_code = main([])
        assert exit_code == 2

    def test_cli_strict_exit_code_on_tamper(self, _trustlog_env):
        """CLI returns exit code 1 when verification fails."""
        env = _trustlog_env

        trustlog_signed.append_signed_decision(
            {"request_id": "r-tamper", "decision": "allow"}
        )

        # Tamper with the ledger
        content = env["log_path"].read_text(encoding="utf-8")
        first = json.loads(content.strip())
        first["decision_payload"]["request_id"] = "TAMPERED"
        env["log_path"].write_text(json.dumps(first) + "\n", encoding="utf-8")

        from veritas_os.cli.verify_trustlog import main
        exit_code = main(["--witness-ledger", str(env["log_path"]), "--json"])
        assert exit_code == 1

    def test_cli_text_output_format(self, _trustlog_env, capsys):
        """CLI text output contains expected sections."""
        env = _trustlog_env

        trustlog_signed.append_signed_decision(
            {"request_id": "r-text", "decision": "allow"}
        )

        from veritas_os.cli.verify_trustlog import main
        exit_code = main(["--witness-ledger", str(env["log_path"])])
        assert exit_code == 0

        captured = capsys.readouterr()
        assert "VERITAS TrustLog Verification Report" in captured.out
        assert "Overall status: PASS" in captured.out

    def test_cli_run_verification_programmatic(self, _trustlog_env):
        """run_verification() can be called programmatically."""
        env = _trustlog_env

        trustlog_signed.append_signed_decision(
            {"request_id": "r-prog", "decision": "allow"}
        )

        from veritas_os.cli.verify_trustlog import run_verification
        result = run_verification(witness_ledger_path=env["log_path"])
        assert result["ok"] is True
        assert result["total_errors"] == 0


# ── Goal C: Evidence Bundle ───────────────────────────────────────────────

class TestEvidenceBundleGeneration:
    """Tests for evidence bundle generation."""

    def test_decision_bundle_generation(self, _trustlog_env):
        """Generate a single decision evidence bundle."""
        env = _trustlog_env
        output_dir = env["tmp_path"] / "bundles"

        trustlog_signed.append_signed_decision(
            {"request_id": "r-bundle-1", "decision": "allow"}
        )

        from veritas_os.audit.evidence_bundle import generate_evidence_bundle
        result = generate_evidence_bundle(
            bundle_type="decision",
            witness_ledger_path=env["log_path"],
            output_dir=output_dir,
            request_ids=["r-bundle-1"],
        )

        assert result["bundle_type"] == "decision"
        assert result["entry_count"] == 1
        assert "manifest.json" in result["files"]
        assert "witness_entries.jsonl" in result["files"]
        assert "acceptance_checklist.json" in result["files"]
        assert "README.txt" in result["files"]
        assert "ui_delivery_hook.json" in result["files"]

        # Verify manifest on disk
        bundle_dir = Path(result["bundle_dir"])
        manifest = json.loads((bundle_dir / "manifest.json").read_text())
        assert manifest["schema_version"] == "1.1.0"
        assert manifest["bundle_type"] == "decision"
        assert manifest["entry_count"] == 1
        decision_record = json.loads((bundle_dir / "decision_record.json").read_text())
        assert decision_record["decision_payload"]["request_id"] == "r-bundle-1"
        assert "trustlog_references" in decision_record
        assert decision_record["verification"]["report_path"] == "verification_report.json"
        assert "runtime_context" not in decision_record

    def test_decision_bundle_full_profile_contains_full_fields(self, _trustlog_env):
        """Decision full profile includes runtime and evidence fields."""
        env = _trustlog_env
        output_dir = env["tmp_path"] / "bundles"

        trustlog_signed.append_signed_decision(
            {"request_id": "r-bundle-full", "decision": "allow"}
        )

        from veritas_os.audit.evidence_bundle import generate_evidence_bundle

        result = generate_evidence_bundle(
            bundle_type="decision",
            witness_ledger_path=env["log_path"],
            output_dir=output_dir,
            request_ids=["r-bundle-full"],
            decision_record_profile="full",
        )

        bundle_dir = Path(result["bundle_dir"])
        decision_record = json.loads((bundle_dir / "decision_record.json").read_text())
        assert "runtime_context" in decision_record
        assert "required_evidence" in decision_record
        assert "human_review_required" in decision_record

    def test_incident_bundle_generation(self, _trustlog_env):
        """Generate an incident evidence bundle with multiple entries."""
        env = _trustlog_env
        output_dir = env["tmp_path"] / "bundles"

        for i in range(3):
            trustlog_signed.append_signed_decision(
                {"request_id": f"r-incident-{i}", "decision": "allow"}
            )

        from veritas_os.audit.evidence_bundle import generate_evidence_bundle
        result = generate_evidence_bundle(
            bundle_type="incident",
            witness_ledger_path=env["log_path"],
            output_dir=output_dir,
            request_ids=[f"r-incident-{i}" for i in range(3)],
            incident_metadata={"incident_id": "INC-001", "severity": "high"},
        )

        assert result["bundle_type"] == "incident"
        assert result["entry_count"] == 3
        assert "incident_metadata.json" in result["files"]

    def test_release_bundle_generation(self, _trustlog_env):
        """Generate a release evidence bundle."""
        env = _trustlog_env
        output_dir = env["tmp_path"] / "bundles"

        for i in range(5):
            trustlog_signed.append_signed_decision(
                {"request_id": f"r-release-{i}", "decision": "allow"}
            )

        from veritas_os.audit.evidence_bundle import generate_evidence_bundle
        result = generate_evidence_bundle(
            bundle_type="release",
            witness_ledger_path=env["log_path"],
            output_dir=output_dir,
            release_provenance={"version": "2.0.0", "git_sha": "abc123"},
        )

        assert result["bundle_type"] == "release"
        assert result["entry_count"] == 5
        assert "release_provenance.json" in result["files"]

    def test_bundle_invalid_type_raises(self, _trustlog_env):
        """Bundle generation rejects invalid types."""
        env = _trustlog_env
        from veritas_os.audit.evidence_bundle import generate_evidence_bundle

        with pytest.raises(ValueError, match="Invalid bundle_type"):
            generate_evidence_bundle(
                bundle_type="invalid",
                witness_ledger_path=env["log_path"],
                output_dir=env["tmp_path"] / "out",
            )

    def test_bundle_no_matching_entries_raises(self, _trustlog_env):
        """Bundle generation raises when no entries match filter."""
        env = _trustlog_env

        trustlog_signed.append_signed_decision(
            {"request_id": "r-no-match", "decision": "allow"}
        )

        from veritas_os.audit.evidence_bundle import generate_evidence_bundle

        with pytest.raises(ValueError, match="No witness entries"):
            generate_evidence_bundle(
                bundle_type="decision",
                witness_ledger_path=env["log_path"],
                output_dir=env["tmp_path"] / "out",
                request_ids=["nonexistent-id"],
            )

    def test_bundle_with_signed_manifest(self, _trustlog_env):
        """Bundle manifest includes signature when signer is provided."""
        env = _trustlog_env
        output_dir = env["tmp_path"] / "bundles"

        trustlog_signed.append_signed_decision(
            {"request_id": "r-signed-bundle", "decision": "allow"}
        )

        def fake_signer(payload_hash: str) -> str:
            return base64.b64encode(b"fake_signature").decode()

        from veritas_os.audit.evidence_bundle import generate_evidence_bundle
        result = generate_evidence_bundle(
            bundle_type="decision",
            witness_ledger_path=env["log_path"],
            output_dir=output_dir,
            signer_fn=fake_signer,
            signer_metadata={"type": "test"},
        )

        bundle_dir = Path(result["bundle_dir"])
        manifest = json.loads((bundle_dir / "manifest.json").read_text())
        assert manifest.get("manifest_signature") is not None
        assert manifest.get("manifest_signer") == {"type": "test"}

    def test_bundle_archive_creation(self, _trustlog_env):
        """Create a tar.gz archive from a bundle."""
        env = _trustlog_env
        output_dir = env["tmp_path"] / "bundles"

        trustlog_signed.append_signed_decision(
            {"request_id": "r-archive", "decision": "allow"}
        )

        from veritas_os.audit.evidence_bundle import (
            generate_evidence_bundle,
            create_bundle_archive,
        )
        result = generate_evidence_bundle(
            bundle_type="decision",
            witness_ledger_path=env["log_path"],
            output_dir=output_dir,
        )

        archive_path = create_bundle_archive(Path(result["bundle_dir"]))
        assert archive_path.exists()
        assert archive_path.suffix == ".gz"


class TestEvidenceBundleVerification:
    """Tests for evidence bundle verification."""

    def test_verify_valid_bundle(self, _trustlog_env):
        """Verification passes for untampered bundle."""
        env = _trustlog_env
        output_dir = env["tmp_path"] / "bundles"

        trustlog_signed.append_signed_decision(
            {"request_id": "r-verify", "decision": "allow"}
        )

        from veritas_os.audit.evidence_bundle import generate_evidence_bundle
        from veritas_os.audit.verify_bundle import verify_evidence_bundle

        result = generate_evidence_bundle(
            bundle_type="decision",
            witness_ledger_path=env["log_path"],
            output_dir=output_dir,
        )

        verify_result = verify_evidence_bundle(Path(result["bundle_dir"]))
        assert verify_result["ok"] is True
        assert verify_result["tampered"] is False
        assert not verify_result["errors"]

    def test_verify_bundle_regression_with_contract_artifacts(self, _trustlog_env):
        """Verification remains green with README/checklist/UI hook artifacts."""
        env = _trustlog_env
        output_dir = env["tmp_path"] / "bundles"

        trustlog_signed.append_signed_decision(
            {"request_id": "r-regression", "decision": "allow"}
        )

        from veritas_os.audit.evidence_bundle import generate_evidence_bundle
        from veritas_os.audit.verify_bundle import verify_evidence_bundle

        result = generate_evidence_bundle(
            bundle_type="decision",
            witness_ledger_path=env["log_path"],
            output_dir=output_dir,
            request_ids=["r-regression"],
            decision_record_profile="minimum",
        )
        bundle_dir = Path(result["bundle_dir"])
        checklist = json.loads((bundle_dir / "acceptance_checklist.json").read_text())
        checklist_ids = {item["id"] for item in checklist["items"]}
        assert "decision_record_contract" in checklist_ids

        verify_result = verify_evidence_bundle(bundle_dir)
        assert verify_result["ok"] is True

    def test_detect_tampered_file(self, _trustlog_env):
        """Verification detects tampered witness entries file."""
        env = _trustlog_env
        output_dir = env["tmp_path"] / "bundles"

        trustlog_signed.append_signed_decision(
            {"request_id": "r-tamper-detect", "decision": "allow"}
        )

        from veritas_os.audit.evidence_bundle import generate_evidence_bundle
        from veritas_os.audit.verify_bundle import verify_evidence_bundle

        result = generate_evidence_bundle(
            bundle_type="decision",
            witness_ledger_path=env["log_path"],
            output_dir=output_dir,
        )

        # Tamper with a file
        bundle_dir = Path(result["bundle_dir"])
        witness_file = bundle_dir / "witness_entries.jsonl"
        witness_file.write_text('{"tampered": true}\n', encoding="utf-8")

        verify_result = verify_evidence_bundle(bundle_dir)
        assert verify_result["ok"] is False
        assert verify_result["tampered"] is True
        assert any("Hash mismatch" in e for e in verify_result["errors"])

    def test_detect_missing_file(self, _trustlog_env):
        """Verification detects deleted file from bundle."""
        env = _trustlog_env
        output_dir = env["tmp_path"] / "bundles"

        trustlog_signed.append_signed_decision(
            {"request_id": "r-missing-file", "decision": "allow"}
        )

        from veritas_os.audit.evidence_bundle import generate_evidence_bundle
        from veritas_os.audit.verify_bundle import verify_evidence_bundle

        result = generate_evidence_bundle(
            bundle_type="decision",
            witness_ledger_path=env["log_path"],
            output_dir=output_dir,
        )

        # Delete a file
        bundle_dir = Path(result["bundle_dir"])
        (bundle_dir / "witness_entries.jsonl").unlink()

        verify_result = verify_evidence_bundle(bundle_dir)
        assert verify_result["ok"] is False
        assert verify_result["tampered"] is True

    def test_detect_missing_manifest(self, tmp_path):
        """Verification detects missing manifest."""
        from veritas_os.audit.verify_bundle import verify_evidence_bundle

        empty_dir = tmp_path / "empty_bundle"
        empty_dir.mkdir()

        verify_result = verify_evidence_bundle(empty_dir)
        assert verify_result["ok"] is False
        assert verify_result["tampered"] is True
        assert any("manifest.json not found" in e for e in verify_result["errors"])

    def test_verify_manifest_hash_integrity(self, _trustlog_env):
        """Verification detects tampered manifest hash."""
        env = _trustlog_env
        output_dir = env["tmp_path"] / "bundles"

        trustlog_signed.append_signed_decision(
            {"request_id": "r-manifest-tamper", "decision": "allow"}
        )

        from veritas_os.audit.evidence_bundle import generate_evidence_bundle
        from veritas_os.audit.verify_bundle import verify_evidence_bundle

        result = generate_evidence_bundle(
            bundle_type="decision",
            witness_ledger_path=env["log_path"],
            output_dir=output_dir,
        )

        # Tamper with manifest
        bundle_dir = Path(result["bundle_dir"])
        manifest_path = bundle_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["created_by"] = "attacker"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

        verify_result = verify_evidence_bundle(bundle_dir)
        assert verify_result["ok"] is False
        assert verify_result["tampered"] is True


# ── Legacy Compatibility ──────────────────────────────────────────────────

class TestLegacyCompatibility:
    """Tests ensuring legacy TrustLog entries remain compatible."""

    def test_legacy_entry_without_anchor_fields(self, _trustlog_env):
        """Entries without anchor fields are accepted as legacy."""
        legacy_entry = {
            "decision_id": "test-legacy-id",
            "timestamp": "2024-01-01T00:00:00Z",
            "previous_hash": None,
            "decision_payload": {"request_id": "r-legacy"},
            "payload_hash": "abc123",
            "signature": "sig123",
            "signer_type": "file",
            "signer_key_id": "key123",
        }

        def _always_true(_entry):
            return True

        result = verify_witness_ledger(
            entries=[legacy_entry],
            verify_signature_fn=_always_true,
        )
        # Legacy entries may have notes but should not produce anchor errors
        anchor_errors = [
            e for e in result["detailed_errors"]
            if "anchor" in e.get("reason", "")
        ]
        assert not anchor_errors

    def test_noop_anchor_still_works(self, _trustlog_env):
        """NoOp anchor backend continues to function."""
        env = _trustlog_env

        entry = trustlog_signed.append_signed_decision(
            {"request_id": "r-noop", "decision": "allow"}
        )

        assert entry["anchor_backend"] == "noop"
        assert entry["anchor_status"] == "skipped"

        result = trustlog_signed.verify_trustlog_chain(path=env["log_path"])
        assert result["ok"] is True

    def test_local_anchor_still_works(self, monkeypatch, tmp_path):
        """Local anchor backend continues to function."""
        log_path = tmp_path / "trustlog.jsonl"
        anchor_path = tmp_path / "anchor.jsonl"
        private_key = tmp_path / "keys" / "priv.key"
        public_key = tmp_path / "keys" / "pub.key"

        monkeypatch.setattr(trustlog_signed, "SIGNED_TRUSTLOG_JSONL", log_path)
        monkeypatch.setattr(trustlog_signed, "PRIVATE_KEY_PATH", private_key)
        monkeypatch.setattr(trustlog_signed, "PUBLIC_KEY_PATH", public_key)
        monkeypatch.setenv("VERITAS_TRUSTLOG_ANCHOR_BACKEND", "local")
        monkeypatch.setenv("VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH", str(anchor_path))

        entry = trustlog_signed.append_signed_decision(
            {"request_id": "r-local", "decision": "allow"}
        )

        assert entry["anchor_backend"] == "local"
        assert entry["anchor_status"] == "anchored"
        assert anchor_path.exists()


# ── Secure/Prod Posture ──────────────────────────────────────────────────

class TestPostureIntegration:
    """Tests for secure/prod posture integration."""

    def test_build_anchor_backend_tsa(self, monkeypatch):
        """_build_anchor_backend returns TSA backend when configured."""
        monkeypatch.setenv("VERITAS_TRUSTLOG_ANCHOR_BACKEND", "tsa")
        monkeypatch.setenv("VERITAS_TRUSTLOG_TSA_URL", "https://tsa.example.com/tsr")

        backend = trustlog_signed._build_anchor_backend()
        assert backend.backend_name == "tsa"

    def test_build_anchor_backend_unsupported(self, monkeypatch):
        """_build_anchor_backend raises for unsupported backends."""
        monkeypatch.setenv("VERITAS_TRUSTLOG_ANCHOR_BACKEND", "blockchain")

        with pytest.raises(ValueError, match="Unsupported"):
            trustlog_signed._build_anchor_backend()

    def test_tsa_backend_factory(self, monkeypatch):
        """build_tsa_anchor_backend reads from env."""
        monkeypatch.setenv("VERITAS_TRUSTLOG_TSA_URL", "https://tsa.example.com/tsr")
        monkeypatch.setenv("VERITAS_TRUSTLOG_TSA_TIMEOUT_SECONDS", "30")

        from veritas_os.audit.anchor_backends import build_tsa_anchor_backend
        backend = build_tsa_anchor_backend()
        assert backend.backend_name == "tsa"
        assert backend._timeout == 30.0


# ── Evidence Bundle Schema ────────────────────────────────────────────────

class TestEvidenceBundleSchema:
    """Tests for evidence bundle schema definitions."""

    def test_schema_version(self):
        from veritas_os.audit.evidence_bundle_schema import BUNDLE_SCHEMA_VERSION
        assert BUNDLE_SCHEMA_VERSION == "1.1.0"

    def test_bundle_types(self):
        from veritas_os.audit.evidence_bundle_schema import BUNDLE_TYPES
        assert "decision" in BUNDLE_TYPES
        assert "incident" in BUNDLE_TYPES
        assert "release" in BUNDLE_TYPES

    def test_manifest_required_fields(self):
        from veritas_os.audit.evidence_bundle_schema import MANIFEST_REQUIRED_FIELDS
        assert "schema_version" in MANIFEST_REQUIRED_FIELDS
        assert "bundle_type" in MANIFEST_REQUIRED_FIELDS
        assert "bundle_id" in MANIFEST_REQUIRED_FIELDS

    def test_decision_snapshot_required_fields(self):
        from veritas_os.audit.evidence_bundle_schema import (
            DECISION_SNAPSHOT_FULL_REQUIRED_FIELDS,
            DECISION_SNAPSHOT_MINIMUM_REQUIRED_FIELDS,
            DECISION_SNAPSHOT_REQUIRED_FIELDS,
        )

        assert "gate_decision" in DECISION_SNAPSHOT_REQUIRED_FIELDS
        assert "business_decision" in DECISION_SNAPSHOT_REQUIRED_FIELDS
        assert "next_action" in DECISION_SNAPSHOT_REQUIRED_FIELDS
        assert "runtime_context" in DECISION_SNAPSHOT_FULL_REQUIRED_FIELDS
        assert "runtime_context" not in DECISION_SNAPSHOT_MINIMUM_REQUIRED_FIELDS
