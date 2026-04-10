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
    assert "previous_hash_mismatch" in reasons
    assert "signature_invalid" in reasons
    assert "full_payload_hash_invalid" in reasons
    assert "mirror_receipt_invalid" in reasons


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
