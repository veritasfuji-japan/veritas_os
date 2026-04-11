"""Tests for unified TrustLog verification API and CLI."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

from veritas_os.audit.trustlog_verify import (
    verify_full_ledger,
    verify_trustlogs,
    verify_witness_ledger,
)
from veritas_os.logging.encryption import encrypt, generate_key
from veritas_os.security.hash import sha256_hex, sha256_of_canonical_json


class _FakeS3Client:
    def __init__(
        self,
        *,
        head_response: Dict[str, Any] | None = None,
        head_error: Exception | None = None,
        retention_response: Dict[str, Any] | None = None,
        retention_error: Exception | None = None,
    ) -> None:
        self.head_response = head_response or {}
        self.head_error = head_error
        self.retention_response = retention_response or {}
        self.retention_error = retention_error
        self.head_calls = 0

    def head_object(self, **_: Any) -> Dict[str, Any]:
        self.head_calls += 1
        if self.head_error is not None:
            raise self.head_error
        return self.head_response

    def get_object_retention(self, **_: Any) -> Dict[str, Any]:
        if self.retention_error is not None:
            raise self.retention_error
        return self.retention_response

    def get_object_legal_hold(self, **_: Any) -> Dict[str, Any]:
        return {"LegalHold": {"Status": "ON"}}


def _full_hash(prev_hash: str | None, entry: Dict[str, Any]) -> str:
    payload = dict(entry)
    payload.pop("sha256", None)
    payload.pop("sha256_prev", None)
    entry_json = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    combined = f"{prev_hash}{entry_json}" if prev_hash else entry_json
    return sha256_hex(combined)


def _write_full_log(path: Path, entries: List[Dict[str, Any]]) -> None:
    prev_hash = None
    lines = []
    for entry in entries:
        row = dict(entry)
        row["sha256_prev"] = prev_hash
        row["sha256"] = _full_hash(prev_hash, row)
        prev_hash = row["sha256"]
        lines.append(encrypt(json.dumps(row, ensure_ascii=False)))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _iter_full_rows(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        from veritas_os.logging.encryption import decrypt
        for line in file:
            stripped = line.strip()
            if not stripped:
                continue
            rows.append(json.loads(decrypt(stripped)))
    return rows


def _build_witness_chain() -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    previous_hash = None
    for idx in range(2):
        payload = {"request_id": f"r-{idx}", "decision": "allow"}
        entry = {
            "decision_payload": payload,
            "payload_hash": sha256_of_canonical_json(payload),
            "previous_hash": previous_hash,
            "signature": "sig-ok",
            # legacy compatibility: omit full_payload_hash on first entry
        }
        if idx == 1:
            entry["full_payload_hash"] = "a" * 64
            entry["mirror_receipt"] = {"bucket": "b", "key": "k"}
        chain_hash = sha256_hex(
            json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        )
        previous_hash = chain_hash
        entries.append(entry)
    return entries


def test_unified_verifier_good_path(tmp_path: Path, monkeypatch) -> None:
    """Good path should pass with legacy witness metadata omitted."""
    monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", generate_key())
    full_log = tmp_path / "trust_log.jsonl"
    witness = _build_witness_chain()
    _write_full_log(full_log, [{"request_id": "r-0"}, {"request_id": "r-1"}])

    result = verify_trustlogs(
        full_log_path=full_log,
        witness_entries=witness,
        verify_signature_fn=lambda _: True,
    )

    assert result["ok"] is True
    assert result["chain_ok"] is True
    assert result["signature_ok"] is True
    assert result["linkage_ok"] is True
    assert result["mirror_ok"] is True
    assert result["invalid_entries"] == 0
    note_codes = {note["code"] for note in result["verification_notes"]}
    assert "legacy_entry" in note_codes


def test_unified_verifier_broken_path(tmp_path: Path, monkeypatch) -> None:
    """Broken chain/signature/linkage/mirror should be reported."""
    monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", generate_key())
    full_log = tmp_path / "trust_log.jsonl"
    _write_full_log(full_log, [{"request_id": "r-0"}])

    witness = _build_witness_chain()
    witness[1]["previous_hash"] = "broken-prev"
    witness[1]["full_payload_hash"] = "not-a-hash"
    witness[1]["mirror_receipt"] = "invalid-receipt"

    result = verify_trustlogs(
        full_log_path=full_log,
        witness_entries=witness,
        verify_signature_fn=lambda _: False,
    )

    assert result["ok"] is False
    assert result["chain_ok"] is False
    assert result["signature_ok"] is False
    assert result["linkage_ok"] is False
    assert result["mirror_ok"] is False
    assert result["invalid_entries"] > 0
    reasons = {error["reason"] for error in result["detailed_errors"]}
    codes = {error["code"] for error in result["detailed_errors"]}
    assert "previous_hash_mismatch" in reasons
    assert "signature_invalid" in reasons
    assert "full_payload_hash_invalid" in reasons
    assert "mirror_receipt_malformed" in reasons
    assert "chain_broken" in codes
    assert "signature_invalid" in codes
    assert "schema_invalid" in codes
    assert "mirror_receipt_malformed" in codes



def test_witness_linkage_verification_success(tmp_path: Path, monkeypatch) -> None:
    """Witness linkage succeeds when artifact_ref resolves to full ledger entry."""
    monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", generate_key())
    full_entry = {"request_id": "r-link-ok", "decision": "allow"}
    full_log = tmp_path / "trust_log.jsonl"
    _write_full_log(full_log, [full_entry])

    full_rows = list(_iter_full_rows(full_log))
    assert len(full_rows) == 1
    full_payload = full_rows[0]

    witness = [
        {
            "decision_payload": {"request_id": "r-link-ok"},
            "payload_hash": sha256_of_canonical_json({"request_id": "r-link-ok"}),
            "previous_hash": None,
            "signature": "sig-ok",
            "full_payload_hash": sha256_of_canonical_json(full_payload),
            "artifact_ref": {
                "artifact_ref": "trustlog_full_payload",
                "artifact_type": "trust_log_entry",
                "artifact_storage_backend": "trustlog_full_ledger",
                "artifact_locator": f"sha256:{full_payload['sha256']}",
                "artifact_hash_algorithm": "sha256_canonical_json",
            },
        }
    ]

    result = verify_witness_ledger(
        witness,
        lambda _: True,
        artifact_search_roots=[tmp_path],
    )

    assert result["ok"] is True
    assert result["linkage_ok"] is True


def test_witness_linkage_artifact_missing(tmp_path: Path, monkeypatch) -> None:
    """Missing artifact reference must surface artifact_missing."""
    monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", generate_key())
    payload = {"request_id": "r-missing"}
    witness = [
        {
            "decision_payload": payload,
            "payload_hash": sha256_of_canonical_json(payload),
            "previous_hash": None,
            "signature": "sig-ok",
            "full_payload_hash": "a" * 64,
            "artifact_ref": {
                "artifact_ref": "trustlog_full_payload",
                "artifact_type": "trust_log_entry",
                "artifact_storage_backend": "trustlog_full_ledger",
                "artifact_locator": "sha256:" + "b" * 64,
                "artifact_hash_algorithm": "sha256_canonical_json",
            },
        }
    ]

    result = verify_witness_ledger(
        witness,
        lambda _: True,
        artifact_search_roots=[tmp_path],
    )

    assert result["ok"] is False
    assert result["linkage_ok"] is False
    reasons = {error["reason"] for error in result["detailed_errors"]}
    assert "artifact_missing" in reasons


def test_witness_linkage_hash_mismatch_on_tampered_artifact(tmp_path: Path, monkeypatch) -> None:
    """Tampered artifact content must trigger linkage_hash_mismatch."""
    monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", generate_key())
    full_entry = {"request_id": "r-tamper", "decision": "allow"}
    full_log = tmp_path / "trust_log.jsonl"
    _write_full_log(full_log, [full_entry])

    full_rows = list(_iter_full_rows(full_log))
    tampered = dict(full_rows[0])
    tampered["decision"] = "reject"
    _write_full_log(full_log, [tampered])
    rewritten_rows = list(_iter_full_rows(full_log))

    witness = [
        {
            "decision_payload": {"request_id": "r-tamper"},
            "payload_hash": sha256_of_canonical_json({"request_id": "r-tamper"}),
            "previous_hash": None,
            "signature": "sig-ok",
            "full_payload_hash": sha256_of_canonical_json(full_rows[0]),
            "artifact_ref": {
                "artifact_ref": "trustlog_full_payload",
                "artifact_type": "trust_log_entry",
                "artifact_storage_backend": "trustlog_full_ledger",
                "artifact_locator": f"sha256:{rewritten_rows[0]['sha256']}",
                "artifact_hash_algorithm": "sha256_canonical_json",
            },
        }
    ]

    result = verify_witness_ledger(
        witness,
        lambda _: True,
        artifact_search_roots=[tmp_path],
    )

    assert result["ok"] is False
    reasons = {error["reason"] for error in result["detailed_errors"]}
    assert "linkage_hash_mismatch" in reasons


def test_witness_linkage_legacy_without_artifact_ref(tmp_path: Path, monkeypatch) -> None:
    """Legacy entry without artifact_ref remains verifiable via request_id fallback."""
    monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", generate_key())
    full_entry = {"request_id": "r-legacy", "decision": "allow"}
    full_log = tmp_path / "trust_log.jsonl"
    _write_full_log(full_log, [full_entry])
    full_rows = list(_iter_full_rows(full_log))

    witness = [
        {
            "decision_payload": {"request_id": "r-legacy"},
            "payload_hash": sha256_of_canonical_json({"request_id": "r-legacy"}),
            "previous_hash": None,
            "signature": "sig-ok",
            "full_payload_hash": sha256_of_canonical_json(full_rows[0]),
        }
    ]

    result = verify_witness_ledger(
        witness,
        lambda _: True,
        artifact_search_roots=[tmp_path],
    )

    assert result["ok"] is True
    assert result["linkage_ok"] is True


def test_witness_linkage_malformed_artifact_ref(tmp_path: Path, monkeypatch) -> None:
    """Malformed artifact_ref must not be accepted."""
    monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", generate_key())
    payload = {"request_id": "r-bad-ref"}

    witness = [
        {
            "decision_payload": payload,
            "payload_hash": sha256_of_canonical_json(payload),
            "previous_hash": None,
            "signature": "sig-ok",
            "full_payload_hash": "a" * 64,
            "artifact_ref": "not-a-dict",
        }
    ]

    result = verify_witness_ledger(
        witness,
        lambda _: True,
        artifact_search_roots=[tmp_path],
    )

    assert result["ok"] is False
    reasons = {error["reason"] for error in result["detailed_errors"]}
    assert "malformed_artifact_ref" in reasons

def test_verify_trust_log_cli_json_output(tmp_path: Path, monkeypatch) -> None:
    """CLI must expose required stable output fields."""
    monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", generate_key())
    full_log = tmp_path / "trust_log.jsonl"
    witness_log = tmp_path / "trustlog.jsonl"
    _write_full_log(full_log, [{"request_id": "r-0"}])
    witness_log.write_text("", encoding="utf-8")

    cmd = [
        sys.executable,
        "-m",
        "veritas_os.scripts.verify_trust_log",
        "--full-log",
        str(full_log),
        "--witness-log",
        str(witness_log),
        "--json",
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    data = json.loads(completed.stdout)

    required = {
        "total_entries",
        "valid_entries",
        "invalid_entries",
        "chain_ok",
        "signature_ok",
        "linkage_ok",
        "mirror_ok",
        "last_hash",
        "detailed_errors",
        "verification_notes",
    }
    assert required.issubset(data.keys())
    assert completed.returncode == 0


def test_individual_apis_cover_full_and_witness(tmp_path: Path, monkeypatch) -> None:
    """Stable individual APIs should remain callable for local/dev flows."""
    monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", generate_key())
    full_log = tmp_path / "trust_log.jsonl"
    _write_full_log(full_log, [{"request_id": "r-0"}])

    full_result = verify_full_ledger(full_log)
    witness_result = verify_witness_ledger(_build_witness_chain(), lambda _: True)

    assert full_result["ok"] is True
    assert witness_result["ok"] is True


def _s3_receipt_witness() -> List[Dict[str, Any]]:
    payload = {"request_id": "r-s3", "decision": "allow"}
    return [
        {
            "decision_payload": payload,
            "payload_hash": sha256_of_canonical_json(payload),
            "previous_hash": None,
            "signature": "sig-ok",
            "mirror_backend": "s3_object_lock",
            "mirror_receipt": {
                "bucket": "trustlog-bucket",
                "key": "mirror/path.jsonl",
                "version_id": "v1",
                "etag": '"etag-1"',
                "retention_mode": "GOVERNANCE",
                "retain_until_date": "2030-01-01T00:00:00Z",
            },
        }
    ]


def test_mirror_remote_verification_success(monkeypatch) -> None:
    monkeypatch.setenv("VERITAS_TRUSTLOG_VERIFY_MIRROR_REMOTE", "1")
    monkeypatch.setenv("VERITAS_TRUSTLOG_VERIFY_MIRROR_S3_STRICT", "1")
    client = _FakeS3Client(
        head_response={"VersionId": "v1", "ETag": '"etag-1"'},
        retention_response={
            "Retention": {
                "Mode": "GOVERNANCE",
                "RetainUntilDate": "2030-01-01T00:00:00Z",
            }
        },
    )
    result = verify_witness_ledger(_s3_receipt_witness(), lambda _: True, s3_client=client)
    assert result["ok"] is True
    assert result["mirror_ok"] is True


def test_mirror_remote_object_missing(monkeypatch) -> None:
    monkeypatch.setenv("VERITAS_TRUSTLOG_VERIFY_MIRROR_REMOTE", "1")
    client = _FakeS3Client(head_error=RuntimeError("not found"))
    result = verify_witness_ledger(_s3_receipt_witness(), lambda _: True, s3_client=client)
    errors = result["detailed_errors"]
    reasons = {error["reason"] for error in errors}
    codes = {error["code"] for error in errors}
    assert "mirror_object_not_found" in reasons
    assert "mirror_unreachable" in codes


def test_mirror_remote_version_mismatch(monkeypatch) -> None:
    monkeypatch.setenv("VERITAS_TRUSTLOG_VERIFY_MIRROR_REMOTE", "1")
    client = _FakeS3Client(head_response={"VersionId": "v2", "ETag": '"etag-1"'})
    result = verify_witness_ledger(_s3_receipt_witness(), lambda _: True, s3_client=client)
    reasons = {error["reason"] for error in result["detailed_errors"]}
    codes = {error["code"] for error in result["detailed_errors"]}
    assert "mirror_version_mismatch" in reasons
    assert "tamper_suspected" in codes


def test_mirror_remote_retention_missing_in_strict_mode(monkeypatch) -> None:
    monkeypatch.setenv("VERITAS_TRUSTLOG_VERIFY_MIRROR_REMOTE", "1")
    monkeypatch.setenv("VERITAS_TRUSTLOG_VERIFY_MIRROR_S3_STRICT", "1")
    client = _FakeS3Client(
        head_response={"VersionId": "v1", "ETag": '"etag-1"'},
        retention_response={},
    )
    result = verify_witness_ledger(_s3_receipt_witness(), lambda _: True, s3_client=client)
    reasons = {error["reason"] for error in result["detailed_errors"]}
    assert "mirror_retention_missing" in reasons


def test_mirror_receipt_missing_strict_vs_non_strict(monkeypatch) -> None:
    entry = {
        "decision_payload": {"request_id": "r-old"},
        "payload_hash": sha256_of_canonical_json({"request_id": "r-old"}),
        "previous_hash": None,
        "signature": "sig-ok",
    }
    result = verify_witness_ledger([entry], lambda _: True)
    assert result["ok"] is True

    monkeypatch.setenv("VERITAS_TRUSTLOG_VERIFY_MIRROR_S3_STRICT", "1")
    strict_result = verify_witness_ledger([entry], lambda _: True)
    reasons = {error["reason"] for error in strict_result["detailed_errors"]}
    codes = {error["code"] for error in strict_result["detailed_errors"]}
    assert "mirror_receipt_missing" in reasons
    assert "mirror_unreachable" in codes


def test_mirror_remote_offline_mode_skips_validation(monkeypatch) -> None:
    monkeypatch.delenv("VERITAS_TRUSTLOG_VERIFY_MIRROR_REMOTE", raising=False)
    client = _FakeS3Client(head_error=RuntimeError("offline-skip"))
    result = verify_witness_ledger(_s3_receipt_witness(), lambda _: True, s3_client=client)
    assert result["ok"] is True
    assert client.head_calls == 0


def test_full_ledger_key_missing_classification(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("VERITAS_ENCRYPTION_KEY", raising=False)
    full_log = tmp_path / "trust_log.jsonl"
    full_log.write_text("not-encrypted\n", encoding="utf-8")
    result = verify_full_ledger(full_log)
    codes = {error["code"] for error in result["detailed_errors"]}
    assert "key_missing" in codes or "decrypt_failed" in codes


def test_witness_payload_hash_mismatch_code() -> None:
    payload = {"request_id": "r-payload"}
    entry = {
        "decision_payload": payload,
        "payload_hash": "0" * 64,
        "previous_hash": None,
        "signature": "sig-ok",
    }
    result = verify_witness_ledger([entry], lambda _: True)
    codes = {error["code"] for error in result["detailed_errors"]}
    assert "payload_hash_mismatch" in codes


def test_witness_unsupported_backend_code(tmp_path: Path) -> None:
    payload = {"request_id": "r-backend"}
    witness = [
        {
            "decision_payload": payload,
            "payload_hash": sha256_of_canonical_json(payload),
            "previous_hash": None,
            "signature": "sig-ok",
            "full_payload_hash": "a" * 64,
            "artifact_ref": {
                "artifact_ref": "trustlog_full_payload",
                "artifact_type": "trust_log_entry",
                "artifact_storage_backend": "unknown_backend",
                "artifact_locator": "sha256:" + "b" * 64,
                "artifact_hash_algorithm": "sha256_canonical_json",
            },
        }
    ]
    result = verify_witness_ledger(witness, lambda _: True, artifact_search_roots=[tmp_path])
    codes = {error["code"] for error in result["detailed_errors"]}
    assert "unsupported_backend" in codes


def test_mirror_remote_verification_skipped_note(monkeypatch) -> None:
    monkeypatch.setenv("VERITAS_TRUSTLOG_VERIFY_MIRROR_REMOTE", "1")
    monkeypatch.setattr(
        "veritas_os.audit.trustlog_verify.importlib.import_module",
        lambda _: (_ for _ in ()).throw(RuntimeError("no boto3")),
    )
    result = verify_witness_ledger(_s3_receipt_witness(), lambda _: True, s3_client=None)
    note_codes = {note["code"] for note in result["verification_notes"]}
    assert "verification_skipped" in note_codes


def test_segment_manifest_hash_validation() -> None:
    manifest = {
        "segment_id": "seg-001",
        "entry_count": 2,
        "first_timestamp": "2026-04-11T00:00:00Z",
        "last_timestamp": "2026-04-11T00:00:02Z",
        "first_hash": "a" * 64,
        "last_hash": "b" * 64,
        "segment_payload_hash": "c" * 64,
        "object_keys_written": ["audit/segments/seg-001.jsonl", "audit/segments/seg-001.manifest.json"],
    }
    payload = {"request_id": "r-segment", "decision": "allow"}
    entry = {
        "decision_payload": payload,
        "payload_hash": sha256_of_canonical_json(payload),
        "previous_hash": None,
        "signature": "sig-ok",
        "mirror_receipt": {
            "mode": "sealed_segments",
            "manifest": manifest,
            "manifest_hash": sha256_of_canonical_json(manifest),
        },
    }
    result = verify_witness_ledger([entry], lambda _: True)
    assert result["ok"] is True


def test_segment_manifest_tamper_detected() -> None:
    manifest = {
        "segment_id": "seg-002",
        "entry_count": 1,
        "first_timestamp": "2026-04-11T00:00:00Z",
        "last_timestamp": "2026-04-11T00:00:00Z",
        "first_hash": "d" * 64,
        "last_hash": "d" * 64,
        "segment_payload_hash": "e" * 64,
        "object_keys_written": ["audit/segments/seg-002.jsonl", "audit/segments/seg-002.manifest.json"],
    }
    payload = {"request_id": "r-segment-tampered", "decision": "allow"}
    entry = {
        "decision_payload": payload,
        "payload_hash": sha256_of_canonical_json(payload),
        "previous_hash": None,
        "signature": "sig-ok",
        "mirror_receipt": {
            "mode": "sealed_segments",
            "manifest": manifest,
            "manifest_hash": "f" * 64,
        },
    }
    result = verify_witness_ledger([entry], lambda _: True)
    reasons = {error["reason"] for error in result["detailed_errors"]}
    codes = {error["code"] for error in result["detailed_errors"]}
    assert "manifest_hash_mismatch" in reasons
    assert "tamper_suspected" in codes
