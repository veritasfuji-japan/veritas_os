# veritas_os/core/models/memory_model.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import math
import uuid
import logging

log = logging.getLogger(__name__)

# =========================================================
# 簡易トークナイザ & コサイン類似度
# =========================================================

def _tokenize(text: str) -> List[str]:
    """超シンプルな単語分割（空白区切り + 小文字化）。"""
    return [t for t in str(text).lower().replace("　", " ").split() if t]

def _cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
    """Bag-of-Words ベクトル同士のコサイン類似度。"""
    if not a or not b:
        return 0.0
    dot = sum(a.get(k, 0.0) * b.get(k, 0.0) for k in a.keys())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


# =========================================================
# in-memory ベクトルストア
# =========================================================

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
    - テキストを Bag-of-Words ベクトルに変換
    - コサイン類似度で検索
    本気運用時は sentence-transformers / faiss 等に差し替え予定。
    """

    def __init__(self) -> None:
        self._items: List[MemoryItem] = []

    # ---- 内部: text -> bag-of-words ベクトル ----
    def _encode(self, text: str) -> Dict[str, float]:
        toks = _tokenize(text)
        v: Dict[str, float] = {}
        for t in toks:
            v[t] = v.get(t, 0.0) + 1.0
        return v

    # ---- 追加 ----
    def add(
        self,
        kind: str,
        text: str,
        tags: Optional[List[str]] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        kind: "semantic" / "skills" などの種別
        text: 検索対象になる本文
        tags, meta: 任意のメタ情報
        """
        mid = uuid.uuid4().hex
        item = MemoryItem(
            id=mid,
            kind=str(kind or "semantic"),
            text=text,
            tags=list(tags or []),
            meta=dict(meta or {}),
            vec=self._encode(text),
        )
        self._items.append(item)
        return mid

    # ---- 検索 ----
    def search(
        self,
        query: str,
        k: int = 8,
        kinds: Optional[List[str]] = None,
        min_sim: float = 0.25,
    ) -> List[Dict[str, Any]]:
        """
        query に似たメモリを上位 k 件返す。
        戻り値: list[{"id","kind","text","tags","meta","score"}]
        """
        qv = self._encode(query or "")
        kinds_set = set(kinds) if kinds else None

        scored: List[tuple[float, MemoryItem]] = []
        for it in self._items:
            if kinds_set and it.kind not in kinds_set:
                continue
            sim = _cosine(qv, it.vec)
            if sim >= float(min_sim):
                scored.append((sim, it))

        scored.sort(key=lambda x: x[0], reverse=True)

        hits: List[Dict[str, Any]] = []
        for sim, it in scored[: int(k)]:
            hits.append(
                {
                    "id": it.id,
                    "kind": it.kind,
                    "text": it.text,
                    "tags": it.tags,
                    "meta": it.meta,
                    "score": float(sim),
                }
            )
        return hits


# =========================================================
# グローバルオブジェクト（MemoryOS から参照）
# =========================================================

# ベクトル検索用
MEM_VEC: SimpleMemVec = SimpleMemVec()

# ゲート用の分類器は、いまは載せない（Noneで固定）
MEM_CLF = None

# pipeline.py 側のパス検出用ダミー
MODEL_FILE = ""
MODEL_PATH = ""


# =========================================================
# FUJI gate 用ラッパ（安全版）
# =========================================================

def predict_gate_label(text: str) -> Dict[str, float]:
    """
    FUJI ゲートから呼ばれる安全なラッパ。

    いまはまだ学習済みモデルがないので、
    「常に allow=0.5」というニュートラルなスコアだけ返す。

    将来、本物の分類器を載せる場合はここを書き換える。
    """
    # ここで MEM_CLF を使わないようにしておく（None前提）
    # 何か簡単なヒューリスティックを入れてもいいが、
    # とりあえずニュートラル値だけ返す。
    return {"allow": 0.5}
