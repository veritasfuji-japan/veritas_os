# -*- coding: utf-8 -*-
"""
memory/engine.py インターフェイス層のテスト。

目的:
- Embedder / VectorIndex / MemoryStore が import できること
- Embedder のデフォルト実装が NotImplementedError を投げること
- VectorIndex / MemoryStore を継承したダミー実装が
  型的・インターフェイス的に問題なく動くこと
  （＝将来の実装差し替えに耐えられるプロトコルになっていること）
"""

from typing import Any, Dict, Optional, List


import numpy as np
import pytest

from veritas_os.memory import engine as mem_engine


# ---------------------------------------------------------
# 基本インターフェイスの存在確認
# ---------------------------------------------------------


def test_engine_interfaces_exist():
    """Embedder / VectorIndex / MemoryStore が存在することだけを確認。"""
    assert hasattr(mem_engine, "Embedder")
    assert hasattr(mem_engine, "VectorIndex")
    assert hasattr(mem_engine, "MemoryStore")


# ---------------------------------------------------------
# Embedder
# ---------------------------------------------------------


def test_embedder_default_raises_not_implemented():
    """
    Embedder は抽象インターフェイスとして NotImplementedError を投げる。
    """
    emb = mem_engine.Embedder()
    with pytest.raises(NotImplementedError):
        emb.embed(["hello", "world"])


class DummyEmbedder(mem_engine.Embedder):
    """テスト用のシンプルな Embedder 実装。

    - texts の長さ N に対して (N, 4) のベクトルを返すだけ。
    - 実装側が np.ndarray を返却するという契約を確認する。
    """

    def embed(self, texts: List[str]) -> np.ndarray:
        n = len(texts)
        # 0, 1, 2, ... を詰めた (N, 4) の行列を返すだけのダミー実装
        arr = np.arange(n * 4, dtype=float).reshape(n, 4)
        return arr


def test_dummy_embedder_returns_ndarray_and_shape():
    emb = DummyEmbedder()
    texts = ["foo", "bar", "baz"]
    vecs = emb.embed(texts)

    assert isinstance(vecs, np.ndarray)
    assert vecs.shape == (len(texts), 4)


# ---------------------------------------------------------
# VectorIndex
# ---------------------------------------------------------


class DummyVectorIndex(mem_engine.VectorIndex):
    """VectorIndex のプロトコル確認用のダミー実装。

    - add: 内部辞書に id -> ベクトル を保存
    - search: クエリベクトルとの内積をスコアとして topk を返却
    """

    def __init__(self) -> None:
        self._store: Dict[str, np.ndarray] = {}

    def add(self, vecs: np.ndarray, ids: List[str]) -> None:
        assert vecs.shape[0] == len(ids)
        for i, _id in enumerate(ids):
            self._store[_id] = vecs[i]

    def search(self, vecs: np.ndarray, topk: int) -> List[List[tuple[str, float]]]:
        results: List[List[tuple[str, float]]] = []
        for q in vecs:
            # 内積ベースのスコア
            scores = [
                (key, float(np.dot(q, v))) for key, v in self._store.items()
            ]
            scores.sort(key=lambda x: x[1], reverse=True)
            results.append(scores[:topk])
        return results

    def save(self) -> None:
        # テスト用なので何もしない
        return None

    def load(self) -> None:
        # テスト用なので何もしない
        return None


def test_vector_index_add_and_search_roundtrip():
    """VectorIndex プロトコルが add/search で一応ラウンドトリップできること。"""
    emb = DummyEmbedder()
    index = DummyVectorIndex()

    texts = ["apple", "banana", "cherry"]
    vecs = emb.embed(texts)
    ids = [f"id_{i}" for i in range(len(texts))]

    index.add(vecs, ids)

    # 1件だけクエリする（apple に近いものを探す想定）
    query_vec = vecs[0:1]  # shape (1, D)
    results = index.search(query_vec, topk=2)

    # search は List[List[Tuple[str, float]]] を返す前提
    assert isinstance(results, list)
    assert len(results) == 1
    inner = results[0]
    assert isinstance(inner, list)
    assert len(inner) <= 2
    for _id, score in inner:
        assert isinstance(_id, str)
        assert isinstance(score, float)


# ---------------------------------------------------------
# MemoryStore
# ---------------------------------------------------------


class DummyMemoryStore(mem_engine.MemoryStore):
    """MemoryStore プロトコル確認用のダミー実装。

    - put: kind と item を保存し、単純な文字列 ID を返す
    - search: kinds フィルタと k 上限を効かせて返す
    """

    def __init__(self) -> None:
        self._items: Dict[str, Dict[str, Any]] = {}
        self._counter = 0

    def put(self, kind: str, item: Dict[str, Any]) -> str:
        self._counter += 1
        _id = f"{kind}_{self._counter}"
        stored = dict(item)
        stored["id"] = _id
        stored["kind"] = kind
        self._items[_id] = stored
        return _id

    def search(
        self,
        query: str,
        k: int = 8,
        kinds: Optional[List[str]] = None,
    ) -> Dict[str, List[Dict]]:
        # 単純に kinds でフィルタし、最大 k 件返すだけのダミー。
        kinds = kinds or ["episodic", "semantic", "skills"]
        result: Dict[str, List[Dict]] = {kind: [] for kind in kinds}
        for item in self._items.values():
            kind = item.get("kind")
            if kind in kinds and len(result[kind]) < k:
                result[kind].append(item)
        return result


def test_memory_store_put_and_search_with_kinds_filter():
    """MemoryStore の kinds フィルタと k 上限が一応動くことを確認。"""
    store = DummyMemoryStore()

    # 3種類の kind を登録
    store.put("episodic", {"content": "e1"})
    store.put("episodic", {"content": "e2"})
    store.put("semantic", {"content": "s1"})
    store.put("skills", {"content": "sk1"})

    res = store.search("dummy query", k=1, kinds=["episodic", "semantic"])

    # kinds で指定した key だけが存在する
    assert set(res.keys()) == {"episodic", "semantic"}
    # episodic/semantic とも最大 1 件までに制限されている
    assert len(res["episodic"]) <= 1
    assert len(res["semantic"]) <= 1
    # skills は返ってこない
    # （keys に含まれていないので length チェックせず）


