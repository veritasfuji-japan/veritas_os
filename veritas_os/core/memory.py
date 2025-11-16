from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime
import json
import os
import time

# ▼ ここで安全に joblib を読み込む
try:
    from joblib import load as joblib_load
except ImportError:
    joblib_load = None

# ============================
# モデル関連
# ============================

# veritas_clean_test2/veritas_os/core/memory.py から見て
# REPO_ROOT = .../veritas_clean_test2/veritas_os
REPO_ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = REPO_ROOT / "core" / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

MEMORY_MODEL_PATH = MODELS_DIR / "memory_model.pkl"

print("[MemoryModel] module loaded from:", __file__)

if joblib_load and MEMORY_MODEL_PATH.exists():
    try:
        MODEL = joblib_load(MEMORY_MODEL_PATH)
        print(f"[MemoryModel] loaded: {MEMORY_MODEL_PATH}")
    except Exception as e:
        MODEL = None
        print("[MemoryModel] load skipped:", e)
else:
    MODEL = None
    print("[MemoryModel] load skipped: model file missing or joblib not available")


def predict_decision_status(query_text: str) -> str:
    """（暫定）クエリテキストから決定ステータスを推定するヘルパー"""
    if MODEL is None:
        return "unknown"
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer

        vec = TfidfVectorizer().fit([query_text])
        X = vec.transform([query_text])
        pred = MODEL.predict(X)[0]
        return str(pred)
    except Exception as e:
        print("[MemoryModel] predict error:", e)
        return "unknown"


# ============================
# ストレージ設定
# ============================

from .config import cfg

MEM_PATH_ENV = os.getenv("VERITAS_MEMORY_PATH")
if MEM_PATH_ENV:
    MEM_PATH = Path(MEM_PATH_ENV).expanduser()
else:
    # config で決めた scripts/logs/memory.json を統一で使う
    MEM_PATH = cfg.memory_path

DATA_DIR = MEM_PATH.parent
DATA_DIR.mkdir(parents=True, exist_ok=True)


# ============================
# MemoryStore クラス
# ============================

class MemoryStore:
    """シンプルな JSON ベースの MemoryOS"""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump([], f)

    @classmethod
    def load(cls, path: Path) -> "MemoryStore":
        return cls(path)

    # ---- 内部ヘルパー ----
    def _load_all(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            return []
        return self._normalize(raw)

    def _normalize(self, raw: Any) -> List[Dict[str, Any]]:
        # 既に list 形式ならそのまま
        if isinstance(raw, list):
            return raw

        # 旧形式 {"users": {...}} からのマイグレーション
        if isinstance(raw, dict) and "users" in raw:
            migrated: List[Dict[str, Any]] = []
            for uid, udata in (raw.get("users") or {}).items():
                if isinstance(udata, dict):
                    for k, v in udata.items():
                        migrated.append(
                            {
                                "user_id": uid,
                                "key": k,
                                "value": v,
                                "ts": time.time(),
                            }
                        )
            print("[MemoryOS] migrated old dict-format → list-format")
            return migrated

        return []

    def _save_all(self, data: List[Dict[str, Any]]) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ---- 公開 API ----

    def put(self, user_id: str, key: str, value: Any = None) -> bool:
        """value が渡されなかった場合でも安全に処理する。"""
        if value is None:
            value = {}

        data = self._load_all()
        data.append(
            {
                "user_id": user_id,
                "key": key,
                "value": value,
                "ts": time.time(),
            }
        )
        self._save_all(data)
        return True

    def append_history(self, user_id: str, record: Dict[str, Any]) -> bool:
        key = f"history_{int(time.time())}"
        return self.put(user_id, key, record)

    def add_usage(self, user_id: str, cited_ids: Optional[List[str]] = None) -> bool:
        record = {
            "used": True,
            "citations": cited_ids or [],
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        key = f"usage_{int(time.time())}"
        return self.put(user_id, key, record)

    def get(self, user_id: str, key: str) -> Any:
        for r in reversed(self._load_all()):
            if r.get("user_id") == user_id and r.get("key") == key:
                return r.get("value")
        return None

    def list_all(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        data = self._load_all()
        if user_id:
            data = [r for r in data if r.get("user_id") == user_id]
        return data

    def recent(
        self,
        user_id: str,
        limit: int = 20,
        contains: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        items = self.list_all(user_id)
        items.sort(key=lambda r: r.get("ts", 0), reverse=True)

        if contains:
            s = contains.strip()
            filtered: List[Dict[str, Any]] = []
            for r in items:
                v = r.get("value")
                if isinstance(v, dict):
                    q = str(v.get("query") or v.get("text") or "")
                else:
                    q = str(v)
                if s in q:
                    filtered.append(r)
            items = filtered

        return items[:limit]

    # ---- DebateOS / PlanOS 互換 ----

    def search(
        self,
        query: str,
        k: int = 10,
        kinds: Optional[List[str]] = None,
        min_sim: float = 0.0,
        **kwargs,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        新しい decide() が呼ぶ MEM.search(...) と互換のインターフェイス。
        ここではシンプルに「episode 系の履歴を全部 'episodic' として返す」
        だけにしておく（スコアや類似度はダミー）。
        """
        data = self._load_all()
        episodic: List[Dict[str, Any]] = []

        for r in data:
            val = r.get("value") or {}
            if not isinstance(val, dict):
                continue
            text = str(val.get("text") or val.get("query") or "")
            if not text:
                continue

            episodic.append(
                {
                    "id": r.get("key"),
                    "text": text,
                    "tags": val.get("tags", []),
                    "meta": val.get("meta", {}),
                    "score": 0.5,  # とりあえず固定
                }
            )

        episodic = episodic[:k]
        return {"episodic": episodic}

    def put_episode(
        self,
        text: str,
        tags: Optional[List[str]] = None,
        meta: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> bool:
        """
        server.py 側から

            MEM.put_episode(
                text=episode_text,
                tags=[...],
                meta={...},
            )

        の形で呼ばれても動くようにしたラッパー。
        """
        record: Dict[str, Any] = {
            "text": text,
            "tags": tags or [],
            "meta": meta or {},
        }

        # 互換用：追加の kwargs も value の中に押し込んでおく
        for k, v in kwargs.items():
            if k not in record:
                record[k] = v

        # meta 内に user_id があればそれを使う。なければ "episodic"
        user_id = (record.get("meta") or {}).get("user_id", "episodic")
        key = f"episode_{int(time.time())}"
        return self.put(user_id, key, record)


# ==== グローバル MEM 初期化 ====
try:
    MEM = MemoryStore.load(MEM_PATH)
    print(f"[MemoryOS] initialized at {MEM_PATH}")
except Exception as e:
    print(f"[MemoryOS] init failed: {e}")
    MEM = MemoryStore.load(MEM_PATH)

# 他モジュールで MEM を直接使えるようにする
import builtins
builtins.MEM = MEM


# ============================
# 関数 API（既存コード互換）
# ============================

def put(user_id: str, key: str, value: Any) -> bool:
    """グローバル関数版 put（内部では MEM を使う）"""
    return MEM.put(user_id, key, value)


def add_usage(user_id: str, cited_ids: Optional[List[str]] = None) -> bool:
    return MEM.add_usage(user_id, cited_ids)


def get(user_id: str, key: str) -> Any:
    return MEM.get(user_id, key)


def list_all(user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    return MEM.list_all(user_id)


def append_history(user_id: str, record: Dict[str, Any]) -> bool:
    return MEM.append_history(user_id, record)


def recent(
    user_id: str,
    limit: int = 20,
    contains: Optional[str] = None,
) -> List[Dict[str, Any]]:
    return MEM.recent(user_id, limit=limit, contains=contains)
