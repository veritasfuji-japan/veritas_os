# -*- coding: utf-8 -*-
"""
memory/index_cosine.py のテスト。

カバーするポイント:
- 初期化（path あり / なし）と size / vecs / ids の初期状態
- add:
    - 1D / 2D ベクトルの追加
    - dim mismatch / ids 長さ mismatch での ValueError
- search:
    - 空インデックス時の挙動（クエリ数だけ空リスト）
    - 1クエリ / 複数クエリ / k > size のときの挙動
    - 類似度順（cosine）で返ってきていること
- 永続化:
    - save → 再インスタンス化時に _load されるか
    - 壊れた npz の場合に例外を飲み込んで空からスタートするか
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import numpy as np
import pytest

from veritas_os.memory.index_cosine import CosineIndex


# ---------------------------------------------------------
# 初期化まわり
# ---------------------------------------------------------


def test_cosine_index_init_without_path():
    """path なしで初期化した場合、空インデックスからスタートする。"""
    idx = CosineIndex(dim=4)

    assert idx.dim == 4
    assert idx.path is None
    assert idx.size == 0
    assert isinstance(idx.vecs, np.ndarray)
    assert idx.vecs.shape == (0, 4)
    assert idx.ids == []


def test_cosine_index_init_with_nonexistent_path(tmp_path):
    """path あり & ファイル未存在 → _load は空インデックスのまま。"""
    p = tmp_path / "index.npz"
    assert not p.exists()

    idx = CosineIndex(dim=3, path=p)

    assert idx.dim == 3
    assert idx.path == p
    assert idx.size == 0
    assert idx.vecs.shape == (0, 3)
    assert idx.ids == []


@pytest.mark.parametrize("invalid_dim", [0, -1, 1.5, "2", None])
def test_cosine_index_init_with_invalid_dim_raises(invalid_dim):
    """dim が正の int でない場合は ValueError。"""
    with pytest.raises(ValueError) as exc:
        CosineIndex(dim=invalid_dim)  # type: ignore[arg-type]

    assert "dim must be a positive int" in str(exc.value)


def test_cosine_index_init_with_broken_npz(tmp_path):
    """
    path あり & 中身が壊れたファイル → 例外を飲み込んで空からスタート。
    """
    p = tmp_path / "broken_index.npz"
    # わざと npz ではない中身を書き込む
    p.write_text("this_is_not_npz", encoding="utf-8")

    idx = CosineIndex(dim=5, path=p)

    assert idx.dim == 5
    assert idx.path == p
    # 壊れていても empty にフォールバックしていること
    assert idx.size == 0
    assert idx.vecs.shape == (0, 5)
    assert idx.ids == []


def test_cosine_index_refuses_symlink_path(tmp_path):
    """シンボリックリンクの index path は安全上の理由で読み込まない。"""
    real = tmp_path / "real_index.npz"
    vecs = np.array([[1.0, 0.0]], dtype=np.float32)
    ids = np.array(["real"], dtype=str)
    np.savez(real, vecs=vecs, ids=ids)

    link = tmp_path / "index_link.npz"
    link.symlink_to(real)

    idx = CosineIndex(dim=2, path=link)

    assert idx.size == 0
    assert idx.vecs.shape == (0, 2)
    assert idx.ids == []


def test_cosine_index_refuses_non_regular_file_path(tmp_path):
    """ディレクトリを path に指定した場合は空インデックスにフォールバック。"""
    d = tmp_path / "not_a_file.npz"
    d.mkdir()

    idx = CosineIndex(dim=2, path=d)

    assert idx.size == 0
    assert idx.vecs.shape == (0, 2)
    assert idx.ids == []


def test_cosine_index_refuses_path_under_symlink_directory(tmp_path):
    """親ディレクトリがシンボリックリンクなら読み込みを拒否する。"""
    real_dir = tmp_path / "real_dir"
    real_dir.mkdir()
    link_dir = tmp_path / "linked_dir"
    link_dir.symlink_to(real_dir, target_is_directory=True)

    p = link_dir / "index.npz"
    vecs = np.array([[1.0, 0.0]], dtype=np.float32)
    ids = np.array(["a"], dtype=str)
    np.savez(p, vecs=vecs, ids=ids)

    idx = CosineIndex(dim=2, path=p)

    assert idx.size == 0
    assert idx.vecs.shape == (0, 2)
    assert idx.ids == []


def test_cosine_index_legacy_npz_is_always_rejected(tmp_path):
    """レガシーnpz(allow_pickleが必要)は常に拒否して空インデックスへフォールバック。"""
    p = tmp_path / "legacy_index.npz"
    vecs = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    ids = np.array(["a", "b"], dtype=object)
    np.savez(p, vecs=vecs, ids=ids)

    idx = CosineIndex(dim=2, path=p)

    assert idx.size == 0
    assert idx.vecs.shape == (0, 2)
    assert idx.ids == []


def test_cosine_index_load_dim_mismatch_resets_to_empty(tmp_path):
    """保存データの次元と指定 dim が不一致なら空インデックスに戻す。"""
    p = tmp_path / "index.npz"
    vecs = np.array([[1.0, 0.0, 0.0]], dtype=np.float32)
    ids = np.array(["x"], dtype=str)
    np.savez(p, vecs=vecs, ids=ids)

    idx = CosineIndex(dim=2, path=p)

    assert idx.size == 0
    assert idx.vecs.shape == (0, 2)


def test_cosine_index_load_propagates_unexpected_exception(monkeypatch, tmp_path):
    """Unexpected errors during load should propagate for visibility."""
    p = tmp_path / "index.npz"
    np.savez(p, vecs=np.array([[1.0, 0.0]], dtype=np.float32), ids=np.array(["a"], dtype=str))

    def _boom(*_args, **_kwargs):
        raise KeyboardInterrupt("stop")

    monkeypatch.setattr("veritas_os.memory.index_cosine.np.load", _boom)

    with pytest.raises(KeyboardInterrupt):
        CosineIndex(dim=2, path=p)


def test_cosine_index_load_ids_count_mismatch_resets_to_empty(tmp_path):
    """保存データの ids 数と vec 数が不一致なら空インデックスに戻す。"""
    p = tmp_path / "index.npz"
    vecs = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    ids = np.array(["x"], dtype=str)
    np.savez(p, vecs=vecs, ids=ids)

    idx = CosineIndex(dim=2, path=p)

    assert idx.size == 0
    assert idx.vecs.shape == (0, 2)
    assert idx.ids == []

# ---------------------------------------------------------
# add: ベクトル追加とエラーケース
# ---------------------------------------------------------


def test_add_single_vector_1d():
    """1D ベクトル + 単一 id でも追加できる。"""
    idx = CosineIndex(dim=3)
    v = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    idx.add(v, ids=["a"])

    assert idx.size == 1
    assert idx.vecs.shape == (1, 3)
    assert idx.ids == ["a"]


def test_add_multiple_vectors_2d(tmp_path):
    """2D ベクトル + 複数 id の追加と、その後の size / ids / vecs 
を確認。"""
    p = tmp_path / "index.npz"
    idx = CosineIndex(dim=2, path=p)

    vecs = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    idx.add(vecs, ids=["x", "y"])

    assert idx.size == 2
    assert idx.vecs.shape == (2, 2)
    assert idx.ids == ["x", "y"]
    # save が呼ばれているのでファイルが存在するはず
    assert p.exists()


def test_add_dim_mismatch_raises():
    """ベクトルの次元が dim と違う場合は ValueError。"""
    idx = CosineIndex(dim=4)
    vecs = np.ones((2, 3), dtype=np.float32)  # dim=3

    with pytest.raises(ValueError) as exc:
        idx.add(vecs, ids=["a", "b"])

    msg = str(exc.value)
    assert "dim mismatch" in msg
    assert "3 != 4" in msg


def test_add_with_invalid_rank_raises():
    """3次元配列は add で受け付けず ValueError。"""
    idx = CosineIndex(dim=2)
    vecs = np.ones((1, 1, 2), dtype=np.float32)

    with pytest.raises(ValueError) as exc:
        idx.add(vecs, ids=["a"])

    assert "vectors must be 1D or 2D" in str(exc.value)


def test_search_with_invalid_rank_raises():
    """3次元配列は search で受け付けず ValueError。"""
    idx = CosineIndex(dim=2)
    qv = np.ones((1, 1, 2), dtype=np.float32)

    with pytest.raises(ValueError) as exc:
        idx.search(qv, k=1)

    assert "vectors must be 1D or 2D" in str(exc.value)

def test_add_ids_length_mismatch_raises():
    """ids の長さと vecs.shape[0] が違う場合も ValueError。"""
    idx = CosineIndex(dim=2)
    vecs = np.ones((3, 2), dtype=np.float32)  # N=3

    with pytest.raises(ValueError) as exc:
        idx.add(vecs, ids=["a", "b"])  # len=2

    msg = str(exc.value)
    assert "len(ids)=2" in msg
    assert "vecs.shape[0]=3" in msg


# ---------------------------------------------------------
# search: 空インデックス / 基本挙動
# ---------------------------------------------------------


def test_search_on_empty_index_with_single_query():
    """
    size == 0 のとき、1D クエリは [[ ]] を返す。
    """
    idx = CosineIndex(dim=3)
    q = np.zeros(3, dtype=np.float32)

    res = idx.search(q, k=5)

    assert res == [[]]


def test_search_on_empty_index_with_multi_query():
    """
    size == 0 のとき、(Q, D) クエリは Q 個の空リストを返す。
    """
    idx = CosineIndex(dim=3)
    q = np.zeros((4, 3), dtype=np.float32)

    res = idx.search(q, k=5)

    assert isinstance(res, list)
    assert len(res) == 4
    for row in res:
        assert row == []


# ---------------------------------------------------------
# search: 類似度順 / k 制御
# ---------------------------------------------------------


def test_search_similarity_and_topk():
    """
    cosine 類似度に基づいてスコアが高い順に返っていること / k > size 
のときは size まで。
    """
    idx = CosineIndex(dim=3)

    # 3つの直交ベクトルを登録
    base_vecs = np.eye(3, dtype=np.float32)  # e1, e2, e3
    ids = ["e1", "e2", "e3"]
    idx.add(base_vecs, ids=ids)

    # e1 に近いクエリ（ほぼ e1、その次に e2, e3 が続く形）
    q = np.array([1.0, 0.1, 0.1], dtype=np.float32)
    res = idx.search(q, k=10)  # k > size

    # クエリは 1 つなので res は 1 リストだけ
    assert len(res) == 1
    row = res[0]

    # size=3 なので 3 件まで
    assert len(row) == 3

    # 1番目は e1 であるべき
    first_id, first_score = row[0]
    assert first_id == "e1"
    assert isinstance(first_score, float)

    # スコアは降順になっている
    scores = [s for _, s in row]
    assert scores == sorted(scores, reverse=True)


def test_search_multi_query_returns_same_length_as_queries():
    """複数クエリを渡した場合、クエリ数と同じ長さのリストが返る。"""
    idx = CosineIndex(dim=2)
    vecs = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    idx.add(vecs, ids=["x", "y"])

    queries = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)  # Q=2
    res = idx.search(queries, k=1)

    assert len(res) == 2
    # 1件だけ返っている
    assert len(res[0]) == 1
    assert len(res[1]) == 1
    # それぞれ最も近い id が返っている
    assert res[0][0][0] == "x"
    assert res[1][0][0] == "y"


def test_search_dim_mismatch_raises():
    """クエリ次元が index.dim と異なる場合は ValueError。"""
    idx = CosineIndex(dim=3)
    idx.add(np.array([[1.0, 0.0, 0.0]], dtype=np.float32), ids=["a"])

    with pytest.raises(ValueError) as exc:
        idx.search(np.array([1.0, 0.0], dtype=np.float32), k=1)

    msg = str(exc.value)
    assert "dim mismatch" in msg
    assert "2 != 3" in msg


def test_search_invalid_k_raises():
    """k が 1 未満の場合は ValueError。"""
    idx = CosineIndex(dim=2)
    idx.add(np.array([[1.0, 0.0]], dtype=np.float32), ids=["x"])

    with pytest.raises(ValueError) as exc:
        idx.search(np.array([1.0, 0.0], dtype=np.float32), k=0)

    assert "k must be >= 1" in str(exc.value)


@pytest.mark.parametrize("invalid_k", [1.2, "2", None, True])
def test_search_non_integer_k_raises(invalid_k):
    """k が int 以外（および bool）の場合は ValueError。"""
    idx = CosineIndex(dim=2)
    idx.add(np.array([[1.0, 0.0]], dtype=np.float32), ids=["x"])

    with pytest.raises(ValueError) as exc:
        idx.search(np.array([1.0, 0.0], dtype=np.float32), k=invalid_k)  # type: ignore[arg-type]

    assert "k must be an int" in str(exc.value)


def test_search_tie_scores_keep_insertion_order():
    """同点スコアでは挿入順序を維持して結果を返す。"""
    idx = CosineIndex(dim=2)
    idx.add(np.array([[1.0, 0.0], [1.0, 0.0]], dtype=np.float32), ids=["first", "second"])

    res = idx.search(np.array([1.0, 0.0], dtype=np.float32), k=2)

    assert [item_id for item_id, _ in res[0]] == ["first", "second"]


# ---------------------------------------------------------
# 永続化: save / _load のラウンドトリップ
# ---------------------------------------------------------


def test_save_and_reload_roundtrip(tmp_path):
    """
    add → save → 新しいインスタンスで path を指定 → _load 
されていること。
    """
    p = tmp_path / "cosine_idx.npz"

    # 1つ目のインスタンスで add & save
    idx1 = CosineIndex(dim=2, path=p)
    vecs1 = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    ids1: List[str] = ["a", "b"]
    idx1.add(vecs1, ids=ids1)

    assert p.exists()
    assert idx1.size == 2

    # 2つ目のインスタンスでは __init__ 中に _load が呼ばれる
    idx2 = CosineIndex(dim=2, path=p)

    assert idx2.size == 2
    assert idx2.ids == ids1
    # ベクトルも同じ形・値でロードされているはず
    assert idx2.vecs.shape == vecs1.shape
    assert np.allclose(idx2.vecs, vecs1.astype(np.float32))


def test_save_noop_when_path_is_none():
    """
    path が None の場合、save は何もしない（例外が出ないことだけ確認）。
    """
    idx = CosineIndex(dim=3)
    # 何も追加していない状態で save() を呼んでもノーエラー
    idx.save()
