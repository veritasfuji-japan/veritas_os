# veritas/memory/embedder.py
import hashlib

import numpy as np

class HashEmbedder:
    def __init__(self, dim: int = 384):
        self.dim = dim
    def _h(self, t: str) -> np.ndarray:
        h = hashlib.blake2b(t.encode('utf-8'), digest_size=64).digest()
        # 64byte→dimへ拡張/繰り返し
        arr = np.frombuffer(h, dtype=np.uint8).astype(np.float32)
        v = np.tile(arr, int(np.ceil(self.dim/arr.size)))[:self.dim]
        v = (v - v.mean()) / (v.std() + 1e-6)
        return v
    def embed(self, texts):
        return np.vstack([self._h(t) for t in texts])
