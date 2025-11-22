# veritas_os/core/models/memory_model.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any
import math
import uuid

# ここでは標準ライブラリだけで “なんちゃって埋め込み” を作る
# （本気版は sentence-transformers や OpenAI embedding に差し替え）

def _tokenize(text: str) -> List[str]:
    return [t for t in text.lower().replace("　", " ").split() if t]

def _cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(a.get(k, 0.0) * b.get(k, 0.0) for k in a.keys())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


@dataclass
class MemoryItem:
    id: str
    kind: str
    text: str
    tags: List[str]
    meta: Dict[str, Any]
    vec: Dict[str, float]


class SimpleMemVec:
    """
    超シンプルな in-memory ベクトルストア。
    本気になったら:
      - sentence-transformers でベクトル化
      - faiss / chroma 等に差し替え
    """
    def __init__(self) -> None:
        self._items: List[MemoryItem] = []

    # ---- 内部用: text -> bag-of-words ベクトル ----
    def _encode(self, text: str) -> Dict[str, float]:
        toks = _tokenize(text)
        v: Dict[str, float] = {}
        for t in toks:
            v[t] = v.get(t, 0.0) + 1.0
        return v

    # ---- 追加 ----
    def add(self, kind: str, text: str, tags=None, meta=None) -> str:
        mid = uuid.uuid4().hex
        item = MemoryItem(
            id=mid,
            kind=kind,
            text=text,
            tags=list(tags or []),
            meta=dict(meta or {}),
            vec=self._encode(text),
        )
        self._items.append(item)
        return mid

    # ---- 検索 ----
    def search(self, query: str, k: int = 8, kinds=None, min_sim: float = 
0.25):
        qv = self._encode(query or "")
        kinds_set = set(kinds) if kinds else None

        scored = []
        for it in self._items:
            if kinds_set and it.kind not in kinds_set:
                continue
            sim = _cosine(qv, it.vec)
            if sim >= min_sim:
                scored.append((sim, it))

        scored.sort(key=lambda x: x[0], reverse=True)
        hits = []
        for sim, it in scored[:k]:
            hits.append({
                "id": it.id,
                "kind": it.kind,
                "text": it.text,
                "tags": it.tags,
                "meta": it.meta,
                "score": sim,
            })
        return hits


# server.py から import されるグローバル
MEM_VEC = SimpleMemVec()

# いまは未使用でOK
MEM_CLF = None
