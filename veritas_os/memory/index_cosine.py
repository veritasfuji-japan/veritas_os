# veritas/memory/index_cosine.py
import os
import threading
import logging

import numpy as np
from pathlib import Path
from typing import Any, Iterable, List, Optional, Tuple

from veritas_os.core.atomic_io import atomic_write_npz

logger = logging.getLogger(__name__)


class PickleSecurityWarning(UserWarning):
    """
    Custom warning category for pickle-related security risks.
    Allows filtering of security warnings separately from other UserWarnings.
    """
    pass


def _allow_legacy_pickle_npz() -> bool:
    """
    Allow loading legacy npz files that require pickle.

    ⚠️ SECURITY WARNING: Pickle deserialization can execute arbitrary code.
    This feature is DEPRECATED and should only be enabled temporarily
    during one-time migration of legacy data files.

    To enable (NOT recommended for production):
        export VERITAS_MEMORY_ALLOW_LEGACY_NPZ=1

    After migration, disable immediately and regenerate index files.
    """
    import warnings
    value = os.getenv("VERITAS_MEMORY_ALLOW_LEGACY_NPZ", "").strip().lower()
    if value in {"1", "true", "yes", "y", "on"}:
        warnings.warn(
            "VERITAS_MEMORY_ALLOW_LEGACY_NPZ is enabled. This is a security risk. "
            "Pickle deserialization can execute arbitrary code. "
            "Disable after migrating legacy data files.",
            PickleSecurityWarning,
            stacklevel=2,
        )
        return True
    return False


def _validate_finite_array(name: str, values: np.ndarray) -> None:
    """Raise ValueError when an input vector contains NaN/Inf values."""
    if not np.isfinite(values).all():
        raise ValueError(f"CosineIndex.{name}: vectors must be finite (no NaN/Inf)")


class CosineIndex:
    """
    シンプルな Cosine 類似度インデックス + 永続化 (.npz)

    - add(vecs, ids): ベクトルと id を追加し、その場で保存
    - search(qv, k): 上位 k 件の (id, score) を返す（クエリが複数でもOK）

    スレッドセーフ: 全ての読み書き操作は RLock で保護されています。
    """

    def __init__(self, dim: int, path: Optional[Path] = None):
        """Create a cosine index.

        Args:
            dim: Vector dimensionality. Must be a positive integer.
            path: Optional `.npz` persistence path.

        Raises:
            ValueError: If ``dim`` is not a positive integer.
        """
        if not isinstance(dim, int) or dim < 1:
            raise ValueError(f"CosineIndex.__init__: dim must be a positive int, got {dim!r}")

        self.dim = dim
        self.path = Path(path) if path is not None else None
        self._lock = threading.RLock()  # リエントラントロック

        self.vecs = np.zeros((0, dim), dtype=np.float32)  # (N, D)
        self.ids: List[str] = []                          # len=N

        # 既存 index があればロード
        if self.path is not None and self.path.exists():
            self._load()

    # ---- 永続化 -------------------------------------------------
    def _load(self) -> None:
        with self._lock:
            try:
                with np.load(self.path, allow_pickle=False) as data:
                    self.vecs = data["vecs"].astype(np.float32)
                    self.ids = [str(i) for i in data["ids"].tolist()]
                self._validate_loaded_index_or_reset()
                return
            except Exception as e:
                # ★ M-18 修正: エラーをログに記録（破損と不在を区別可能に）
                logger.debug(
                    "[CosineIndex] Failed to load index (allow_pickle=False): %s: %s",
                    self.path, e,
                )

            if _allow_legacy_pickle_npz():
                # ★ セキュリティ: ファイルサイズ制限（メモリ枯渇防止）
                _MAX_LEGACY_NPZ_BYTES = 512 * 1024 * 1024  # 512 MB
                try:
                    file_size = self.path.stat().st_size
                except OSError:
                    file_size = 0
                if file_size > _MAX_LEGACY_NPZ_BYTES:
                    logger.warning(
                        "[CosineIndex] Legacy pickle file too large (%d bytes, limit=%d): %s",
                        file_size, _MAX_LEGACY_NPZ_BYTES, self.path,
                    )
                else:
                    logger.warning(
                        "[CosineIndex] Loading legacy pickle-based npz file: %s. "
                        "This is a security risk. Re-save the index to migrate.",
                        self.path,
                    )
                    try:
                        with np.load(self.path, allow_pickle=True) as data:
                            self.vecs = data["vecs"].astype(np.float32)
                            self.ids = [str(i) for i in data["ids"].tolist()]
                        self._validate_loaded_index_or_reset()
                        # Immediately re-save without pickle to migrate
                        self.save()
                        logger.info(
                            "[CosineIndex] Migrated legacy pickle file to safe format: %s",
                            self.path,
                        )
                        return
                    except Exception as e:
                        # ★ M-18 修正: レガシー読み込みの失敗もログに記録
                        logger.warning(
                            "[CosineIndex] Failed to load legacy pickle file: %s: %s",
                            self.path, e,
                        )

            # 壊れていたら諦めて空からスタート
            self.vecs = np.zeros((0, self.dim), dtype=np.float32)
            self.ids = []

    def _validate_loaded_index_or_reset(self) -> None:
        """Validate loaded arrays and reset to empty index when data is inconsistent."""
        if self.vecs.ndim != 2:
            logger.warning(
                "[CosineIndex] Invalid vecs ndim (%d), resetting index: %s",
                self.vecs.ndim,
                self.path,
            )
            self.vecs = np.zeros((0, self.dim), dtype=np.float32)
            self.ids = []
            return

        if self.vecs.shape[1] != self.dim:
            logger.warning(
                "[CosineIndex] Loaded vec dim mismatch (%d != %d), resetting index: %s",
                self.vecs.shape[1],
                self.dim,
                self.path,
            )
            self.vecs = np.zeros((0, self.dim), dtype=np.float32)
            self.ids = []
            return

        if len(self.ids) != self.vecs.shape[0]:
            logger.warning(
                "[CosineIndex] Loaded ids/vec count mismatch (%d != %d), resetting index: %s",
                len(self.ids),
                self.vecs.shape[0],
                self.path,
            )
            self.vecs = np.zeros((0, self.dim), dtype=np.float32)
            self.ids = []
            return

        if not np.isfinite(self.vecs).all():
            logger.warning(
                "[CosineIndex] Loaded vecs include non-finite values (NaN/Inf), resetting index: %s",
                self.path,
            )
            self.vecs = np.zeros((0, self.dim), dtype=np.float32)
            self.ids = []

    def save(self) -> None:
        if self.path is None:
            return
        with self._lock:
            try:
                atomic_write_npz(
                    self.path,
                    vecs=self.vecs,
                    ids=np.array(self.ids, dtype=str),
                )
            except Exception as e:
                logger.error("[CosineIndex] save failed: %s", e)

    # ---- 基本操作 ------------------------------------------------
    @property
    def size(self) -> int:
        with self._lock:
            return len(self.ids)

    def add(self, vecs: Any, ids: Iterable[str]) -> None:
        """ベクトルと id を追加して即保存（スレッドセーフ）"""
        vecs = np.asarray(vecs, dtype=np.float32)
        if vecs.ndim == 1:
            vecs = vecs.reshape(1, -1)
        _validate_finite_array("add", vecs)

        if vecs.shape[1] != self.dim:
            raise ValueError(f"CosineIndex.add: dim mismatch {vecs.shape[1]} != {self.dim}")

        ids = list(ids)
        if len(ids) != vecs.shape[0]:
            raise ValueError(f"CosineIndex.add: len(ids)={len(ids)} != vecs.shape[0]={vecs.shape[0]}")

        with self._lock:
            if self.vecs.size == 0:
                self.vecs = vecs
            else:
                self.vecs = np.concatenate([self.vecs, vecs], axis=0)
            self.ids.extend([str(i) for i in ids])

            self.save()

    def search(self, qv: Any, k: int = 8) -> List[List[Tuple[str, float]]]:
        """
        qv: (D,) or (Q, D)
        k: 取得する上位件数（1以上）
        戻り値: [[(id, score), ...], ...]  （クエリごとに1リスト）
        スレッドセーフ: 検索中は一貫したスナップショットを使用
        """
        if k < 1:
            raise ValueError(f"CosineIndex.search: k must be >= 1, got {k}")

        q = np.asarray(qv, dtype=np.float32)
        if q.ndim == 1:
            q = q.reshape(1, -1)
        _validate_finite_array("search", q)
        if q.shape[1] != self.dim:
            raise ValueError(f"CosineIndex.search: dim mismatch {q.shape[1]} != {self.dim}")

        with self._lock:
            # ロック内でスナップショットを取得
            if len(self.ids) == 0:
                return [[] for _ in range(q.shape[0])]

            V = self.vecs.copy()  # スナップショット
            ids_snapshot = list(self.ids)

        # ロック外で計算（パフォーマンス向上）
        # 正規化（cosine 類似度）
        Vn = V / (np.linalg.norm(V, axis=1, keepdims=True) + 1e-8)
        Qn = q / (np.linalg.norm(q, axis=1, keepdims=True) + 1e-8)

        sims = np.clip(Qn @ Vn.T, -1.0, 1.0)  # (Q, N)

        out: List[List[Tuple[str, float]]] = []
        for row in sims:
            kk = min(k, len(ids_snapshot))
            idx = np.argsort(-row)[:kk]
            out.append([(ids_snapshot[i], float(row[i])) for i in idx])
        return out
