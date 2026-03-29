# veritas_os/core/memory_vector.py
"""
VectorMemory - built-in vector memory implementation.

Provides the ``VectorMemory`` class which uses sentence-transformers for
embedding generation and cosine similarity for semantic search.  The class
is thread-safe (RLock protected) and persists its index as JSON.

The singleton lifecycle (``MEM_VEC``, ``_get_mem_vec``) and prediction
helpers (``predict_gate_label``, ``predict_decision_status``) remain in
``memory.py`` because tests frequently monkeypatch those module-level
symbols.  This module is purely the data-structure / algorithm layer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import json
import time
import threading
import base64
import logging

from ..config import capability_cfg
from .memory_security import (
    emit_legacy_pickle_runtime_blocked,
    is_explicitly_enabled,
)

logger = logging.getLogger(__name__)


# Module-level wrappers used by VectorMemory methods.
# Tests that import VectorMemory from ``memory.py`` can patch
# ``memory._is_explicitly_enabled`` — memory.py re-assigns
# ``memory_vector._is_explicitly_enabled`` to keep the override visible.
def _is_explicitly_enabled(env_key: str) -> bool:
    return is_explicitly_enabled(env_key)


def _emit_legacy_pickle_runtime_blocked(path: Path, artifact_name: str) -> None:
    emit_legacy_pickle_runtime_blocked(path=path, artifact_name=artifact_name)


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

            # Resolve config at call time so module reloads are visible.
            from .config import capability_cfg as _cfg

            if not _cfg.enable_memory_sentence_transformers:
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
                    "[VectorMemory] Loaded JSON index: %d documents",
                    len(self.documents),
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
                "[VectorMemory] Search '%s...' found %d/%d hits",
                query[:50],
                len(top_results),
                len(results),
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
            "[VectorMemory] Rebuilding index for %d documents...",
            len(documents),
        )

        # ★ 競合修正: ロック外で全埋め込みを事前計算し、
        # ロック内でアトミックに差し替える
        import numpy as np

        new_docs = []
        embeddings_list = []
        counter = 0
        for doc in documents:
            text = doc.get("text", "")
            if not text or not text.strip():
                continue
            embedding = self.model.encode([text])[0]
            counter += 1
            new_doc = {
                "id": f"{doc.get('kind', 'semantic')}_{counter}_{int(time.time())}",
                "kind": doc.get("kind", "semantic"),
                "text": text,
                "tags": doc.get("tags") or [],
                "meta": doc.get("meta") or {},
                "ts": time.time(),
            }
            new_docs.append(new_doc)
            embeddings_list.append(embedding)

        with self._lock:
            self.documents = new_docs
            self._id_counter = counter
            if embeddings_list:
                self.embeddings = np.vstack([e.reshape(1, -1) for e in embeddings_list])
            else:
                self.embeddings = None

        self._save_index()
        logger.info(
            "[VectorMemory] Index rebuilt: %d documents indexed",
            len(self.documents),
        )
