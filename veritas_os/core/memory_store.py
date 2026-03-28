# veritas_os/core/memory_store.py
"""
MemoryStore - JSON-based KVS core for MemoryOS.

Provides:
- MemoryStore class with put/get/list_all/search/erase_user operations
- Lifecycle metadata normalization (retention class, expiry, legal hold)
- In-memory caching with TTL
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from copy import deepcopy
import json
import os
import time
import threading
import logging

from .memory_storage import locked_memory
from .memory_summary_helpers import build_planner_summary
from .memory_compliance import (
    erase_user_data,
    is_record_legal_hold,
    should_cascade_delete_semantic,
)

logger = logging.getLogger(__name__)

DEFAULT_RETENTION_CLASS = "standard"
ALLOWED_RETENTION_CLASSES = {
    "short",
    "standard",
    "long",
    "regulated",
}


class MemoryStore:
    """JSON ベースの MemoryOS（KVS部分） + ファイルロック + インメモリキャッシュ"""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Resolve symlinks after directory creation to prevent TOCTOU
        # attacks where a symlink could redirect writes outside the
        # intended directory.
        resolved_parent = self.path.parent.resolve(strict=True)
        self.path = resolved_parent / self.path.name

        # キャッシュ関連
        self._cache_data: Optional[List[Dict[str, Any]]] = None
        self._cache_mtime: float = 0.0
        self._cache_loaded_at: float = 0.0
        _raw_ttl = os.getenv("VERITAS_MEMORY_CACHE_TTL", "5.0")
        try:
            self._cache_ttl: float = max(0.0, min(3600.0, float(_raw_ttl)))
        except (ValueError, TypeError):
            logger.warning("Invalid VERITAS_MEMORY_CACHE_TTL=%r, using default 5.0", _raw_ttl)
            self._cache_ttl = 5.0
        self._cache_lock = threading.RLock()

        # 初期ファイル生成
        if not self.path.exists():
            self._save_all([])

    @classmethod
    def load(cls, path: Path) -> "MemoryStore":
        return cls(path)

    def _normalize(self, raw: Any) -> List[Dict[str, Any]]:
        if isinstance(raw, list):
            return raw

        # 旧形式からのマイグレーション
        if isinstance(raw, dict) and "users" in raw:
            migrated: List[Dict[str, Any]] = []
            users = raw.get("users")
            if not isinstance(users, dict):
                logger.warning("[MemoryOS] old-format 'users' is not a dict, skipping migration")
                return []
            for uid, udata in users.items():
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
            logger.info("[MemoryOS] migrated old dict-format → list-format")
            return migrated

        return []

    def _load_all(
        self,
        *,
        copy: bool = True,
        use_cache: bool = True,
    ) -> List[Dict[str, Any]]:
        """memory.json 全体を読み込む"""
        #
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
                        return deepcopy(data)
                    return data

        if not self.path.exists():
            logger.debug("[MemoryOS] memory file not found: %s", self.path)
            data: List[Dict[str, Any]] = []
        else:
            try:
                with locked_memory(self.path):
                    with open(self.path, "r", encoding="utf-8") as f:
                        raw = json.load(f)
                data = self._normalize(raw)
            except json.JSONDecodeError as e:
                logger.error("[MemoryOS] JSON decode error: %s", e)
                data = []
            except (OSError, TimeoutError) as e:
                logger.error("[MemoryOS] load error: %s", e)
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
            return deepcopy(data)
        return data

    def _save_all(self, data: List[Dict[str, Any]]) -> bool:
        """memory.json 全体を保存（atomic_write_json でクラッシュ安全）"""
        try:
            from veritas_os.core.atomic_io import atomic_write_json
            with locked_memory(self.path):
                atomic_write_json(self.path, data, indent=2)

            # キャッシュ無効化
            with self._cache_lock:
                self._cache_data = None
                self._cache_mtime = 0.0
                self._cache_loaded_at = 0.0

            return True
        except (
            OSError,
            TimeoutError,
            TypeError,
            ValueError,
            RuntimeError,
        ) as e:
            logger.error("[MemoryOS] save error: %s", e)
            return False

    def put(self, user_id: str, key: str, value: Any) -> bool:
        """KVS put 操作。

        Lifecycle metadata policy (P1-4):
        - value.meta.retention_class を標準化
        - value.meta.expires_at をUTC ISO-8601へ正規化
        - value.meta.legal_hold を bool 化
        """
        normalized_value = self._normalize_lifecycle(value)
        data = self._load_all(copy=True)

        # 既存レコードを探す
        found = False
        for r in data:
            if r.get("user_id") == user_id and r.get("key") == key:
                r["value"] = normalized_value
                r["ts"] = time.time()
                found = True
                break

        # 新規レコード
        if not found:
            data.append(
                {
                    "user_id": user_id,
                    "key": key,
                    "value": normalized_value,
                    "ts": time.time(),
                }
            )

        return self._save_all(data)

    def get(self, user_id: str, key: str) -> Any:
        """KVS get 操作"""
        data = self._load_all(copy=True)
        for r in data:
            if r.get("user_id") == user_id and r.get("key") == key:
                if self._is_record_expired(r):
                    return None
                return r.get("value")
        return None

    def list_all(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """全レコードをリスト"""
        data = self._load_all(copy=True)
        filtered_data = [r for r in data if not self._is_record_expired(r)]
        if user_id is not None:
            return [r for r in filtered_data if r.get("user_id") == user_id]
        return filtered_data

    @staticmethod
    def _parse_expires_at(expires_at: Any) -> Optional[str]:
        """Normalize expires_at to UTC ISO8601 string, or None."""
        if expires_at in (None, ""):
            return None

        if isinstance(expires_at, (int, float)):
            try:
                dt = datetime.fromtimestamp(float(expires_at), tz=timezone.utc)
            except (OverflowError, OSError, ValueError):
                return None
            return dt.isoformat()

        if isinstance(expires_at, str):
            raw = expires_at.strip()
            if not raw:
                return None
            iso = raw.replace("Z", "+00:00")
            try:
                dt = datetime.fromisoformat(iso)
            except ValueError:
                return None
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()

        return None

    @staticmethod
    def _normalize_lifecycle(value: Any) -> Any:
        """Attach lifecycle fields only to memory-document style dict payloads.

        Backward compatibility:
        - Generic KVS dictionaries (e.g. ``{"foo": "bar"}``) must be
          preserved as-is.
        - Lifecycle normalization is applied only when the value looks like a
          MemoryOS document (has any of ``text/kind/tags/meta`` keys).
        """
        if not isinstance(value, dict):
            return value

        lifecycle_target_keys = {"text", "kind", "tags", "meta"}
        if not any(key in value for key in lifecycle_target_keys):
            return value

        normalized = dict(value)
        meta = dict(normalized.get("meta") or {})

        retention_class = str(
            meta.get("retention_class") or DEFAULT_RETENTION_CLASS
        ).strip().lower()
        if retention_class not in ALLOWED_RETENTION_CLASSES:
            retention_class = DEFAULT_RETENTION_CLASS

        raw_hold = meta.get("legal_hold", False)
        if isinstance(raw_hold, str):
            legal_hold = raw_hold.strip().lower() in ("true", "1", "yes")
        else:
            legal_hold = bool(raw_hold)
        normalized_expires_at = MemoryStore._parse_expires_at(meta.get("expires_at"))

        meta["retention_class"] = retention_class
        meta["legal_hold"] = legal_hold
        meta["expires_at"] = normalized_expires_at

        normalized["meta"] = meta
        return normalized

    @staticmethod
    def _is_record_expired(record: Dict[str, Any], now_ts: Optional[float] = None) -> bool:
        """Return True if record has passed expires_at and is not on legal hold."""
        value = record.get("value") or {}
        if not isinstance(value, dict):
            return False

        meta = value.get("meta") or {}
        if not isinstance(meta, dict):
            return False

        raw_hold = meta.get("legal_hold", False)
        hold = raw_hold.strip().lower() in ("true", "1", "yes") if isinstance(raw_hold, str) else bool(raw_hold)
        if hold:
            return False

        expires_at = MemoryStore._parse_expires_at(meta.get("expires_at"))
        if not expires_at:
            return False

        try:
            expire_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError:
            return False

        now = now_ts if now_ts is not None else time.time()
        return expire_dt.timestamp() <= float(now)

    def erase_user(
        self,
        user_id: str,
        reason: str,
        actor: str,
    ) -> Dict[str, Any]:
        """Erase user records while honoring legal hold, with audit trail.

        Delegates to memory_compliance.erase_user_data() for the core logic.
        """
        data = self._load_all(copy=True, use_cache=False)
        kept_records, report = erase_user_data(data, user_id, reason, actor)
        saved = self._save_all(kept_records)
        report["ok"] = bool(saved)
        return report

    @staticmethod
    def _is_record_legal_hold(record: Dict[str, Any]) -> bool:
        """Return True when record carries legal hold metadata."""
        return is_record_legal_hold(record)

    @staticmethod
    def _should_cascade_delete_semantic(
        record: Dict[str, Any],
        user_id: str,
        erased_keys: set,
    ) -> bool:
        """Check semantic distill lineage and decide cascade deletion."""
        return should_cascade_delete_semantic(record, user_id, erased_keys)

    def append_history(self, user_id: str, record: Dict[str, Any]) -> bool:
        """履歴を追加"""
        key = f"history_{int(time.time())}"
        return self.put(user_id, key, record)

    def add_usage(self, user_id: str, cited_ids: Optional[List[str]] = None) -> bool:
        """使用状況を記録"""
        key = f"usage_{int(time.time())}"
        value = {
            "cited_ids": cited_ids or [],
            "ts": time.time(),
        }
        return self.put(user_id, key, value)

    def recent(
        self,
        user_id: str,
        limit: int = 20,
        contains: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """最近のレコードを取得"""
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

    def _simple_score(self, query: str, text: str) -> float:
        """シンプルな類似度スコア計算"""
        q = (query or "").strip().lower()
        t = (text or "").strip().lower()
        if not q or not t:
            return 0.0

        # 部分一致
        if q in t or t in q:
            base = 0.5
        else:
            base = 0.0

        # トークン一致
        q_tokens = set(q.split())
        t_tokens = set(t.split())
        if q_tokens and t_tokens:
            inter = q_tokens & t_tokens
            token_score = len(inter) / max(len(q_tokens), 1)
        else:
            token_score = 0.0

        return min(1.0, base + 0.5 * token_score)

    def search(
        self,
        query: str,
        k: int = 10,
        kinds: Optional[List[str]] = None,  # 現状 "episodic" のみ
        min_sim: float = 0.0,
        user_id: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """KVSベースの検索（フォールバック用）"""
        query = (query or "").strip()
        if not query:
            return {}

        try:
            limit = max(0, int(k))
        except (TypeError, ValueError):
            limit = 0

        if limit == 0:
            return {}

        try:
            min_similarity = float(min_sim)
        except (TypeError, ValueError):
            # fail-closed: invalid threshold should not broaden matches.
            min_similarity = 1.1

        data = self._load_all(copy=True)
        episodic: List[Dict[str, Any]] = []
        target_user = user_id if user_id is not None else None

        for r in data:
            if target_user is not None and r.get("user_id") != target_user:
                continue

            val = r.get("value") or {}
            if not isinstance(val, dict):
                continue

            text = str(val.get("text") or val.get("query") or "").strip()
            if not text:
                continue

            score = self._simple_score(query, text)
            if score < min_similarity:
                continue

            tags = val.get("tags") or []
            kind = val.get("kind", "episodic")

            if kinds and kind not in kinds:
                continue

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
                        "kind": kind,
                    },
                }
            )

        episodic.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        if not episodic:
            return {}

        logger.debug("[MemoryOS][KVS] episodic hits=%d", len(episodic))
        return {"episodic": episodic[:limit]}

    def put_episode(
        self,
        text: str,
        tags: Optional[List[str]] = None,
        meta: Optional[Dict[str, Any]] = None,
        _get_mem_vec_fn: Any = None,
        **kwargs,
    ) -> str:
        """
        エピソードを追加。

        - KVS に保存
        - 可能なら VectorMemory にも同時に追加
        """
        record: Dict[str, Any] = {
            "text": text,
            "tags": tags or [],
            "meta": meta or {},
        }

        for k, v in kwargs.items():
            if k not in record:
                record[k] = v

        user_id = (record.get("meta") or {}).get("user_id", "episodic")
        key = f"episode_{int(time.time())}"

        # KVS
        saved = self.put(user_id, key, record)
        if not saved:
            logger.error("[MemoryOS] put_episode persist failed: key=%s", key)
            return key

        # ベクトルインデックスにも追加
        if _get_mem_vec_fn is not None:
            _vec = _get_mem_vec_fn()
            if _vec is not None:
                try:
                    _vec.add(
                            kind="episodic",
                            text=text,
                            tags=tags or [],
                            meta=meta or {},
                        )
                except Exception as e:
                    logger.warning("[MemoryOS] put_episode MEM_VEC.add error: %s", e)

        return key

    def summarize_for_planner(
        self,
        user_id: str,
        query: str,
        limit: int = 8,
    ) -> str:
        """Planner用のサマリ生成（KVS検索ベース）"""
        res = self.search(query=query, k=limit, user_id=user_id)
        episodic = res.get("episodic") or []

        return build_planner_summary(episodic)
