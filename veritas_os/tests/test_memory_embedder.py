# -*- coding: utf-8 -*-
"""
veritas_os.memory.embedder.HashEmbedder のテスト。

カバーするポイント:

- embed(["text"]) が (1, dim) の np.ndarray を返す
- 同じテキストは常に同じベクトル（決定的）
- 異なるテキストは基本的に異なるベクトル
- 各ベクトルは「平均 ≈ 0」「標準偏差 ≈ 1」に正規化されている
- 複数テキスト入力で (N, dim) になる
- 空リストを渡すと ValueError になる（現在の実装通り np.vstack([]) 
の挙動）
"""

from __future__ import annotations

import numpy as np
import pytest

from veritas_os.memory.embedder import HashEmbedder


def test_embed_single_shape_and_dtype():
    """1件入力で (1, dim) の float32 ベクトルが返る。"""
    dim = 16
    emb = HashEmbedder(dim=dim)

    vec = emb.embed(["hello"])

    assert isinstance(vec, np.ndarray)
    assert vec.shape == (1, dim)
    # 実装上 float32 のはず
    assert vec.dtype == np.float32


def test_embed_is_deterministic_for_same_text():
    """同じテキストは必ず同じベクトルになる（決定的）。"""
    emb = HashEmbedder(dim=32)

    v1 = emb.embed(["hello"])[0]
    v2 = emb.embed(["hello"])[0]

    assert np.allclose(v1, v2)


def test_embed_differs_for_different_texts():
    """異なるテキストはほぼ必ず異なるベクトルになる。"""
    emb = HashEmbedder(dim=32)

    v1, v2 = emb.embed(["hello", "world"])

    # 完全一致はほぼありえない前提
    assert not np.allclose(v1, v2)


def test_embed_vector_is_mean_zero_std_one_like():
    """
    _h 内で (v - mean)/std 正規化されているので、
    1ベクトルごとに mean ≈ 0, std ≈ 1 になっていることを確認。
    """
    emb = HashEmbedder(dim=64)

    vec = emb.embed(["some longish sample text for hashing"])[0]

    mean = float(vec.mean())
    std = float(vec.std())

    # だいたい 0 ± 1e-2 くらい
    assert abs(mean) < 1e-2
    # std は 1 ± 1e-2 程度（+1e-6 の補正がある）
    assert 0.98 < std < 1.02


def test_embed_multiple_texts_shape():
    """複数テキストで (N, dim) になる。"""
    emb = HashEmbedder(dim=24)
    texts = ["a", "b", "c"]

    vecs = emb.embed(texts)

    assert vecs.shape == (len(texts), 24)


def test_embed_empty_list_raises_value_error():
    """
    現状の実装では np.vstack([]) により ValueError が発生する。
    その挙動をテストで明示しておく。
    （後で空リスト対応を入れるなら、このテストを変更する）
    """
    emb = HashEmbedder(dim=16)

    with pytest.raises(ValueError):
        emb.embed([])

