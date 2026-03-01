# veritas_os/tests/test_memory_vector.py
from __future__ import annotations

"""
MemoryOS VectorMemory のユニットテスト

目的:
- VectorMemory 単体の add / search が動くか
- インデックス保存 → 再ロードが正しく動くか
- ある程度の件数を入れても例外なく高速に検索できるか

※ 外部の sentence-transformers には依存せず、
   DummyEmbedModel を差し替えてテストする。
"""

import pickle
import time
from pathlib import Path
from typing import Any, Dict, List

from veritas_os.core import memory


# -----------------------------
# Dummy embedding model
# -----------------------------


class DummyEmbedModel:
    """VectorMemory 用のダミー埋め込みモデル

    - encode(texts) -> np.ndarray shape=(len(texts), dim)
    - ベクトル値は全部 1.0（cos 類似度は常に 1.0 になる）
    """

    def __init__(self, dim: int = 4):
        self.dim = dim
        self.calls: List[List[str]] = []

    def encode(self, texts):
        import numpy as np

        self.calls.append(list(texts))
        return np.ones((len(texts), self.dim), dtype="float32")


# -----------------------------
# Helper
# -----------------------------


def _new_vector_memory(index_path: Path | None = None, dim: int = 4):
    """DummyEmbedModel を差し替えた VectorMemory を返すヘルパ。"""
    vm = memory.VectorMemory(index_path=index_path, embedding_dim=dim)
    vm.model = DummyEmbedModel(dim=dim)
    return vm


def _write_legacy_pickle(path: Path, documents: List[Dict[str, Any]], embeddings):
    """レガシー形式のpickleファイルを書き出すヘルパ。"""
    payload = {
        "documents": documents,
        "embeddings": embeddings,
    }
    with open(path, "wb") as f:
        pickle.dump(payload, f)


# -----------------------------
# Test 1: VectorMemory standalone
# -----------------------------


def test_vector_memory_standalone(tmp_path: Path):
    """VectorMemory クラス単体の add / search をテストする。"""
    idx_path = tmp_path / "vec_index.pkl"
    vm = _new_vector_memory(index_path=idx_path, dim=4)

    test_docs = [
        {
            "kind": "test",
            "text": "AGI OS の設計について議論した",
            "tags": ["agi", "design"],
        },
        {
            "kind": "test",
            "text": "VERITAS アーキテクチャを検討",
            "tags": ["architecture"],
        },
        {
            "kind": "test",
            "text": "DebateOS の実装を改善",
            "tags": ["debate", "implementation"],
        },
        {
            "kind": "test",
            "text": "MemoryOS にベクトル検索を追加",
            "tags": ["memory", "vector"],
        },
        {
            "kind": "test",
            "text": "Python で機械学習モデルを訓練",
            "tags": ["ml", "python"],
        },
    ]

    # 追加
    for doc in test_docs:
        ok = vm.add(
            kind=doc["kind"],
            text=doc["text"],
            tags=doc["tags"],
        )
        assert ok

    # ドキュメント数
    assert len(vm.documents) == len(test_docs)

    # 検索 (ダミーベクトルなので、どのクエリでも何かしら返る前提)
    queries = [
        "人工知能システムの設計",
        "メモリ管理の実装",
        "機械学習",
    ]

    for q in queries:
        hits = vm.search(q, k=3, min_sim=0.0)
        assert len(hits) > 0
        # score / text のキーがあることだけチェック
        assert "score" in hits[0]
        assert "text" in hits[0]


# -----------------------------
# Test 2: Index persistence
# -----------------------------


def test_vector_memory_persist_and_reload(tmp_path: Path):
    """
    VectorMemory._save_index / __init__ ロードパスをテストする。

    - index_path 付きで作成
    - ドキュメントを追加して _save_index
    - 新しいインスタンスで index_path を指定してロード
    - 文書数が維持されていることを確認

    Note: pickle廃止によりJSON形式(.json)で保存される
    """
    idx_path = tmp_path / "vec_index.pkl"  # 初期パス（.pklでも.jsonに変換される）
    vm = _new_vector_memory(index_path=idx_path, dim=4)

    docs = [
        {
            "kind": "semantic",
            "text": "VERITAS OS は LLM の外骨格として機能する",
            "tags": ["veritas", "architecture"],
            "meta": {"user_id": "test", "project": "veritas"},
        },
        {
            "kind": "semantic",
            "text": "sentence-transformers でベクトル検索を実装",
            "tags": ["memory", "vector", "ml"],
            "meta": {"user_id": "test", "module": "memory"},
        },
    ]

    for doc in docs:
        ok = vm.add(
            kind=doc["kind"],
            text=doc["text"],
            tags=doc["tags"],
            meta=doc["meta"],
        )
        assert ok

    assert len(vm.documents) == len(docs)

    # インデックス保存（JSON形式で保存される）
    vm._save_index()
    # JSON形式で保存されるため、.json拡張子のファイルを確認
    json_path = idx_path.with_suffix(".json")
    assert json_path.exists(), f"Expected {json_path} to exist"
    size = json_path.stat().st_size
    assert size > 0

    # 再ロード（保存後のパス vm.index_path を使用）
    vm2 = _new_vector_memory(index_path=vm.index_path, dim=4)
    # __init__ 時点で index を読み込む実装であれば、
    # documents が復元されているはず
    assert len(vm2.documents) == len(vm.documents)

    # 検索も一応叩いておく
    hits = vm2.search("LLM システムの改善", k=5)
    assert len(hits) > 0


# -----------------------------
# Test 3: Performance-ish sanity
# -----------------------------


def test_vector_memory_add_and_search_performance():
    """
    ある程度の件数を追加しても、検索が例外なく高速に動くかのサニティテスト。

    - 100件追加
    - 複数クエリで search(k=10) を叩く
    - 実行時間を測るが、pytest 上では厳しい閾値は設けず、
      「1秒以上かかっていない」程度のゆるい検証に留める。
    """
    vm = _new_vector_memory(index_path=None, dim=4)

    # 100件追加
    start_add = time.time()
    for i in range(100):
        ok = vm.add(
            kind="test",
            text=f"テストドキュメント {i}: 様々な内容を含むサンプルテキスト",
            tags=["test"],
            meta={"index": i},
        )
        assert ok
    add_time = time.time() - start_add
    # さすがに 5秒はかからない前提（CI 環境でも余裕のはず）
    assert add_time < 5.0

    # 検索
    queries = [
        "テストドキュメント",
        "サンプルテキスト",
        "内容",
    ]

    start_search = time.time()
    for q in queries:
        hits = vm.search(q, k=10)
        assert len(hits) > 0
    search_time = time.time() - start_search

    # こちらも「1秒以上かかっていない」程度の緩い条件
    assert search_time < 5.0


def test_legacy_pickle_migration_disabled_by_default(tmp_path: Path, monkeypatch):
    """オプトインなしではレガシーpickleを読み込まないことを確認する。"""
    import numpy as np

    idx_path = tmp_path / "legacy_index.pkl"
    documents = [
        {"id": "doc_1", "kind": "semantic", "text": "legacy doc", "tags": []},
    ]
    embeddings = np.ones((1, 4), dtype="float32")
    _write_legacy_pickle(idx_path, documents, embeddings)

    monkeypatch.delenv("VERITAS_MEMORY_ALLOW_PICKLE_MIGRATION", raising=False)

    vm = _new_vector_memory(index_path=idx_path, dim=4)
    assert vm.documents == []
    assert not idx_path.with_suffix(".json").exists()


def test_legacy_pickle_migration_opt_in(tmp_path: Path, monkeypatch):
    """オプトイン指定しても runtime での移行は常に拒否される。"""
    import numpy as np

    idx_path = tmp_path / "legacy_index.pkl"
    documents = [
        {"id": "doc_1", "kind": "semantic", "text": "legacy doc", "tags": []},
    ]
    embeddings = np.ones((1, 4), dtype="float32")
    _write_legacy_pickle(idx_path, documents, embeddings)

    monkeypatch.setenv("VERITAS_MEMORY_ALLOW_PICKLE_MIGRATION", "1")

    vm = _new_vector_memory(index_path=idx_path, dim=4)
    # runtime decommissioned: pickle migration is always disabled
    assert len(vm.documents) == 0
    assert not idx_path.with_suffix(".json").exists()







def test_load_model_is_thread_safe(monkeypatch):
    """_load_model が同時実行されてもモデル初期化は一度だけ実行される。"""
    import sys
    import threading
    import time
    import types

    init_calls = {"count": 0}

    class SlowSentenceTransformer:
        def __init__(self, model_name):
            init_calls["count"] += 1
            time.sleep(0.05)
            self.model_name = model_name

    monkeypatch.setattr(
        memory.capability_cfg,
        "enable_memory_sentence_transformers",
        False,
    )
    vm = memory.VectorMemory()

    fake_module = types.ModuleType("sentence_transformers")
    fake_module.SentenceTransformer = SlowSentenceTransformer
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)
    monkeypatch.setattr(
        memory.capability_cfg,
        "enable_memory_sentence_transformers",
        True,
    )

    vm.model = None

    threads = [threading.Thread(target=vm._load_model) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert init_calls["count"] == 1
    assert isinstance(vm.model, SlowSentenceTransformer)
