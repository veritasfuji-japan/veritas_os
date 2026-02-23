# -*- coding: utf-8 -*-
"""
memory/store.py のテスト。

カバーするポイント:

- __init__ / _boot:
    - FILES / INDEX を tmp_path に差し替えた状態で初期化できる
    - 既存の JSONL から index（FakeIndex）を再構築する

- put:
    - JSONL に 1 行追記される
    - id / ts / tags / text / meta の構造確認
    - embed が呼ばれ、idx.add が正しい shape と id で呼ばれる

- search:
    - 空文字列 / 空白のみのクエリなら {} を返す（embed も search 
も呼ばれない）
    - topk 引数が k を上書きする
    - min_sim でスコアがフィルタされる（低スコアは落とされる）
    - kinds 引数で対象 kind を絞れる
    - index.search が例外を投げても安全に out[kind] = [] で返す

- put_episode:
    - kind="episodic" で MemoryStore.put に委譲される
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pytest


# ---------------------------------------------------------
# 共通フィクスチャ: FILES / INDEX / HashEmbedder / CosineIndex を差し替え
# ---------------------------------------------------------


@pytest.fixture
def memory_env(tmp_path, monkeypatch):
    """
    store.py 内の FILES / INDEX を tmp_path に向けつつ、
    HashEmbedder / CosineIndex をテスト用のフェイクに差し替える。

    各テストは:store, files, index_paths, FakeIndex, FakeEmbedder = memory_env
    の形で受け取って使う。
    """
    import veritas_os.memory.store as store

    # kind ごとの JSONL / index ファイルを tmp_path 配下に置く
    kinds = ["episodic", "semantic", "skills"]
    files: Dict[str, Path] = {k: tmp_path / f"{k}.jsonl" for k in kinds}
    index_paths: Dict[str, Path] = {k: tmp_path / f"{k}.index.npz" for k in kinds}

    monkeypatch.setattr(store, "FILES", files, raising=False)
    monkeypatch.setattr(store, "INDEX", index_paths, raising=False)

    # ---- Fake HashEmbedder ----
    class FakeEmbedder:
        def __init__(self, dim: int = 4):
            self.dim = dim
            self.calls: List[List[str]] = []

        def embed(self, texts: List[str]) -> np.ndarray:
            # 呼び出しログだけ残して、全て 1 のベクトルを返す（cosine = 1）
            self.calls.append(list(texts))
            return np.ones((len(texts), self.dim), dtype=np.float32)

    # ---- Fake CosineIndex ----
    class FakeIndex:
        """
        MemoryStore 側から見た最低限のインターフェース + ログ用。
        """

        def __init__(self, dim: int, path: Path):
            self.dim = dim
            self.path = Path(path)
            self.add_calls: List[Tuple[np.ndarray, List[str]]] = []
            self.search_calls: List[Tuple[np.ndarray, int]] = []
            self._size = 0
            # テストから上書きすることで search の戻り値を制御できる
            self._search_result: Any = None

        @property
        def size(self) -> int:
            return self._size

        def add(self, vecs: Any, ids: List[str]):
            arr = np.asarray(vecs, dtype=np.float32)
            self.add_calls.append((arr, list(ids)))
            self._size += len(ids)

        def search(self, qv: Any, k: int = 8):
            q = np.asarray(qv, dtype=np.float32)
            self.search_calls.append((q, k))
            if self._search_result is not None:
                return self._search_result
            # デフォルトではヒットなし
            return [[]]

    monkeypatch.setattr(store, "HashEmbedder", FakeEmbedder, raising=False)
    monkeypatch.setattr(store, "CosineIndex", FakeIndex, raising=False)

    return store, files, index_paths, FakeIndex, FakeEmbedder


# ---------------------------------------------------------
# _boot: 既存 JSONL から index 再構築
# ---------------------------------------------------------


def test_boot_rebuilds_index_from_existing_jsonl(memory_env):
    """
    _boot が:
      - 既存 episodic.jsonl から id / text(or summary) を読み取り
      - embed を 1 回呼び
      - FakeIndex.add にまとめて渡す
    ことを確認。
    """
    store, files, index_paths, FakeIndex, FakeEmbedder = memory_env

    # episodic の JSONL を事前に作成
    items = [
        {"id": "e1", "text": "first text", "tags": [], "meta": {}, "ts": 1.0},
        # text が無くても summary から拾えるか
        {"id": "e2", "summary": "summary text", "tags": [], "meta": {}, "ts": 2.0},
    ]
    with open(files["episodic"], "w", encoding="utf-8") as f:
        for it in items:
            json.dump(it, f, ensure_ascii=False)
            f.write("\n")

    # 初期化 → _boot が走る
    ms = store.MemoryStore(dim=4)

    # embed は 1 回、2件分呼ばれているはず
    assert isinstance(ms.emb, FakeEmbedder)
    assert len(ms.emb.calls) == 1
    assert set(ms.emb.calls[0]) == {"first text", "summary text"}

    idx_ep = ms.idx["episodic"]
    assert isinstance(idx_ep, FakeIndex)
    # add は 1 回、2件分
    assert len(idx_ep.add_calls) == 1
    vecs, ids = idx_ep.add_calls[0]
    assert vecs.shape == (2, ms.emb.dim)
    assert set(ids) == {"e1", "e2"}
    assert idx_ep.size == 2


# ---------------------------------------------------------
# put: JSONL 書き込み + index 追加
# ---------------------------------------------------------


def test_put_appends_jsonl_and_updates_index(memory_env):
    """
    put:
      - JSONL に 1 行追記する
      - id / ts / text / tags / meta のフィールドを持つ
      - emb.embed / idx.add が正しく呼ばれている
    """
    store, files, index_paths, FakeIndex, FakeEmbedder = memory_env

    ms = store.MemoryStore(dim=4)

    item_id = ms.put(
        "episodic",
        {"text": "hello world", "tags": ["t1"], "meta": {"foo": "bar"}},
    )

    assert isinstance(item_id, str) and item_id

    # JSONL に 1 行だけ書かれている
    content = files["episodic"].read_text(encoding="utf-8").splitlines()
    assert len(content) == 1
    row = json.loads(content[0])

    assert row["id"] == item_id
    assert row["text"] == "hello world"
    assert row["tags"] == ["t1"]
    assert row["meta"] == {"foo": "bar"}
    assert isinstance(row["ts"], (int, float))

    # embed は 1 回、テキスト1件で呼ばれている
    assert len(ms.emb.calls) >= 1
    assert ms.emb.calls[-1] == ["hello world"]

    # index.add も 1 回、id 1件・ベクトル shape=(1, dim) で呼ばれている
    idx_ep = ms.idx["episodic"]
    assert isinstance(idx_ep, FakeIndex)
    assert len(idx_ep.add_calls) >= 1
    vecs, ids = idx_ep.add_calls[-1]
    assert vecs.shape == (1, ms.emb.dim)
    assert ids == [item_id]


def test_put_rejects_too_long_text(memory_env):
    """put は過大な text を拒否して ValueError を送出する。"""
    store, files, index_paths, FakeIndex, FakeEmbedder = memory_env

    ms = store.MemoryStore(dim=4)
    too_long = "x" * (store.MAX_ITEM_TEXT_LENGTH + 1)

    with pytest.raises(ValueError, match="Item text too long"):
        ms.put("episodic", {"text": too_long, "tags": [], "meta": {}})


def test_put_validates_tags_and_meta_types(memory_env):
    """put は tags / meta の型不正を拒否する。"""
    store, files, index_paths, FakeIndex, FakeEmbedder = memory_env

    ms = store.MemoryStore(dim=4)

    with pytest.raises(TypeError, match="item.tags must be a list"):
        ms.put("episodic", {"text": "ok", "tags": "not-list", "meta": {}})

    with pytest.raises(TypeError, match="item.meta must be a dict"):
        ms.put("episodic", {"text": "ok", "tags": [], "meta": "not-dict"})


def test_put_validates_tags_constraints(memory_env):
    """put は tags の件数・要素長・空要素を検証する。"""
    store, files, index_paths, FakeIndex, FakeEmbedder = memory_env

    ms = store.MemoryStore(dim=4)

    too_many_tags = [f"t{i}" for i in range(store.MAX_TAGS_PER_ITEM + 1)]
    with pytest.raises(ValueError, match="item.tags too many"):
        ms.put("episodic", {"text": "ok", "tags": too_many_tags, "meta": {}})

    too_long_tag = "x" * (store.MAX_TAG_LENGTH + 1)
    with pytest.raises(ValueError, match="item.tags element too long"):
        ms.put("episodic", {"text": "ok", "tags": [too_long_tag], "meta": {}})

    with pytest.raises(ValueError, match="item.tags must not contain empty values"):
        ms.put("episodic", {"text": "ok", "tags": ["   "], "meta": {}})


def test_put_validates_id_shape_and_length(memory_env):
    """put は不正な id 形状と過剰長 id を拒否する。"""
    store, files, index_paths, FakeIndex, FakeEmbedder = memory_env

    ms = store.MemoryStore(dim=4)

    with pytest.raises(TypeError, match="item.id must be a scalar value"):
        ms.put("episodic", {"id": {"bad": "id"}, "text": "ok", "tags": [], "meta": {}})

    with pytest.raises(ValueError, match="item.id must not be empty"):
        ms.put("episodic", {"id": "   ", "text": "ok", "tags": [], "meta": {}})

    too_long_id = "a" * (store.MAX_ITEM_ID_LENGTH + 1)
    with pytest.raises(ValueError, match="item.id too long"):
        ms.put("episodic", {"id": too_long_id, "text": "ok", "tags": [], "meta": {}})


def test_put_normalizes_scalar_id(memory_env):
    """put は scalar な id を文字列に正規化して保存する。"""
    store, files, index_paths, FakeIndex, FakeEmbedder = memory_env

    ms = store.MemoryStore(dim=4)
    item_id = ms.put("episodic", {"id": 42, "text": "hello", "tags": [], "meta": {}})

    assert item_id == "42"
    content = files["episodic"].read_text(encoding="utf-8").splitlines()
    row = json.loads(content[0])
    assert row["id"] == "42"


# ---------------------------------------------------------
# search: 空クエリ
# ---------------------------------------------------------


def test_search_empty_query_returns_empty_dict(memory_env):
    """
    query が空文字列 / 空白のみの場合は {} を返し、
    embed / index.search は呼ばれない。
    """
    store, files, index_paths, FakeIndex, FakeEmbedder = memory_env

    ms = store.MemoryStore(dim=4)

    # _boot で embed が呼ばれていない前提（JSONL なし）
    assert ms.emb.calls == []

    res1 = ms.search("", kinds=["episodic"])
    res2 = ms.search("   ", kinds=["episodic"])

    assert res1 == {}
    assert res2 == {}
    # 依然として emb.embed / index.search は呼ばれていない
    assert ms.emb.calls == []
    assert ms.idx["episodic"].search_calls == []


# ---------------------------------------------------------
# search: topk / min_sim / kinds
# ---------------------------------------------------------


def test_search_uses_topk_and_min_sim_and_kinds(memory_env):
    """
    - topk が k を上書きして idx.search に渡る
    - min_sim より低い score は除外される
    - kinds で対象 kind を絞れる
    """
    store, files, index_paths, FakeIndex, FakeEmbedder = memory_env

    # episodic JSONL に2件登録
    base_items = [
        {"id": "high", "text": "high score", "tags": [], "meta": {}, "ts": 1.0},
        {"id": "low", "text": "low score", "tags": [], "meta": {}, "ts": 2.0},
    ]
    with open(files["episodic"], "w", encoding="utf-8") as f:
        for it in base_items:
            json.dump(it, f, ensure_ascii=False)
            f.write("\n")

    ms = store.MemoryStore(dim=4)

    # index 側の search 戻り値を上書き:
    #   high: 0.9, low: 0.1 → min_sim=0.25 で low は落とされる
    idx_ep = ms.idx["episodic"]
    idx_ep._search_result = [[("high", 0.9), ("low", 0.1)]]

    res = ms.search(
        "some query",
        topk=5,                 # k=5 に上書きされるはず
        kinds=["episodic"],
        min_sim=0.25,
    )

    # 結果は episodic のみ / high のみ
    assert set(res.keys()) == {"episodic"}
    hits = res["episodic"]
    assert len(hits) == 1
    hit = hits[0]
    assert hit["id"] == "high"
    assert hit["text"] == "high score"
    assert hit["score"] == pytest.approx(0.9)

    # idx.search が 1 回、k=5 で呼ばれている
    assert len(idx_ep.search_calls) == 1
    _, k_used = idx_ep.search_calls[0]
    assert k_used == 5


# ---------------------------------------------------------
# search: index.search が例外を投げたときのフォールバック
# ---------------------------------------------------------




def test_search_normalizes_min_sim_invalid_or_out_of_range(memory_env):
    """search は min_sim を有限な [0,1] に正規化する。"""
    store, files, index_paths, FakeIndex, FakeEmbedder = memory_env

    base_items = [
        {"id": "high", "text": "high score", "tags": [], "meta": {}, "ts": 1.0},
        {"id": "low", "text": "low score", "tags": [], "meta": {}, "ts": 2.0},
    ]
    with open(files["episodic"], "w", encoding="utf-8") as f:
        for it in base_items:
            json.dump(it, f, ensure_ascii=False)
            f.write("\n")

    ms = store.MemoryStore(dim=4)
    idx_ep = ms.idx["episodic"]
    idx_ep._search_result = [[("high", 0.9), ("low", 0.1)]]

    # 文字列などの不正値はデフォルト 0.25 扱いになる
    res_invalid = ms.search("query", kinds=["episodic"], min_sim="invalid")
    assert [item["id"] for item in res_invalid["episodic"]] == ["high"]

    # 負値は 0.0 に clamp されるので low も残る
    res_negative = ms.search("query", kinds=["episodic"], min_sim=-5)
    assert [item["id"] for item in res_negative["episodic"]] == ["high", "low"]

    # 1.0 超は 1.0 に clamp されるので全件除外される
    res_large = ms.search("query", kinds=["episodic"], min_sim=2.0)
    assert res_large["episodic"] == []


def test_search_normalizes_min_sim_non_finite(memory_env):
    """search は NaN/inf の min_sim を安全な既定値にフォールバックする。"""
    store, files, index_paths, FakeIndex, FakeEmbedder = memory_env

    with open(files["episodic"], "w", encoding="utf-8") as f:
        json.dump(
            {"id": "high", "text": "high score", "tags": [], "meta": {}, "ts": 1.0},
            f,
            ensure_ascii=False,
        )
        f.write("\n")

    ms = store.MemoryStore(dim=4)
    idx_ep = ms.idx["episodic"]
    idx_ep._search_result = [[("high", 0.9)]]

    res_nan = ms.search("query", kinds=["episodic"], min_sim=float("nan"))
    assert [item["id"] for item in res_nan["episodic"]] == ["high"]

    res_inf = ms.search("query", kinds=["episodic"], min_sim=float("inf"))
    assert [item["id"] for item in res_inf["episodic"]] == ["high"]

def test_search_handles_index_error_gracefully(memory_env, monkeypatch):
    """
    idx.search が例外を投げても:
        - その kind は [] として扱われ
        - 全体として正常に Dict[str, List] を返す
    """
    store, files, index_paths, FakeIndex, FakeEmbedder = memory_env

    ms = store.MemoryStore(dim=4)

    # episodic の index.search を壊す
    def broken_search(self, qv, k=8):
        raise RuntimeError("boom")

    monkeypatch.setattr(FakeIndex, "search", broken_search, raising=False)

    res = ms.search("query", kinds=["episodic"])

    # 例外を飲み込んで空リストを返している
    assert "episodic" in res
    assert res["episodic"] == []


# ---------------------------------------------------------
# put_episode: kind="episodic" で put に委譲
# ---------------------------------------------------------


def test_put_episode_delegates_to_put(memory_env, monkeypatch):
    """
    put_episode が kind="episodic" で MemoryStore.put に委譲しているか。
    """
    store, files, index_paths, FakeIndex, FakeEmbedder = memory_env

    calls: Dict[str, Any] = {}

    def fake_put(self, kind: str, item: Dict[str, Any]) -> str:
        calls["kind"] = kind
        calls["item"] = item
        return "fake-id"

    monkeypatch.setattr(store.MemoryStore, "put", fake_put, raising=False)

    ms = store.MemoryStore(dim=4)
    rid = ms.put_episode("episode text", tags=["tag1"], meta={"foo": 
"bar"})

    assert rid == "fake-id"
    assert calls["kind"] == "episodic"

    it = calls["item"]
    assert it["text"] == "episode text"
    assert it["tags"] == ["tag1"]
    assert it["meta"] == {"foo": "bar"}
    # ts は put_episode 側で埋められている
    assert isinstance(it["ts"], (int, float))
