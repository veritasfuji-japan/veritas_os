from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime
import json
import os
import time
import threading
from contextlib import contextmanager

# OS 判定
IS_WIN = os.name == "nt"

if not IS_WIN:
    try:
        import fcntl  # type: ignore
    except ImportError:  # 非POSIX環境の保険
        fcntl = None  # type: ignore
else:
    fcntl = None  # type: ignore

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
    """
    （暫定）クエリテキストから「決定ステータス」を推定するヘルパー。

    前提:
    - memory_model.pkl は sklearn の Pipeline or モデルで、
      .predict([text]) が動く
    """
    if MODEL is None:
        return "unknown"
    try:
        pred = MODEL.predict([query_text])[0]
        return str(pred)
    except Exception as e:
        print("[MemoryModel] predict_decision_status error:", e)
        return "unknown"


def predict_gate_label(text: str) -> Dict[str, float]:
    """
    FUJI/ValueCore から使える gate 用ラッパー。

    優先順:
      1) MEM_CLF (core.models.memory_model 側で学習した分類器)
      2) 上記が無い場合は memory_model.pkl (MODEL) の predict_proba
      3) どちらもダメなら {"allow": 0.5}
    """
    prob_allow = 0.5

    # 1) MEM_CLF 優先
    clf = MEM_CLF
    if clf is not None:
        try:
            probs = clf.predict_proba([text])[0]
            classes = list(getattr(clf, "classes_", []))
            if "allow" in classes:
                idx = classes.index("allow")
                prob_allow = float(probs[idx])
            else:
                # "allow" クラス名が無い場合は最大値を採用
                prob_allow = float(max(probs))
            return {"allow": prob_allow}
        except Exception as e:
            print("[MemoryModel] MEM_CLF.predict_proba error:", e)

    # 2) MODEL (memory_model.pkl) に predict_proba があれば使う
    if MODEL is not None and hasattr(MODEL, "predict_proba"):
        try:
            probs = MODEL.predict_proba([text])[0]
            classes = list(getattr(MODEL, "classes_", []))
            if "allow" in classes:
                idx = classes.index("allow")
                prob_allow = float(probs[idx])
            else:
                prob_allow = float(max(probs))
        except Exception as e:
            print("[MemoryModel] MODEL.predict_proba error:", e)

    return {"allow": prob_allow}


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
# ファイルロック（multi-process 対応）
# ============================

@contextmanager
def locked_memory(path: Path, timeout: float = 5.0) -> Any:
    """
    memory.json 用のシンプルな排他ロック。

    - POSIX: fcntl.flock による排他ロック
    - Windows: .lock ファイルを用いた簡易ロック
    """
    start = time.time()
    lockfile: Optional[Path] = None
    fh = None

    if not IS_WIN and fcntl is not None:
        # POSIX: fcntl によるファイルロック
        path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(path, "a+", encoding="utf-8")
        while True:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)  # type: ignore[arg-type]
                break
            except BlockingIOError:
                if time.time() - start > timeout:
                    fh.close()
                    raise TimeoutError(f"failed to acquire lock for {path}")
                time.sleep(0.02)
        try:
            yield
        finally:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)  # type: ignore[arg-type]
            except Exception as e:
                print("[MemoryOS] unlock failed:", e)
            fh.close()
    else:
        # Windows or 非POSIX: .lock ファイルで排他
        lockfile = path.with_suffix(path.suffix + ".lock")
        backoff = 0.01
        while True:
            try:
                fd = os.open(str(lockfile), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                break
            except FileExistsError:
                if time.time() - start > timeout:
                    raise TimeoutError(f"failed to acquire lock for {path}")
                time.sleep(backoff)
                backoff = min(backoff * 2.0, 0.32)
        try:
            yield
        finally:
            try:
                if lockfile.exists():
                    lockfile.unlink()
            except Exception as e:
                print("[MemoryOS] lockfile cleanup failed:", e)


# ============================
# MemoryStore クラス（KVS）
# ============================


class MemoryStore:
    """JSON ベースの MemoryOS（KVS部分） + ファイルロック + インメモリキャッシュ"""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

        # キャッシュ関連
        self._cache_data: Optional[List[Dict[str, Any]]] = None
        self._cache_mtime: float = 0.0
        self._cache_loaded_at: float = 0.0
        self._cache_ttl: float = float(
            os.getenv("VERITAS_MEMORY_CACHE_TTL", "5.0")
        )  # 秒
        self._cache_lock = threading.RLock()

        # 初期ファイル生成
        if not self.path.exists():
            # 最初の生成だけはロック範囲内で空配列を書き込む
            self._save_all([])

    @classmethod
    def load(cls, path: Path) -> "MemoryStore":
        return cls(path)

    # ---- 内部ヘルパー ----

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

    def _load_all(
        self,
        *,
        copy: bool = True,
        use_cache: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        memory.json 全体を読み込む。

        - use_cache=True かつ TTL 内で、ファイルの mtime が変わっていなければ
          インメモリキャッシュを返す。
        - それ以外は locked_memory でファイルからロードしてキャッシュ更新。
        """
        # キャッシュチェック
        if use_cache and self._cache_ttl > 0:
            with self._cache_lock:
                try:
                    mtime = self.path.stat().st_mtime
                except FileNotFoundError:
                    mtime = 0.0

                now = time.time()
                if (
                    self._cache_data is not None
                    and mtime == self._cache_mtime
                    and (now - self._cache_loaded_at) <= self._cache_ttl
                ):
                    data = self._cache_data
                    if copy:
                        return [dict(r) for r in data]
                    return data

        if not self.path.exists():
            print(f"[MemoryOS][DEBUG] memory file not found: {self.path}")
            data: List[Dict[str, Any]] = []
        else:
            try:
                with locked_memory(self.path):
                    with open(self.path, "r", encoding="utf-8") as f:
                        raw = json.load(f)
                data = self._normalize(raw)
                print(
                    f"[MemoryOS][DEBUG] loaded {len(data)} records from {self.path}"
                )
            except Exception as e:
                print(f"[MemoryOS][DEBUG] load failed: {e!r}")
                data = []

        # キャッシュ更新
        with self._cache_lock:
            self._cache_data = data
            try:
                self._cache_mtime = self.path.stat().st_mtime
            except FileNotFoundError:
                self._cache_mtime = 0.0
            self._cache_loaded_at = time.time()

        if copy:
            return [dict(r) for r in data]
        return data

    def _save_all(self, data: List[Dict[str, Any]]) -> None:
        """
        memory.json 全体を書き出す。

        - locked_memory による排他
        - tmp ファイルへの書き出し + os.replace によるアトミック更新
        - fsync 失敗時は warning を出す
        """
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        with locked_memory(self.path):
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError as e:
                    # 一部環境では fsync 不要な場合もあるので warning のみにする
                    print("[MemoryOS] fsync failed (non-fatal):", e)
            os.replace(tmp_path, self.path)

        # キャッシュ更新
        with self._cache_lock:
            self._cache_data = [dict(r) for r in data]
            try:
                self._cache_mtime = self.path.stat().st_mtime
            except FileNotFoundError:
                self._cache_mtime = 0.0
            self._cache_loaded_at = time.time()

    # ---- 公開 API（KVS） ----

    def put(self, user_id: str, key: str, value: Any = None) -> bool:
        """value が渡されなかった場合でも安全に処理する。"""
        if value is None:
            value = {}

        # 書き込み前は必ずディスクから最新を取り直す（use_cache=False）
        data = self._load_all(copy=True, use_cache=False)
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
        for r in reversed(self._load_all(copy=False)):
            if r.get("user_id") == user_id and r.get("key") == key:
                return r.get("value")
        return None

    def list_all(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        data = self._load_all(copy=True)
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

        # まず「部分一致」があるだけで 0.5 点
        if q in t or t in q:
            base = 0.5
        else:
            base = 0.0

        # スペース区切りトークン一致も見る
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

        data = self._load_all(copy=True)
        episodic: List[Dict[str, Any]] = []
        target_user = user_id  # 指定があればそれを使う

        for r in data:
            # user_id 指定があればそれだけ、なければ全ユーザー対象
            if target_user and r.get("user_id") != target_user:
                continue

            val = r.get("value") or {}
            if not isinstance(val, dict):
                continue

            text = str(
                val.get("text")
                or val.get("query")
                or ""
            ).strip()
            if not text:
                continue

            score = self._simple_score(query, text)
            if score < min_sim:
                continue

            tags = val.get("tags") or []

            episodic.append(
                {
                    "id": r.get("key"),
                    "text": text,
                    "score": float(score),
                    "tags": tags,
                    "ts": r.get("ts"),
                    "meta": {
                        "user_id": r.get("user_id"),
                        "created_at": r.get("ts"),
                        "kind": "episodic",
                    },
                }
            )

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
        """
        res = self.search(query=query, k=limit, user_id=user_id)
        episodic = res.get("episodic") or []

        if not episodic:
            return "MemoryOS から参照すべき重要メモは見つかりませんでした。"

        lines: List[str] = []
        lines.append("【MemoryOS 要約】最近の関連エピソード（スコア順・最大数件）")
        for i, ep in enumerate(episodic, start=1):
            text = str(ep.get("text") or "")
            tags = ep.get("tags") or []
            ts = ep.get("ts")
            if ts:
                try:
                    ts_str = datetime.utcfromtimestamp(float(ts)).isoformat() + "Z"
                except Exception:
                    ts_str = "unknown"
            else:
                ts_str = "unknown"

            tag_str = f" tags={tags}" if tags else ""
            if len(text) > 120:
                text_short = text[:117] + "..."
            else:
                text_short = text

            lines.append(f"- #{i} [{ts_str}]{tag_str} {text_short}")

        return "\n".join(lines)


# ============================
# Evidence read for /v1/decide
# ============================


def _hits_to_evidence(
    hits: List[Dict[str, Any]],
    *,
    source_prefix: str = "memory",
) -> List[Dict[str, Any]]:
    """
    Memory / MEM_VEC.search のヒット結果(list[dict])を
    /v1/decide 用の evidence(list[Dict]) に変換する。
    """
    evidence: List[Dict[str, Any]] = []

    for h in hits:
        if not isinstance(h, dict):
            continue

        text = str(h.get("text") or "")
        if not text:
            continue

        meta = h.get("meta") or {}
        kind = meta.get("kind") or "episodic"
        uri = meta.get("uri") or meta.get("url") or None

        score = h.get("score")
        try:
            confidence = float(score) if score is not None else 0.7
        except Exception:
            confidence = 0.7

        evidence.append(
            {
                "source": f"{source_prefix}:{kind}",
                "uri": uri,
                "snippet": text[:300],
                "confidence": confidence,
            }
        )

    return evidence


def get_evidence_for_decision(
    decision: Dict[str, Any],
    *,
    user_id: Optional[str] = None,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """
    decision_snapshot(dict) から query を取り出し、
    MemoryOS（MEM_VEC or KVS）を検索して evidence を返す。
    """
    if not isinstance(decision, dict):
        return []

    q = (
        decision.get("query")
        or (decision.get("chosen") or {}).get("query")
        or (decision.get("chosen") or {}).get("title")
        or (decision.get("chosen") or {}).get("description")
        or ""
    )
    q = str(q).strip()
    if not q:
        return []

    ctx = decision.get("context") or {}
    uid = (
        user_id
        or ctx.get("user_id")
        or ctx.get("user")
        or ctx.get("session_id")
        or None
    )

    hits = search(
        query=q,
        k=top_k,
        user_id=uid,
    )
    if not hits or not isinstance(hits, list):
        return []

    return _hits_to_evidence(hits, source_prefix="memory")


def get_evidence_for_query(
    query: str,
    *,
    user_id: Optional[str] = None,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """
    テスト用 / デバッグ用のユーティリティ。
    決定スナップショットが無くても query だけで MemoryEvidence を試す。
    """
    query = (query or "").strip()
    if not query:
        return []

    hits = search(query=query, k=top_k, user_id=user_id)
    if not hits or not isinstance(hits, list):
        return []

    return _hits_to_evidence(hits, source_prefix="memory")


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

    呼び出しモードは4パターン：

    1) 旧 KVS モード
       put(user_id, key, value)
       put(user_id, key=..., value=...)

    2) ベクトル / エピソードモード
       put(kind, {"text": ..., "tags": [...], "meta": {...}})

    3) kwargs 指定
       put(user_id=..., key=..., value=...)

    4) それ以外は TypeError
    """

    # ---- 1) user_id だけ位置引数で、key/value が kwargs ----
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

        if not text and not doc:
            return False

        if MEM_VEC is not None:
            try:
                base_text = text or json.dumps(doc, ensure_ascii=False)
                MEM_VEC.add(kind=kind, text=base_text, tags=tags, meta=meta)
            except Exception as e:
                print("[MemoryOS] MEM_VEC.add error (fallback to KVS):", e)

        user_id = meta.get("user_id", kind)
        key = f"{kind}_{int(time.time())}"
        return MEM.put(user_id, key, doc)

    # ---- 3) 完全位置引数 3つ（従来 KVS モード）----
    if len(args) >= 3:
        user_id, key, value = args[0], args[1], args[2]
        return MEM.put(user_id, key, value)

    # ---- 4) kwargs だけで指定された場合 ----
    if "user_id" in kwargs and "key" in kwargs:
        return MEM.put(kwargs["user_id"], kwargs["key"], kwargs.get("value"))

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
) -> List[Dict[str, Any]]:
    """
    グローバル関数版 search。

    優先順:
      1) MEM_VEC があればベクトル検索を試す
         - 非空の list[dict] または
           dict 内の "hits" / "episodic" / "results" が list[dict] のときだけ採用
      2) それ以外（0件 or エラー）は、KVS ベースの simple search にフォールバック

    戻り値はいずれも list[dict] を返す。
    """

    # -------------------------
    # 1) ベクトル検索（あれば優先）
    # -------------------------
    if MEM_VEC is not None:
        try:
            raw = MEM_VEC.search(
                query=query,
                k=k,
                kinds=kinds,
                min_sim=min_sim,
            )

            candidates: Optional[List[Dict[str, Any]]] = None

            # パターンA: そのまま list[dict]
            if isinstance(raw, list):
                candidates = [h for h in raw if isinstance(h, dict)]

            # パターンB: dict の中に hits / episodic / results があるケース
            elif isinstance(raw, dict):
                for key in ("hits", "episodic", "results"):
                    v = raw.get(key)
                    if isinstance(v, list):
                        candidates = [h for h in v if isinstance(h, dict)]
                        if candidates:
                            break

            # 非空ならそのまま返す
            if candidates:
                return candidates

            # ここまで来たら「0件ヒット」扱い → KVS にフォールバック
            print("[MemoryOS] MEM_VEC.search returned no hits; fallback to KVS")

        except TypeError:
            # 旧シグネチャ (MEM_VEC.search(query, k)) へのフォールバック
            try:
                raw = MEM_VEC.search(query, k=k)
                if isinstance(raw, list) and raw:
                    return [h for h in raw if isinstance(h, dict)]
                print("[MemoryOS] MEM_VEC.search(old sig) no hits; fallback to KVS")
            except Exception as e:
                print("[MemoryOS] MEM_VEC.search(old sig) error:", e)

        except Exception as e:
            print("[MemoryOS] MEM_VEC.search error:", e)

    # -------------------------
    # 2) フォールバック: KVS simple search
    # -------------------------
    res = MEM.search(
        query=query,
        k=k,
        kinds=kinds,
        min_sim=min_sim,
        user_id=user_id,
        **kwargs,
    )

    # MemoryStore.search は {"episodic": [...]} を返す実装
    if isinstance(res, dict) and "episodic" in res:
        hits = res["episodic"]
        if isinstance(hits, list):
            return [h for h in hits if isinstance(h, dict)]
        return []

    # 念のため、すでに list で返ってきた場合もハンドリング
    if isinstance(res, list):
        return [h for h in res if isinstance(h, dict)]

    return []


def summarize_for_planner(
    user_id: str,
    query: str,
    limit: int = 8,
) -> str:
    """Planner から直接呼べるラッパー"""
    return MEM.summarize_for_planner(user_id=user_id, query=query, limit=limit)
