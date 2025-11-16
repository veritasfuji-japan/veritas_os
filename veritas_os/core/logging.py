import os, json, hashlib, datetime
from .config import cfg  # ← 相対パス指定を安全に
os.makedirs(cfg.data_dir, exist_ok=True)
from datetime import datetime, timezone

def _sha(s: str) -> str:
    """UTF-8ハッシュ生成"""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def append_trust_log(entry: dict) -> dict:
    """TrustLogに新規エントリを追加。前レコードのハッシュ連鎖も計算。"""
    prev = None
    # 既存ログの最終行を参照
    if os.path.exists(cfg.trust_log_path):
        try:
            with open(cfg.trust_log_path, "rb") as f:
                lines = f.readlines()
                if lines:
                    last = lines[-1].decode("utf-8").strip()
                    prev = _sha(last)
        except Exception as e:
            print(f"[WARN] trust_log 読み込み失敗: {e}")
            prev = None

    # 連鎖ハッシュを付与
    entry["sha256_prev"] = prev

    # 追記
    with open(cfg.trust_log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return entry

def iso_now() -> str:
    """ISO8601 UTC時刻（監査ログ標準フォーマット）"""
    return datetime.now(timezone.utc).isoformat()
