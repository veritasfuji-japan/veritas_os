# -*- coding: utf-8 -*-
"""TrustLog 単体テスト

TrustLog ハッシュチェーン / 暗号化 / 署名 / Compaction / 敵対テスト。"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


# ============================================================
# Source: test_trust_log.py
# ============================================================


import json
import hashlib
import re
import builtins
from typing import Any, Dict

from datetime import datetime

import pytest

from veritas_os.logging import trust_log


# ============================
#  pytest 用ユーティリティ
# ============================


@pytest.fixture
def temp_log_env(tmp_path, monkeypatch):
    """
    trust_log が使うパス類を tmp_path に向けるフィクスチャ。

    - LOG_DIR
    - LOG_JSON
    - LOG_JSONL
    - open_trust_log_for_append
    - VERITAS_ENCRYPTION_KEY（secure-by-default に必須）
    """
    # ★ secure-by-default: テスト用の暗号鍵を設定
    from veritas_os.logging.encryption import generate_key
    monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", generate_key())

    # LOG_DIR を差し替え
    monkeypatch.setattr(trust_log, "LOG_DIR", tmp_path, raising=False)

    # trust_log.json / .jsonl も tmp に差し替え
    json_path = tmp_path / "trust_log.json"
    jsonl_path = tmp_path / "trust_log.jsonl"
    monkeypatch.setattr(trust_log, "LOG_JSON", json_path, raising=False)
    monkeypatch.setattr(trust_log, "LOG_JSONL", jsonl_path, raising=False)

    # JSONL を開く関数を単純化（rotate を通さず直接開く）
    def _open_trust_log_for_append():
        trust_log.LOG_JSONL.parent.mkdir(parents=True, exist_ok=True)
        return open(trust_log.LOG_JSONL, "a", encoding="utf-8")

    monkeypatch.setattr(
        trust_log,
        "open_trust_log_for_append",
        _open_trust_log_for_append,
        raising=False,
    )

    return {
        "log_dir": tmp_path,
        "json": json_path,
        "jsonl": jsonl_path,
    }


# ============================
#  ハッシュ系ヘルパーのテスト
# ============================


def test_compute_sha256_and_calc_sha256_consistent():
    payload = {"b": 2, "a": 1}
    # test対象
    h1 = trust_log._compute_sha256(payload)
    h2 = trust_log.calc_sha256(payload)

    # 両方とも 64桁の16進
    assert re.fullmatch(r"[0-9a-f]{64}", h1)
    assert re.fullmatch(r"[0-9a-f]{64}", h2)

    # RFC 8785 canonical JSON（空白なし・キーソート）で計算したものと一致するか
    expected = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    assert h2 == expected

    # _compute_sha256 は ensure_ascii=False だが、
    # ASCII のみの payload なので同じになるはず
    assert h1 == expected


def test_compute_sha256_handles_unserializable_objects():
    # set は json.dumps できないので except パスに入る
    payload = {"x": {1, 2, 3}}
    h = trust_log._compute_sha256(payload)
    assert re.fullmatch(r"[0-9a-f]{64}", h)


def test_calc_sha256_matches_manual_hash():
    payload = {"x": "y"}
    h = trust_log.calc_sha256(payload)
    # RFC 8785 canonical JSON（空白なし・キーソート）
    expected = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    assert h == expected


def test_calc_sha256_handles_unserializable_objects():
    payload = {"x": {1, 2, 3}}
    h = trust_log.calc_sha256(payload)
    assert re.fullmatch(r"[0-9a-f]{64}", h)


def test_load_mask_pii_raises_runtime_error_on_unexpected_import_failure(monkeypatch):
    """Unexpected import failures should not be swallowed silently."""
    original_import = builtins.__import__

    def _guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "veritas_os.core.sanitize":
            raise RuntimeError("unexpected import failure")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _guarded_import)

    with pytest.raises(RuntimeError, match="unexpected import failure"):
        trust_log._load_mask_pii()


# ============================
#  _load_logs_json / _save_json のテスト
# ============================


def test_load_logs_json_handles_dict_list_and_invalid(temp_log_env):
    # dict 形式 + items キー
    obj = {"items": [{"a": 1}, "bad", 123]}
    temp_log_env["json"].write_text(json.dumps(obj), encoding="utf-8")
    items = trust_log._load_logs_json()
    assert items == [{"a": 1}]

    # 配列ルート
    obj2 = [{"b": 2}, "x"]
    temp_log_env["json"].write_text(json.dumps(obj2), encoding="utf-8")
    items2 = trust_log._load_logs_json()
    assert items2 == [{"b": 2}]

    # items が list ではないケース
    obj3 = {"items": "not-a-list"}
    temp_log_env["json"].write_text(json.dumps(obj3), encoding="utf-8")
    items3 = trust_log._load_logs_json()
    assert items3 == []

    # 壊れた JSON → except 側に落ちて [] になる
    temp_log_env["json"].write_text("{not valid json", encoding="utf-8")
    items4 = trust_log._load_logs_json()
    assert items4 == []


def test_save_json_writes_items(temp_log_env):
    data = [{"x": 1}, {"y": 2}]
    trust_log._save_json(data)

    text = temp_log_env["json"].read_text(encoding="utf-8")
    obj = json.loads(text)
    assert isinstance(obj, dict)
    assert obj["items"] == data

def test_load_logs_json_non_collection_returns_empty(temp_log_env):
    # dict でも list でもない JSON を書き込む（int など）
    trust_log.LOG_JSON.write_text("123", encoding="utf-8")

    items = trust_log._load_logs_json()

    # 変な値は全部捨てて空リストになる想定
    assert items == []


# ============================
#  get_last_hash のテスト
# ============================


def test_get_last_hash_no_file_returns_none(temp_log_env):
    # LOG_JSONL が存在しない → None
    assert trust_log.get_last_hash() is None

    # 空ファイルでも None
    temp_log_env["jsonl"].write_text("", encoding="utf-8")
    assert trust_log.get_last_hash() is None


def test_get_last_hash_reads_last_line_sha256(temp_log_env):
    # 2行分の JSONL を書いて、最後の sha256 を返せるか
    entries = [
        {"sha256": "a" * 64},
        {"sha256": "b" * 64},
    ]
    with open(temp_log_env["jsonl"], "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")

    last = trust_log.get_last_hash()
    assert last == "b" * 64


def test_get_last_hash_invalid_json_returns_none(temp_log_env):
    temp_log_env["jsonl"].write_text("not a json\n", encoding="utf-8")
    assert trust_log.get_last_hash() is None


def test_get_last_hash_handles_very_large_last_line(temp_log_env):
    payload = {"sha256": "c" * 64, "blob": "x" * 70000}
    temp_log_env["jsonl"].write_text(json.dumps(payload) + "\n", encoding="utf-8")

    assert trust_log.get_last_hash() == "c" * 64


def test_get_last_hash_skips_trailing_partial_json_line(temp_log_env):
    valid = json.dumps({"sha256": "d" * 64})
    partial = '{"sha256": "broken"'
    temp_log_env["jsonl"].write_text(f"{valid}\n{partial}", encoding="utf-8")

    assert trust_log.get_last_hash() == "d" * 64


def test_get_last_hash_recovers_from_rotated_log_when_marker_missing(temp_log_env):
    rotated = temp_log_env["jsonl"].with_name("trust_log_old.jsonl")
    entries = [
        {"sha256": "e" * 64},
        {"sha256": "f" * 64},
    ]
    with open(rotated, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")

    assert trust_log.get_last_hash() == "f" * 64


def test_get_last_hash_recovers_from_rotated_log_when_active_empty(temp_log_env):
    temp_log_env["jsonl"].write_text("", encoding="utf-8")

    rotated = temp_log_env["jsonl"].with_name("trust_log_old.jsonl")
    rotated.write_text(json.dumps({"sha256": "1" * 64}) + "\n", encoding="utf-8")

    assert trust_log.get_last_hash() == "1" * 64


def test_extract_last_sha256_from_lines_ignores_invalid_entries():
    valid_hash = "a" * 64
    lines = [
        "",
        "not-json",
        json.dumps(["list", "is", "ignored"]),
        json.dumps({"sha256": ""}),
        json.dumps({"sha256": "good_hash"}),
        json.dumps({"sha256": valid_hash}),
    ]

    assert trust_log._extract_last_sha256_from_lines(lines) == valid_hash




def test_extract_last_sha256_from_lines_accepts_uppercase_hex():
    uppercase_hash = "A" * 64
    lines = [json.dumps({"sha256": uppercase_hash})]

    assert trust_log._extract_last_sha256_from_lines(lines) == uppercase_hash

def test_extract_last_sha256_from_lines_falls_back_to_non_hex_sha256():
    lines = [
        json.dumps({"sha256": "g" * 64}),
        json.dumps({"sha256": "123"}),
    ]

    assert trust_log._extract_last_sha256_from_lines(lines) == "123"


# ============================
#  append_trust_log のチェーン検証
# ============================


def _recompute_chain_hash(prev_hash: str | None, entry: Dict[str, Any]) -> str:
    """
    trust_log.append_trust_log の実装通りに、
    渡された entry から期待される sha256 を再計算するヘルパ。
    RFC 8785 canonical JSON（空白なし・キーソート）を使用。
    """
    # entry から sha256, sha256_prev を除外 → r_t
    payload = dict(entry)
    payload.pop("sha256", None)
    payload.pop("sha256_prev", None)
    entry_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    if prev_hash:
        combined = prev_hash + entry_json
    else:
        combined = entry_json

    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def test_append_trust_log_chain_integrity_and_jsonl_json(temp_log_env):
    # 1件目を追加
    trust_log.append_trust_log({"request_id": "r1", "step": 1})
    # 2件目を追加
    trust_log.append_trust_log({"request_id": "r2", "step": 2})

    # trust_log.json が存在し、items に2件入っていること
    assert temp_log_env["json"].exists()
    with open(temp_log_env["json"], "r", encoding="utf-8") as f:
        obj = json.load(f)

    assert isinstance(obj, dict)
    items = obj.get("items")
    assert isinstance(items, list)
    assert len(items) == 2

    first, second = items

    # 共通フィールド
    assert first["request_id"] == "r1"
    assert second["request_id"] == "r2"
    assert first["sha256_prev"] is None
    assert second["sha256_prev"] == first["sha256"]
    assert "created_at" in first
    assert "created_at" in second

    # チェーンハッシュの式に完全準拠しているか検証
    expected_h1 = _recompute_chain_hash(None, first)
    expected_h2 = _recompute_chain_hash(first["sha256"], second)

    assert first["sha256"] == expected_h1
    assert second["sha256"] == expected_h2

    # JSONL 側も2行あり、最後の sha256 が second と一致しているはず
    # ★ JSONL は暗号化されているので iter_trust_log 経由で検証
    entries = list(trust_log.iter_trust_log(reverse=False))
    assert len(entries) == 2
    assert entries[-1]["sha256"] == second["sha256"]

    # get_last_hash も同じ値を返すこと
    assert trust_log.get_last_hash() == second["sha256"]


def test_append_trust_log_max_items_rotation(temp_log_env, monkeypatch):
    # MAX_JSON_ITEMS を小さくしてローテーション挙動をテスト
    monkeypatch.setattr(trust_log, "MAX_JSON_ITEMS", 3, raising=False)

    for i in range(5):
        trust_log.append_trust_log({"request_id": f"r{i}", "step": i})

    with open(temp_log_env["json"], "r", encoding="utf-8") as f:
        obj = json.load(f)

    items = obj.get("items")
    assert len(items) == 3  # MAX_JSON_ITEMS=3 なので 3件のみ残る
    # 古い2件が削られ、新しいほう3件だけ残っている
    remaining_ids = [it["request_id"] for it in items]
    assert remaining_ids == ["r2", "r3", "r4"]


# ============================
#  write_shadow_decide のテスト
# ============================




def test_append_trust_log_increments_failure_count_on_oserror(temp_log_env, monkeypatch):
    monkeypatch.setattr(trust_log, "_append_failure_count", 0, raising=False)

    def _raise_oserror(*_args, **_kwargs):
        raise OSError("disk-full")

    monkeypatch.setattr(trust_log, "_save_json", _raise_oserror, raising=False)

    with pytest.raises(OSError):
        trust_log.append_trust_log({"request_id": "req-oserr"})

    stats = trust_log.get_trust_log_stats()
    assert stats["append_failure"] >= 1


def test_append_trust_log_does_not_swallow_unexpected_runtime_error(temp_log_env, monkeypatch):
    monkeypatch.setattr(trust_log, "_append_failure_count", 0, raising=False)

    def _raise_runtime_error(*_args, **_kwargs):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(trust_log, "_save_json", _raise_runtime_error, raising=False)

    with pytest.raises(RuntimeError):
        trust_log.append_trust_log({"request_id": "req-runtime"})

    stats = trust_log.get_trust_log_stats()
    assert stats["append_failure"] == 0

def test_write_shadow_decide_creates_snapshot_file(temp_log_env):
    # LOG_DIR を tmp にした状態で write_shadow_decide を呼ぶ
    request_id = "req-123"
    body = {
        "query": "What is VERITAS?",
        "context": {"query": "ignored because query key exists"},
    }
    chosen = {"answer": "test"}
    telos_score = 0.85
    fuji = {"status": {"level": "ok"}}

    trust_log.write_shadow_decide(
        request_id=request_id,
        body=body,
        chosen=chosen,
        telos_score=telos_score,
        fuji=fuji,
    )

    shadow_dir = trust_log.LOG_DIR / "DASH"
    assert shadow_dir.exists()
    files = list(shadow_dir.glob("decide_*.json"))
    assert len(files) == 1

    with open(files[0], "r", encoding="utf-8") as f:
        rec = json.load(f)

    assert rec["request_id"] == request_id
    assert rec["query"] == "What is VERITAS?"
    assert rec["chosen"] == chosen
    assert rec["telos_score"] == pytest.approx(telos_score)
    # fuji は status フィールドのみ取り出されている
    assert rec["fuji"] == {"level": "ok"}

    # created_at が ISO8601 (UTC, "Z" 付き) でパース可能であることを確認
    assert isinstance(rec["created_at"], str)
    dt = datetime.fromisoformat(rec["created_at"].replace("Z", "+00:00"))
    assert dt.tzinfo is not None


def test_write_shadow_decide_falls_back_to_context_query_and_none_fuji(temp_log_env):
    # body["query"] が無く、context.query が使われるケース
    request_id = "req-ctx"
    body = {
        "context": {"query": "from context"},
    }

    trust_log.write_shadow_decide(
        request_id=request_id,
        body=body,
        chosen={},
        telos_score=0.0,
        fuji={},  # status キーが無い → None
    )

    shadow_dir = trust_log.LOG_DIR / "DASH"
    files = sorted(shadow_dir.glob("decide_*.json"))
    assert files

    with open(files[-1], "r", encoding="utf-8") as f:
        rec = json.load(f)

    assert rec["request_id"] == request_id
    assert rec["query"] == "from context"
    assert rec["fuji"] is None


# ============================================================
# Source: test_trust_log_api.py
# ============================================================


import json

from fastapi.testclient import TestClient
import pytest

import veritas_os.api.server as server
import veritas_os.logging.trust_log as trust_log


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("VERITAS_API_KEY", "test-key")
    return TestClient(server.app)


def _write_jsonl(path, rows):
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def test_trust_logs_pagination(client, monkeypatch, tmp_path):
    jsonl = tmp_path / "trust_log.jsonl"
    json_file = tmp_path / "trust_log.json"

    rows = [
        {"request_id": "req-1", "stage": "plan", "sha256": "h1", "sha256_prev": None},
        {"request_id": "req-2", "stage": "value", "sha256": "h2", "sha256_prev": "h1"},
        {"request_id": "req-3", "stage": "fuji", "sha256": "h3", "sha256_prev": "h2"},
    ]
    _write_jsonl(jsonl, rows)
    json_file.write_text(json.dumps({"items": rows}, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(server, "LOG_JSONL", jsonl)
    monkeypatch.setattr(server, "LOG_JSON", json_file)
    monkeypatch.setattr(trust_log, "LOG_JSONL", jsonl)
    monkeypatch.setattr(trust_log, "LOG_JSON", json_file)

    response = client.get("/v1/trust/logs?limit=2", headers={"X-API-Key": "test-key"})

    assert response.status_code == 200
    body = response.json()
    assert body["limit"] == 2
    assert body["has_more"] is True
    assert body["next_cursor"] == "2"
    assert [item["request_id"] for item in body["items"]] == ["req-3", "req-2"]


def test_trust_log_by_request_chain_status(client, monkeypatch, tmp_path):
    jsonl = tmp_path / "trust_log.jsonl"
    json_file = tmp_path / "trust_log.json"

    rows = [
        {"request_id": "same", "stage": "evidence", "sha256": "a1", "sha256_prev": None},
        {"request_id": "other", "stage": "plan", "sha256": "b1", "sha256_prev": "a1"},
        {"request_id": "same", "stage": "value", "sha256": "a2", "sha256_prev": "a1"},
    ]
    _write_jsonl(jsonl, rows)
    json_file.write_text(json.dumps({"items": rows}, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(server, "LOG_JSONL", jsonl)
    monkeypatch.setattr(server, "LOG_JSON", json_file)
    monkeypatch.setattr(trust_log, "LOG_JSONL", jsonl)
    monkeypatch.setattr(trust_log, "LOG_JSON", json_file)

    response = client.get("/v1/trust/same", headers={"X-API-Key": "test-key"})

    assert response.status_code == 200
    body = response.json()
    assert body["request_id"] == "same"
    assert body["count"] == 2
    assert body["chain_ok"] is True
    assert body["verification_result"] == "ok"


# ============================================================
# Source: test_trustlog_adversarial.py
# ============================================================


import base64
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from veritas_os.audit import trustlog_signed
from veritas_os.audit.trustlog_signed import (
    SignedTrustLogWriteError,
    _entry_chain_hash,
    _read_all_entries,
    _read_last_entry,
    append_signed_decision,
    verify_signature,
    verify_trustlog_chain,
)
from veritas_os.logging import encryption, trust_log
from veritas_os.logging.encryption import (
    DecryptionError,
    EncryptionKeyMissing,
    decrypt,
    encrypt,
    generate_key,
    is_encryption_enabled,
)
from veritas_os.security.signing import (
    sign_payload_hash,
    store_keypair,
    verify_payload_signature,
)
from veritas_os.security.hash import sha256_of_canonical_json


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _set_valid_key(monkeypatch: pytest.MonkeyPatch, raw: bytes | None = None) -> bytes:
    key = raw or (b"K" * 32)
    monkeypatch.setenv(
        "VERITAS_ENCRYPTION_KEY",
        base64.urlsafe_b64encode(key).decode("ascii"),
    )
    return key


def _stub_signing(monkeypatch):
    """Stub out signing infrastructure for unit isolation."""
    monkeypatch.setattr(trustlog_signed, "_ensure_signing_keys", lambda: None)
    monkeypatch.setattr(
        trustlog_signed, "sha256_of_canonical_json", lambda _p: "h" * 64,
    )
    monkeypatch.setattr(
        trustlog_signed, "sign_payload_hash", lambda *a, **kw: "sig",
    )
    monkeypatch.setattr(
        trustlog_signed, "public_key_fingerprint", lambda _p: "fp",
    )


# ===========================================================================
# 1. Encryption — missing key
# ===========================================================================

class TestEncryptionMissingKey:
    """Encryption must fail-closed when key is absent."""

    def test_encrypt_raises_without_key(self, monkeypatch):
        monkeypatch.delenv("VERITAS_ENCRYPTION_KEY", raising=False)
        with pytest.raises(EncryptionKeyMissing):
            encrypt("secret data")

    def test_decrypt_raises_without_key_for_encrypted_input(self, monkeypatch):
        monkeypatch.delenv("VERITAS_ENCRYPTION_KEY", raising=False)
        with pytest.raises(EncryptionKeyMissing):
            decrypt("ENC:hmac-ctr:dGVzdA==")

    def test_decrypt_raises_without_key_for_aesgcm_input(self, monkeypatch):
        monkeypatch.delenv("VERITAS_ENCRYPTION_KEY", raising=False)
        with pytest.raises(EncryptionKeyMissing):
            decrypt("ENC:aesgcm:dGVzdA==")

    def test_is_encryption_disabled_when_key_unset(self, monkeypatch):
        monkeypatch.delenv("VERITAS_ENCRYPTION_KEY", raising=False)
        assert is_encryption_enabled() is False

    def test_encrypt_type_error_for_non_string(self, monkeypatch):
        _set_valid_key(monkeypatch)
        with pytest.raises(TypeError):
            encrypt(12345)  # type: ignore[arg-type]


# ===========================================================================
# 2. Encryption — wrong key
# ===========================================================================

class TestEncryptionWrongKey:
    """Decryption with wrong key must fail-closed (not return garbage)."""

    def test_wrong_key_hmac_ctr_raises(self, monkeypatch):
        _set_valid_key(monkeypatch, raw=b"A" * 32)
        monkeypatch.setattr(encryption, "_USE_REAL_AES", False)
        ct = encrypt("locked-data")

        _set_valid_key(monkeypatch, raw=b"B" * 32)
        with pytest.raises(DecryptionError):
            decrypt(ct)

    def test_wrong_key_invalid_base64(self, monkeypatch):
        monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", "%%%not-base64%%%")
        assert is_encryption_enabled() is False

    def test_wrong_key_too_short(self, monkeypatch):
        monkeypatch.setenv(
            "VERITAS_ENCRYPTION_KEY",
            base64.urlsafe_b64encode(b"short").decode("ascii"),
        )
        assert is_encryption_enabled() is False
        with pytest.raises(EncryptionKeyMissing):
            encrypt("data")

    def test_wrong_key_too_long(self, monkeypatch):
        monkeypatch.setenv(
            "VERITAS_ENCRYPTION_KEY",
            base64.urlsafe_b64encode(b"X" * 64).decode("ascii"),
        )
        assert is_encryption_enabled() is False
        with pytest.raises(EncryptionKeyMissing):
            encrypt("data")


# ===========================================================================
# 3. Encryption — corrupted ciphertext
# ===========================================================================

class TestCorruptedCiphertext:
    """Tampered ciphertext must be detected and rejected."""

    def test_flipped_bit_in_payload(self, monkeypatch):
        _set_valid_key(monkeypatch, raw=b"C" * 32)
        monkeypatch.setattr(encryption, "_USE_REAL_AES", False)
        ct = encrypt("tamper-target")

        # Flip a character in the base64 payload
        prefix, payload = ct.rsplit(":", 1)
        corrupted_payload = payload[:-2] + ("Z" if payload[-2] != "Z" else "Q") + payload[-1]
        corrupted = f"{prefix}:{corrupted_payload}"

        with pytest.raises(DecryptionError):
            decrypt(corrupted)

    def test_completely_random_payload(self, monkeypatch):
        _set_valid_key(monkeypatch, raw=b"D" * 32)
        random_b64 = base64.urlsafe_b64encode(os.urandom(128)).decode("ascii")
        with pytest.raises(DecryptionError):
            decrypt(f"ENC:hmac-ctr:{random_b64}")

    def test_empty_payload_after_prefix(self, monkeypatch):
        _set_valid_key(monkeypatch, raw=b"E" * 32)
        with pytest.raises(DecryptionError):
            decrypt("ENC:hmac-ctr:")

    def test_truncated_payload_too_short(self, monkeypatch):
        _set_valid_key(monkeypatch, raw=b"F" * 32)
        # Just a few bytes, less than HMAC_SIZE + IV_SIZE + 1
        short_b64 = base64.urlsafe_b64encode(b"x" * 10).decode("ascii")
        with pytest.raises(DecryptionError):
            decrypt(f"ENC:hmac-ctr:{short_b64}")

    def test_mixed_old_new_format_rejected(self, monkeypatch):
        _set_valid_key(monkeypatch, raw=b"F" * 32)
        with pytest.raises(DecryptionError, match="invalid base64 payload"):
            decrypt("ENC:hmac-ctr:legacy:payload")

    def test_legacy_payload_requires_explicit_opt_in(self, monkeypatch):
        _set_valid_key(monkeypatch, raw=b"Q" * 32)
        monkeypatch.setattr(encryption, "_USE_REAL_AES", False)
        modern = encrypt("legacy-migration")
        legacy = modern.replace("ENC:hmac-ctr:", "ENC:")

        with pytest.raises(DecryptionError, match="legacy encrypted envelope not accepted"):
            decrypt(legacy)

        monkeypatch.setenv("VERITAS_ENCRYPTION_LEGACY_DECRYPT", "true")
        assert decrypt(legacy) == "legacy-migration"


# ===========================================================================
# 4. Truncated line handling
# ===========================================================================

class TestTruncatedLine:
    """Truncated/corrupt JSONL lines must not break the pipeline."""

    def test_decode_line_returns_none_for_truncated_json(self):
        result = trust_log._decode_line('{"request_id": "r1", "sha256":')
        assert result is None

    def test_decode_line_returns_none_for_empty(self):
        assert trust_log._decode_line("") is None
        assert trust_log._decode_line("   \n") is None

    def test_decode_line_returns_none_for_corrupted_encryption(self, monkeypatch):
        _set_valid_key(monkeypatch, raw=b"G" * 32)
        result = trust_log._decode_line("ENC:hmac-ctr:GARBAGE_NOT_BASE64")
        assert result is None

    def test_verify_trust_log_detects_truncated_entry(self, monkeypatch, tmp_path):
        _set_valid_key(monkeypatch, raw=b"H" * 32)
        monkeypatch.setattr(encryption, "_USE_REAL_AES", False)
        log_file = tmp_path / "trust_log.jsonl"

        # Write a truncated encrypted line — verify_trust_log should detect it
        log_file.write_text("ENC:hmac-ctr:TRUNC\n", encoding="utf-8")

        monkeypatch.setattr(trust_log, "LOG_JSONL", log_file)
        result = trust_log.verify_trust_log()
        # Truncated encrypted lines fail decryption → reported as decode error
        assert result["broken"] is True
        assert result["broken_reason"] in ("json_decode_error",)

    def test_extract_last_sha256_skips_truncated_lines(self, monkeypatch):
        _set_valid_key(monkeypatch, raw=b"I" * 32)
        monkeypatch.setattr(encryption, "_USE_REAL_AES", False)

        good_entry = json.dumps({"sha256": "a" * 64})
        enc_good = encrypt(good_entry)

        lines = ["TRUNCATED_GARBAGE", enc_good, "ANOTHER_BAD_LINE"]
        result = trust_log._extract_last_sha256_from_lines(lines)
        assert result == "a" * 64


# ===========================================================================
# 5. Signature invalid
# ===========================================================================

class TestSignatureInvalid:
    """Invalid/tampered signatures must be detected."""

    def test_verify_signature_rejects_tampered_signature(self, tmp_path):
        priv_path = tmp_path / "priv.key"
        pub_path = tmp_path / "pub.key"
        store_keypair(priv_path, pub_path)

        payload_hash = sha256_of_canonical_json({"decision": "allow"})
        sig = sign_payload_hash(payload_hash, priv_path)

        # Tamper with signature
        sig_bytes = base64.urlsafe_b64decode(sig)
        tampered = bytes([b ^ 0xFF for b in sig_bytes[:4]]) + sig_bytes[4:]
        tampered_sig = base64.urlsafe_b64encode(tampered).decode("ascii")

        assert verify_payload_signature(payload_hash, tampered_sig, pub_path) is False

    def test_verify_signature_rejects_wrong_payload(self, tmp_path):
        priv_path = tmp_path / "priv.key"
        pub_path = tmp_path / "pub.key"
        store_keypair(priv_path, pub_path)

        payload_hash = sha256_of_canonical_json({"decision": "allow"})
        sig = sign_payload_hash(payload_hash, priv_path)

        wrong_hash = sha256_of_canonical_json({"decision": "deny"})
        assert verify_payload_signature(wrong_hash, sig, pub_path) is False

    def test_verify_trustlog_chain_detects_forged_signature(self, tmp_path, monkeypatch):
        # Create real keys
        priv_path = tmp_path / "keys" / "priv.key"
        pub_path = tmp_path / "keys" / "pub.key"
        store_keypair(priv_path, pub_path)
        monkeypatch.setattr(trustlog_signed, "PUBLIC_KEY_PATH", pub_path)

        # Build a valid entry then tamper its signature
        payload = {"decision": "allow", "request_id": "sig-test"}
        payload_hash = sha256_of_canonical_json(payload)

        # Create a completely wrong signature (valid base64 of random bytes)
        wrong_sig = base64.urlsafe_b64encode(os.urandom(64)).decode("ascii")

        entry = {
            "decision_id": "test-id",
            "timestamp": "2026-01-01T00:00:00Z",
            "previous_hash": None,
            "decision_payload": payload,
            "payload_hash": payload_hash,
            "signature": wrong_sig,
            "signature_key_fingerprint": "fp",
        }

        trustlog_path = tmp_path / "trustlog.jsonl"
        trustlog_path.write_text(json.dumps(entry) + "\n", encoding="utf-8")

        result = verify_trustlog_chain(trustlog_path)
        assert result["ok"] is False
        assert any(i["reason"] == "signature_invalid" for i in result["issues"])

    def test_verify_signature_returns_false_for_missing_fields(self, tmp_path):
        # Missing key file
        assert verify_signature({"payload_hash": "h" * 64, "signature": "sig"}) is False
        # Missing required fields
        assert verify_signature({"payload_hash": "h" * 64}) is False
        assert verify_signature({}) is False


# ===========================================================================
# 6. previous_hash mismatch
# ===========================================================================

class TestPreviousHashMismatch:
    """Chain hash breaks must be detected."""

    def test_verify_trustlog_chain_detects_previous_hash_mismatch(self, tmp_path, monkeypatch):
        priv_path = tmp_path / "keys" / "priv.key"
        pub_path = tmp_path / "keys" / "pub.key"
        store_keypair(priv_path, pub_path)
        monkeypatch.setattr(trustlog_signed, "PUBLIC_KEY_PATH", pub_path)

        # Build entry 1
        payload1 = {"decision": "allow", "request_id": "chain-1"}
        payload_hash1 = sha256_of_canonical_json(payload1)
        sig1 = sign_payload_hash(payload_hash1, priv_path)
        entry1 = {
            "decision_id": "id-1",
            "timestamp": "2026-01-01T00:00:00Z",
            "previous_hash": None,
            "decision_payload": payload1,
            "payload_hash": payload_hash1,
            "signature": sig1,
            "signature_key_fingerprint": "fp",
        }

        # Build entry 2 with WRONG previous_hash
        payload2 = {"decision": "deny", "request_id": "chain-2"}
        payload_hash2 = sha256_of_canonical_json(payload2)
        sig2 = sign_payload_hash(payload_hash2, priv_path)
        entry2 = {
            "decision_id": "id-2",
            "timestamp": "2026-01-01T00:01:00Z",
            "previous_hash": "WRONG_HASH_VALUE",  # Should be hash of entry1
            "decision_payload": payload2,
            "payload_hash": payload_hash2,
            "signature": sig2,
            "signature_key_fingerprint": "fp",
        }

        trustlog_path = tmp_path / "trustlog.jsonl"
        lines = json.dumps(entry1) + "\n" + json.dumps(entry2) + "\n"
        trustlog_path.write_text(lines, encoding="utf-8")

        result = verify_trustlog_chain(trustlog_path)
        assert result["ok"] is False
        assert any(i["reason"] == "previous_hash_mismatch" for i in result["issues"])

    def test_verify_trust_log_detects_sha256_prev_mismatch(self, monkeypatch, tmp_path):
        """Main trust_log.verify_trust_log catches sha256_prev chain breaks."""
        _set_valid_key(monkeypatch, raw=b"J" * 32)
        monkeypatch.setattr(encryption, "_USE_REAL_AES", False)

        log_file = tmp_path / "trust_log.jsonl"
        monkeypatch.setattr(trust_log, "LOG_JSONL", log_file)

        # Write two entries where second has wrong sha256_prev
        entry1 = {"request_id": "r1", "sha256_prev": None, "data": "first"}
        entry1_json = trust_log._normalize_entry_for_hash(entry1)
        entry1["sha256"] = trust_log._sha256(entry1_json)
        line1 = encrypt(json.dumps(entry1))

        entry2 = {"request_id": "r2", "sha256_prev": "WRONG", "data": "second"}
        entry2_json = trust_log._normalize_entry_for_hash(entry2)
        entry2["sha256"] = trust_log._sha256("WRONG" + entry2_json)
        line2 = encrypt(json.dumps(entry2))

        log_file.write_text(line1 + "\n" + line2 + "\n", encoding="utf-8")

        result = trust_log.verify_trust_log()
        assert result["ok"] is False
        assert result["broken_reason"] == "sha256_prev_mismatch"


# ===========================================================================
# 7. WORM mirror write failure
# ===========================================================================

class TestWORMMirrorFailure:
    """WORM mirror failures must be handled according to configuration."""

    def test_worm_soft_fail_returns_error_dict(self, monkeypatch, tmp_path):
        """Default soft-fail mode: WORM error returned but not raised."""
        trustlog_path = tmp_path / "trustlog.jsonl"
        monkeypatch.setattr(trustlog_signed, "SIGNED_TRUSTLOG_JSONL", trustlog_path)
        _stub_signing(monkeypatch)

        # Configure WORM path to a read-only location
        worm_path = tmp_path / "readonly" / "worm.jsonl"
        monkeypatch.setenv("VERITAS_TRUSTLOG_WORM_MIRROR_PATH", str(worm_path))
        monkeypatch.delenv("VERITAS_TRUSTLOG_WORM_HARD_FAIL", raising=False)

        # Make WORM write fail
        original_append = trustlog_signed._append_line

        def _fail_worm(path, line):
            if str(path) == str(worm_path):
                raise OSError("WORM storage read-only")
            original_append(path, line)

        monkeypatch.setattr(trustlog_signed, "_append_line", _fail_worm)

        entry = append_signed_decision({"request_id": "worm-soft"})
        assert entry["worm_mirror"]["configured"] is True
        assert entry["worm_mirror"]["ok"] is False
        assert "error" in entry["worm_mirror"]

    def test_worm_hard_fail_raises(self, monkeypatch, tmp_path):
        """Hard-fail mode: WORM error causes SignedTrustLogWriteError."""
        trustlog_path = tmp_path / "trustlog.jsonl"
        monkeypatch.setattr(trustlog_signed, "SIGNED_TRUSTLOG_JSONL", trustlog_path)
        _stub_signing(monkeypatch)

        worm_path = tmp_path / "worm.jsonl"
        monkeypatch.setenv("VERITAS_TRUSTLOG_WORM_MIRROR_PATH", str(worm_path))
        monkeypatch.setenv("VERITAS_TRUSTLOG_WORM_HARD_FAIL", "1")

        original_append = trustlog_signed._append_line

        def _fail_worm(path, line):
            if str(path) == str(worm_path):
                raise OSError("WORM disk full")
            original_append(path, line)

        monkeypatch.setattr(trustlog_signed, "_append_line", _fail_worm)

        with pytest.raises(SignedTrustLogWriteError):
            append_signed_decision({"request_id": "worm-hard"})

    def test_worm_not_configured_returns_unconfigured(self, monkeypatch, tmp_path):
        """When WORM is not configured, entry shows unconfigured status."""
        trustlog_path = tmp_path / "trustlog.jsonl"
        monkeypatch.setattr(trustlog_signed, "SIGNED_TRUSTLOG_JSONL", trustlog_path)
        _stub_signing(monkeypatch)
        monkeypatch.delenv("VERITAS_TRUSTLOG_WORM_MIRROR_PATH", raising=False)

        entry = append_signed_decision({"request_id": "worm-none"})
        assert entry["worm_mirror"]["configured"] is False

    def test_worm_failure_is_logged(self, monkeypatch, tmp_path, caplog):
        """WORM write failure emits a warning log."""
        import logging

        trustlog_path = tmp_path / "trustlog.jsonl"
        monkeypatch.setattr(trustlog_signed, "SIGNED_TRUSTLOG_JSONL", trustlog_path)
        _stub_signing(monkeypatch)

        worm_path = tmp_path / "worm.jsonl"
        monkeypatch.setenv("VERITAS_TRUSTLOG_WORM_MIRROR_PATH", str(worm_path))
        monkeypatch.delenv("VERITAS_TRUSTLOG_WORM_HARD_FAIL", raising=False)

        original_append = trustlog_signed._append_line

        def _fail_worm(path, line):
            if str(path) == str(worm_path):
                raise OSError("permission denied")
            original_append(path, line)

        monkeypatch.setattr(trustlog_signed, "_append_line", _fail_worm)

        with caplog.at_level(logging.WARNING):
            append_signed_decision({"request_id": "worm-log"})

        assert any("WORM mirror write failed" in r.message for r in caplog.records)


# ===========================================================================
# 8. Transparency anchor failure
# ===========================================================================

class TestTransparencyAnchorFailure:
    """Transparency anchor failures must be handled according to configuration."""

    def test_transparency_soft_fail_returns_error_dict(self, monkeypatch, tmp_path):
        trustlog_path = tmp_path / "trustlog.jsonl"
        monkeypatch.setattr(trustlog_signed, "SIGNED_TRUSTLOG_JSONL", trustlog_path)
        _stub_signing(monkeypatch)

        anchor_path = tmp_path / "anchor.jsonl"
        monkeypatch.setenv("VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH", str(anchor_path))
        monkeypatch.delenv("VERITAS_TRUSTLOG_TRANSPARENCY_REQUIRED", raising=False)

        original_append = trustlog_signed._append_line

        def _fail_anchor(path, line):
            if str(path) == str(anchor_path):
                raise OSError("anchor fs read-only")
            original_append(path, line)

        monkeypatch.setattr(trustlog_signed, "_append_line", _fail_anchor)

        entry = append_signed_decision({"request_id": "anchor-soft"})
        assert entry["transparency_anchor"]["configured"] is True
        assert entry["transparency_anchor"]["ok"] is False

    def test_transparency_hard_fail_raises(self, monkeypatch, tmp_path):
        trustlog_path = tmp_path / "trustlog.jsonl"
        monkeypatch.setattr(trustlog_signed, "SIGNED_TRUSTLOG_JSONL", trustlog_path)
        _stub_signing(monkeypatch)

        anchor_path = tmp_path / "anchor.jsonl"
        monkeypatch.setenv("VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH", str(anchor_path))
        monkeypatch.setenv("VERITAS_TRUSTLOG_TRANSPARENCY_REQUIRED", "1")

        original_append = trustlog_signed._append_line

        def _fail_anchor(path, line):
            if str(path) == str(anchor_path):
                raise OSError("anchor write error")
            original_append(path, line)

        monkeypatch.setattr(trustlog_signed, "_append_line", _fail_anchor)

        with pytest.raises(SignedTrustLogWriteError):
            append_signed_decision({"request_id": "anchor-hard"})

    def test_transparency_failure_is_logged(self, monkeypatch, tmp_path, caplog):
        """Transparency anchor write failure emits a warning log."""
        import logging

        trustlog_path = tmp_path / "trustlog.jsonl"
        monkeypatch.setattr(trustlog_signed, "SIGNED_TRUSTLOG_JSONL", trustlog_path)
        _stub_signing(monkeypatch)

        anchor_path = tmp_path / "anchor.jsonl"
        monkeypatch.setenv("VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH", str(anchor_path))
        monkeypatch.delenv("VERITAS_TRUSTLOG_TRANSPARENCY_REQUIRED", raising=False)

        original_append = trustlog_signed._append_line

        def _fail_anchor(path, line):
            if str(path) == str(anchor_path):
                raise OSError("disk error")
            original_append(path, line)

        monkeypatch.setattr(trustlog_signed, "_append_line", _fail_anchor)

        with caplog.at_level(logging.WARNING):
            append_signed_decision({"request_id": "anchor-log"})

        assert any("Transparency anchor write failed" in r.message for r in caplog.records)


# ===========================================================================
# 9. No-downgrade / fail-closed guarantees
# ===========================================================================

class TestFailClosedGuarantees:
    """Verify that no silent security downgrade can occur."""

    def test_append_trust_log_raises_when_encryption_key_missing(self, monkeypatch, tmp_path):
        """append_trust_log must raise when encryption is required but key is absent."""
        monkeypatch.delenv("VERITAS_ENCRYPTION_KEY", raising=False)
        monkeypatch.setattr(trust_log, "LOG_DIR", tmp_path)
        monkeypatch.setattr(trust_log, "LOG_JSON", tmp_path / "trust_log.json")
        monkeypatch.setattr(trust_log, "LOG_JSONL", tmp_path / "trust_log.jsonl")
        monkeypatch.setattr(trust_log, "_get_last_hash_unlocked", lambda: None)
        monkeypatch.setattr(
            trust_log, "open_trust_log_for_append",
            lambda: (tmp_path / "trust_log.jsonl").open("a", encoding="utf-8"),
        )

        with pytest.raises(EncryptionKeyMissing):
            trust_log.append_trust_log({"request_id": "no-key"})

    def test_encryption_enforcement_rejects_plaintext_when_enabled(self, monkeypatch, tmp_path):
        """Even if _encrypt_line somehow returns plaintext, enforcement catches it."""
        _set_valid_key(monkeypatch, raw=b"L" * 32)
        monkeypatch.setattr(trust_log, "LOG_DIR", tmp_path)
        monkeypatch.setattr(trust_log, "LOG_JSON", tmp_path / "trust_log.json")
        monkeypatch.setattr(trust_log, "LOG_JSONL", tmp_path / "trust_log.jsonl")
        monkeypatch.setattr(trust_log, "_get_last_hash_unlocked", lambda: None)
        monkeypatch.setattr(
            trust_log, "open_trust_log_for_append",
            lambda: (tmp_path / "trust_log.jsonl").open("a", encoding="utf-8"),
        )

        # Simulate broken encrypt that returns plaintext
        monkeypatch.setattr(trust_log, "_encrypt_line", lambda x: x)

        with pytest.raises(EncryptionKeyMissing, match="Plaintext write blocked"):
            trust_log.append_trust_log({"request_id": "plaintext-block"})

    def test_decrypt_plaintext_passthrough_only_without_enc_prefix(self, monkeypatch):
        """Only non-ENC: prefixed strings pass through decrypt unchanged."""
        _set_valid_key(monkeypatch)
        assert decrypt("plain text") == "plain text"
        assert decrypt("not encrypted") == "not encrypted"
        # ENC: prefix MUST attempt decryption (fail-closed)
        with pytest.raises(DecryptionError):
            decrypt("ENC:bad-algorithm:payload")

    def test_no_secret_leakage_in_exception_messages(self, monkeypatch):
        """Exception messages must not contain key material or plaintext."""
        monkeypatch.delenv("VERITAS_ENCRYPTION_KEY", raising=False)
        try:
            encrypt("TOP_SECRET_DATA")
        except EncryptionKeyMissing as exc:
            msg = str(exc)
            assert "TOP_SECRET_DATA" not in msg
            assert "VERITAS_ENCRYPTION_KEY" in msg  # OK to mention env var name

    def test_signed_trustlog_payload_hash_mismatch_detected(self, tmp_path, monkeypatch):
        """Entries with tampered payload_hash field are detected."""
        priv_path = tmp_path / "keys" / "priv.key"
        pub_path = tmp_path / "keys" / "pub.key"
        store_keypair(priv_path, pub_path)
        monkeypatch.setattr(trustlog_signed, "PUBLIC_KEY_PATH", pub_path)

        payload = {"decision": "allow"}
        real_hash = sha256_of_canonical_json(payload)
        sig = sign_payload_hash(real_hash, priv_path)

        entry = {
            "decision_id": "id-tamper",
            "timestamp": "2026-01-01T00:00:00Z",
            "previous_hash": None,
            "decision_payload": payload,
            "payload_hash": "TAMPERED_HASH",  # Wrong!
            "signature": sig,
            "signature_key_fingerprint": "fp",
        }

        trustlog_path = tmp_path / "trustlog.jsonl"
        trustlog_path.write_text(json.dumps(entry) + "\n", encoding="utf-8")

        result = verify_trustlog_chain(trustlog_path)
        assert result["ok"] is False
        assert any(i["reason"] == "payload_hash_mismatch" for i in result["issues"])


# ===========================================================================
# 10. Corrupt signed TrustLog entry handling
# ===========================================================================

class TestCorruptSignedEntries:
    """Corrupt entries in the signed TrustLog must be handled gracefully."""

    def test_read_last_entry_skips_corrupt_trailing_line(self, tmp_path):
        valid = json.dumps({"decision_id": "good", "payload_hash": "h" * 64})
        corrupt = "NOT_VALID_JSON{{{{"
        log_path = tmp_path / "trustlog.jsonl"
        log_path.write_text(valid + "\n" + corrupt + "\n", encoding="utf-8")

        result = _read_last_entry(log_path)
        assert result is not None
        assert result["decision_id"] == "good"

    def test_read_all_entries_skips_corrupt_lines(self, tmp_path):
        valid = json.dumps({"decision_id": "ok"})
        log_path = tmp_path / "trustlog.jsonl"
        log_path.write_text(
            valid + "\n" + "CORRUPT\n" + valid + "\n", encoding="utf-8"
        )

        entries = _read_all_entries(log_path)
        assert len(entries) == 2
        assert all(e["decision_id"] == "ok" for e in entries)

    def test_read_last_entry_returns_none_for_all_corrupt(self, tmp_path):
        log_path = tmp_path / "trustlog.jsonl"
        log_path.write_text("BAD1\nBAD2\nBAD3\n", encoding="utf-8")

        result = _read_last_entry(log_path)
        assert result is None

    def test_read_last_entry_returns_none_for_empty_file(self, tmp_path):
        log_path = tmp_path / "trustlog.jsonl"
        log_path.write_text("", encoding="utf-8")

        result = _read_last_entry(log_path)
        assert result is None

    def test_read_last_entry_returns_none_for_missing_file(self, tmp_path):
        result = _read_last_entry(tmp_path / "nonexistent.jsonl")
        assert result is None


# ============================================================
# Source: test_trustlog_compaction.py
# ============================================================


import json
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

from veritas_os.audit import trustlog_signed
from veritas_os.audit.trustlog_signed import (
    MAX_ENTRY_LINE_BYTES,
    _OVERSIZED_MARKER,
    _enforce_entry_size,
    append_signed_decision,
    build_trustlog_summary,
    verify_trustlog_chain,
    verify_signature,
    export_signed_trustlog,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def signed_env(tmp_path, monkeypatch):
    """Redirect signed TrustLog to a temp directory with fresh keys."""
    log_path = tmp_path / "trustlog.jsonl"
    private_key = tmp_path / "keys" / "priv.key"
    public_key = tmp_path / "keys" / "pub.key"

    monkeypatch.setattr(trustlog_signed, "SIGNED_TRUSTLOG_JSONL", log_path)
    monkeypatch.setattr(trustlog_signed, "PRIVATE_KEY_PATH", private_key)
    monkeypatch.setattr(trustlog_signed, "PUBLIC_KEY_PATH", public_key)

    return {"jsonl": log_path, "private_key": private_key, "public_key": public_key}


def _make_bulky_payload(*, request_id: str = "req-bulky") -> Dict[str, Any]:
    """Create a realistic full decision payload with large nested data."""
    return {
        "request_id": request_id,
        "created_at": "2026-01-01T00:00:00Z",
        "context": {
            "user_id": "user-42",
            "world_state": {f"entity_{i}": {"data": "x" * 500} for i in range(50)},
            "projects": [{"name": f"proj-{i}", "history": list(range(200))} for i in range(10)],
            "memory": {"long_history": ["event"] * 1000},
        },
        "query": "Should I proceed?",
        "chosen": {
            "title": "Approve",
            "answer": "Yes, proceed.",
            "full_rationale": "x" * 5000,
            "evidence_chain": [{"doc": "y" * 2000}] * 5,
        },
        "telos_score": 0.92,
        "fuji": {
            "status": "approved",
            "risk": 0.1,
            "full_policy_trace": "z" * 3000,
        },
        "gate_status": "pass",
        "gate_risk": 0.1,
        "gate_total": 0.95,
        "plan_steps": 3,
        "fast_mode": False,
        "mem_hits": 5,
        "web_hits": 2,
        "critique_ok": True,
        "critique_mode": "auto",
        "critique_reason": None,
        "decision_status": "approved",
        "rejection_reason": None,
        "sha256": "a" * 64,
        "sha256_prev": None,
    }


# ---------------------------------------------------------------------------
# build_trustlog_summary tests
# ---------------------------------------------------------------------------

class TestBuildTrustlogSummary:

    def test_excludes_world_state(self):
        full = _make_bulky_payload()
        summary = build_trustlog_summary(full)
        assert "context" not in summary
        assert "world_state" not in json.dumps(summary)

    def test_excludes_projects(self):
        full = _make_bulky_payload()
        summary = build_trustlog_summary(full)
        serialized = json.dumps(summary)
        assert "projects" not in serialized
        assert "history" not in serialized

    def test_excludes_large_evidence_and_rationale(self):
        full = _make_bulky_payload()
        summary = build_trustlog_summary(full)
        serialized = json.dumps(summary)
        assert "full_rationale" not in serialized
        assert "evidence_chain" not in serialized
        assert "full_policy_trace" not in serialized

    def test_preserves_audit_essential_fields(self):
        full = _make_bulky_payload()
        summary = build_trustlog_summary(full)
        assert summary["request_id"] == "req-bulky"
        assert summary["telos_score"] == 0.92
        assert summary["gate_status"] == "pass"
        assert summary["gate_risk"] == 0.1
        assert summary["fast_mode"] is False
        assert summary["critique_ok"] is True
        assert summary["decision_status"] == "approved"

    def test_extracts_nested_scalars(self):
        full = _make_bulky_payload()
        summary = build_trustlog_summary(full)
        assert summary.get("fuji_status") == "approved"
        assert summary.get("fuji_risk") == 0.1
        assert summary.get("chosen_title") == "Approve"

    def test_summary_is_much_smaller_than_full(self):
        full = _make_bulky_payload()
        summary = build_trustlog_summary(full)
        full_size = len(json.dumps(full).encode("utf-8"))
        summary_size = len(json.dumps(summary).encode("utf-8"))
        # Summary should be at least 10x smaller than the bulky payload
        assert summary_size < full_size / 10, (
            f"Summary ({summary_size}B) is not significantly smaller "
            f"than full ({full_size}B)"
        )

    def test_summary_line_under_max_bytes(self):
        full = _make_bulky_payload()
        summary = build_trustlog_summary(full)
        line = json.dumps(summary, ensure_ascii=False).encode("utf-8")
        assert len(line) < MAX_ENTRY_LINE_BYTES

    def test_empty_payload_produces_empty_summary(self):
        summary = build_trustlog_summary({})
        assert isinstance(summary, dict)
        # Should be a valid, small dict
        assert len(json.dumps(summary)) < 100


# ---------------------------------------------------------------------------
# _enforce_entry_size tests
# ---------------------------------------------------------------------------

class TestEnforceEntrySize:

    def test_small_entry_passes_through(self):
        entry = {"decision_payload": {"request_id": "r1"}, "payload_hash": "abc"}
        result = _enforce_entry_size(entry)
        assert result is entry  # same object, not replaced

    def test_oversized_entry_replaced_with_stub(self):
        huge_payload = {"request_id": "r-huge", "blob": "x" * (MAX_ENTRY_LINE_BYTES + 1000)}
        entry = {"decision_payload": huge_payload, "payload_hash": "hash123"}
        result = _enforce_entry_size(entry)
        assert result["decision_payload"].get(_OVERSIZED_MARKER) is True
        assert result["decision_payload"]["request_id"] == "r-huge"
        assert result["decision_payload"]["original_payload_hash"] == "hash123"

    def test_oversized_stub_is_within_limit(self):
        huge_payload = {"request_id": "r-huge", "blob": "x" * (MAX_ENTRY_LINE_BYTES * 2)}
        entry = {"decision_payload": huge_payload, "payload_hash": "hash456"}
        result = _enforce_entry_size(entry)
        line = json.dumps(result, ensure_ascii=False).encode("utf-8")
        assert len(line) < MAX_ENTRY_LINE_BYTES


# ---------------------------------------------------------------------------
# append_signed_decision integration (with compaction)
# ---------------------------------------------------------------------------

class TestAppendSignedDecisionCompaction:

    def test_single_append_with_bulky_payload(self, signed_env):
        full = _make_bulky_payload(request_id="r-compact-1")
        entry = append_signed_decision(full)

        # Entry should have compact decision_payload
        dp = entry["decision_payload"]
        assert "context" not in dp
        serialized = json.dumps(dp)
        assert "world_state" not in serialized
        assert "projects" not in serialized

        # Should have full_payload_hash for cross-reference
        assert "full_payload_hash" in entry
        assert len(entry["full_payload_hash"]) == 64

        # Signature should verify
        assert verify_signature(entry) is True

    def test_multiple_appends_no_corruption(self, signed_env):
        """Multiple appends should not produce corrupt trailing entries."""
        for i in range(5):
            full = _make_bulky_payload(request_id=f"r-multi-{i}")
            append_signed_decision(full)

        # Verify chain integrity
        result = verify_trustlog_chain(path=signed_env["jsonl"])
        assert result["ok"] is True
        assert result["entries_checked"] == 5

        # Verify each line is valid JSON
        lines = signed_env["jsonl"].read_text(encoding="utf-8").splitlines()
        assert len(lines) == 5
        for idx, line in enumerate(lines):
            parsed = json.loads(line)
            assert "decision_payload" in parsed, f"Line {idx} missing decision_payload"
            assert "world_state" not in json.dumps(parsed), f"Line {idx} contains world_state"

    def test_no_trailing_corruption_after_repeated_appends(self, signed_env):
        """Regression: 2+ appends must not produce corrupt trailing entry."""
        for i in range(10):
            append_signed_decision({"request_id": f"r-trail-{i}", "action": "approve"})

        # Read all lines — every one should parse cleanly
        lines = signed_env["jsonl"].read_text(encoding="utf-8").splitlines()
        for idx, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            try:
                json.loads(line)
            except json.JSONDecodeError:
                pytest.fail(f"Corrupt trailing entry at line {idx}")

        result = verify_trustlog_chain(path=signed_env["jsonl"])
        assert result["ok"] is True

    def test_line_size_bounded(self, signed_env):
        """Each JSONL line should stay within MAX_ENTRY_LINE_BYTES."""
        for i in range(3):
            full = _make_bulky_payload(request_id=f"r-size-{i}")
            append_signed_decision(full)

        lines = signed_env["jsonl"].read_text(encoding="utf-8").splitlines()
        for idx, line in enumerate(lines):
            size = len(line.encode("utf-8"))
            assert size <= MAX_ENTRY_LINE_BYTES, (
                f"Line {idx} is {size} bytes, exceeds {MAX_ENTRY_LINE_BYTES}"
            )

    def test_hash_chain_integrity_with_compaction(self, signed_env):
        """Hash chain verification must pass after compaction."""
        payloads = [
            _make_bulky_payload(request_id=f"r-chain-{i}")
            for i in range(5)
        ]
        for p in payloads:
            append_signed_decision(p)

        result = verify_trustlog_chain(path=signed_env["jsonl"])
        assert result["ok"] is True
        assert result["entries_checked"] == 5
        assert not result["issues"]

    def test_signature_validation_after_compaction(self, signed_env):
        """Signatures must verify against the compact payload hash."""
        full = _make_bulky_payload(request_id="r-sig")
        entry = append_signed_decision(full)

        assert verify_signature(entry) is True

        # Verify via chain as well
        result = verify_trustlog_chain(path=signed_env["jsonl"])
        assert result["ok"] is True

    def test_full_payload_hash_differs_from_summary_hash(self, signed_env):
        """full_payload_hash and payload_hash should differ (different data)."""
        full = _make_bulky_payload(request_id="r-diff")
        entry = append_signed_decision(full)

        assert entry["full_payload_hash"] != entry["payload_hash"]
        assert len(entry["full_payload_hash"]) == 64
        assert len(entry["payload_hash"]) == 64

    def test_export_after_compaction(self, signed_env):
        """Exported entries should contain compact payloads."""
        for i in range(3):
            append_signed_decision(_make_bulky_payload(request_id=f"r-export-{i}"))

        export = export_signed_trustlog(path=signed_env["jsonl"])
        assert export["count"] == 3
        for entry in export["entries"]:
            dp = entry["decision_payload"]
            serialized = json.dumps(dp)
            assert "world_state" not in serialized
            assert "projects" not in serialized

    def test_concurrent_signed_appends_no_corruption(self, signed_env):
        """10 threads × 3 appends must not corrupt the signed TrustLog chain."""
        import threading

        errors: list = []
        n_threads = 10
        n_writes = 3

        def worker(tid: int) -> None:
            try:
                for seq in range(n_writes):
                    append_signed_decision(
                        {"request_id": f"r-conc-{tid}-{seq}", "thread": tid}
                    )
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=worker, args=(t,))
            for t in range(n_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert not errors, f"Concurrent signed append errors: {errors}"

        result = verify_trustlog_chain(path=signed_env["jsonl"])
        assert result["ok"] is True
        assert result["entries_checked"] == n_threads * n_writes

        # Every line must be valid JSON
        lines = signed_env["jsonl"].read_text(encoding="utf-8").splitlines()
        assert len(lines) == n_threads * n_writes
        for idx, line in enumerate(lines):
            try:
                json.loads(line)
            except json.JSONDecodeError:
                pytest.fail(f"Corrupt entry at line {idx} after concurrent writes")

    def test_15_sequential_appends_chain_intact(self, signed_env):
        """15 sequential appends must keep the hash chain and signatures intact."""
        for i in range(15):
            full = _make_bulky_payload(request_id=f"r-seq15-{i}")
            entry = append_signed_decision(full)
            assert verify_signature(entry) is True

        result = verify_trustlog_chain(path=signed_env["jsonl"])
        assert result["ok"] is True
        assert result["entries_checked"] == 15
        assert not result["issues"]

        # Verify no world_state / projects leak in any line
        raw = signed_env["jsonl"].read_text(encoding="utf-8")
        assert "world_state" not in raw
        assert '"projects"' not in raw

    def test_detect_tampering_still_works(self, signed_env):
        """Tampering detection must still work with compact payloads."""
        from veritas_os.audit.trustlog_signed import detect_tampering

        for i in range(3):
            append_signed_decision({"request_id": f"r-tamper-{i}", "action": "ok"})

        # Tamper with second entry
        lines = signed_env["jsonl"].read_text(encoding="utf-8").splitlines()
        obj = json.loads(lines[1])
        obj["decision_payload"]["request_id"] = "TAMPERED"
        lines[1] = json.dumps(obj, ensure_ascii=False)
        signed_env["jsonl"].write_text("\n".join(lines) + "\n", encoding="utf-8")

        result = detect_tampering(path=signed_env["jsonl"])
        assert result["tampered"] is True


# ---------------------------------------------------------------------------
# persist_audit_log compaction tests
# ---------------------------------------------------------------------------

class TestPersistAuditLogCompaction:

    def test_audit_entry_excludes_context(self):
        """The audit entry passed to append_trust_log should not contain ctx.context."""
        from veritas_os.core.pipeline_persist import persist_audit_log
        from veritas_os.core.pipeline_types import PipelineContext

        captured_entries = []

        def fake_append(entry):
            captured_entries.append(entry)
            return entry

        def fake_shadow(*args, **kwargs):
            pass

        ctx = PipelineContext()
        ctx.request_id = "req-ctx-test"
        ctx.query = "test query"
        ctx.context = {
            "user_id": "u1",
            "world_state": {"huge": "data" * 1000},
            "projects": [{"name": "p1", "history": list(range(500))}],
        }
        ctx.chosen = {"title": "OK", "answer": "yes", "giant_blob": "z" * 5000}
        ctx.telos = 0.8
        ctx.fuji_dict = {"status": "pass", "risk": 0.1}
        ctx.values_payload = {"total": 0.9}
        ctx.plan = {"steps": [1, 2]}
        ctx.fast_mode = False
        ctx.response_extras = {"metrics": {"mem_hits": 1, "web_hits": 2}}
        ctx.critique = {"ok": True, "mode": "auto", "reason": None}
        ctx.body = {"query": "test query"}

        persist_audit_log(ctx, append_trust_log_fn=fake_append, write_shadow_decide_fn=fake_shadow)

        assert len(captured_entries) == 1
        entry = captured_entries[0]

        # Must NOT contain the full context dict
        assert "context" not in entry
        # Must have context_user_id instead
        assert entry.get("context_user_id") == "u1"
        # world_state and projects must not appear
        serialized = json.dumps(entry)
        assert "world_state" not in serialized
        assert "projects" not in serialized
        # chosen should be compacted (no giant_blob)
        assert "giant_blob" not in json.dumps(entry.get("chosen", {}))
        # But title should be preserved
        assert entry["chosen"].get("title") == "OK"


# ---------------------------------------------------------------------------
# Oversized entry verification roundtrip
# ---------------------------------------------------------------------------

class TestOversizedEntryVerification:
    """Verify that oversized entries pass chain verification after stub replacement."""

    def test_oversized_entry_passes_chain_verification(self, signed_env):
        """An oversized entry must not cause false-positive chain breakage."""
        # First, append a normal entry
        append_signed_decision({"request_id": "r-normal-1", "action": "ok"})

        # Then append an oversized payload that triggers stub replacement.
        # Use an allowlisted field so the *summary* itself exceeds the limit.
        huge_payload = _make_bulky_payload(request_id="r-oversized")
        huge_payload["rejection_reason"] = "x" * (MAX_ENTRY_LINE_BYTES + 5000)
        append_signed_decision(huge_payload)

        # Append another normal entry after the oversized one
        append_signed_decision({"request_id": "r-normal-2", "action": "ok"})

        # The chain must still verify cleanly
        result = verify_trustlog_chain(path=signed_env["jsonl"])
        assert result["ok"] is True, (
            f"Chain verification failed after oversized entry: {result['issues']}"
        )
        assert result["entries_checked"] == 3

    def test_oversized_stub_has_marker(self, signed_env):
        """Oversized entries must contain the __trustlog_oversized__ marker."""
        # Use an allowlisted field with a huge value so the summary itself is oversized
        huge_payload = {
            "request_id": "r-huge-mark",
            "rejection_reason": "y" * (MAX_ENTRY_LINE_BYTES + 5000),
        }
        entry = append_signed_decision(huge_payload)

        dp = entry["decision_payload"]
        assert dp.get(_OVERSIZED_MARKER) is True
        assert dp.get("original_payload_hash") is not None

    def test_oversized_entry_signature_verifies(self, signed_env):
        """Signature must verify against the recalculated stub payload_hash."""
        huge_payload = {
            "request_id": "r-huge-sig",
            "rejection_reason": "z" * (MAX_ENTRY_LINE_BYTES + 5000),
        }
        entry = append_signed_decision(huge_payload)

        assert verify_signature(entry) is True


# ---------------------------------------------------------------------------
# Concurrent full-pipeline append_trust_log test
# ---------------------------------------------------------------------------

class TestConcurrentAppendTrustLog:
    """Verify that 10+ concurrent append_trust_log calls don't corrupt the chain."""

    def test_concurrent_full_pipeline_appends(self, tmp_path, monkeypatch):
        """10 threads × 3 appends through the full append_trust_log pipeline."""
        import threading
        from veritas_os.logging.encryption import generate_key
        from veritas_os.logging import trust_log

        key = generate_key()
        monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", key)
        monkeypatch.setattr(trust_log, "LOG_DIR", tmp_path, raising=False)
        monkeypatch.setattr(trust_log, "LOG_JSON", tmp_path / "trust_log.json", raising=False)

        jsonl_path = tmp_path / "trust_log.jsonl"
        monkeypatch.setattr(trust_log, "LOG_JSONL", jsonl_path, raising=False)

        def _open():
            jsonl_path.parent.mkdir(parents=True, exist_ok=True)
            return open(jsonl_path, "a", encoding="utf-8")

        monkeypatch.setattr(trust_log, "open_trust_log_for_append", _open, raising=False)
        # Redirect signed TrustLog to avoid interference
        monkeypatch.setattr(trustlog_signed, "SIGNED_TRUSTLOG_JSONL", tmp_path / "trustlog.jsonl")
        monkeypatch.setattr(trustlog_signed, "PRIVATE_KEY_PATH", tmp_path / "keys" / "priv.key")
        monkeypatch.setattr(trustlog_signed, "PUBLIC_KEY_PATH", tmp_path / "keys" / "pub.key")

        errors: list = []
        n_threads = 10
        n_writes = 3

        def worker(tid: int) -> None:
            try:
                for seq in range(n_writes):
                    trust_log.append_trust_log({
                        "request_id": f"conc-{tid}-{seq}",
                        "event": "test",
                        "data": f"thread {tid} seq {seq}",
                    })
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=worker, args=(t,))
            for t in range(n_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)

        assert not errors, f"Concurrent append_trust_log errors: {errors}"

        # Verify the encrypted hash chain is intact
        result = trust_log.verify_trust_log()
        assert result["ok"] is True, f"Chain broken after concurrent writes: {result}"
        assert result["checked"] == n_threads * n_writes


# ============================================================
# Source: test_trustlog_signed.py
# ============================================================

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


def test_append_signed_decision_adds_transparency_anchor(monkeypatch, tmp_path):
    """Signed append records transparency anchor when configured."""
    trustlog_path = tmp_path / "trustlog.jsonl"
    anchor_path = tmp_path / "transparency.jsonl"

    monkeypatch.setattr(trustlog_signed, "SIGNED_TRUSTLOG_JSONL", trustlog_path)
    monkeypatch.setattr(trustlog_signed, "_ensure_signing_keys", lambda: None)
    monkeypatch.setattr(trustlog_signed, "_read_all_entries", lambda _path: [])
    monkeypatch.setattr(
        trustlog_signed,
        "sha256_of_canonical_json",
        lambda _payload: "h" * 64,
    )
    monkeypatch.setattr(trustlog_signed, "sign_payload_hash", lambda *_args, **_kwargs: "sig")
    monkeypatch.setattr(trustlog_signed, "public_key_fingerprint", lambda _path: "fp")
    monkeypatch.setenv("VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH", str(anchor_path))

    entry = trustlog_signed.append_signed_decision({"request_id": "req-transparency"})

    assert entry["transparency_anchor"]["configured"] is True
    assert entry["transparency_anchor"]["ok"] is True
    assert entry["transparency_anchor"]["path"] == str(anchor_path)
    assert anchor_path.exists()
    lines = anchor_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["entry_hash"] == entry["transparency_anchor"]["entry_hash"]


def test_append_signed_decision_raises_when_transparency_required(monkeypatch, tmp_path):
    """Required transparency anchor mode fails closed on write errors."""
    trustlog_path = tmp_path / "trustlog.jsonl"

    monkeypatch.setattr(trustlog_signed, "SIGNED_TRUSTLOG_JSONL", trustlog_path)
    monkeypatch.setattr(trustlog_signed, "_ensure_signing_keys", lambda: None)
    monkeypatch.setattr(trustlog_signed, "_read_all_entries", lambda _path: [])
    monkeypatch.setattr(
        trustlog_signed,
        "sha256_of_canonical_json",
        lambda _payload: "h" * 64,
    )
    monkeypatch.setattr(trustlog_signed, "sign_payload_hash", lambda *_args, **_kwargs: "sig")
    monkeypatch.setattr(trustlog_signed, "public_key_fingerprint", lambda _path: "fp")
    monkeypatch.setenv("VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH", str(tmp_path / "tp.jsonl"))
    monkeypatch.setenv("VERITAS_TRUSTLOG_TRANSPARENCY_REQUIRED", "1")

    original_append_line = trustlog_signed._append_line

    def _append_line_fail_for_anchor(path, line):
        if str(path).endswith("tp.jsonl"):
            raise OSError("anchor fs readonly")
        original_append_line(path, line)

    monkeypatch.setattr(trustlog_signed, "_append_line", _append_line_fail_for_anchor)

    with pytest.raises(trustlog_signed.SignedTrustLogWriteError):
        trustlog_signed.append_signed_decision({"request_id": "req-anchor-hard-fail"})
