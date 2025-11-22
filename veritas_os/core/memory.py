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

# ▼ ベクトルメモリ / メモリ分類モデル（あれば使う）
try:
    from veritas_os.core.models import memory_model as memory_model_core
    MEM_VEC = getattr(memory_model_core, "MEM_VEC", None)
    MEM_CLF = getattr(memory_model_core, "MEM_CLF", None)
except Exception:
    MEM_VEC = None
    MEM_CLF = None

# ============================
# モデル関連（旧：memory_model.pkl）
# ============================

# veritas_os/core/memory.py から見て
# REPO_ROOT = .../veritas_os
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
    # MEM_CLF がちゃんと用意されていればそちらを優先してもよいが、
    # いまは既存の MODEL ベースの実装を残しておく。
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
# MemoryStore クラス（KVS）
# ============================


class MemoryStore:
    """シンプルな JSON ベースの MemoryOS（KVS部分）"""

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
            print(f"[MemoryOS][DEBUG] memory file not found: {self.path}")
            return []
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            data = self._normalize(raw)
            print(f"[MemoryOS][DEBUG] loaded {len(data)} records from {self.path}")
            return data
        except Exception as e:
            print(f"[MemoryOS][DEBUG] load failed: {e!r}")
            return []

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

    # ---- 公開 API（KVS） ----

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

    # ---- DebateOS / PlanOS 互換 + simple semantic search ----

    def _simple_score(self, query: str, text: str) -> float:
        q = (query or "").strip().lower()
        t = (text or "").strip().lower()
        if not q or not t:
            return 0.0

        # まず「部分一致」があるだけで 0.5 点はあげる
        if q in t or t in q:
            base = 0.5
        else:
            base = 0.0

        # それに加えて、スペース区切りトークン一致も見る
        q_tokens = set(q.split())
        t_tokens = set(t.split())
        if q_tokens and t_tokens:
            inter = q_tokens & t_tokens
            token_score = len(inter) / max(len(q_tokens), 1)
        else:
            token_score = 0.0

        # 両方合成（最大 1.0）
        return min(1.0, base + 0.5 * token_score)

    def search(
        self,
        query: str,
        k: int = 10,
        kinds: Optional[List[str]] = None,
        min_sim: float = 0.0,
        user_id: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        旧スタイルの episodic メモリ検索。
        - memory.json に蓄積された decision / episodic ログを対象にする
        - query との簡易類似度でソートして返す
        - 戻り値は {"episodic": [ ... ]} 形式
        """
        query = (query or "").strip()
        if not query:
            return {}

    # memory.json 全体をロード
        data = self._load_all()

        episodic: List[Dict[str, Any]] = []

        target_user = user_id  # 指定があればそれを使う

        for r in data:
    # user_id 指定があればそれだけ、なければ全ユーザー対象
            if target_user and r.get("user_id") != target_user:
                continue

            val = r.get("value") or {}
            if not isinstance(val, dict):
                continue

        # テキスト候補（decision 保存時の query / text を使う）
            text = str(
                val.get("text")
                or val.get("query")
                or ""
            ).strip()
            if not text:
                continue

        # 簡易スコア（0〜1想定）
            score = self._simple_score(query, text)
            if score < min_sim:
                continue

            episodic.append(
                {
                    "id": r.get("key"),
                    "text": text,
                    "score": float(score),
                    "meta": {
                        "user_id": r.get("user_id"),
                        "created_at": r.get("created_at") or r.get("timestamp"),
                        "kind": "episodic",
                    },
                }
            )

    # スコア順にソートして上位 k 件
        episodic.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        if not episodic:
            return {}
        print(f"[MemoryOS][DEBUG] episodic hits={len(episodic)}")
        return {"episodic": episodic[:k]}

    def put_episode(
        self,
        text: str,
        tags: Optional[List[str]] = None,
        meta: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> str:
        """
        server.py 側から

            new_id = MEM.put_episode(
                text=episode_text,
                tags=[...],
                meta={...},
            )

        の形で呼ばれても動くようにしたラッパー。
        戻り値: 追加されたエピソードの key (例: "episode_1736312345")
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

        # 実際の保存
        self.put(user_id, key, record)

        return key

    # ---- Planner 用サマリ ----

    def summarize_for_planner(
        self,
        user_id: str,
        query: str,
        limit: int = 8,
    ) -> str:
        """
        Planner 用に「最近の関連エピソード」を1つのテキストにまとめる。
        - simple QA / AGI どちらでもそのまま貼り込めるような短いサマリ
        """
        res = self.search(query=query, k=limit, user_id=user_id)
        episodic = res.get("episodic") or []

        if not episodic:
            return "MemoryOS から参照すべき重要メモは見つかりませんでした。"

        lines: List[str] = []
        lines.append("【MemoryOS 要約】最近の関連エピソード（新しい順・最大数件）")
        for i, ep in enumerate(episodic, start=1):
            text = str(ep.get("text") or "")
            tags = ep.get("tags") or []
            ts = ep.get("ts")
            if ts:
                ts_str = datetime.utcfromtimestamp(ts).isoformat() + "Z"
            else:
                ts_str = "unknown"

            tag_str = f" tags={tags}" if tags else ""
            # 1行で収まるように軽くトリム
            if len(text) > 120:
                text_short = text[:117] + "..."
            else:
                text_short = text

            lines.append(f"- #{i} [{ts_str}]{tag_str} {text_short}")

        return "\n".join(lines)


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
# 関数 API（既存コード互換＋ベクトル対応）
# ============================


def put(*args, **kwargs) -> bool:
    """
    グローバル関数版 put。

    呼び出しモードは4パターンをサポート：

    1) 旧 KVS モード（既存互換）
       put(user_id, key, value)
       put(user_id, key=..., value=...)

    2) 新ベクトルモード／エピソードモード
       put(kind, {"text": ..., "tags": [...], "meta": {...}})

       MEM_VEC があればベクトルメモリにも保存し、
       MEM_VEC がなくても KVS にフォールバックして保存する。

    3) kwargs 指定（既存互換）
       put(user_id=..., key=..., value=...)

    4) それ以外は TypeError
    """

    # ---- 1) user_id だけ位置引数で、key/value が kwargs ----
    # 例: mem.put(uid, key="xxx", value={...})
    if len(args) == 1 and "key" in kwargs:
        user_id = args[0]
        key = kwargs["key"]
        value = kwargs.get("value")
        return MEM.put(user_id, key, value)

    # ---- 2) kind + dict （ベクトル / エピソードモード）----
    if len(args) == 2 and isinstance(args[1], dict):
        kind = str(args[0] or "semantic")
        doc = dict(args[1])
        text = (doc.get("text") or "").strip()
        tags = doc.get("tags") or []
        meta = doc.get("meta") or {}

        # 何もないものは保存しない
        if not text and not doc:
            return False

        # ベクトルメモリ（あれば）
        if MEM_VEC is not None:
            try:
                base_text = text or json.dumps(doc, ensure_ascii=False)
                MEM_VEC.add(kind=kind, text=base_text, tags=tags, meta=meta)
            except Exception as e:
                print("[MemoryOS] MEM_VEC.add error (fallback to KVS):", e)

        # KVS にも保存（MEM_VEC が無くてもここは動く）
        user_id = meta.get("user_id", kind)
        key = f"{kind}_{int(time.time())}"
        return MEM.put(user_id, key, doc)

    # ---- 3) 完全位置引数 3つ（従来 KVS モード）----
    # 例: mem.put(user_id, key, value)
    if len(args) >= 3:
        user_id, key, value = args[0], args[1], args[2]
        return MEM.put(user_id, key, value)

    # ---- 4) kwargs だけで指定された場合 ----
    # 例: mem.put(user_id="xxx", key="yyy", value={...})
    if "user_id" in kwargs and "key" in kwargs:
        return MEM.put(kwargs["user_id"], kwargs["key"], kwargs.get("value"))

    # どれにも当てはまらなければ TypeError
    raise TypeError(
        "put() expected (user_id, key, value) for KVS "
        "or (kind, {text,tags,meta}) for vector mode"
    )


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


def search(
    query: str,
    k: int = 10,
    kinds: Optional[List[str]] = None,
    min_sim: float = 0.0,
    user_id: Optional[str] = None,
    **kwargs,
):
    """
    グローバル関数版 search。

    - MEM_VEC があれば、まずベクトル検索を使う（list[dict] を返す想定）
    - なければ旧 KVS の simple search を使い、episodic リストだけを返す。
    """
    # ---- ベクトル検索が利用可能ならそちらを優先 ----
    if MEM_VEC is not None:
        try:
            # SimpleMemVec.search と合わせて、引数は名前付きで渡す
            hits = MEM_VEC.search(query=query, k=k, kinds=kinds, min_sim=min_sim)
            return hits
        except TypeError:
            # 旧シグネチャ等へのフォールバック
            try:
                hits = MEM_VEC.search(query, k=k)
                return hits
            except Exception as e:
                print("[MemoryOS] MEM_VEC.search (fallback) error:", e)
        except Exception as e:
            print("[MemoryOS] MEM_VEC.search error:", e)

    # ---- フォールバック：KVSベースの簡易 search ----
    res = MEM.search(
        query=query,
        k=k,
        kinds=kinds,
        min_sim=min_sim,
        user_id=user_id,
        **kwargs,
    )
    if isinstance(res, dict) and "episodic" in res:
        return res["episodic"]
    return res


def summarize_for_planner(
    user_id: str,
    query: str,
    limit: int = 8,
) -> str:
    """
    Planner から直接呼べるようにしたラッパー。
    """
    return MEM.summarize_for_planner(user_id=user_id, query=query, limit=limit)
