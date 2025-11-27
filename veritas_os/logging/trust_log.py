# veritas_os/logging/trust_log.py
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
        s = json.dumps(payload, sort_keys=True, 
ensure_ascii=False).encode("utf-8")
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
            return last.get("sha256_self")
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
    - 直前のログから sha256_prev を引き継ぐ
    - 自分の内容から sha256 を計算して付与
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

    # 自分自身のハッシュを計算（まだ sha256 は含めない）
    hash_payload = dict(entry)
    hash_payload.pop("sha256", None)
    entry["sha256"] = _compute_sha256(hash_payload)

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

    ts_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    out = shadow_dir / f"decide_{ts_str}.json"

    fuji_safe = fuji if isinstance(fuji, dict) else {}

    rec = {
        "request_id": request_id,
        "created_at": datetime.utcnow().isoformat(timespec="seconds") + 
"Z",
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
