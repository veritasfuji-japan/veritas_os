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

logger = logging.getLogger(__name__)

# OS 判定
IS_WIN = os.name == "nt"

if not IS_WIN:
    try:
        import fcntl  # type: ignore
    except ImportError:
        fcntl = None  # type: ignore
else:
    fcntl = None  # type: ignore

# joblib
try:
    from joblib import load as joblib_load
except ImportError:
    joblib_load = None


def _allow_legacy_pickle_migration() -> bool:
    """
    レガシーpickle移行を許可するか判定する。

    ★ 重要: Pickle は本質的に安全ではありません。
    この機能は廃止予定です。新しいデータは JSON 形式で保存されます。
    """
    value = os.getenv("VERITAS_MEMORY_ALLOW_PICKLE_MIGRATION", "").strip().lower()
    if value in {"1", "true", "yes", "y", "on"}:
        logger.warning(
            "[SECURITY] Legacy pickle migration is enabled. "
            "This feature is DEPRECATED and will be removed in a future version. "
            "Please ensure all data is migrated to JSON format."
        )
        return True
    return False


def _should_delete_pickle_after_migration() -> bool:
    """
    ★ セキュリティ修正: 移行後にpickleファイルを削除するか判定する。
    デフォルトは削除（セキュリティ向上）。VERITAS_MEMORY_KEEP_PICKLE_BACKUP=1で保持。
    """
    value = os.getenv("VERITAS_MEMORY_KEEP_PICKLE_BACKUP", "").strip().lower()
    return value not in {"1", "true", "yes", "y", "on"}


def _is_pickle_file_stale(path: Path, max_age_days: int = 90) -> bool:
    """
    ★ セキュリティ修正: pickleファイルが古すぎないか確認する。
    古すぎるpickleファイルは移行を拒否し、手動対応を要求する。

    max_age_days を 365 → 90 日に短縮（セキュリティ強化）
    """
    try:
        mtime = path.stat().st_mtime
        age_days = (time.time() - mtime) / (60 * 60 * 24)
        return age_days > max_age_days
    except OSError as exc:
        logger.warning("Cannot stat pickle file %s: %s", path, exc)
        return True  # エラー時は古いとみなす（安全側に倒す）


def _validate_pickle_data_structure(data: Any) -> bool:
    """
    ★ セキュリティ修正: デシリアライズ後のデータ構造を検証する。

    期待される構造:
    - dict であること
    - "documents" キーが存在し、list であること
    - "embeddings" キーが存在し、None または numpy array であること

    Returns:
        True: 構造が正しい、False: 不正な構造
    """
    if not isinstance(data, dict):
        return False

    # documents の検証
    documents = data.get("documents")
    if documents is not None and not isinstance(documents, list):
        return False

    # documents の各要素が dict であることを確認
    if documents:
        for doc in documents[:100]:  # 最初の100件のみチェック（パフォーマンス）
            if not isinstance(doc, dict):
                return False

    # embeddings の検証（numpy array または None）
    embeddings = data.get("embeddings")
    if embeddings is not None:
        try:
            import numpy as np
            if not isinstance(embeddings, np.ndarray):
                return False
            # 次元数の検証（1D または 2D のみ許可）
            if embeddings.ndim not in (1, 2):
                return False
            # サイズの検証（異常に大きい場合は拒否）
            if embeddings.size > 100_000_000:  # 100M 要素まで
                return False
        except Exception:
            return False

    return True


class RestrictedUnpickler:
    """
    安全なPickle読み込み用の制限付きUnpickler。

    ★★★ 重要: このクラスは廃止予定です ★★★

    Pickle は本質的に安全ではなく、制限付きでも攻撃のリスクがあります。
    新しいコードでは JSON 形式を使用してください。

    許可された型のみデシリアライズし、任意コード実行を防止しますが、
    完全な安全性は保証されません。
    """

    # ★ セキュリティ強化: _reconstruct を許可リストから削除
    # _reconstruct は任意のバイト列から配列を再構築するため、悪用の可能性がある
    # 代わりに、ndarray と dtype のみを許可し、データは JSON 形式で保持する
    ALLOWED_NUMPY_TYPES = frozenset({
        # numpy の安全な型のみ（_reconstruct は除外）
        "numpy.ndarray",
        "numpy.dtype",
    })

    # 許可する基本型（必要最小限に制限）
    ALLOWED_BUILTINS = frozenset({
        "dict",
        "list",
        "tuple",
        "str",
        "int",
        "float",
        "bool",
        "bytes",
        # set, frozenset, type は除外（通常不要）
    })

    _DEPRECATION_WARNED = False

    @classmethod
    def _find_class(cls, module: str, name: str):
        """許可されたクラスのみを読み込む。"""
        import pickle
        import builtins

        full_name = f"{module}.{name}"

        # ★ セキュリティ強化: _reconstruct / scalar は任意コード実行のリスクがあるため拒否
        if "_reconstruct" in name or "scalar" in name:
            logger.warning(
                f"[SECURITY] Pickle contains blocked numpy type: {full_name}. "
                "Please migrate to JSON format."
            )
            raise pickle.UnpicklingError(
                f"Restricted unpickler: {full_name} is blocked for security"
            )

        # numpy型（安全なもののみ）
        if full_name in cls.ALLOWED_NUMPY_TYPES:
            import numpy as np
            if hasattr(np, name):
                return getattr(np, name)
            raise pickle.UnpicklingError(
                f"Restricted unpickler: numpy type {name} not found"
            )

        # builtins
        if module == "builtins" and name in cls.ALLOWED_BUILTINS:
            return getattr(builtins, name)

        raise pickle.UnpicklingError(
            f"Restricted unpickler: {full_name} is not allowed"
        )

    @classmethod
    def loads(cls, data: bytes) -> Any:
        """
        制限付きでPickleデータを読み込む。

        ★ 廃止予定: この関数は将来のバージョンで削除されます。
        新しいコードでは JSON 形式を使用してください。
        """
        import pickle
        import io

        # 廃止警告（1回のみ）
        if not cls._DEPRECATION_WARNED:
            cls._DEPRECATION_WARNED = True
            logger.warning(
                "[SECURITY] RestrictedUnpickler.loads() is DEPRECATED. "
                "Pickle deserialization poses security risks. "
                "Please migrate to JSON format."
            )

        class _Unpickler(pickle.Unpickler):
            find_class = staticmethod(cls._find_class)

        result = _Unpickler(io.BytesIO(data)).load()

        # ★ セキュリティ修正: デシリアライズ後のデータ構造を検証
        if not _validate_pickle_data_structure(result):
            raise pickle.UnpicklingError(
                "Restricted unpickler: Invalid data structure after deserialization"
            )

        return result


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
        """埋め込みモデルをロード"""
        try:
            from sentence_transformers import SentenceTransformer

            self.model = SentenceTransformer(self.model_name)
            logger.info(f"[VectorMemory] Loaded model: {self.model_name}")
        except ImportError:
            logger.warning(
                "[VectorMemory] sentence-transformers not available. "
                "Install with: pip install sentence-transformers"
            )
            self.model = None
        except Exception as e:
            logger.error(f"[VectorMemory] Failed to load model: {e}")
            self.model = None

    def _load_index(self):
        """永続化されたインデックスをロード（JSON形式、旧pickle形式からの移行は明示的許可時のみ）"""
        if not self.index_path:
            return

        # JSON形式のパス（.json拡張子）
        json_path = self.index_path.with_suffix(".json")
        legacy_pkl_path = self.index_path  # 旧pickle形式

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

            # 2) 旧pickle形式からのマイグレーション
            if legacy_pkl_path.exists() and legacy_pkl_path.suffix == ".pkl":
                if not _allow_legacy_pickle_migration():
                    logger.warning(
                        "[VectorMemory] Legacy pickle migration disabled. "
                        "Set VERITAS_MEMORY_ALLOW_PICKLE_MIGRATION=1 to enable."
                    )
                    return

                # ★ セキュリティ修正: 古すぎるpickleファイルは移行を拒否
                if _is_pickle_file_stale(legacy_pkl_path):
                    logger.error(
                        "[VectorMemory] Legacy pickle file is too old (>90 days). "
                        "Manual migration required for security reasons. "
                        "Please delete the pickle file or contact support."
                    )
                    return

                logger.info("[VectorMemory] Migrating from legacy pickle format...")
                try:
                    # セキュリティ: RestrictedUnpickler を使用して安全にデシリアライズ
                    with open(legacy_pkl_path, "rb") as f:
                        raw_data = f.read()
                    data = RestrictedUnpickler.loads(raw_data)

                    self.documents = data.get("documents", [])
                    self.embeddings = data.get("embeddings")

                    logger.info(
                        f"[VectorMemory] Loaded legacy pickle: {len(self.documents)} documents"
                    )

                    # 新形式で保存（マイグレーション）
                    self.index_path = json_path  # 新しいパスに更新
                    self._save_index()

                    # ★ セキュリティ修正: 移行後は旧pickleファイルを削除（デフォルト）
                    if _should_delete_pickle_after_migration():
                        try:
                            legacy_pkl_path.unlink()
                            logger.info(
                                f"[VectorMemory] Deleted legacy pickle file: {legacy_pkl_path}"
                            )
                        except Exception as del_e:
                            logger.warning(
                                f"[VectorMemory] Failed to delete pickle file: {del_e}. "
                                "Please manually remove for security."
                            )
                    else:
                        # バックアップとしてリネーム（VERITAS_MEMORY_KEEP_PICKLE_BACKUP=1の場合のみ）
                        backup_path = legacy_pkl_path.with_suffix(".pkl.bak")
                        legacy_pkl_path.rename(backup_path)
                        logger.info(
                            f"[VectorMemory] Migrated to JSON. Backup: {backup_path}"
                        )
                    return
                except Exception as e:
                    logger.warning(f"[VectorMemory] Pickle migration failed: {e}")

        except Exception as e:
            logger.error(f"[VectorMemory] Failed to load index: {e}")

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
                f"[VectorMemory] Saved JSON index: {len(self.documents)} documents"
            )
        except Exception as e:
            logger.error(f"[VectorMemory] Failed to save index: {e}")

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
            meta: メタデータ

        Returns:
            成功したかどうか
        """
        if not self.model:
            logger.warning("[VectorMemory] Model not loaded, cannot add document")
            return False

        if not text or not text.strip():
            return False

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
                self.documents.append(doc)

                # 埋め込み配列を更新
                if self.embeddings is None:
                    self.embeddings = embedding.reshape(1, -1)
                else:
                    self.embeddings = np.vstack([self.embeddings, embedding])

                # 定期的に保存（100件ごと）
                if len(self.documents) % 100 == 0 and self.index_path:
                    self._save_index()

            logger.debug(f"[VectorMemory] Added document: {doc['id']}")
            return True

        except Exception as e:
            logger.error(f"[VectorMemory] Failed to add document: {e}")
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
            logger.error(f"[VectorMemory] Search failed: {e}")
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
            logger.error(f"[VectorMemory] Cosine similarity calculation failed: {e}")
            import numpy as np

            return np.zeros(len(matrix))

    def rebuild_index(self, documents: List[Dict[str, Any]]):
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
except Exception:
    try:
        # パッケージとしてでなくローカルから叩く場合の保険
        from .models import memory_model as memory_model_core  # type: ignore
    except Exception:
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

# モデル関連（旧: memory_model.pkl）
REPO_ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = REPO_ROOT / "core" / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

MEMORY_MODEL_PATH = MODELS_DIR / "memory_model.pkl"
VECTOR_INDEX_PATH = MODELS_DIR / "vector_index.pkl"

logger.info(f"[MemoryModel] module loaded from: {__file__}")

# memory_model.pkl のロード（分類器用）
if joblib_load and MEMORY_MODEL_PATH.exists():
    try:
        MODEL = joblib_load(MEMORY_MODEL_PATH)
        logger.info(f"[MemoryModel] loaded: {MEMORY_MODEL_PATH}")
    except Exception as e:
        MODEL = None
        logger.warning(f"[MemoryModel] load skipped: {e}")
else:
    MODEL = None
    logger.info(
        "[MemoryModel] load skipped: model file missing or joblib not available"
    )

# VectorMemory インスタンスの初期化
# ★ 修正 (H-10): MEM_VEC へのアクセスをスレッドセーフにするためのロック
_mem_vec_lock = threading.Lock()
MEM_VEC = None
try:
    # 外部 MEM_VEC を使うかどうかの判定
    use_external = False
    if MEM_VEC_EXTERNAL is not None:
        ext_model = getattr(MEM_VEC_EXTERNAL, "model", None)

        # 「ちゃんと埋め込みモデルが載っている」場合だけ採用
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
        # デフォルトは組み込み VectorMemory
        MEM_VEC = VectorMemory(index_path=VECTOR_INDEX_PATH)
        logger.info("[VectorMemory] Using built-in VectorMemory implementation")

except Exception as e:
    logger.error(f"[VectorMemory] Initialization failed: {e}")
    MEM_VEC = None


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
        logger.error(f"[MemoryModel] predict_decision_status error: {e}")
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
            logger.error(f"[MemoryModel] MEM_CLF.predict_proba error: {e}")

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
            logger.error(f"[MemoryModel] MODEL.predict_proba error: {e}")

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
                logger.error(f"[MemoryOS] unlock failed: {e}")
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
                except OSError:
                    pass
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
                logger.error(f"[MemoryOS] lockfile cleanup failed: {e}")


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
        self._cache_ttl: float = float(os.getenv("VERITAS_MEMORY_CACHE_TTL", "5.0"))
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
                        return [dict(r) for r in data]
                    return data

        if not self.path.exists():
            logger.debug(f"[MemoryOS] memory file not found: {self.path}")
            data: List[Dict[str, Any]] = []
        else:
            try:
                with locked_memory(self.path):
                    with open(self.path, "r", encoding="utf-8") as f:
                        raw = json.load(f)
                data = self._normalize(raw)
            except json.JSONDecodeError as e:
                logger.error(f"[MemoryOS] JSON decode error: {e}")
                data = []
            except Exception as e:
                logger.error(f"[MemoryOS] load error: {e}")
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
        except Exception as e:
            logger.error(f"[MemoryOS] save error: {e}")
            return False

    def put(self, user_id: str, key: str, value: Any) -> bool:
        """KVS put 操作"""
        data = self._load_all(copy=True)

        # 既存レコードを探す
        found = False
        for r in data:
            if r.get("user_id") == user_id and r.get("key") == key:
                r["value"] = value
                r["ts"] = time.time()
                found = True
                break

        # 新規レコード
        if not found:
            data.append(
                {
                    "user_id": user_id,
                    "key": key,
                    "value": value,
                    "ts": time.time(),
                }
            )

        return self._save_all(data)

    def get(self, user_id: str, key: str) -> Any:
        """KVS get 操作"""
        data = self._load_all(copy=True)
        for r in data:
            if r.get("user_id") == user_id and r.get("key") == key:
                return r.get("value")
        return None

    def list_all(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """全レコードをリスト"""
        data = self._load_all(copy=True)
        if user_id:
            return [r for r in data if r.get("user_id") == user_id]
        return data

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

        data = self._load_all(copy=True)
        episodic: List[Dict[str, Any]] = []
        target_user = user_id

        for r in data:
            if target_user and r.get("user_id") != target_user:
                continue

            val = r.get("value") or {}
            if not isinstance(val, dict):
                continue

            text = str(val.get("text") or val.get("query") or "").strip()
            if not text:
                continue

            score = self._simple_score(query, text)
            if score < min_sim:
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

        logger.debug(f"[MemoryOS][KVS] episodic hits={len(episodic)}")
        return {"episodic": episodic[:k]}

    def put_episode(
        self,
        text: str,
        tags: Optional[List[str]] = None,
        meta: Optional[Dict[str, Any]] = None,
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
        self.put(user_id, key, record)

        # ベクトルインデックスにも追加
        # ★ 修正 (H-10): ローカル変数でスナップショットし、
        #   チェックと使用の間で MEM_VEC が None になる競合を防止
        with _mem_vec_lock:
            _vec = MEM_VEC
            if _vec is not None:
                try:
                    _vec.add(
                        kind="episodic",
                        text=text,
                        tags=tags or [],
                        meta=meta or {},
                    )
                except Exception as e:
                    logger.warning(f"[MemoryOS] put_episode MEM_VEC.add error: {e}")

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
                    # Python 3.14 以降での推奨パターン（UTCの timezone-aware datetime）
                    dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)
                    # 既存仕様に合わせて naive + "Z" にする場合
                    ts_str = dt.replace(tzinfo=None).isoformat() + "Z"
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
    """検索結果をEvidence形式に変換"""
    evidence: List[Dict[str, Any]] = []
    for h in hits:
        if not isinstance(h, dict):
            continue

        text = str(h.get("text") or "")
        if not text:
            continue

        evidence.append(
            {
                "source": f"{source_prefix}:{h.get('id', 'unknown')}",
                "text": text,
                "score": h.get("score", 0.0),
                "tags": h.get("tags", []),
                "meta": h.get("meta", {}),
            }
        )

    return evidence


def get_evidence_for_decision(
    decision: Dict[str, Any],
    *,
    user_id: Optional[str] = None,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """決定のためのエビデンスを取得"""
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
    """クエリのためのエビデンスを取得"""
    query = (query or "").strip()
    if not query:
        return []

    hits = search(query=query, k=top_k, user_id=user_id)
    if not hits or not isinstance(hits, list):
        return []

    return _hits_to_evidence(hits, source_prefix="memory")


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
            except Exception as exc:
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
    with _mem_vec_lock:
        _vec = MEM_VEC
        if _vec is not None:
            try:
                _vec.add(
                    kind=kind,
                    text=text,
                    tags=tags or [],
                    meta=entry_meta,
                )
            except Exception as e:
                logger.warning(f"[MemoryOS.add] MEM_VEC.add error: {e}")

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
        with _mem_vec_lock:
            _vec = MEM_VEC
            if _vec is not None:
                try:
                    base_text = text or json.dumps(doc, ensure_ascii=False)
                    success = _vec.add(kind=kind, text=base_text, tags=tags, meta=meta)
                    if success:
                        logger.debug(f"[MemoryOS] Added to vector index: {kind}")
                except Exception as e:
                    logger.warning(f"[MemoryOS] MEM_VEC.add error (fallback to KVS): {e}")

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
    unique: List[Dict[str, Any]] = []
    seen = set()

    for h in hits:
        if not isinstance(h, dict):
            continue

        text = str(h.get("text") or "")
        meta = h.get("meta") or {}
        uid = str((meta or {}).get("user_id") or "")

        key = (text, uid)
        if key in seen:
            continue

        seen.add(key)
        unique.append(h)

        if len(unique) >= k:
            break

    return unique


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
    _vec = MEM_VEC
    if _vec is not None:
        try:
            raw = _vec.search(
                query=query,
                k=k,
                kinds=kinds,
                min_sim=min_sim,
            )

            candidates: Optional[List[Dict[str, Any]]] = None

            # パターンA: list[dict]
            if isinstance(raw, list):
                candidates = [h for h in raw if isinstance(h, dict)]

            # パターンB: dict{"hits"/"episodic"/"results": list}
            elif isinstance(raw, dict):
                for key in ("hits", "episodic", "results"):
                    v = raw.get(key)
                    if isinstance(v, list):
                        candidates = [h for h in v if isinstance(h, dict)]
                        if candidates:
                            break

            if candidates:
                # user_id指定があればフィルタ（meta.user_id が一致 or 未指定）
                if user_id is not None:
                    filtered: List[Dict[str, Any]] = []
                    for h in candidates:
                        meta = h.get("meta") or {}
                        uid = meta.get("user_id")
                        if uid is None or uid == user_id:
                            filtered.append(h)
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
            except Exception as e:
                logger.warning(f"[MemoryOS] MEM_VEC.search(old sig) error: {e}")

        except Exception as e:
            logger.warning(f"[MemoryOS] MEM_VEC.search error: {e}")

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

    hits: List[Dict[str, Any]] = []

    # MemoryStore.search は {"episodic": [...]} を返す想定
    if isinstance(res, dict) and "episodic" in res:
        episodic = res.get("episodic") or []
        if isinstance(episodic, list):
            hits = [h for h in episodic if isinstance(h, dict)]

    # list で返ってきた場合
    elif isinstance(res, list):
        hits = [h for h in res if isinstance(h, dict)]

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
    """
    エピソードのリストから、LLM に投げる要約プロンプトを組み立てる。
    """
    lines: List[str] = []
    lines.append(
        "You are VERITAS OS's Memory Distill module.\n"
        "Your job is to compress the user's recent episodic memories into a concise, "
        "useful long-term note that VERITAS can reuse later."
    )
    lines.append("")
    lines.append(f"Target user_id: {user_id}")
    lines.append("")
    lines.append("Here are recent episodic records (newest first):")

    for i, ep in enumerate(episodes, start=1):
        ts = ep.get("ts")
        try:
            ts_f = float(ts)
            ts_str = datetime.fromtimestamp(ts_f, tz=timezone.utc).isoformat()
        except Exception:
            ts_str = "unknown"

        text = str(ep.get("text") or "").strip()
        tags = ep.get("tags") or []
        tag_str = f" tags={tags}" if tags else ""

        if len(text) > 300:
            text_short = text[:297] + "..."
        else:
            text_short = text

        lines.append(f"- #{i} [{ts_str}]{tag_str} {text_short}")

    lines.append("")
    lines.append(
        "Please write a Japanese summary that captures:\n"
        "1. The main topics and decisions the user is working on\n"
        "2. Ongoing projects or threads (e.g., VERITAS, 労働紛争, 音楽制作)\n"
        "3. Open TODOs or follow-ups that seem important\n"
        "4. Any stable preferences or values that appear\n"
        "\n"
        "Format:\n"
        "「概要」セクション: 箇条書きで3〜7行\n"
        "「プロジェクト別ノート」セクション: VERITAS / 労働紛争 / 音楽 / その他 に分けて\n"
        "「TODO / Next Actions」セクション: 箇条書きで3〜10行\n"
    )

    return "\n".join(lines)


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
    except Exception as e:
        logger.error(f"[MemoryDistill] list_all failed for user={user_id}: {e}")
        return None

    episodic: List[Dict[str, Any]] = []
    filter_tags = set(tags or [])

    for r in all_records:
        value = r.get("value") or {}
        if not isinstance(value, dict):
            continue

        kind = str(value.get("kind") or "episodic")
        if kind != "episodic":
            continue

        text = str(value.get("text") or "").strip()
        if len(text) < min_text_len:
            continue

        ep_tags = value.get("tags") or []

        # tags 指定がある場合は、そのタグを含むものだけ対象
        if filter_tags and not (filter_tags & set(ep_tags)):
            continue

        ep = {
            "text": text,
            "tags": ep_tags,
            "ts": r.get("ts") or time.time(),
        }
        episodic.append(ep)

    if not episodic:
        logger.info(f"[MemoryDistill] no episodic records for user={user_id}")
        return None

    # 新しい順にソートして max_items までに圧縮
    episodic.sort(key=lambda x: x.get("ts", 0.0), reverse=True)
    target_eps = episodic[:max_items]

    # 2) プロンプト生成
    prompt = _build_distill_prompt(user_id, target_eps)
    system_msg = "You are VERITAS Memory Distill module."

    # 3) LLM コール (llm_client モジュールを直接叩く)
    try:
        import inspect

        chat_fn = None
        # 優先順で関数を探す
        if hasattr(llm_client, "chat_completion"):
            chat_fn = llm_client.chat_completion
        elif hasattr(llm_client, "call_chat"):
            chat_fn = llm_client.call_chat
        elif hasattr(llm_client, "chat"):
            chat_fn = llm_client.chat

        if chat_fn is None:
            logger.error(
                "[MemoryDistill] llm_client has no chat function "
                "(expected chat_completion / call_chat / chat)"
            )
            return None

        sig = inspect.signature(chat_fn)
        param_names = list(sig.parameters.keys())

        # chat_fn が受け取れる引数だけ詰める
        common_kwargs: Dict[str, Any] = {}
        if "model" in param_names:
            common_kwargs["model"] = model or None
        if "max_tokens" in param_names:
            common_kwargs["max_tokens"] = 1024

        resp = None

        # --- パターン1: system / user / prompt をそのまま受ける系 ---
        if "system" in param_names and ("user" in param_names or "prompt" in param_names):
            kwargs = dict(common_kwargs)
            kwargs["system"] = system_msg
            if "user" in param_names:
                kwargs["user"] = prompt
            else:
                kwargs["prompt"] = prompt
            resp = chat_fn(**kwargs)

        # --- パターン2: system_prompt / user_prompt 方式 ---
        elif "system_prompt" in param_names and "user_prompt" in param_names:
            kwargs = dict(common_kwargs)
            # まずキーワード引数で試す
            try:
                resp = chat_fn(
                    system_prompt=system_msg,
                    user_prompt=prompt,
                    **kwargs,
                )
            except TypeError:
                # キーワードがダメな実装の場合は位置引数で再トライ
                resp = chat_fn(system_msg, prompt, **kwargs)

        # --- パターン3: system がなく、prompt / user / 位置引数でまとめて渡す系 ---
        else:
            combined = f"{system_msg}\n\nUser:\n{prompt}"
            kwargs = dict(common_kwargs)

            if "prompt" in param_names:
                kwargs["prompt"] = combined
                resp = chat_fn(**kwargs)
            elif "user" in param_names:
                kwargs["user"] = combined
                resp = chat_fn(**kwargs)
            else:
                # 最終手段: 先頭の位置引数として渡す
                resp = chat_fn(combined, **kwargs)

    except TypeError as e:
        logger.error(f"[MemoryDistill] LLM call TypeError: {e}")
        return None
    except Exception as e:
        logger.error(f"[MemoryDistill] LLM call failed: {e}")
        return None

    # 4) レスポンスからテキストを取り出す
    summary_text = ""

    if isinstance(resp, dict):
        # 典型的な OpenAI / LLM スタイルのレスポンスも一応ハンドル
        if "choices" in resp:
            try:
                summary_text = (
                    resp["choices"][0]["message"]["content"]
                    or ""
                )
            except Exception:
                summary_text = ""
        if not summary_text:
            summary_text = (
                resp.get("text")
                or resp.get("content")
                or resp.get("output")
                or ""
            )
    elif isinstance(resp, str):
        summary_text = resp
    else:
        summary_text = str(getattr(resp, "text", "") or "")

    summary_text = str(summary_text).strip()
    if not summary_text:
        logger.error("[MemoryDistill] empty summary_text from LLM")
        return None

    # 5) semantic メモリとして永続化
    meta = {
        "user_id": user_id,
        "source": "distill_memory_for_user",
        "item_count": len(target_eps),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    doc: Dict[str, Any] = {
        "kind": "semantic",
        "text": summary_text,
        "tags": (tags or []) + ["memory_distill", "summary", "long_term"],
        "meta": meta,
    }

    ok = put("semantic", doc)
    if not ok:
        logger.error("[MemoryDistill] failed to save semantic memory")
        return None

    logger.info(
        f"[MemoryDistill] semantic note saved for user={user_id} "
        f"(items={len(target_eps)}, chars={len(summary_text)})"
    )
    return doc


def rebuild_vector_index():
    """
    既存のmemory.jsonからベクトルインデックスを再構築

    使用例:
        from veritas_os.core import memory
        memory.rebuild_vector_index()
    """
    # ★ 修正 (H-10): _mem_vec_lock で排他制御し、
    #   リビルド中に他スレッドが MEM_VEC を使用しないようにする
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
        documents: List[Dict[str, Any]] = []
        for record in all_data:
            value = record.get("value")
            if not isinstance(value, dict):
                continue

            text = value.get("text", "")
            if not text or not text.strip():
                continue

            meta = value.get("meta", {}) or {}
            meta = {
                "user_id": record.get("user_id"),
                "created_at": record.get("ts"),
                **meta,
            }

            documents.append(
                {
                    "kind": value.get("kind", "episodic"),
                    "text": text,
                    "tags": value.get("tags", []),
                    "meta": meta,
                }
            )

        logger.info(f"[MemoryOS] Found {len(documents)} documents to index")

        # インデックス再構築
        _vec.rebuild_index(documents)  # type: ignore[arg-type]

        logger.info("[MemoryOS] Vector index rebuild complete")






