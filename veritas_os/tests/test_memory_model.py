# veritas_os/tests/test_memory_model.py
# -*- coding: utf-8 -*-

import math

from veritas_os.core.models import memory_model as mm


# =========================================================
# _tokenize / _cosine のテスト
# =========================================================

def test_tokenize_basic_and_zenkaku_space():
    # 全角スペース + 大文字を含むケース
    text = "Hello　World  テスト"
    tokens = mm._tokenize(text)

    # 小文字化されていること
    assert "hello" in tokens
    assert "world" in tokens
    # 全角スペースも半角扱いになっていること（"テスト" が落ちていない）
    assert "テスト" in tokens

    # 空文字列でも安全に空リスト
    assert mm._tokenize("") == []


def test_cosine_with_empty_and_zero_norm_vectors():
    # どちらかが空 → 0.0
    assert mm._cosine({}, {"a": 1.0}) == 0.0
    assert mm._cosine({"a": 1.0}, {}) == 0.0

    # 要素はあるが全部 0.0 → ノルム 0 → 0.0
    a = {"x": 0.0}
    b = {"x": 1.0}
    assert mm._cosine(a, b) == 0.0

    # 正常なコサイン類似度（1.0 > 0.0）
    v1 = {"hello": 1.0, "world": 1.0}
    v2 = {"hello": 1.0, "there": 1.0}
    sim = mm._cosine(v1, v2)
    assert 0.0 < sim < 1.0


# =========================================================
# SimpleMemVec の基本動作
# =========================================================

def test_simple_mem_vec_add_and_encode_basic():
    mem = mm.SimpleMemVec()

    mid = mem.add(kind="semantic", text="Hello world hello", tags=["tag1"], 
meta={"foo": "bar"})
    assert isinstance(mid, str)

    # 内部状態を直接触るのはあまりよくないが、ここでは挙動確認用に使う
    assert len(mem._items) == 1
    item = mem._items[0]
    assert item.id == mid
    assert item.kind == "semantic"
    assert item.text == "Hello world hello"
    assert item.tags == ["tag1"]
    assert item.meta["foo"] == "bar"

    # _encode が Bag-of-Words 的にカウントしていること
    vec = item.vec
    assert vec["hello"] == 2.0
    assert vec["world"] == 1.0


def test_simple_mem_vec_add_with_default_kind_and_empty_meta_tags():
    mem = mm.SimpleMemVec()

    # kind=None, tags/meta 省略
    mid = mem.add(kind=None, text="some text")

    assert isinstance(mid, str)
    assert len(mem._items) == 1
    item = mem._items[0]
    # kind は str(kind or "semantic") なので "semantic" になる
    assert item.kind == "semantic"
    assert item.tags == []
    assert isinstance(item.meta, dict)
    assert item.meta == {}


# =========================================================
# search の挙動: kinds フィルタ / min_sim / k
# =========================================================

def _build_sample_memvec() -> mm.SimpleMemVec:
    mem = mm.SimpleMemVec()
    # 共有トークン "hello"
    mem.add(kind="semantic", text="hello world")
    mem.add(kind="semantic", text="hello there")
    # まったく違うテキスト
    mem.add(kind="note", text="completely different text")
    return mem


def test_search_basic_order_and_k_limit():
    mem = _build_sample_memvec()

    hits = mem.search(query="hello world", k=2, min_sim=0.0)

    # 上位 2 件だけ返る
    assert len(hits) == 2

    # もっとも似ているのは "hello world" 自身（score 1.0 のはず）
    scores = [h["score"] for h in hits]
    assert scores[0] >= scores[1]
    assert 0.0 <= scores[0] <= 1.0


def test_search_with_kinds_filter():
    mem = _build_sample_memvec()

    # kind="semantic" のみ対象
    hits_semantic = mem.search(query="hello", kinds=["semantic"], min_sim=0.0)
    assert len(hits_semantic) == 2
    assert all(h["kind"] == "semantic" for h in hits_semantic)

    # kind="note" のみ対象
    hits_note = mem.search(query="different", kinds=["note"], min_sim=0.0)
    assert len(hits_note) == 1
    assert hits_note[0]["kind"] == "note"


def test_search_min_sim_filters_low_similarity():
    mem = _build_sample_memvec()

    # query と全く関係ない単語 → min_sim デフォルト(0.25)ではマッチしない
    hits = mem.search(query="zzz-unrelated", k=10)
    assert hits == []

    # query と item がぴったり一致するケース → 高 min_sim にしても残る
    mem_exact = mm.SimpleMemVec()
    mem_exact.add(kind="semantic", text="exact match")
    hits_exact = mem_exact.search(query="exact match", min_sim=0.9)
    assert len(hits_exact) == 1
    assert math.isclose(hits_exact[0]["score"], 1.0, rel_tol=1e-9)


def test_search_with_empty_query_returns_no_hits_due_to_zero_vector():
    mem = _build_sample_memvec()

    # query="" → qv は空ベクトル → 類似度 0.0 → min_sim=0.25 ではヒットなし
    hits = mem.search(query="", k=10)
    assert hits == []


# =========================================================
# グローバルオブジェクト / predict_gate_label
# =========================================================

def test_global_mem_vec_is_simple_mem_vec():
    # グローバル MEM_VEC が SimpleMemVec のインスタンスであること
    assert isinstance(mm.MEM_VEC, mm.SimpleMemVec)

    # 実際に add / search が動くことも軽く確認
    mid = mm.MEM_VEC.add(kind="semantic", text="global memory item")
    assert isinstance(mid, str)

    hits = mm.MEM_VEC.search(query="global memory")
    # 類似度的に 0.25 以上になっていれば 1 件以上ヒットする
    assert isinstance(hits, list)


def test_predict_gate_label_is_neutral_and_does_not_use_mem_clf():
    # MEM_CLF が None でもエラーにならず、
    # 常に {"allow": 0.5} を返すことを保証
    assert mm.MEM_CLF is None

    out = mm.predict_gate_label("any text here")
    assert isinstance(out, dict)
    assert "allow" in out
    assert math.isclose(out["allow"], 0.5, rel_tol=1e-9)

    # 入力テキストを変えても今は同じ値（ニュートラル）であること
    out2 = mm.predict_gate_label("another text")
    assert math.isclose(out2["allow"], 0.5, rel_tol=1e-9)

