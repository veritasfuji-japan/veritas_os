# veritas/memory/engine.py
from typing import List, Dict, Any, Optional, Tuple
import numpy as np

class Embedder:
    def embed(self, texts: List[str]) -> np.ndarray:
        """(N, D) 返却。失敗時はTF-IDFやhashベース代替にフォールバック"""
        raise NotImplementedError

class VectorIndex:
    def add(self, vecs: np.ndarray, ids: List[str]): ...
    def search(self, vecs: np.ndarray, topk: int) -> List[List[Tuple[str, 
float]]]: ...
    def save(self): ...
    def load(self): ...

class MemoryStore:
    def put(self, kind: str, item: Dict[str, Any]) -> str: ...
    def search(self, query: str, k: int = 8, kinds: 
Optional[List[str]]=None) -> Dict[str, List[Dict]]:
        """kinds∈{episodic,semantic,skills}"""
