# veritas/memory/index_cosine.py
import numpy as np
from pathlib import Path
from typing import List, Tuple, Iterable, Optional, Any

from veritas_os.core.atomic_io import atomic_write_npz


class CosineIndex:
    """
    シンプルな Cosine 類似度インデックス + 永続化 (.npz)

    - add(vecs, ids): ベクトルと id を追加し、その場で保存
    - search(qv, k): 上位 k 件の (id, score) を返す（クエリが複数でもOK）
    """

    def __init__(self, dim: int, path: Optional[Path] = None):
        self.dim = dim
        self.path = Path(path) if path is not None else None

        self.vecs = np.zeros((0, dim), dtype=np.float32)  # (N, D)
        self.ids: List[str] = []                          # len=N

        # 既存 index があればロード
        if self.path is not None and self.path.exists():
            self._load()

    # ---- 永続化 -------------------------------------------------
    def _load(self):
        try:
            data = np.load(self.path, allow_pickle=True)
            self.vecs = data["vecs"].astype(np.float32)
            self.ids = list(data["ids"].tolist())
        except Exception:
            # 壊れていたら諦めて空からスタート
            self.vecs = np.zeros((0, self.dim), dtype=np.float32)
            self.ids = []

    def save(self):
        if self.path is None:
            return
        try:
            atomic_write_npz(
                self.path,
                vecs=self.vecs,
                ids=np.array(self.ids, dtype=object)
            )
        except Exception as e:
            print("[CosineIndex] save failed:", e)

    # ---- 基本操作 ------------------------------------------------
    @property
    def size(self) -> int:
        return len(self.ids)

    def add(self, vecs: Any, ids: Iterable[str]):
        """ベクトルと id を追加して即保存"""
        vecs = np.asarray(vecs, dtype=np.float32)
        if vecs.ndim == 1:
            vecs = vecs.reshape(1, -1)

        if vecs.shape[1] != self.dim:
            raise ValueError(f"CosineIndex.add: dim mismatch {vecs.shape[1]} != {self.dim}")

        ids = list(ids)
        if len(ids) != vecs.shape[0]:
            raise ValueError(f"CosineIndex.add: len(ids)={len(ids)} != vecs.shape[0]={vecs.shape[0]}")

        if self.vecs.size == 0:
            self.vecs = vecs
        else:
            self.vecs = np.concatenate([self.vecs, vecs], axis=0)
        self.ids.extend([str(i) for i in ids])

        self.save()

    def search(self, qv: Any, k: int = 8) -> List[List[Tuple[str, float]]]:
        """
        qv: (D,) or (Q, D)
        戻り値: [[(id, score), ...], ...]  （クエリごとに1リスト）
        """
        if self.size == 0:
            # クエリの数だけ空リストを返す
            q = np.asarray(qv, dtype=np.float32)
            if q.ndim == 1:
                return [[]]
            return [[] for _ in range(q.shape[0])]

        q = np.asarray(qv, dtype=np.float32)
        if q.ndim == 1:
            q = q.reshape(1, -1)

        # 正規化（cosine 類似度）
        V = self.vecs
        Vn = V / (np.linalg.norm(V, axis=1, keepdims=True) + 1e-8)
        Qn = q / (np.linalg.norm(q, axis=1, keepdims=True) + 1e-8)

        sims = Qn @ Vn.T  # (Q, N)

        out: List[List[Tuple[str, float]]] = []
        for row in sims:
            kk = min(k, self.size)
            idx = np.argsort(-row)[:kk]
            out.append([(self.ids[i], float(row[i])) for i in idx])
        return out
