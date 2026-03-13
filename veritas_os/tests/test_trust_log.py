# veritas_os/tests/test_trust_log.py
from __future__ import annotations

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
