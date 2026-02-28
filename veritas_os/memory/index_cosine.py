# veritas/memory/index_cosine.py
import threading
import logging

import numpy as np
from pathlib import Path
from typing import Any, Iterable, List, Optional, Tuple

from veritas_os.core.atomic_io import atomic_write_npz

logger = logging.getLogger(__name__)


def _validate_finite_array(name: str, values: np.ndarray) -> None:
    """Raise ValueError when an input vector contains NaN/Inf values."""
    if not np.isfinite(values).all():
        raise ValueError(f"CosineIndex.{name}: vectors must be finite (no NaN/Inf)")


def _ensure_2d_vectors(name: str, values: Any) -> np.ndarray:
    """Convert inputs to a 2D float32 matrix and validate rank.

    Args:
        name: Operation name used in error messages (e.g. ``"add"``).
        values: User-provided vector or matrix-like value.

    Returns:
        A ``(N, D)`` numpy array in ``float32``.

    Raises:
        ValueError: If ``values`` is not a 1D or 2D array-like input.
    """
    arr = np.asarray(values, dtype=np.float32)
    if arr.ndim == 1:
        return arr.reshape(1, -1)
    if arr.ndim != 2:
        raise ValueError(
            f"CosineIndex.{name}: vectors must be 1D or 2D, got ndim={arr.ndim}"
        )
    return arr


def _is_safe_index_path(path: Path) -> bool:
    """Return ``True`` when ``path`` is a regular non-symlink file.

    Security rationale:
        - Symlinks can redirect reads to unexpected files.
        - Non-regular files (directories/devices/FIFOs) can cause unsafe behavior.
        - Symlinked parent directories can hide redirections even when the
          final file itself is not a symlink.
    """

    for parent in path.parents:
        # Stop at filesystem root to avoid unnecessary checks.
        if parent == parent.parent:
            break
        try:
            if parent.is_symlink():
                logger.warning(
                    "[CosineIndex] Refusing to load from path under symlink "
                    "directory for security: %s (via %s)",
                    path,
                    parent,
                )
                return False
        except OSError as exc:
            logger.warning(
                "[CosineIndex] Failed to inspect parent path (%s): %s",
                parent,
                exc,
            )
            return False

    try:
        if path.is_symlink():
            logger.warning(
                "[CosineIndex] Refusing to load from symlink path for security: %s",
                path,
            )
            return False
        if not path.is_file():
            logger.warning(
                "[CosineIndex] Refusing to load from non-regular file: %s",
                path,
            )
            return False
    except OSError as exc:
        logger.warning(
            "[CosineIndex] Failed to stat index path (%s): %s",
            path,
            exc,
        )
        return False
    return True


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
        if not isinstance(dim, int) or isinstance(dim, bool) or dim < 1:
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
            if not _is_safe_index_path(self.path):
                self.vecs = np.zeros((0, self.dim), dtype=np.float32)
                self.ids = []
                return

            try:
                with np.load(self.path, allow_pickle=False) as data:
                    self.vecs = data["vecs"].astype(np.float32)
                    self.ids = [str(i) for i in data["ids"].tolist()]
                self._validate_loaded_index_or_reset()
                return
            except (OSError, ValueError, TypeError, KeyError) as e:
                # ★ M-18 修正: エラーをログに記録（破損と不在を区別可能に）
                logger.debug(
                    "[CosineIndex] Failed to load index (allow_pickle=False): %s: %s",
                    self.path, e,
                )

            logger.warning(
                "[CosineIndex] Refusing to load potentially legacy pickle-based index file: %s. "
                "Legacy pickle deserialization is disabled for security.",
                self.path,
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
            except OSError as e:
                logger.error("[CosineIndex] save failed: %s", e)

    # ---- 基本操作 ------------------------------------------------
    @property
    def size(self) -> int:
        with self._lock:
            return len(self.ids)

    def add(self, vecs: Any, ids: Iterable[str]) -> None:
        """ベクトルと id を追加して即保存（スレッドセーフ）"""
        vecs = _ensure_2d_vectors("add", vecs)
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
        if not isinstance(k, int) or isinstance(k, bool):
            raise ValueError(f"CosineIndex.search: k must be an int, got {type(k).__name__}")
        if k < 1:
            raise ValueError(f"CosineIndex.search: k must be >= 1, got {k}")

        q = _ensure_2d_vectors("search", qv)
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
            idx = np.argsort(-row, kind="stable")[:kk]
            out.append([(ids_snapshot[i], float(row[i])) for i in idx])
        return out
