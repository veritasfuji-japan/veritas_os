# veritas_os/core/logging.py
"""
VERITAS TrustLog / Logging Core

- TrustLog: 暗号学的に連鎖する監査ログ (hₜ = SHA256(hₜ₋₁ || rₜ))
- append_trust_log: 新しいエントリを追記
- verify_trust_log: ハッシュチェーンの整合性を検証
- get_trust_log_entry: request_id で単一エントリを取得
- load_trust_log: 最近のエントリをまとめて取得
- iso_now: 監査用の UTC ISO8601 時刻
"""

from __future__ import annotations

import os
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .config import cfg  # 相対 import

# ---------------------------------
# パス初期化
# ---------------------------------

# data_dir も trust_log_path も両方ケアしておく
os.makedirs(cfg.data_dir, exist_ok=True)
trust_log_dir = Path(cfg.trust_log_path).expanduser().parent
trust_log_dir.mkdir(parents=True, exist_ok=True)


# ---------------------------------
# ヘルパー
# ---------------------------------

def _sha(data: Any) -> str:
    """UTF-8 / bytes から SHA-256 ハッシュを生成"""
    if isinstance(data, bytes):
        raw = data
    else:
        raw = str(data).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def iso_now() -> str:
    """ISO8601 UTC時刻（監査ログ標準フォーマット）"""
    return datetime.now(timezone.utc).isoformat()


def _read_last_entry() -> Optional[Dict[str, Any]]:
    """
    trust_log の最後のエントリを取得（なければ None）
    """
    path = Path(cfg.trust_log_path)
    if not path.exists():
        return None

    try:
        with path.open("rb") as f:
            lines = f.readlines()
        if not lines:
            return None
        last_line = lines[-1].decode("utf-8").strip()
        if not last_line:
            return None
        return json.loads(last_line)
    except Exception as e:
        print(f"[WARN] trust_log last entry read failed: {e}")
        return None


def _normalize_entry_for_hash(entry: Dict[str, Any]) -> str:
    """
    sha256 計算用にエントリを正規化:
    - sha256 / sha256_prev フィールドは除外
    - sort_keys=True で JSON 化して順序を固定
    """
    payload = dict(entry)
    payload.pop("sha256", None)
    payload.pop("sha256_prev", None)
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


# ---------------------------------
# TrustLog 追記
# ---------------------------------

def append_trust_log(entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    TrustLogに新規エントリを追加。論文準拠のハッシュ連鎖を計算。
    
    論文の式: hₜ = SHA256(hₜ₋₁ || rₜ)
    
    where:
        hₜ₋₁ = 前エントリの sha256 フィールドの値
        rₜ   = 現在のエントリ（sha256, sha256_prev を除く）
    
    Args:
        entry: 追加するログエントリ（dict）
    
    Returns:
        sha256, sha256_prev が付与されたエントリ
    """
    # created_at がなければ自動付与
    entry.setdefault("created_at", iso_now())

    # 直前のエントリの sha256 を取得
    prev_entry = _read_last_entry()
    prev_hash = prev_entry.get("sha256") if isinstance(prev_entry, dict) else None

    # sha256_prev を設定（最初のエントリは None のまま）
    entry["sha256_prev"] = prev_hash

    # rₜ を JSON に正規化
    entry_json = _normalize_entry_for_hash(entry)

    # hₜ₋₁ || rₜ を結合
    if prev_hash:
        combined = prev_hash + entry_json
    else:
        combined = entry_json

    # SHA-256 ハッシュ計算
    entry["sha256"] = _sha(combined)

    # 追記
    try:
        with open(cfg.trust_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        # ここで失敗しても pipeline 全体を落としたくないので print に留める
        print(f"[WARN] trust_log append failed: {e}")

    return entry


# ---------------------------------
# TrustLog 読み出し系
# ---------------------------------

def iter_trust_log(reverse: bool = False) -> Iterable[Dict[str, Any]]:
    """
    TrustLog を1行ずつイテレートするジェネレータ
    
    Args:
        reverse: True の場合、末尾から逆順に返す
    
    Yields:
        dict: 個々のログエントリ
    """
    path = Path(cfg.trust_log_path)
    if not path.exists():
        return

    try:
        if reverse:
            with path.open("rb") as f:
                lines = f.readlines()
            for line in reversed(lines):
                line = line.decode("utf-8").strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
        else:
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue
    except Exception as e:
        print(f"[WARN] trust_log iterate failed: {e}")
        return


def load_trust_log(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    TrustLog をまとめて読み込むユーティリティ
    
    Args:
        limit: 最大件数（None の場合は全件）
    
    Returns:
        list[dict]: 新しい順のエントリリスト
    """
    entries: List[Dict[str, Any]] = list(iter_trust_log(reverse=True))
    if limit is not None:
        entries = entries[:limit]
    return entries


def get_trust_log_entry(request_id: str) -> Optional[Dict[str, Any]]:
    """
    指定 request_id の TrustLog エントリを取得（末尾から検索）
    
    Args:
        request_id: /v1/decide の request_id
    
    Returns:
        dict | None: 対応するエントリ or 見つからない場合 None
    """
    if not request_id:
        return None

    for entry in iter_trust_log(reverse=True):
        if entry.get("request_id") == request_id:
            return entry
    return None


# ---------------------------------
# TrustLog 検証
# ---------------------------------

def verify_trust_log(max_entries: Optional[int] = None) -> Dict[str, Any]:
    """
    TrustLog 全体（または先頭から max_entries 件）について
    ハッシュチェーンの整合性を検証する。
    
    Returns:
        {
          "ok": bool,
          "checked": int,
          "broken": bool,
          "broken_index": int | None,
          "broken_reason": str | None,
        }
    """
    path = Path(cfg.trust_log_path)
    if not path.exists():
        return {
            "ok": True,
            "checked": 0,
            "broken": False,
            "broken_index": None,
            "broken_reason": None,
        }

    prev_hash: Optional[str] = None
    checked = 0

    try:
        with path.open("r", encoding="utf-8") as f:
            for idx, line in enumerate(f):
                if max_entries is not None and idx >= max_entries:
                    break

                line = line.strip()
                if not line:
                    continue

                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    return {
                        "ok": False,
                        "checked": checked,
                        "broken": True,
                        "broken_index": idx,
                        "broken_reason": "json_decode_error",
                    }

                # sha256_prev の整合性チェック
                actual_prev = entry.get("sha256_prev")
                if prev_hash is None:
                    # 最初のエントリは sha256_prev が None のはず（もしくは存在しない）
                    if actual_prev not in (None, ""):
                        return {
                            "ok": False,
                            "checked": checked,
                            "broken": True,
                            "broken_index": idx,
                            "broken_reason": "unexpected_sha256_prev_for_first_entry",
                        }
                else:
                    if actual_prev != prev_hash:
                        return {
                            "ok": False,
                            "checked": checked,
                            "broken": True,
                            "broken_index": idx,
                            "broken_reason": "sha256_prev_mismatch",
                        }

                # sha256 の再計算チェック
                expected_prev = prev_hash
                entry_json = _normalize_entry_for_hash(entry)
                if expected_prev:
                    combined = expected_prev + entry_json
                else:
                    combined = entry_json
                expected_hash = _sha(combined)
                if entry.get("sha256") != expected_hash:
                    return {
                        "ok": False,
                        "checked": checked,
                        "broken": True,
                        "broken_index": idx,
                        "broken_reason": "sha256_mismatch",
                    }

                # 状態更新
                prev_hash = entry.get("sha256")
                checked += 1

        return {
            "ok": True,
            "checked": checked,
            "broken": False,
            "broken_index": None,
            "broken_reason": None,
        }

    except Exception as e:
        return {
            "ok": False,
            "checked": checked,
            "broken": True,
            "broken_index": checked,
            "broken_reason": f"exception: {e}",
        }


# ---------------------------------
# 公開 API
# ---------------------------------

__all__ = [
    "iso_now",
    "append_trust_log",
    "iter_trust_log",
    "load_trust_log",
    "get_trust_log_entry",
    "verify_trust_log",
]

