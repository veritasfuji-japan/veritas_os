# veritas_os/core/memory.py
"""
MemoryOS - public API facade.

Public contract:
- ``MemoryStore`` と関連 API は、記憶の保存・検索・要約・ライフサイクル
  制御を担う MemoryOS の互換入口です。
- 本モジュールは MemoryOS の I/O と orchestration を保持し、Planner /
  Kernel / FUJI の責務へ横滑りしません。

Preferred extension points:
- ``memory_helpers.py`` for normalization / compatibility helpers
- ``memory_search_helpers.py`` for search payload shaping and fallback scoring
- ``memory_summary_helpers.py`` for summary text formatting
- ``memory_lifecycle.py`` / ``memory_security.py`` / ``memory_store.py`` for
  lifecycle, security, and backend store details

Compatibility guidance:
- Optional dependency fallback と既存 private wrapper は後方互換のため残して
  あります。新しい検索整形・summary 整形・fallback 分岐は helper 側へ追加し、
  本体へ新規責務を直接積み増さないでください。

Architecture (responsibility split):
- ``memory_vector.py``       : VectorMemory class (algorithm + data structure)
- ``memory_store_compat.py`` : MemoryStore compatibility hooks
- ``memory_distillation.py`` : episodic → semantic distillation orchestration
- ``memory_storage.py``      : file locking (locked_memory) + pickle scanning

This module re-exports every symbol that callers historically imported from
``veritas_os.core.memory`` so the public API surface is unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4
import json
import os
import time
import threading
import logging

from .config import capability_cfg, emit_capability_manifest, cfg
from .memory_security import (
    PICKLE_MIGRATION_GUIDE_PATH,
    emit_legacy_pickle_runtime_blocked,
    is_explicitly_enabled,
    warn_for_legacy_pickle_artifacts,
)
from .memory_lifecycle import (
    is_record_expired,
    is_record_legal_hold,
    normalize_lifecycle,
    parse_expires_at,
    should_cascade_delete_semantic,
)
from .memory_compliance import erase_user_data
from .memory_evidence import (
    get_evidence_for_decision as _get_evidence_for_decision_impl,
    get_evidence_for_query as _get_evidence_for_query_impl,
    hits_to_evidence as _hits_to_evidence_impl,
)
from .memory_helpers import (
    build_distill_prompt as _build_distill_prompt_impl,
    build_semantic_memory_doc,
    build_vector_rebuild_documents,
    collect_episodic_records,
    extract_summary_text,
)
from .memory_search_helpers import (
    collect_candidate_hits,
    dedup_hits as _dedup_hits_impl,
    filter_hits_for_user,
    normalize_store_hits,
)
from .memory_store_helpers import (
    build_kvs_search_hits,
    erase_user_records,
    filter_recent_records,
    is_record_expired_compat as _is_record_expired_compat_impl,
    normalize_document_lifecycle as _normalize_document_lifecycle_impl,
    put_episode_record,
    recent_records_compat,
    search_records_compat,
    simple_score as _simple_score_impl,
    summarize_records_for_planner,
)
from .memory_summary_helpers import build_planner_summary
from . import memory_store as _memory_store_module
from .memory_store import (
    ALLOWED_RETENTION_CLASSES,
    DEFAULT_RETENTION_CLASS,
    MemoryStore,
)

# -- VectorMemory class (authoritative implementation in memory_vector.py) --
from .memory_vector import VectorMemory  # noqa: F401  -- re-exported
from . import memory_vector as _memory_vector_module

# -- File locking (authoritative implementation in memory_storage.py) --
from .memory_storage import locked_memory as _storage_locked_memory
from contextlib import contextmanager

# -- Distill orchestration (authoritative in memory_distillation.py) --
from .memory_distillation import (
    distill_memory_for_user as _distill_impl,
)

# -- Store compat hooks --
from .memory_store_compat import install_memory_store_compat_hooks

from . import llm_client
import sys

logger = logging.getLogger(__name__)

# Attributes that should be propagated to memory_vector when set via
# monkeypatch on the memory module (test compatibility).
_SYNCED_VECTOR_ATTRS = frozenset({"_is_explicitly_enabled", "_emit_legacy_pickle_runtime_blocked"})

_original_module_class = type(sys.modules[__name__])


class _SyncModule(_original_module_class):
    """Module subclass that propagates select monkeypatches to memory_vector."""

    def __setattr__(self, name: str, value: object) -> None:
        super().__setattr__(name, value)
        if name in _SYNCED_VECTOR_ATTRS:
            setattr(_memory_vector_module, name, value)


sys.modules[__name__].__class__ = _SyncModule


# ============================
# Backward-compatible thin wrappers
# ============================


def _is_explicitly_enabled(env_key: str) -> bool:
    """Backward-compatible wrapper for memory security env parsing."""
    return is_explicitly_enabled(env_key)


def _emit_legacy_pickle_runtime_blocked(path: Path, artifact_name: str) -> None:
    """Backward-compatible wrapper for legacy pickle security logging."""
    emit_legacy_pickle_runtime_blocked(path=path, artifact_name=artifact_name)


def _warn_for_legacy_pickle_artifacts(scan_roots: List[Path]) -> None:
    """Backward-compatible wrapper for runtime legacy pickle scanning."""
    warn_for_legacy_pickle_artifacts(scan_roots=scan_roots)


# OS 判定
IS_WIN = os.name == "nt"

if not IS_WIN and capability_cfg.enable_memory_posix_file_lock:
    import fcntl  # type: ignore
else:
    fcntl = None  # type: ignore

if capability_cfg.emit_manifest_on_import:
    emit_capability_manifest(
        component="memory",
        manifest={
            "posix_file_lock": bool(not IS_WIN and fcntl is not None),
            "sentence_transformers": (
                capability_cfg.enable_memory_sentence_transformers
            ),
        },
    )


# ============================
# External model compatibility layer
# ============================

memory_model_core = None
try:
    from veritas_os.core.models import memory_model as memory_model_core  # type: ignore
except (ImportError, ModuleNotFoundError):
    try:
        from .models import memory_model as memory_model_core  # type: ignore
    except (ImportError, ModuleNotFoundError):
        memory_model_core = None

if memory_model_core is not None:
    MEM_VEC_EXTERNAL = getattr(memory_model_core, "MEM_VEC", None)
    MEM_CLF = getattr(memory_model_core, "MEM_CLF", None)
else:
    MEM_VEC_EXTERNAL = None
    MEM_CLF = None

if MEM_VEC_EXTERNAL is not None and MEM_VEC_EXTERNAL.__class__.__name__ == "SimpleMemVec":
    logger.info(
        "[VectorMemory] Detected SimpleMemVec as external MEM_VEC; "
        "ignoring and using built-in VectorMemory instead"
    )
    MEM_VEC_EXTERNAL = None

# モデル関連（ONNX / JSON のみ — pickle は完全廃止済み）
REPO_ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = REPO_ROOT / "core" / "models"

MEMORY_MODEL_PATH = MODELS_DIR / "memory_model.onnx"
VECTOR_INDEX_PATH = MODELS_DIR / "vector_index.json"

logger.info("[MemoryModel] module loaded from: %s", __file__)

MODEL = None


# ============================
# MEM_VEC singleton management
# ============================

# ★ 修正 (H-10): MEM_VEC へのアクセスをスレッドセーフにするためのロック
_mem_vec_lock = threading.Lock()
MEM_VEC = None
_runtime_guard_checked = False


def _run_runtime_pickle_guard_once() -> None:
    """Run legacy pickle detection once at first runtime MemoryOS access."""
    global _runtime_guard_checked

    if _runtime_guard_checked:
        return

    with _mem_vec_lock:
        if _runtime_guard_checked:
            return

        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        runtime_scan_roots = [MODELS_DIR]
        configured_memory_dir = os.getenv("VERITAS_MEMORY_DIR", "").strip()
        if configured_memory_dir:
            runtime_scan_roots.append(Path(configured_memory_dir))
        _warn_for_legacy_pickle_artifacts(runtime_scan_roots)

        legacy_model_path = MODELS_DIR / "memory_model.pkl"
        if legacy_model_path.exists():
            _emit_legacy_pickle_runtime_blocked(
                path=legacy_model_path,
                artifact_name="model",
            )
        elif MEMORY_MODEL_PATH.exists():
            logger.info(
                "[MemoryModel] ONNX model detected at %s but runtime loader is not "
                "enabled in this module.",
                MEMORY_MODEL_PATH,
            )
        else:
            logger.info("[MemoryModel] model file not found: %s", MEMORY_MODEL_PATH)

        _runtime_guard_checked = True


def _get_mem_vec() -> Any:
    """Get MEM_VEC lazily to reduce import-time side effects."""
    global MEM_VEC

    _run_runtime_pickle_guard_once()
    with _mem_vec_lock:
        if MEM_VEC is not None:
            return MEM_VEC

        try:
            use_external = False
            if MEM_VEC_EXTERNAL is not None:
                ext_model = getattr(MEM_VEC_EXTERNAL, "model", None)
                if ext_model is not None:
                    use_external = True
                else:
                    logger.info(
                        "[VectorMemory] External MEM_VEC found "
                        f"({MEM_VEC_EXTERNAL.__class__.__name__}), "
                        "but model is None → ignore and use built-in VectorMemory"
                    )

            if use_external:
                MEM_VEC = MEM_VEC_EXTERNAL
                logger.info(
                    "[VectorMemory] Using external MEM_VEC implementation "
                    f"({MEM_VEC_EXTERNAL.__class__.__name__})"
                )
            else:
                MEM_VEC = VectorMemory(index_path=VECTOR_INDEX_PATH)
                logger.info(
                    "[VectorMemory] Using built-in VectorMemory implementation"
                )

        except (OSError, TypeError, ValueError, RuntimeError) as exc:
            logger.error("[VectorMemory] Initialization failed: %s", exc)
            MEM_VEC = None

        return MEM_VEC


# ============================
# Prediction helpers
# ============================


def predict_decision_status(query_text: str) -> str:
    """（暫定）クエリテキストから「決定ステータス」を推定するヘルパー。"""
    if MODEL is None:
        return "unknown"
    try:
        pred = MODEL.predict([query_text])[0]
        return str(pred)
    except Exception as e:
        logger.error("[MemoryModel] predict_decision_status error: %s", e)
        return "unknown"


def predict_gate_label(text: str) -> Dict[str, float]:
    """FUJI/ValueCore から使える gate 用ラッパー。"""
    prob_allow = 0.5

    clf = MEM_CLF
    if clf is not None:
        try:
            probs = clf.predict_proba([text])[0]
            classes = list(getattr(clf, "classes_", []))
            if "allow" in classes:
                idx = classes.index("allow")
                prob_allow = float(probs[idx])
            else:
                prob_allow = float(max(probs))
            return {"allow": prob_allow}
        except Exception as e:
            logger.error("[MemoryModel] MEM_CLF.predict_proba error: %s", e)

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
            logger.error("[MemoryModel] MODEL.predict_proba error: %s", e)

    return {"allow": prob_allow}


# ============================
# ストレージ設定
# ============================

MEM_PATH_ENV = os.getenv("VERITAS_MEMORY_PATH")
if MEM_PATH_ENV:
    MEM_PATH = Path(MEM_PATH_ENV).expanduser()
else:
    MEM_PATH = cfg.memory_path

DATA_DIR = MEM_PATH.parent
DATA_DIR.mkdir(parents=True, exist_ok=True)


# ============================
# File locking wrapper
# ============================
# Tests monkeypatch ``memory.IS_WIN`` / ``memory.fcntl`` to exercise the
# non-POSIX code path, so the lock wrapper reads from *this* module's globals.


@contextmanager
def locked_memory(path: Path, timeout: float = 5.0):
    """memory.json 用のシンプルな排他ロック。

    Thin wrapper around ``memory_storage.locked_memory`` that reads ``IS_WIN``
    and ``fcntl`` from *this* module's scope so that tests can monkeypatch
    them via ``memory.IS_WIN`` / ``memory.fcntl``.
    """
    if not IS_WIN and fcntl is not None:
        # POSIX path — delegate to storage implementation
        with _storage_locked_memory(path, timeout=timeout):
            yield
    else:
        # Non-POSIX / Windows fallback — must be self-contained so
        # monkeypatching ``memory.fcntl = None`` forces this branch.
        lockfile = path.with_suffix(path.suffix + ".lock")
        _STALE_LOCK_AGE_SECONDS = 300
        backoff = 0.01
        start = time.time()
        while True:
            try:
                fd = os.open(str(lockfile), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                break
            except FileExistsError:
                try:
                    lock_age = time.time() - os.path.getmtime(str(lockfile))
                    if lock_age > _STALE_LOCK_AGE_SECONDS:
                        logger.warning(
                            "[MemoryOS] Removing stale lockfile (age=%.0fs): %s",
                            lock_age, lockfile,
                        )
                        lockfile.unlink(missing_ok=True)
                        continue
                except OSError as e:
                    logger.debug(
                        "[MemoryOS] lockfile mtime check failed: %s (%s)",
                        lockfile, e,
                    )
                if time.time() - start > timeout:
                    raise TimeoutError(f"failed to acquire lock for {path}") from None
                time.sleep(backoff)
                backoff = min(backoff * 2.0, 0.32)
        try:
            yield
        finally:
            try:
                lockfile.unlink(missing_ok=True)
            except Exception as e:
                logger.error("[MemoryOS] lockfile cleanup failed: %s", e)


# ============================
# Store compat hooks (wired once at import time)
# ============================


def _compat_locked_memory(path: Path, timeout: float = 5.0) -> Any:
    """Route shared MemoryStore locking through memory.py for test compatibility."""
    return locked_memory(path, timeout=timeout)


install_memory_store_compat_hooks(
    locked_memory_fn=_compat_locked_memory,
    get_mem_vec_fn=_get_mem_vec,
    memory_module=sys.modules[__name__],
)


# ============================
# Evidence read for /v1/decide
# ============================


def _hits_to_evidence(
    hits: List[Dict[str, Any]],
    *,
    source_prefix: str = "memory",
) -> List[Dict[str, Any]]:
    """検索結果をEvidence形式に変換"""
    return _hits_to_evidence_impl(hits, source_prefix=source_prefix)


def get_evidence_for_decision(
    decision: Dict[str, Any],
    *,
    user_id: Optional[str] = None,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """決定のためのエビデンスを取得"""
    return _get_evidence_for_decision_impl(
        decision,
        search_fn=search,
        user_id=user_id,
        top_k=top_k,
    )


def get_evidence_for_query(
    query: str,
    *,
    user_id: Optional[str] = None,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """クエリのためのエビデンスを取得"""
    return _get_evidence_for_query_impl(
        query,
        search_fn=search,
        user_id=user_id,
        top_k=top_k,
    )


# ============================
# _LazyMemoryStore + MEM global
# ============================


class _LazyMemoryStore:
    """MemoryStore の遅延初期化プロキシ。

    import 時の重い I/O やモデルロードを避け、初回アクセス時にのみ
    MemoryStore を初期化する。
    """

    def __init__(self, loader: Callable[[], "MemoryStore"]) -> None:
        self._loader = loader
        self._lock = threading.Lock()
        self._obj: Optional[MemoryStore] = None
        self._attempted = False
        self._err: Optional[Exception] = None

    def _load(self) -> "MemoryStore":
        if self._obj is not None:
            return self._obj
        if self._attempted and self._err is not None:
            raise RuntimeError(f"MemoryStore load failed: {self._err}") from self._err
        with self._lock:
            if self._obj is not None:
                return self._obj
            if self._attempted and self._err is not None:
                raise RuntimeError(
                    f"MemoryStore load failed: {self._err}"
                ) from self._err
            self._attempted = True
            try:
                self._obj = self._loader()
                self._err = None
            except (OSError, ValueError, TypeError, RuntimeError) as exc:
                self._err = exc
                logger.error("[MemoryOS] lazy init failed: %s", exc)
                raise
        return self._obj

    def __getattr__(self, name: str) -> Any:
        obj = self._load()
        return getattr(obj, name)


def _load_memory_store() -> "MemoryStore":
    """MemoryStore を遅延初期化するためのローダー。"""
    store = MemoryStore.load(MEM_PATH)
    logger.info("[MemoryOS] initialized at %s", MEM_PATH)
    return store


# ==== グローバル MEM (遅延初期化) ====
MEM = _LazyMemoryStore(_load_memory_store)


# ============================
# 関数 API
# ============================


def add(
    *,
    user_id: str,
    text: str,
    kind: str = "note",
    source_label: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
    tags: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    MemoryOS に「1件のテキスト」を追加するためのユーティリティ。
    """
    if not text or not text.strip():
        raise ValueError("[MemoryOS.add] text is empty")

    entry_meta: Dict[str, Any] = dict(meta or {})
    entry_meta.setdefault("user_id", user_id)
    if source_label is not None:
        entry_meta.setdefault("source_label", source_label)

    record: Dict[str, Any] = {
        "kind": kind,
        "text": text,
        "tags": tags or [],
        "meta": entry_meta,
    }

    key = f"{kind}_{int(time.time())}_{uuid4().hex[:8]}"
    ok = MEM.put(user_id, key, record)
    if not ok:
        logger.error("[MemoryOS.add] MEM.put failed")

    _vec = _get_mem_vec()
    if _vec is not None:
        try:
            _vec.add(kind=kind, text=text, tags=tags or [], meta=entry_meta)
        except (AttributeError, TypeError, ValueError, RuntimeError) as e:
            logger.warning("[MemoryOS.add] MEM_VEC.add error: %s", e)

    return record


def put(*args, **kwargs) -> bool:
    """
    グローバル関数版 put

    呼び出しモード:
    1) KVS: put(user_id, key, value)
    2) ベクトル: put(kind, {"text": ..., "tags": [...], "meta": {...}})
    """
    if len(args) == 1 and "key" in kwargs:
        user_id = args[0]
        key = kwargs["key"]
        value = kwargs.get("value")
        return MEM.put(user_id, key, value)

    if len(args) == 2 and isinstance(args[1], dict):
        kind = str(args[0] or "semantic")
        doc = dict(args[1])
        text = (doc.get("text") or "").strip()
        tags = doc.get("tags") or []
        meta = doc.get("meta") or {}

        if not text and not doc:
            return False

        _vec = _get_mem_vec()
        if _vec is not None:
            try:
                base_text = text or json.dumps(doc, ensure_ascii=False)
                success = _vec.add(kind=kind, text=base_text, tags=tags, meta=meta)
                if success:
                    logger.debug("[MemoryOS] Added to vector index: %s", kind)
            except (AttributeError, TypeError, ValueError, RuntimeError) as e:
                logger.warning("[MemoryOS] MEM_VEC.add error (fallback to KVS): %s", e)

        user_id = meta.get("user_id", kind)
        key = f"{kind}_{int(time.time())}"
        return MEM.put(user_id, key, doc)

    if len(args) >= 3:
        user_id, key, value = args[0], args[1], args[2]
        return MEM.put(user_id, key, value)

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


def _dedup_hits(hits: List[Dict[str, Any]], k: int) -> List[Dict[str, Any]]:
    """ヒット結果を (text, user_id) 単位で去重しつつ k 件までに制限する。"""
    return _dedup_hits_impl(hits, k)


def search(
    query: str,
    k: int = 10,
    kinds: Optional[List[str]] = None,
    min_sim: float = 0.0,
    user_id: Optional[str] = None,
    **kwargs,
) -> List[Dict[str, Any]]:
    """
    グローバル関数版 search（改善版）

    優先順:
    1) MEM_VEC があればベクトル検索
    2) エラーまたは0件 → KVS simple search にフォールバック
    """
    _vec = _get_mem_vec()
    if _vec is not None:
        try:
            raw = _vec.search(query=query, k=k, kinds=kinds, min_sim=min_sim)
            candidates = collect_candidate_hits(raw)
            if candidates:
                filtered = filter_hits_for_user(candidates, user_id)
                if filtered:
                    candidates = filtered
                unique = _dedup_hits(candidates, k)
                logger.info(
                    "[MemoryOS] Vector search returned "
                    "%d unique hits (raw=%d)",
                    len(unique), len(candidates),
                )
                return unique

            logger.info(
                "[MemoryOS] MEM_VEC.search returned no hits; fallback to KVS"
            )

        except TypeError:
            try:
                raw = _vec.search(query, k=k)  # type: ignore[call-arg]
                if isinstance(raw, list) and raw:
                    hits = [h for h in raw if isinstance(h, dict)]
                    unique = _dedup_hits(hits, k)
                    logger.info(
                        "[MemoryOS] Vector search (old sig) returned "
                        "%d unique hits (raw=%d)",
                        len(unique), len(hits),
                    )
                    return unique
                logger.info(
                    "[MemoryOS] MEM_VEC.search(old sig) no hits; fallback to KVS"
                )
            except (AttributeError, TypeError, ValueError, RuntimeError) as e:
                logger.warning("[MemoryOS] MEM_VEC.search(old sig) error: %s", e)

        except (AttributeError, ValueError, RuntimeError) as e:
            logger.warning("[MemoryOS] MEM_VEC.search error: %s", e)

    res = MEM.search(
        query=query, k=k, kinds=kinds, min_sim=min_sim,
        user_id=user_id, **kwargs,
    )
    hits = normalize_store_hits(res)

    if not hits:
        return []

    unique = _dedup_hits(hits, k)
    logger.info(
        "[MemoryOS] KVS search returned "
        "%d unique hits (raw=%d)",
        len(unique), len(hits),
    )
    return unique


def summarize_for_planner(
    user_id: str,
    query: str,
    limit: int = 8,
) -> str:
    """Planner から直接呼べるラッパー"""
    return MEM.summarize_for_planner(user_id=user_id, query=query, limit=limit)


# ============================
# Memory Distill（episodic → semantic）
# ============================


def _build_distill_prompt(user_id: str, episodes: List[Dict[str, Any]]) -> str:
    """Backward-compatible wrapper for Memory Distill prompt assembly."""
    return _build_distill_prompt_impl(user_id, episodes)


def distill_memory_for_user(
    user_id: str,
    *,
    max_items: int = 200,
    min_text_len: int = 10,
    tags: Optional[List[str]] = None,
    model: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    指定ユーザーの episodic メモリをまとめて「長期記憶ノート（semantic）」に蒸留する。

    戻り値:
        保存した semantic メモリの dict（失敗時は None）
    """
    return _distill_impl(
        user_id,
        max_items=max_items,
        min_text_len=min_text_len,
        tags=tags,
        model=model,
        mem_store=MEM,
        llm_client_module=llm_client,
        put_fn=put,
    )


def rebuild_vector_index() -> None:
    """
    既存のmemory.jsonからベクトルインデックスを再構築
    """
    with _mem_vec_lock:
        _vec = MEM_VEC

    if _vec is None:
        logger.error("[MemoryOS] Cannot rebuild index: MEM_VEC is None")
        return

    if not hasattr(_vec, "rebuild_index"):
        logger.error(
            "[MemoryOS] Cannot rebuild index: MEM_VEC has no rebuild_index()"
        )
        return

    logger.info("[MemoryOS] Starting vector index rebuild...")

    all_data = MEM.list_all()
    documents = build_vector_rebuild_documents(all_data)

    logger.info("[MemoryOS] Found %d documents to index", len(documents))

    _vec.rebuild_index(documents)  # type: ignore[arg-type]

    logger.info("[MemoryOS] Vector index rebuild complete")
