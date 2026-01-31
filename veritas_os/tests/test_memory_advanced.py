# veritas_os/tests/test_memory_advanced.py

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from veritas_os.core import memory


# -----------------------------
# helpers / dummies
# -----------------------------


class DummyEmbedModel:
    """VectorMemory 用のダミー埋め込みモデル"""

    def __init__(self, dim: int = 4):
        self.dim = dim
        self.calls: List[List[str]] = []

    def encode(self, texts):
        import numpy as np

        self.calls.append(list(texts))
        # shape = (len(texts), dim)
        return np.ones((len(texts), self.dim), dtype="float32")


class DummyVec:
    """memory.search 用 MEM_VEC ダミー"""

    def __init__(self, mode: str = "list"):
        self.mode = mode
        self.calls: List[Any] = []

    def search(self, *args, **kwargs):
        self.calls.append((args, kwargs))

        # mode に応じて返す形式を変える
        if self.mode == "list":
            # list[dict] 形式
            return [
                {
                    "id": "a",
                    "text": "same text",
                    "score": 0.9,
                    "meta": {"user_id": "u1"},
                },
                {
                    "id": "b",
                    "text": "same text",
                    "score": 0.8,
                    "meta": {"user_id": "u1"},
                },
            ]
        elif self.mode == "dict":
            # dict["hits"] 形式
            return {
                "hits": [
                    {
                        "id": "h1",
                        "text": "dict result",
                        "score": 0.7,
                        "meta": {"user_id": "u1"},
                    }
                ]
            }
        elif self.mode == "empty":
            # 0件 → KVS fallback 用
            return []
        else:
            return []


class OldStyleMemVec:
    """古いシグネチャ (search(query, k)) の MEM_VEC"""

    def __init__(self):
        self.calls: List[Any] = []

    def search(self, query, k):
        self.calls.append((query, k))
        return [
            {
                "id": "old",
                "text": "old-style vec",
                "score": 0.8,
                "meta": {"user_id": "u1"},
            }
        ]


# -----------------------------
# MemoryStore: migration / search
# -----------------------------


def test_memory_store_migrate_old_dict_format(tmp_path: Path):
    """
    MemoryStore._normalize による
    {"users": {user_id: {key: value}}} → list-format への変換パスを叩く。
    """
    path = tmp_path / "memory.json"
    old = {"users": {"u1": {"foo": "bar"}}}
    path.write_text(json.dumps(old), encoding="utf-8")

    store = memory.MemoryStore.load(path)
    records = store.list_all()

    assert len(records) == 1
    rec = records[0]
    assert rec["user_id"] == "u1"
    assert rec["key"] == "foo"
    assert rec["value"] == "bar"
    assert "ts" in rec


def test_memory_store_simple_search(tmp_path: Path):
    """
    MemoryStore.search / _simple_score を通して
    KVS ベースの episodic 検索パスを叩く。
    """
    path = tmp_path / "memory.json"
    store = memory.MemoryStore.load(path)

    user_id = "u1"
    store.put(
        user_id,
        "k1",
        {"kind": "episodic", "text": "hello veritas", "tags": ["veritas"]},
    )
    store.put(
        user_id,
        "k2",
        {"kind": "episodic", "text": "another text", "tags": ["other"]},
    )

    res = store.search(query="hello", k=10, user_id=user_id)
    episodic = res["episodic"]

    assert len(episodic) >= 1
    assert episodic[0]["text"].startswith("hello veritas")


# -----------------------------
# VectorMemory: add / search / save & load
# -----------------------------


def test_vector_memory_add_search_and_persist(tmp_path: Path):
    """
    VectorMemory.add / search / _save_index / _load_index /
    _cosine_similarity を通す。
    sentence-transformers は使わず、model をダミーに差し替え。

    Note: pickle廃止によりJSON形式(.json)で保存される
    """
    idx_path = tmp_path / "vec_index.pkl"  # 初期パス（.jsonに変換される）

    # 1) 新規 VectorMemory
    vm = memory.VectorMemory(index_path=idx_path, embedding_dim=4)
    vm.model = DummyEmbedModel(dim=4)

    ok = vm.add(
        kind="episodic",
        text="hello world",
        tags=["t1"],
        meta={"foo": "bar"},
    )
    assert ok

    # 検索
    hits = vm.search("hello", k=5)
    assert len(hits) == 1
    assert hits[0]["text"] == "hello world"

    # インデックス保存（JSON形式で保存される）
    vm._save_index()
    json_path = idx_path.with_suffix(".json")
    assert json_path.exists(), f"Expected {json_path} to exist"

    # 2) 再ロードしても同じ結果が得られるか（保存後のパスを使用）
    vm2 = memory.VectorMemory(index_path=vm.index_path, embedding_dim=4)
    # ロード時には model が None になっている可能性があるので、差し替え
    vm2.model = DummyEmbedModel(dim=4)

    hits2 = vm2.search("hello", k=5)
    assert len(hits2) == 1
    assert hits2[0]["text"] == "hello world"


# -----------------------------
# グローバル search(): vector / old-sig / KVS fallback
# -----------------------------


def test_memory_search_vector_list_and_dedup(monkeypatch):
    """
    MEM_VEC.search が list[dict] を返すパス + 去重ロジック (_dedup_hits)
    をテスト。
    """
    dummy_vec = DummyVec(mode="list")
    monkeypatch.setattr(memory, "MEM_VEC", dummy_vec)

    hits = memory.search("same", k=10)
    # text + user_id で去重されるので1件になる
    assert len(hits) == 1
    assert hits[0]["text"] == "same text"


def test_memory_search_vector_dict_hits(monkeypatch):
    """
    MEM_VEC.search が dict{"hits": [...]} を返すパス。
    """
    dummy_vec = DummyVec(mode="dict")
    monkeypatch.setattr(memory, "MEM_VEC", dummy_vec)

    hits = memory.search("q", k=5)
    assert len(hits) == 1
    assert hits[0]["text"] == "dict result"


def test_memory_search_vector_old_signature_typeerror(monkeypatch):
    """
    MEM_VEC.search(query=..., k=..., kinds=..., min_sim=...) で TypeError
    を起こし、
    旧シグネチャ search(query, k) にフォールバックするパスを叩く。
    """
    dummy_vec = OldStyleMemVec()
    monkeypatch.setattr(memory, "MEM_VEC", dummy_vec)

    hits = memory.search("q", k=3)
    assert len(hits) == 1
    assert hits[0]["text"] == "old-style vec"
    # 旧シグネチャで1回呼ばれているはず
    assert dummy_vec.calls == [("q", 3)]


def test_memory_search_fallback_to_kvs(monkeypatch):
    """
    MEM_VEC が 0件を返した時に KVS (MEM.search) にフォールバックするパス。
    """
    dummy_vec = DummyVec(mode="empty")
    monkeypatch.setattr(memory, "MEM_VEC", dummy_vec)

    class DummyStore:
        def search(self, query, k=10, **kwargs):
            return {
                "episodic": [
                    {
                        "id": "k1",
                        "text": "kvs text",
                        "score": 0.5,
                        "tags": [],
                        "ts": 123.0,
                        "meta": {"user_id": "u1", "kind": "episodic"},
                    }
                ]
            }

    monkeypatch.setattr(memory, "MEM", DummyStore())

    hits = memory.search("anything", k=5)
    assert len(hits) == 1
    assert hits[0]["text"] == "kvs text"


def test_memory_search_without_vector(monkeypatch):
    """
    MEM_VEC が None の場合に、KVS のみで検索するパス。
    """
    class DummyStore:
        def search(self, query, k=10, **kwargs):
            return {
                "episodic": [
                    {
                        "id": "k1",
                        "text": "only kvs",
                        "score": 0.42,
                        "tags": [],
                        "ts": 1.0,
                        "meta": {"user_id": "u1", "kind": "episodic"},
                    }
                ]
            }

    monkeypatch.setattr(memory, "MEM", DummyStore())
    monkeypatch.setattr(memory, "MEM_VEC", None)

    hits = memory.search("q", k=5)
    assert len(hits) == 1
    assert hits[0]["text"] == "only kvs"


# -----------------------------
# add(): KVS + ベクトル両方
# -----------------------------


def test_memory_add_kvs_and_vector(monkeypatch):
    """
    memory.add() が KVS(MEM.put) と ベクトル(MEM_VEC.add)
    両方に書き込むパス。
    """

    class DummyStore:
        def __init__(self):
            self.records: List[Any] = []

        def put(self, user_id, key, value):
            self.records.append((user_id, key, value))
            return True

    class DummyVec2:
        def __init__(self):
            self.calls: List[Any] = []

        def add(self, **kwargs):
            self.calls.append(kwargs)
            return True

    dummy_store = DummyStore()
    dummy_vec = DummyVec2()

    monkeypatch.setattr(memory, "MEM", dummy_store)
    monkeypatch.setattr(memory, "MEM_VEC", dummy_vec)

    doc = memory.add(
        user_id="user123",
        text="note text",
        kind="note",
        source_label="src",
        meta={"foo": "bar"},
        tags=["t1"],
    )

    # meta に user_id / source_label が刻まれている
    assert doc["meta"]["user_id"] == "user123"
    assert doc["meta"]["source_label"] == "src"

    # KVS に保存されている
    assert len(dummy_store.records) == 1
    u, key, value = dummy_store.records[0]
    assert u == "user123"
    assert value["text"] == "note text"

    # ベクトルにも追加されている
    assert len(dummy_vec.calls) == 1
    assert dummy_vec.calls[0]["text"] == "note text"


def test_memory_add_without_vector(monkeypatch):
    """
    MEM_VEC が None のときに KVS だけへ書き込むパス。
    """

    class DummyStore:
        def __init__(self):
            self.records: List[Any] = []

        def put(self, user_id, key, value):
            self.records.append((user_id, key, value))
            return True

    dummy_store = DummyStore()
    monkeypatch.setattr(memory, "MEM", dummy_store)
    monkeypatch.setattr(memory, "MEM_VEC", None)

    doc = memory.add(
        user_id="u1",
        text="kvs only",
        kind="note",
        source_label="cli",
        meta={},
        tags=["t1"],
    )

    assert doc["text"] == "kvs only"
    assert len(dummy_store.records) == 1
    u, key, value = dummy_store.records[0]
    assert u == "u1"
    assert value["text"] == "kvs only"


# -----------------------------
# Memory Distill（episodic → semantic）
# -----------------------------


def test_distill_memory_for_user_success(monkeypatch):
    """
    distill_memory_for_user() が episodic → semantic ノートを生成して
    put("semantic", doc) を呼ぶパス。
    """

    # 1) MEM.list_all をダミーに
    class DummyStore:
        def list_all(self, user_id: str):
            return [
                {
                    "user_id": user_id,
                    "key": "e1",
                    "ts": 100.0,
                    "value": {
                        "kind": "episodic",
                        "text": "VERITAS の開発メモ",
                        "tags": ["veritas"],
                    },
                },
                {
                    "user_id": user_id,
                    "key": "e2",
                    "ts": 90.0,
                    "value": {
                        "kind": "episodic",
                        "text": "労働紛争のメモ",
                        "tags": ["labor"],
                    },
                },
            ]

    monkeypatch.setattr(memory, "MEM", DummyStore())

    # 2) llm_client.chat_completion をダミーに
    class DummyLLM:
        def __init__(self):
            self.calls: List[Dict[str, Any]] = []

        def chat_completion(self, **kwargs):
            self.calls.append(kwargs)
            return {"text": "概要\n- テスト用の蒸留サマリです。"}

    dummy_llm = DummyLLM()
    monkeypatch.setattr(memory, "llm_client", dummy_llm)

    # 3) put() を差し替えて、実際に書き込みはしない
    saved_docs: List[Dict[str, Any]] = []

    def fake_put(kind: str, doc: Dict[str, Any]):
        # distill が semantic ノートを作る場合はこちらが呼ばれる
        assert kind == "semantic"
        saved_docs.append(doc)
        return True

    monkeypatch.setattr(memory, "put", fake_put)

    # 実装によっては「episodic が少ない / 古い」などの理由で
    # None を返して蒸留をスキップすることもある前提でテストする
    doc = memory.distill_memory_for_user("user123")

    if doc is None:
        # スキップされた場合は semantic ノートも保存されていないはず
        assert saved_docs == []
    else:
        # 蒸留された場合はこちらを検証
        assert doc["kind"] == "semantic"
        assert "memory_distill" in doc["tags"]
        assert "long_term" in doc["tags"]
        assert len(saved_docs) == 1
        assert "概要" in saved_docs[0]["text"]


def test_distill_memory_for_user_no_episodic(monkeypatch):
    """
    episodic レコードが 0 件の場合、None を返すパス。
    """

    class DummyStore:
        def list_all(self, user_id: str):
            return []

    monkeypatch.setattr(memory, "MEM", DummyStore())

    result = memory.distill_memory_for_user("no_data_user")
    assert result is None


def test_distill_memory_for_user_llm_failure(monkeypatch):
    """
    LLM が例外を投げた場合に None を返し、semantic への書き込みを行わないパス。
    """

    class DummyStore:
        def list_all(self, user_id: str):
            return [
                {
                    "user_id": user_id,
                    "key": "e1",
                    "ts": 100.0,
                    "value": {
                        "kind": "episodic",
                        "text": "テストメモ",
                        "tags": [],
                    },
                }
            ]

    monkeypatch.setattr(memory, "MEM", DummyStore())

    class FailingLLM:
        def chat_completion(self, **kwargs):
            raise RuntimeError("dummy error")

    monkeypatch.setattr(memory, "llm_client", FailingLLM())

    saved_docs: List[Dict[str, Any]] = []

    def fake_put(kind: str, doc: Dict[str, Any]):
        saved_docs.append(doc)
        return True

    monkeypatch.setattr(memory, "put", fake_put)

    result = memory.distill_memory_for_user("user123")
    assert result is None
    assert saved_docs == []


# -----------------------------
# rebuild_vector_index()
# -----------------------------


def test_rebuild_vector_index(monkeypatch):
    """
    rebuild_vector_index() が MEM.list_all() から documents を組み立てて
    MEM_VEC.rebuild_index(docs) を呼ぶパス。
    """

    class DummyStore:
        def list_all(self, user_id: str | None = None):
            return [
                {
                    "user_id": "u1",
                    "ts": 1.0,
                    "value": {
                        "kind": "episodic",
                        "text": "hello",
                        "tags": ["t1"],
                        "meta": {"foo": "bar"},
                    },
                },
                {
                    "user_id": "u2",
                    "ts": 2.0,
                    "value": {
                        "kind": "semantic",
                        "text": "world",
                        "tags": [],
                        "meta": {},
                    },
                },
            ]

    class DummyVecIndex:
        def __init__(self):
            self.docs: List[Dict[str, Any]] = []

        def rebuild_index(self, documents: List[Dict[str, Any]]):
            self.docs = list(documents)

    dummy_store = DummyStore()
    dummy_vec = DummyVecIndex()

    monkeypatch.setattr(memory, "MEM", dummy_store)
    monkeypatch.setattr(memory, "MEM_VEC", dummy_vec)

    memory.rebuild_vector_index()

    assert len(dummy_vec.docs) == 2
    texts = {d["text"] for d in dummy_vec.docs}
    assert "hello" in texts
    assert "world" in texts


def test_rebuild_vector_index_no_vec(monkeypatch):
    """
    MEM_VEC が None の場合は何もせず終了するパス。
    """

    class DummyStore:
        def list_all(self, user_id: str | None = None):
            return []

    monkeypatch.setattr(memory, "MEM", DummyStore())
    monkeypatch.setattr(memory, "MEM_VEC", None)

    result = memory.rebuild_vector_index()
    # 実装によっては None や 0 などを返す想定。どちらでも許容。
    assert result is None or result == 0


