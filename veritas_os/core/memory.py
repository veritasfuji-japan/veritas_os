# veritas_os/core/memory.py (改善版 + MemoryDistill)
"""
MemoryOS - 改善版

主な改善点:
1. 組み込みベクトル検索実装（sentence-transformers）
2. インデックス管理の改善
3. より詳細なログとデバッグ情報
4. フォールバック戦略の強化
5. Memory Distill（episodic → semantic 要約）の追加
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from datetime import datetime, timezone
from uuid import uuid4
import json
import os
import time
import threading
from contextlib import contextmanager
import logging
import base64

from .config import capability_cfg, emit_capability_manifest
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
    filter_recent_records,
    simple_score as _simple_score_impl,
)
from .memory_summary_helpers import build_planner_summary
from . import memory_store as _memory_store_module
from .memory_store import (
    ALLOWED_RETENTION_CLASSES,
    DEFAULT_RETENTION_CLASS,
    MemoryStore,
)

logger = logging.getLogger(__name__)

_ORIGINAL_ERASE_USER_DATA = erase_user_data
_ORIGINAL_FILTER_RECENT_RECORDS = filter_recent_records
_ORIGINAL_BUILD_KVS_SEARCH_HITS = build_kvs_search_hits


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
# ベクトル検索モジュール（組み込み）
# ============================


class VectorMemory:
    """
    組み込みベクトルメモリ実装

    sentence-transformers を使用してテキストの埋め込みを生成し、
    コサイン類似度で検索を行う。

    スレッドセーフ: 全ての読み書き操作は RLock で保護されています。
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        index_path: Optional[Path] = None,
        embedding_dim: int = 384,
    ):
        self.model_name = model_name
        self.index_path = index_path
        self.embedding_dim = embedding_dim
        self._lock = threading.RLock()
        self._id_counter = 0

        # データストア
        self.documents: List[Dict[str, Any]] = []
        self.embeddings: Optional[Any] = None  # numpy array

        # モデルのロード
        self.model = None
        self._load_model()

        # インデックスのロード
        if index_path and index_path.exists():
            self._load_index()

    def _load_model(self):
        """埋め込みモデルをスレッドセーフに一度だけロードする。"""
        if self.model is not None:
            return

        with self._lock:
            if self.model is not None:
                return

            if not capability_cfg.enable_memory_sentence_transformers:
                logger.info(
                    "[VectorMemory] sentence-transformers disabled by "
                    "VERITAS_CAP_MEMORY_SENTENCE_TRANSFORMERS"
                )
                return

            try:
                from sentence_transformers import SentenceTransformer

                self.model = SentenceTransformer(self.model_name)
                logger.info("[VectorMemory] Loaded model: %s", self.model_name)
            except ImportError as exc:
                if _is_explicitly_enabled(
                    "VERITAS_CAP_MEMORY_SENTENCE_TRANSFORMERS"
                ):
                    raise RuntimeError(
                        "sentence-transformers is required when "
                        "VERITAS_CAP_MEMORY_SENTENCE_TRANSFORMERS=1"
                    ) from exc
                logger.warning(
                    "[CONFIG_MISMATCH] sentence-transformers is unavailable while "
                    "the default capability is enabled; continuing with fallback "
                    "embedding mode. To enforce strict mode, set "
                    "VERITAS_CAP_MEMORY_SENTENCE_TRANSFORMERS=1 explicitly."
                )
                self.model = None
            except (OSError, RuntimeError, ValueError, TypeError) as e:
                logger.error("[VectorMemory] Failed to load model: %s", e)
                self.model = None

    def _load_index(self):
        """永続化されたインデックスをロード（JSON形式のみ）。"""
        if not self.index_path:
            return

        # JSON形式のパス（.json拡張子）
        json_path = self.index_path.with_suffix(".json")
        legacy_pkl_path = self.index_path

        try:
            import numpy as np

            # 1) まずJSON形式を試す
            if json_path.exists():
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                self.documents = data.get("documents", [])
                embeddings_data = data.get("embeddings")

                if embeddings_data is not None:
                    # Base64形式の場合
                    if isinstance(embeddings_data, str):
                        raw_bytes = base64.b64decode(embeddings_data)
                        dtype = data.get("embeddings_dtype", "float32")
                        shape = data.get("embeddings_shape")
                        self.embeddings = np.frombuffer(raw_bytes, dtype=dtype)
                        if shape:
                            self.embeddings = self.embeddings.reshape(shape)
                    # リスト形式の場合
                    elif isinstance(embeddings_data, list):
                        self.embeddings = np.array(embeddings_data, dtype=np.float32)
                    else:
                        self.embeddings = None

                logger.info(
                    f"[VectorMemory] Loaded JSON index: {len(self.documents)} documents"
                )
                return

            # 2) 旧pickle形式は runtime では読み込まない
            if legacy_pkl_path.exists() and legacy_pkl_path.suffix == ".pkl":
                _emit_legacy_pickle_runtime_blocked(
                    path=legacy_pkl_path,
                    artifact_name="vector index",
                )
                return

        except (OSError, ValueError, TypeError, json.JSONDecodeError) as e:
            logger.error("[VectorMemory] Failed to load index: %s", e)

    def _save_index(self):
        """インデックスをJSON形式で永続化（セキュリティ向上のためpickle廃止）"""
        if not self.index_path:
            return

        try:
            # JSON形式のパス（.json拡張子に統一）
            json_path = self.index_path.with_suffix(".json")
            json_path.parent.mkdir(parents=True, exist_ok=True)

            # embeddingsをBase64エンコード（コンパクト＋JSON互換）
            embeddings_b64 = None
            embeddings_shape = None
            embeddings_dtype = None

            if self.embeddings is not None:
                import numpy as np
                # numpy arrayの場合
                if hasattr(self.embeddings, "tobytes"):
                    embeddings_b64 = base64.b64encode(
                        self.embeddings.astype(np.float32).tobytes()
                    ).decode("ascii")
                    embeddings_shape = list(self.embeddings.shape)
                    embeddings_dtype = "float32"

            data = {
                "documents": self.documents,
                "embeddings": embeddings_b64,
                "embeddings_shape": embeddings_shape,
                "embeddings_dtype": embeddings_dtype,
                "model_name": self.model_name,
                "embedding_dim": self.embedding_dim,
                "format_version": "2.0",  # バージョン管理
            }

            # アトミック書き込み（途中で失敗しても元ファイルを壊さない）
            from veritas_os.core.atomic_io import atomic_write_json
            atomic_write_json(json_path, data)

            # index_pathも更新（次回保存時のため）
            self.index_path = json_path

            logger.info(
                "[VectorMemory] Saved JSON index: %d documents", len(self.documents)
            )
        except (OSError, TypeError, ValueError) as e:
            logger.error("[VectorMemory] Failed to save index: %s", e)

    def add(
        self,
        kind: str,
        text: str,
        tags: Optional[List[str]] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        ドキュメントを追加してインデックスを更新

        Args:
            kind: ドキュメント種別（"semantic", "episodic" など）
            text: テキスト内容
            tags: タグのリスト
            meta: メタデータ。``meta["lineage"]`` に辞書を渡すと
                  データリネージュ情報（EU AI Act Art. 10 / GAP-05）
                  がドキュメントに記録される。

        Returns:
            成功したかどうか
        """
        if not self.model:
            logger.warning("[VectorMemory] Model not loaded, cannot add document")
            return False

        if not text or not text.strip():
            return False

        # GAP-05 (Art. 10): Data quality validation at ingestion
        # Log quality issues for audit trail but do not block — memory
        # operations may involve short text and other acceptable edge cases.
        try:
            from veritas_os.core.eu_ai_act_compliance_module import validate_data_quality

            quality = validate_data_quality(text=text, kind=kind, meta=meta)
            if not quality["passed"]:
                logger.info(
                    "[VectorMemory] Data quality issue detected (Art. 10): %s",
                    quality["issues"],
                )
        except ImportError:
            pass

        try:
            import numpy as np

            # 埋め込み生成（ロック外で実行 - 計算コストが高い）
            embedding = self.model.encode([text])[0]

            with self._lock:
                # ドキュメント追加
                self._id_counter += 1
                doc = {
                    "id": f"{kind}_{self._id_counter}_{int(time.time())}",
                    "kind": kind,
                    "text": text,
                    "tags": tags or [],
                    "meta": meta or {},
                    "ts": time.time(),
                }

                # GAP-05 (Art. 10): Data lineage tracking
                lineage = (meta or {}).get("lineage")
                if isinstance(lineage, dict):
                    doc["lineage"] = lineage
                else:
                    doc["lineage"] = {
                        "source": "internal",
                        "document_type": kind,
                        "ingested_at": datetime.now(timezone.utc).isoformat(),
                    }

                self.documents.append(doc)

                # 埋め込み配列を更新
                if self.embeddings is None:
                    self.embeddings = embedding.reshape(1, -1)
                else:
                    self.embeddings = np.vstack([self.embeddings, embedding])

                # 定期的に保存（100件ごと）
                if len(self.documents) % 100 == 0 and self.index_path:
                    self._save_index()

            logger.debug("[VectorMemory] Added document: %s", doc["id"])
            return True

        except Exception as e:
            logger.error("[VectorMemory] Failed to add document: %s", e)
            return False

    def search(
        self,
        query: str,
        k: int = 10,
        kinds: Optional[List[str]] = None,
        min_sim: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """
        ベクトル検索を実行

        Args:
            query: 検索クエリ
            k: 返す最大件数
            kinds: フィルタするドキュメント種別
            min_sim: 最小類似度閾値（0.0-1.0）

        Returns:
            検索結果のリスト（スコア降順）
        """
        if not self.model:
            logger.debug("[VectorMemory] Model not loaded")
            return []

        if not query or not query.strip():
            return []

        if not self.documents or self.embeddings is None:
            logger.debug("[VectorMemory] No documents in index")
            return []

        try:
            # クエリの埋め込み生成（ロック外で実行 - 計算コストが高い）
            query_embedding = self.model.encode([query])[0]

            with self._lock:
                if not self.documents or self.embeddings is None:
                    return []

                # スナップショットを取得
                docs_snapshot = list(self.documents)
                import numpy as np
                embeddings_snapshot = np.array(self.embeddings, copy=True)

            # ロック外で計算
            # コサイン類似度計算
            similarities = self._cosine_similarity(query_embedding, embeddings_snapshot)

            # 結果を構築
            results: List[Dict[str, Any]] = []
            for idx, sim in enumerate(similarities):
                if sim < min_sim:
                    continue

                if idx >= len(docs_snapshot):
                    continue

                doc = docs_snapshot[idx]

                # kinds フィルタリング
                if kinds and doc.get("kind") not in kinds:
                    continue

                results.append(
                    {
                        "id": doc["id"],
                        "text": doc["text"],
                        "score": float(sim),
                        "kind": doc["kind"],
                        "tags": doc.get("tags", []),
                        "meta": doc.get("meta", {}),
                        "ts": doc.get("ts"),
                    }
                )

            # スコア降順でソート
            results.sort(key=lambda x: x["score"], reverse=True)

            # 上位k件を返す
            top_results = results[:k]

            logger.info(
                f"[VectorMemory] Search '{query[:50]}...' "
                f"found {len(top_results)}/{len(results)} hits"
            )

            return top_results

        except Exception as e:
            logger.error("[VectorMemory] Search failed: %s", e)
            return []

    @staticmethod
    def _cosine_similarity(vec: Any, matrix: Any) -> Any:
        """コサイン類似度を計算"""
        try:
            import numpy as np

            # ベクトルを正規化
            vec_norm = vec / (np.linalg.norm(vec) + 1e-10)
            matrix_norm = matrix / (
                np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-10
            )

            # 内積 = コサイン類似度
            similarities = np.dot(matrix_norm, vec_norm)

            return similarities

        except Exception as e:
            logger.error("[VectorMemory] Cosine similarity calculation failed: %s", e)
            import numpy as np

            return np.zeros(len(matrix))

    def rebuild_index(self, documents: List[Dict[str, Any]]) -> None:
        """
        既存のドキュメントリストからインデックスを再構築

        Args:
            documents: ドキュメントのリスト
        """
        if not self.model:
            logger.warning("[VectorMemory] Model not loaded, cannot rebuild index")
            return

        logger.info(
            f"[VectorMemory] Rebuilding index for {len(documents)} documents..."
        )

        with self._lock:
            self.documents = []
            self.embeddings = None

        for doc in documents:
            text = doc.get("text", "")
            if not text:
                continue

            self.add(
                kind=doc.get("kind", "semantic"),
                text=text,
                tags=doc.get("tags"),
                meta=doc.get("meta"),
            )

        self._save_index()
        logger.info(
            f"[VectorMemory] Index rebuilt: {len(self.documents)} documents indexed"
        )


# ============================
# 旧コードとの互換性レイヤー
# ============================

# 外部モジュールからの読み込み試行（後方互換性）
memory_model_core = None
try:
    # 通常インストール時
    from veritas_os.core.models import memory_model as memory_model_core  # type: ignore
except (ImportError, ModuleNotFoundError):
    try:
        # パッケージとしてでなくローカルから叩く場合の保険
        from .models import memory_model as memory_model_core  # type: ignore
    except (ImportError, ModuleNotFoundError):
        memory_model_core = None

if memory_model_core is not None:
    MEM_VEC_EXTERNAL = getattr(memory_model_core, "MEM_VEC", None)
    MEM_CLF = getattr(memory_model_core, "MEM_CLF", None)
else:
    MEM_VEC_EXTERNAL = None
    MEM_CLF = None

# SimpleMemVec のようなダミー実装は無視して VectorMemory を優先する
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

# VectorMemory インスタンスの初期化
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


def predict_decision_status(query_text: str) -> str:
    """
    （暫定）クエリテキストから「決定ステータス」を推定するヘルパー。
    """
    if MODEL is None:
        return "unknown"
    try:
        pred = MODEL.predict([query_text])[0]
        return str(pred)
    except Exception as e:
        logger.error("[MemoryModel] predict_decision_status error: %s", e)
        return "unknown"


def predict_gate_label(text: str) -> Dict[str, float]:
    """
    FUJI/ValueCore から使える gate 用ラッパー。
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
                prob_allow = float(max(probs))
            return {"allow": prob_allow}
        except Exception as e:
            logger.error("[MemoryModel] MEM_CLF.predict_proba error: %s", e)

    # 2) MODEL (runtime optional model) に predict_proba があれば使う
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

from .config import cfg
from . import llm_client

MEM_PATH_ENV = os.getenv("VERITAS_MEMORY_PATH")
if MEM_PATH_ENV:
    MEM_PATH = Path(MEM_PATH_ENV).expanduser()
else:
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
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)  # type: ignore
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
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)  # type: ignore
            except Exception as e:
                logger.error("[MemoryOS] unlock failed: %s", e)
            fh.close()
    else:
        # Windows or 非POSIX: .lock ファイルで排他
        lockfile = path.with_suffix(path.suffix + ".lock")
        _STALE_LOCK_AGE_SECONDS = 300  # 5 minutes
        backoff = 0.01
        while True:
            try:
                fd = os.open(str(lockfile), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                break
            except FileExistsError:
                # Stale lock detection: remove lockfile older than threshold
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
                        lockfile,
                        e,
                    )
                if time.time() - start > timeout:
                    raise TimeoutError(f"failed to acquire lock for {path}")
                time.sleep(backoff)
                backoff = min(backoff * 2.0, 0.32)
        try:
            yield
        finally:
            try:
                # Use missing_ok=True to avoid TOCTOU race condition
                # (file could be deleted between exists() check and unlink())
                lockfile.unlink(missing_ok=True)
            except Exception as e:
                logger.error("[MemoryOS] lockfile cleanup failed: %s", e)






def _compat_locked_memory(path: Path, timeout: float = 5.0) -> Any:
    """Route shared MemoryStore locking through memory.py for test compatibility."""
    return locked_memory(path, timeout=timeout)


def _install_memory_store_compat_hooks() -> None:
    """Keep shared MemoryStore behavior patchable via memory.py symbols."""

    def _parse_expires_at_compat(expires_at: Any) -> Optional[str]:
        return parse_expires_at(expires_at)

    def _normalize_lifecycle_compat(value: Any) -> Any:
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

    def _is_record_expired_compat(
        record: Dict[str, Any],
        now_ts: Optional[float] = None,
    ) -> bool:
        value = record.get("value") or {}
        if not isinstance(value, dict):
            return False

        meta = value.get("meta") or {}
        if not isinstance(meta, dict):
            return False

        raw_hold = meta.get("legal_hold", False)
        if isinstance(raw_hold, str):
            hold = raw_hold.strip().lower() in ("true", "1", "yes")
        else:
            hold = bool(raw_hold)
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

    def _erase_user_compat(
        self: MemoryStore,
        user_id: str,
        reason: str,
        actor: str,
    ) -> Dict[str, Any]:
        helper = _memory_store_module.erase_user_data
        if helper is _ORIGINAL_ERASE_USER_DATA:
            helper = erase_user_data
        data = self._load_all(copy=True, use_cache=False)
        kept_records, report = helper(
            data=data,
            user_id=user_id,
            reason=reason,
            actor=actor,
        )
        saved = self._save_all(kept_records)
        report["ok"] = bool(saved)
        return report

    def _is_record_legal_hold_compat(record: Dict[str, Any]) -> bool:
        return is_record_legal_hold(record)

    def _should_cascade_delete_semantic_compat(
        record: Dict[str, Any],
        user_id: str,
        erased_keys: set[str],
    ) -> bool:
        return should_cascade_delete_semantic(
            record=record,
            user_id=user_id,
            erased_keys=erased_keys,
        )

    def _recent_compat(
        self: MemoryStore,
        user_id: str,
        limit: int = 20,
        contains: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        helper = _memory_store_module.filter_recent_records
        if helper is _ORIGINAL_FILTER_RECENT_RECORDS:
            helper = filter_recent_records
        return helper(
            self.list_all(user_id),
            contains=contains,
            limit=limit,
        )

    def _simple_score_compat(self: MemoryStore, query: str, text: str) -> float:
        return _simple_score_impl(query, text)

    def _search_compat(
        self: MemoryStore,
        query: str,
        k: int = 10,
        kinds: Optional[List[str]] = None,
        min_sim: float = 0.0,
        user_id: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, List[Dict[str, Any]]]:
        helper = _memory_store_module.build_kvs_search_hits
        if helper is _ORIGINAL_BUILD_KVS_SEARCH_HITS:
            helper = build_kvs_search_hits
        episodic = helper(
            self._load_all(copy=True),
            query=query,
            k=k,
            kinds=kinds,
            min_sim=min_sim,
            user_id=user_id,
        )
        if not episodic:
            return {}
        logger.debug("[MemoryOS][KVS] episodic hits=%d", len(episodic))
        return {"episodic": episodic}

    def _put_episode_compat(
        self: MemoryStore,
        text: str,
        tags: Optional[List[str]] = None,
        meta: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> str:
        record: Dict[str, Any] = {
            "text": text,
            "tags": tags or [],
            "meta": meta or {},
        }
        for key, value in kwargs.items():
            if key not in record:
                record[key] = value
        user_id = (record.get("meta") or {}).get("user_id", "episodic")
        key = f"episode_{int(time.time())}"
        self.put(user_id, key, record)
        mem_vec = _get_mem_vec()
        if mem_vec is not None:
            try:
                mem_vec.add(
                    kind="episodic",
                    text=text,
                    tags=tags or [],
                    meta=meta or {},
                )
            except Exception as exc:
                logger.warning("[MemoryOS] put_episode MEM_VEC.add error: %s", exc)
        return key

    def _summarize_for_planner_compat(
        self: MemoryStore,
        user_id: str,
        query: str,
        limit: int = 8,
    ) -> str:
        result = self.search(query=query, k=limit, user_id=user_id)
        episodic = result.get("episodic") or []
        return build_planner_summary(episodic)

    _memory_store_module.locked_memory = _compat_locked_memory
    _memory_store_module.erase_user_data = erase_user_data
    _memory_store_module.filter_recent_records = filter_recent_records
    _memory_store_module.build_kvs_search_hits = build_kvs_search_hits
    MemoryStore._parse_expires_at = staticmethod(_parse_expires_at_compat)
    MemoryStore._normalize_lifecycle = staticmethod(_normalize_lifecycle_compat)
    MemoryStore._is_record_expired = staticmethod(_is_record_expired_compat)
    MemoryStore.erase_user = _erase_user_compat
    MemoryStore._is_record_legal_hold = staticmethod(_is_record_legal_hold_compat)
    MemoryStore._should_cascade_delete_semantic = staticmethod(
        _should_cascade_delete_semantic_compat
    )
    MemoryStore.recent = _recent_compat
    MemoryStore._simple_score = _simple_score_compat
    MemoryStore.search = _search_compat
    MemoryStore.put_episode = _put_episode_compat
    MemoryStore.summarize_for_planner = _summarize_for_planner_compat


_install_memory_store_compat_hooks()


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

# ★ 修正: builtins.MEM への代入を削除。
# 他モジュールは from veritas_os.core.memory import MEM で明示的にインポートしてください。


# ============================
# 関数 API（改善版）
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

    例: import_pdf_to_memory.py からの呼び出しを想定

        memory.add(
            user_id="fujishita",
            text="PDFから切り出したチャンク",
            kind="doc",
            source_label="VERITAS_Zenodo_JP",
            meta={"page": 3},
        )
    """
    if not text or not text.strip():
        raise ValueError("[MemoryOS.add] text is empty")

    entry_meta: Dict[str, Any] = dict(meta or {})
    # user_id / source_label も meta に刻んでおく
    entry_meta.setdefault("user_id", user_id)
    if source_label is not None:
        entry_meta.setdefault("source_label", source_label)

    record: Dict[str, Any] = {
        "kind": kind,
        "text": text,
        "tags": tags or [],
        "meta": entry_meta,
    }

    # ---- 1) KVS に保存 ----
    key = f"{kind}_{int(time.time())}_{uuid4().hex[:8]}"
    ok = MEM.put(user_id, key, record)
    if not ok:
        logger.error("[MemoryOS.add] MEM.put failed")

    # ---- 2) ベクトルインデックスにも追加（失敗しても致命的ではない） ----
    # ★ 修正 (H-10): ローカル変数スナップショットで TOCTOU を防止
    _vec = _get_mem_vec()
    if _vec is not None:
        try:
            _vec.add(
                kind=kind,
                text=text,
                tags=tags or [],
                meta=entry_meta,
            )
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
    # user_id + key/value kwargs
    if len(args) == 1 and "key" in kwargs:
        user_id = args[0]
        key = kwargs["key"]
        value = kwargs.get("value")
        return MEM.put(user_id, key, value)

    # kind + dict (ベクトルモード)
    if len(args) == 2 and isinstance(args[1], dict):
        kind = str(args[0] or "semantic")
        doc = dict(args[1])
        text = (doc.get("text") or "").strip()
        tags = doc.get("tags") or []
        meta = doc.get("meta") or {}

        if not text and not doc:
            return False

        # ベクトルインデックスに追加
        # ★ 修正 (H-10): ローカル変数スナップショットで TOCTOU を防止
        _vec = _get_mem_vec()
        if _vec is not None:
            try:
                base_text = text or json.dumps(doc, ensure_ascii=False)
                success = _vec.add(kind=kind, text=base_text, tags=tags, meta=meta)
                if success:
                    logger.debug("[MemoryOS] Added to vector index: %s", kind)
            except (AttributeError, TypeError, ValueError, RuntimeError) as e:
                logger.warning("[MemoryOS] MEM_VEC.add error (fallback to KVS): %s", e)

        # KVSにも保存
        user_id = meta.get("user_id", kind)
        key = f"{kind}_{int(time.time())}"
        return MEM.put(user_id, key, doc)

    # 完全位置引数 (KVSモード)
    if len(args) >= 3:
        user_id, key, value = args[0], args[1], args[2]
        return MEM.put(user_id, key, value)

    # kwargs 指定
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
    """
    ヒット結果を (text, user_id) 単位で去重しつつ k 件までに制限する。
    順序は元のリストの順を維持する。
    """
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

    戻り値: list[dict]
    """

    # ===========================
    # 1) ベクトル検索（優先）
    # ===========================
    # ★ 修正 (H-10): ローカル変数スナップショットで TOCTOU を防止
    _vec = _get_mem_vec()
    if _vec is not None:
        try:
            raw = _vec.search(
                query=query,
                k=k,
                kinds=kinds,
                min_sim=min_sim,
            )
            candidates = collect_candidate_hits(raw)
            if candidates:
                filtered = filter_hits_for_user(candidates, user_id)
                if filtered:
                    candidates = filtered
                unique = _dedup_hits(candidates, k)
                logger.info(
                    f"[MemoryOS] Vector search returned "
                    f"{len(unique)} unique hits (raw={len(candidates)})"
                )
                return unique

            logger.info(
                "[MemoryOS] MEM_VEC.search returned no hits; fallback to KVS"
            )

        except TypeError:
            # 旧シグネチャへのフォールバック
            try:
                raw = _vec.search(query, k=k)  # type: ignore[call-arg]
                if isinstance(raw, list) and raw:
                    hits = [h for h in raw if isinstance(h, dict)]
                    unique = _dedup_hits(hits, k)
                    logger.info(
                        f"[MemoryOS] Vector search (old sig) returned "
                        f"{len(unique)} unique hits (raw={len(hits)})"
                    )
                    return unique
                logger.info(
                    "[MemoryOS] MEM_VEC.search(old sig) no hits; fallback to KVS"
                )
            except (AttributeError, TypeError, ValueError, RuntimeError) as e:
                logger.warning("[MemoryOS] MEM_VEC.search(old sig) error: %s", e)

        except (AttributeError, ValueError, RuntimeError) as e:
            logger.warning("[MemoryOS] MEM_VEC.search error: %s", e)

    # ===========================
    # 2) フォールバック: KVS simple search
    # ===========================
    res = MEM.search(
        query=query,
        k=k,
        kinds=kinds,
        min_sim=min_sim,
        user_id=user_id,
        **kwargs,
    )
    hits = normalize_store_hits(res)

    if not hits:
        return []

    unique = _dedup_hits(hits, k)
    logger.info(
        f"[MemoryOS] KVS search returned "
        f"{len(unique)} unique hits (raw={len(hits)})"
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
    # 1) memory.json から対象ユーザーのレコードを取得
    try:
        all_records = MEM.list_all(user_id=user_id)
    except (OSError, RuntimeError, ValueError, TypeError) as e:
        logger.error("[MemoryDistill] list_all failed for user=%s: %s", user_id, e)
        return None

    episodic = collect_episodic_records(
        all_records,
        min_text_len=min_text_len,
        tags=tags,
    )

    if not episodic:
        logger.info("[MemoryDistill] no episodic records for user=%s", user_id)
        return None

    target_eps = episodic[:max_items]

    # 2) プロンプト生成
    prompt = _build_distill_prompt(user_id, target_eps)
    system_msg = "You are VERITAS Memory Distill module."

    # 3) LLM コール（唯一の境界: llm_client.chat_completion）
    try:
        chat_fn = getattr(llm_client, "chat_completion", None)
        if not callable(chat_fn):
            logger.error("[MemoryDistill] llm_client.chat_completion not available")
            return None
        kwargs: Dict[str, Any] = {"max_tokens": 1024}
        if model:
            kwargs["model"] = model

        resp = chat_fn(
            system_prompt=system_msg,
            user_prompt=prompt,
            **kwargs,
        )

    except TypeError as e:
        logger.error("[MemoryDistill] LLM call TypeError: %s", e)
        return None
    except (RuntimeError, ValueError, OSError) as e:
        logger.error("[MemoryDistill] LLM call failed: %s", e)
        return None

    # 4) レスポンスからテキストを取り出す
    summary_text = extract_summary_text(resp)
    if not summary_text:
        logger.error("[MemoryDistill] empty summary_text from LLM")
        return None

    # 5) semantic メモリとして永続化
    doc = build_semantic_memory_doc(
        user_id=user_id,
        summary_text=summary_text,
        episodes=target_eps,
        tags=tags,
    )

    ok = put("semantic", doc)
    if not ok:
        logger.error("[MemoryDistill] failed to save semantic memory")
        return None

    logger.info(
        f"[MemoryDistill] semantic note saved for user={user_id} "
        f"(items={len(target_eps)}, chars={len(summary_text)})"
    )
    return doc


def rebuild_vector_index() -> None:
    """
    既存のmemory.jsonからベクトルインデックスを再構築

    使用例:
        from veritas_os.core import memory
        memory.rebuild_vector_index()
    """
    # NOTE:
    #   rebuild は明示運用コマンドのため、MEM_VEC が未初期化(None)なら
    #   ここでは暗黙初期化せずに即 return する。
    #   これにより「MEM_VEC が None のときは何もしない」という既存契約を維持する。
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

    # memory.jsonから全データを読み込み
    all_data = MEM.list_all()

    # ベクトル化可能なドキュメントを抽出
    documents = build_vector_rebuild_documents(all_data)

    logger.info("[MemoryOS] Found %d documents to index", len(documents))

    # インデックス再構築
    _vec.rebuild_index(documents)  # type: ignore[arg-type]

    logger.info("[MemoryOS] Vector index rebuild complete")
