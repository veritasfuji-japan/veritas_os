# veritas_os/tests/test_logging_core_trustlog.py
"""
core/logging.py ラッパーと logging/trust_log.py 正規実装のテスト。

core/logging.py は後方互換性のためのラッパーであり、
実際の実装は logging/trust_log.py にあります。
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import veritas_os.core.logging as core_logging
import veritas_os.logging.trust_log as trust_log_impl
import veritas_os.logging.paths as log_paths


def _setup_tmp_trust_log(tmp_path, monkeypatch):
    """
    trust_log の LOG_DIR, LOG_JSON, LOG_JSONL を一時ディレクトリに切り替えるヘルパー。
    """
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_jsonl = log_dir / "trust_log.jsonl"
    log_json = log_dir / "trust_log.json"

    # paths モジュールをパッチ（rotate.py が参照する）
    monkeypatch.setattr(log_paths, "LOG_DIR", log_dir)
    monkeypatch.setattr(log_paths, "LOG_JSONL", log_jsonl)
    monkeypatch.setattr(log_paths, "LOG_JSON", log_json)

    # 正規実装のパスをパッチ
    monkeypatch.setattr(trust_log_impl, "LOG_DIR", log_dir)
    monkeypatch.setattr(trust_log_impl, "LOG_JSONL", log_jsonl)
    monkeypatch.setattr(trust_log_impl, "LOG_JSON", log_json)

    # ラッパーにもエクスポートされているのでそちらもパッチ
    monkeypatch.setattr(core_logging, "LOG_JSONL", log_jsonl)
    monkeypatch.setattr(core_logging, "LOG_JSON", log_json)

    return log_jsonl


def test_iso_now_returns_utc_iso():
    """iso_now が UTC 付き ISO8601 を返していることを確認"""
    s = core_logging.iso_now()
    dt = datetime.fromisoformat(s)
    assert dt.tzinfo is not None
    assert dt.tzinfo.utcoffset(dt).total_seconds() == 0  # UTC であること


def test_append_and_iter_and_load_and_get(tmp_path, monkeypatch):
    """
    append_trust_log → iter_trust_log → load_trust_log →
    get_trust_log_entry の一連の正常系をまとめて検証。
    """
    log_path = _setup_tmp_trust_log(tmp_path, monkeypatch)

    # 1件目
    e1 = core_logging.append_trust_log({"request_id": "r1", "decision": "allow"})
    assert "sha256" in e1 and e1["sha256"]
    # 最初のエントリは sha256_prev が None のはず
    assert e1.get("sha256_prev") is None

    # 2件目
    e2 = core_logging.append_trust_log({"request_id": "r2", "decision": "reject"})
    assert "sha256" in e2 and e2["sha256"]
    # 2件目の sha256_prev は 1件目の sha256 と一致する
    assert e2["sha256_prev"] == e1["sha256"]

    # forward 方向の iter_trust_log
    entries_forward = list(core_logging.iter_trust_log(reverse=False))
    assert [e["request_id"] for e in entries_forward] == ["r1", "r2"]

    # reverse=True の iter_trust_log（逆順になる）
    entries_reverse = list(core_logging.iter_trust_log(reverse=True))
    assert [e["request_id"] for e in entries_reverse] == ["r2", "r1"]

    # load_trust_log(limit=1) は新しい方だけ返す
    latest_only = core_logging.load_trust_log(limit=1)
    assert len(latest_only) == 1
    assert latest_only[0]["request_id"] == "r2"

    # get_trust_log_entry は request_id で検索（末尾から）
    got = core_logging.get_trust_log_entry("r1")
    assert got is not None
    assert got["request_id"] == "r1"

    # verify_trust_log も OK であること
    verified = core_logging.verify_trust_log()
    assert verified["ok"] is True
    assert verified["broken"] is False
    assert verified["checked"] == 2

    # 念のためファイルがちゃんとできているかも見ておく
    assert log_path.exists()


def test_verify_trust_log_empty_file(tmp_path, monkeypatch):
    """
    trust_log ファイルが存在しない場合の verify_trust_log の挙動。
    """
    log_path = _setup_tmp_trust_log(tmp_path, monkeypatch)
    # ファイルは作らない
    if log_path.exists():
        log_path.unlink()

    result = core_logging.verify_trust_log()
    assert result["ok"] is True
    assert result["checked"] == 0
    assert result["broken"] is False
    assert result["broken_index"] is None


def test_verify_trust_log_after_rotation(tmp_path, monkeypatch):
    """
    ログローテーション後の JSONL ファイルで、最初のエントリが
    非 None の sha256_prev を持つ場合も verify_trust_log が
    正常にチェーンを検証できることを確認。
    """
    log_path = _setup_tmp_trust_log(tmp_path, monkeypatch)

    # まず 2 件のエントリを正常に作成
    e1 = core_logging.append_trust_log({"request_id": "r1", "value": 1})
    e2 = core_logging.append_trust_log({"request_id": "r2", "value": 2})

    # ローテーションをシミュレート:
    # 古い JSONL を別名に退避し、2 件目だけを新しい JSONL に残す。
    # 2 件目は sha256_prev が非 None（= e1 の sha256）なので、
    # 新ファイル先頭のエントリが sha256_prev != None になる。
    log_path.write_text(
        json.dumps(e2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    result = core_logging.verify_trust_log()
    assert result["ok"] is True
    assert result["checked"] == 1
    assert result["broken"] is False


def test_verify_trust_log_detects_tamper(tmp_path, monkeypatch):
    """
    途中でハッシュを書き換えて改ざんされている場合に、
    verify_trust_log が検出することをテスト。
    """
    log_path = _setup_tmp_trust_log(tmp_path, monkeypatch)

    # 正常チェーンを2件作成
    core_logging.append_trust_log({"request_id": "r1", "value": 1})
    core_logging.append_trust_log({"request_id": "r2", "value": 2})

    # 最後の行の sha256 を書き換えて改ざん
    lines = log_path.read_text(encoding="utf-8").splitlines()
    last = json.loads(lines[-1])
    last["sha256"] = "0" * 64  # 明らかにおかしい値にする
    lines[-1] = json.dumps(last, ensure_ascii=False)
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = core_logging.verify_trust_log()
    assert result["ok"] is False
    assert result["broken"] is True
    # どこかで sha256_mismatch が検出されるはず
    assert result["broken_reason"] == "sha256_mismatch"
    assert isinstance(result["broken_index"], int)
