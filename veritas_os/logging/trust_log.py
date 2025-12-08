# veritas_os/logging/trust_log.py
# 完全修正版: 論文の式 hₜ = SHA256(hₜ₋₁ || rₜ) に完全準拠
from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List

from veritas_os.logging.paths import LOG_DIR
from veritas_os.logging.rotate import open_trust_log_for_append

# trust_log の JSON/JSONL は LOG_DIR 直下に置く
LOG_JSON = LOG_DIR / "trust_log.json"
LOG_JSONL = LOG_DIR / "trust_log.jsonl"

# trust_log.json に保持する最大件数
MAX_JSON_ITEMS = 2000


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
    """直近の trust_log.jsonl から最後の SHA-256 値を取得"""
    try:
        if LOG_JSONL.exists():
            with open(LOG_JSONL, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if not lines:
                return None
            last = json.loads(lines[-1])
            return last.get("sha256")  # sha256_self ではなく sha256
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
    with open(LOG_JSON, "w", encoding="utf-8") as f:
        json.dump({"items": items}, f, ensure_ascii=False, indent=2)


def append_trust_log(entry: dict) -> None:
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
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # ---- 直前ハッシュの取得（JSON 側）----
    items = _load_logs_json()
    sha256_prev = None
    if items:
        last = items[-1]
        sha256_prev = last.get("sha256")

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

    # ---- JSONL に1行追記 ----
    with open_trust_log_for_append() as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # ---- JSON(配列) を更新（最新 N 件だけ残す）----
    items.append(entry)
    if len(items) > MAX_JSON_ITEMS:
        items = items[-MAX_JSON_ITEMS:]

    _save_json(items)


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

    with open(out, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=2)


