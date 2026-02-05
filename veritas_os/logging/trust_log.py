# veritas_os/logging/trust_log.py
# 正規TrustLog実装: 論文の式 hₜ = SHA256(hₜ₋₁ || rₜ) に完全準拠
#
# このモジュールがVERITASの唯一のTrustLog実装です。
# 他のモジュールはここをインポートして使用してください。
#
# 機能:
# - append_trust_log: ハッシュチェーン付きでエントリを追記
# - iter_trust_log: ログをイテレート
# - load_trust_log: 最近のエントリをまとめて取得
# - get_trust_log_entry: request_id で単一エントリを取得
# - verify_trust_log: ハッシュチェーンの整合性を検証
# - iso_now: 監査用 UTC ISO8601 時刻
from __future__ import annotations

import json
import hashlib
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from veritas_os.logging.paths import LOG_DIR
from veritas_os.logging.rotate import open_trust_log_for_append
from veritas_os.core.atomic_io import atomic_write_json, atomic_append_line

# trust_log の JSON/JSONL は LOG_DIR 直下に置く
LOG_JSON = LOG_DIR / "trust_log.json"
LOG_JSONL = LOG_DIR / "trust_log.jsonl"

# trust_log.json に保持する最大件数
MAX_JSON_ITEMS = 2000

# スレッドセーフ化: ハッシュチェーンの整合性を保証するためのロック
# ★ マルチスレッド環境（FastAPI等）での同時書き込みによるチェーン破損を防止
_trust_log_lock = threading.RLock()


# =============================================================================
# ヘルパー関数
# =============================================================================

def iso_now() -> str:
    """ISO8601 UTC時刻（監査ログ標準フォーマット）"""
    return datetime.now(timezone.utc).isoformat()


def _sha256(data: Any) -> str:
    """UTF-8 / bytes から SHA-256 ハッシュを生成"""
    if isinstance(data, bytes):
        raw = data
    else:
        raw = str(data).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


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


def _compute_sha256(payload: dict) -> str:
    """
    entry 用の SHA-256 ハッシュを計算する。
    - dict を key でソートして JSON 化
    - それを UTF-8 でエンコードして sha256 に通す
    """
    try:
        s = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    except Exception:
        s = repr(payload).encode("utf-8", "ignore")
    return hashlib.sha256(s).hexdigest()


def get_last_hash() -> str | None:
    """直近の trust_log.jsonl から最後の SHA-256 値を取得。

    ファイル末尾からシークして最終行のみを読み込む。
    全行をメモリに読み込まないため、大きなファイルでもメモリ効率が良い。
    """
    try:
        if not LOG_JSONL.exists():
            return None
        file_size = LOG_JSONL.stat().st_size
        if file_size == 0:
            return None
        with open(LOG_JSONL, "rb") as f:
            # 末尾から最大 4KB を読んで最終行を取得
            chunk_size = min(4096, file_size)
            f.seek(file_size - chunk_size)
            chunk = f.read().decode("utf-8")
            lines = chunk.strip().split("\n")
            if lines:
                last = json.loads(lines[-1])
                return last.get("sha256")
    except Exception:
        return None
    return None


def calc_sha256(payload: dict) -> str:
    """entry の SHA-256 ハッシュを計算する（外部用の薄いヘルパー）"""
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _load_logs_json() -> list:
    """
    trust_log.json から items(list[dict]) を安全に読み込む。
    変な値（int, str など）が混ざっていても捨てる。
    """
    try:
        with open(LOG_JSON, "r", encoding="utf-8") as f:
            obj = json.load(f)

        if isinstance(obj, dict):
            items = obj.get("items", [])
        elif isinstance(obj, list):
            items = obj
        else:
            items = []

        if not isinstance(items, list):
            return []
        return [x for x in items if isinstance(x, dict)]
    except Exception:
        return []


def _save_json(items: list) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_json(LOG_JSON, {"items": items}, indent=2)


def append_trust_log(entry: dict) -> Dict[str, Any]:
    """
    決定ごとの監査ログ（軽量）を JSONL + JSON に保存。

    論文の式に従った実装:
        hₜ = SHA256(hₜ₋₁ || rₜ)

    where:
        hₜ₋₁ = 直前のハッシュ値 (sha256_prev)
        rₜ   = 現在のエントリ (JSON化、sha256とsha256_prevを除外)
        ||   = 文字列連結
        hₜ   = 現在のハッシュ値 (sha256)

    実装詳細:
        1. 直前のハッシュ値 (sha256_prev) を取得
        2. 現在のエントリに sha256_prev をセット
        3. エントリから sha256 と sha256_prev を除外してJSON化 (rₜ)
        4. sha256_prev + rₜ を連結
        5. SHA-256ハッシュを計算して sha256 にセット
        6. JSONLとJSONファイルに保存

    - JSONL は 5000 行でローテーション（rotate.py 側）
    - trust_log.json は最新 MAX_JSON_ITEMS 件だけ保持

    ★ スレッドセーフ: RLock で全操作を保護（ハッシュチェーンの整合性保証）

    Returns:
        sha256, sha256_prev が付与されたエントリ（渡された entry も更新される）
    """
    import os

    # ★ スレッドセーフ: ハッシュチェーンの整合性を保証するためロックを取得
    with _trust_log_lock:
        LOG_DIR.mkdir(parents=True, exist_ok=True)

        # ---- 直前ハッシュの取得（JSONL 側を正とする）----
        # ★ 修正: JSON (MAX_JSON_ITEMS 件に制限) ではなく JSONL (全件) から
        #   直前ハッシュを取得する。JSON が 2000 件で切られている場合、
        #   JSON の末尾と JSONL の末尾が乖離してチェーンが壊れる問題を修正。
        sha256_prev = get_last_hash()

        items = _load_logs_json()

        # 元 entry を壊さないようにコピー
        entry = dict(entry)
        entry.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        entry["sha256_prev"] = sha256_prev

        # ✅ 論文の式に準拠: hₜ = SHA256(hₜ₋₁ || rₜ)
        # エントリから sha256 と sha256_prev を除外（これが rₜ）
        hash_payload = dict(entry)
        hash_payload.pop("sha256", None)
        hash_payload.pop("sha256_prev", None)  # ⚠️ 重要: sha256_prev をハッシュ計算から除外

        # rₜ を JSON化（キーをソートして一意性を保証）
        entry_json = json.dumps(hash_payload, sort_keys=True, ensure_ascii=False)

        # hₜ₋₁ || rₜ を結合
        if sha256_prev:
            combined = sha256_prev + entry_json
        else:
            # 最初のエントリの場合は rₜ のみ
            combined = entry_json

        # SHA-256計算: hₜ = SHA256(hₜ₋₁ || rₜ)
        entry["sha256"] = hashlib.sha256(combined.encode("utf-8")).hexdigest()

        # ---- JSONL に1行追記 (with fsync for durability) ----
        with open_trust_log_for_append() as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())

        # ---- JSON(配列) を更新（最新 N 件だけ残す）----
        items.append(entry)
        if len(items) > MAX_JSON_ITEMS:
            items = items[-MAX_JSON_ITEMS:]

        _save_json(items)

        return entry


def write_shadow_decide(
    request_id: str,
    body: dict,
    chosen: dict,
    telos_score: float,
    fuji: dict,
) -> None:
    """
    Doctor / ダッシュボード用の 1-decide スナップショット
    """
    shadow_dir = LOG_DIR / "DASH"
    shadow_dir.mkdir(parents=True, exist_ok=True)

    # タイムゾーン付きの UTC 時刻を使用（utcnow() は非推奨）
    now_utc = datetime.now(timezone.utc)

    # ファイル名用タイムスタンプ（ミリ秒まで）
    ts_str = now_utc.strftime("%Y%m%d_%H%M%S_%f")[:-3]
    out = shadow_dir / f"decide_{ts_str}.json"

    fuji_safe = fuji if isinstance(fuji, dict) else {}

    rec = {
        "request_id": request_id,
        # ISO8601 + "Z"（UTC）に正規化
        "created_at": now_utc.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "query": (
            body.get("query")
            or (body.get("context") or {}).get("query")
            or ""
        ),
        "chosen": chosen,
        "telos_score": float(telos_score or 0.0),
        "fuji": fuji_safe.get("status"),
    }

    atomic_write_json(out, rec, indent=2)


# =============================================================================
# TrustLog 読み出し系
# =============================================================================

def iter_trust_log(reverse: bool = False) -> Iterable[Dict[str, Any]]:
    """
    TrustLog を1行ずつイテレートするジェネレータ

    Args:
        reverse: True の場合、末尾から逆順に返す

    Yields:
        dict: 個々のログエントリ
    """
    if not LOG_JSONL.exists():
        return

    try:
        if reverse:
            with LOG_JSONL.open("rb") as f:
                lines = f.readlines()
            for line in reversed(lines):
                line_str = line.decode("utf-8").strip()
                if not line_str:
                    continue
                try:
                    yield json.loads(line_str)
                except json.JSONDecodeError:
                    continue
        else:
            with LOG_JSONL.open("r", encoding="utf-8") as f:
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


# =============================================================================
# TrustLog 検証
# =============================================================================

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
    if not LOG_JSONL.exists():
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
        with LOG_JSONL.open("r", encoding="utf-8") as f:
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
                expected_hash = _sha256(combined)
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


# =============================================================================
# 公開 API
# =============================================================================

__all__ = [
    "iso_now",
    "append_trust_log",
    "iter_trust_log",
    "load_trust_log",
    "get_trust_log_entry",
    "verify_trust_log",
    "write_shadow_decide",
    "get_last_hash",
    "calc_sha256",
    "LOG_JSON",
    "LOG_JSONL",
]
