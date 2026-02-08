# veritas/memory/embedder.py
import hashlib

import numpy as np

# ★ M-17 修正: 入力サイズ制限（リソース枯渇防止）
MAX_TEXT_LENGTH = 100_000
MAX_BATCH_SIZE = 10_000

class HashEmbedder:
    def __init__(self, dim: int = 384) -> None:
        self.dim = dim
    def _h(self, t: str) -> np.ndarray:
        h = hashlib.blake2b(t.encode('utf-8'), digest_size=64).digest()
        # 64byte→dimへ拡張/繰り返し
        arr = np.frombuffer(h, dtype=np.uint8).astype(np.float32)
        v = np.tile(arr, int(np.ceil(self.dim/arr.size)))[:self.dim]
        v = (v - v.mean()) / (v.std() + 1e-6)
        return v
    def embed(self, texts: list[str]) -> np.ndarray:
        if len(texts) > MAX_BATCH_SIZE:
            raise ValueError(f"Batch size {len(texts)} exceeds limit {MAX_BATCH_SIZE}")
        for t in texts:
            if len(t) > MAX_TEXT_LENGTH:
                raise ValueError(f"Text length {len(t)} exceeds limit {MAX_TEXT_LENGTH}")
        return np.vstack([self._h(t) for t in texts])
