"""Tests for signed TrustLog error handling."""

import json

import pytest

from veritas_os.audit import trustlog_signed
from veritas_os.logging import trust_log


def test_append_signed_decision_wraps_oserror(monkeypatch):
    """Expected runtime write failures are wrapped in domain error."""

    monkeypatch.setattr(trustlog_signed, "_ensure_signing_keys", lambda: None)
    monkeypatch.setattr(trustlog_signed, "_read_all_entries", lambda _path: [])
    monkeypatch.setattr(
        trustlog_signed,
        "sha256_of_canonical_json",
        lambda _payload: "h" * 64,
    )
    monkeypatch.setattr(trustlog_signed, "sign_payload_hash", lambda *_args, **_kwargs: "sig")
    monkeypatch.setattr(
        trustlog_signed,
        "public_key_fingerprint",
        lambda _path: "fp",
    )

    def _raise_oserror(_path, _line):
        raise OSError("disk full")

    monkeypatch.setattr(trustlog_signed, "_append_line", _raise_oserror)

    with pytest.raises(trustlog_signed.SignedTrustLogWriteError):
        trustlog_signed.append_signed_decision({"request_id": "req-1"})


def test_append_trust_log_continues_on_signed_log_runtime_error(monkeypatch, tmp_path):
    """Primary TrustLog append continues when signed append hits handled errors."""
    from veritas_os.logging.encryption import generate_key

    monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", generate_key())
    monkeypatch.setattr(trust_log, "LOG_DIR", tmp_path)
    monkeypatch.setattr(trust_log, "LOG_JSON", tmp_path / "trust_log.json")
    monkeypatch.setattr(trust_log, "LOG_JSONL", tmp_path / "trust_log.jsonl")
    monkeypatch.setattr(trust_log, "get_last_hash", lambda: None)
    monkeypatch.setattr(
        trust_log,
        "open_trust_log_for_append",
        lambda: (tmp_path / "trust_log.jsonl").open("a", encoding="utf-8"),
    )
    monkeypatch.setattr(
        trust_log,
        "append_signed_decision",
        lambda _entry: (_ for _ in ()).throw(
            trust_log.SignedTrustLogWriteError("signed append failed")
        ),
    )

    result = trust_log.append_trust_log({"request_id": "req-2", "decision_status": "allow"})

    assert result["request_id"] == "req-2"
    assert result["sha256"]
    assert (tmp_path / "trust_log.jsonl").exists()

    # ★ JSONL は暗号化されているので iter_trust_log 経由で検証
    entries = list(trust_log.iter_trust_log(reverse=False))
    assert len(entries) == 1
