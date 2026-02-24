"""Memory engine interfaces.

This module defines abstract contracts used by MemoryOS components.
Implementations are intentionally separate so planners/kernels can swap
embedding/index/store backends without changing call sites.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


class Embedder(ABC):
    """Text-to-vector encoder contract."""

    @abstractmethod
    def embed(self, texts: List[str]) -> np.ndarray:
        """Return an ``(N, D)`` embedding matrix for ``texts``."""


class VectorIndex(ABC):
    """Vector retrieval backend contract."""

    @abstractmethod
    def add(self, vecs: np.ndarray, ids: List[str]) -> None:
        """Store vectors and their IDs in the index."""

    @abstractmethod
    def search(self, vecs: np.ndarray, topk: int) -> List[List[Tuple[str, float]]]:
        """Return top-k scored IDs for each query vector."""

    @abstractmethod
    def save(self) -> None:
        """Persist index state."""

    @abstractmethod
    def load(self) -> None:
        """Load previously persisted index state."""


class MemoryStore(ABC):
    """Long-term memory persistence/search contract."""

    @abstractmethod
    def put(self, kind: str, item: Dict[str, Any]) -> str:
        """Persist an item and return its assigned identifier."""

    @abstractmethod
    def search(self, query: str, k: int = 8, kinds: Optional[List[str]] = None) -> Dict[str, List[Dict]]:
        """Search items. ``kinds`` is typically episodic/semantic/skills."""
