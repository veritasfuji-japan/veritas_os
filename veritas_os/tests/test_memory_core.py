# tests/test_memory_core.py
from __future__ import annotations

from pathlib import Path
import json
import time
from typing import Any, Dict, List

import pytest

from veritas_os.core import memory


# -------------------------------------------------
# 1. MemoryStore 基本動作（put / get / list / recent）
# -------------------------------------------------


def test_memory_store_put_get_list_recent(tmp_path: Path):
    path = tmp_path / "memory.json"
    store = memory.MemoryStore(path)

    # 初期状態: なにもない
    assert store.get("u1", "k1") is None
    assert store.list_all("u1") == []

    # put → get
    ok = store.put("u1", "k1", {"text": "hello", "kind": "episodic"})
    assert ok is True

    v = store.get("u1", "k1")
    assert isinstance(v, dict)
    assert v["text"] == "hello"

    all_u1 = store.list_all("u1")
    assert len(all_u1) == 1
    assert all_u1[0]["user_id"] == "u1"

    # recent（contains フィルタ付き）
    recent = store.recent("u1", limit=10, contains="hello")
    assert len(recent) == 1
    assert recent[0]["key"] == "k1"


# -------------------------------------------------
# 2. MemoryStore: 旧形式 dict → list へのマイグレーション
# -------------------------------------------------


def test_memory_store_normalize_migrate_old_format(tmp_path: Path):
    path = tmp_path / "memory_old.json"

    raw = {"users": {"u1": {"foo": "bar"}}}
    path.write_text(json.dumps(raw), encoding="utf-8")

    store = memory.MemoryStore(path)
    data = store._load_all()

    assert len(data) == 1
    rec = data[0]
    assert rec["user_id"] == "u1"
    assert rec["key"] == "foo"
    assert rec["value"] == "bar"
    assert "ts" in rec


# -------------------------------------------------
# 3. MemoryStore.search (KVSベース検索)
# -------------------------------------------------


def test_memory_store_search_episodic(tmp_path: Path):
    path = tmp_path / "memory.json"
    store = memory.MemoryStore(path)

    # episodic レコードを2件投入
    store.put(
        "u1",
        "ep1",
        {"text": "今日はVERITASのテストを書いた", "kind": "episodic", 
"tags": ["veritas"]},
    )
    store.put(
        "u1",
        "ep2",
        {"text": "音楽制作をしていた", "kind": "episodic", "tags": 
["music"]},
    )

    res = store.search(query="VERITAS テスト", k=5, user_id="u1")

    assert "episodic" in res
    hits = res["episodic"]
    assert len(hits) >= 1
    assert hits[0]["text"].startswith("今日はVERITAS")
    assert hits[0]["meta"]["kind"] == "episodic"
    assert hits[0]["meta"]["user_id"] == "u1"


# -------------------------------------------------
# 4. MemoryStore.put_episode + summarize_for_planner
# -------------------------------------------------


def test_memory_store_put_episode_and_summarize(tmp_path: Path, 
monkeypatch):
    path = tmp_path / "memory.json"
    store = memory.MemoryStore(path)

    # グローバル MEM をこのテスト用にすり替え
    monkeypatch.setattr(memory, "MEM", store)

    # ベクトルメモリは使わない（None）
    monkeypatch.setattr(memory, "MEM_VEC", None)

    key = store.put_episode(
        text="VERITAS OS のテストを書いた",
        tags=["veritas", "test"],
        meta={"user_id": "user123"},
    )
    assert key.startswith("episode_")

    summary = store.summarize_for_planner("user123", query="VERITAS", 
limit=5)
    assert "MemoryOS 要約" in summary
    assert "VERITAS OS" in summary


# -------------------------------------------------
# 5. グローバル add / put / get / recent / search（KVSフォールバック）
# -------------------------------------------------


class DummyVec:
    def __init__(self):
        self.add_calls: List[Dict[str, Any]] = []
        self.search_calls: List[Dict[str, Any]] = []

    def add(self, kind: str, text: str, tags=None, meta=None) -> bool:
        self.add_calls.append(
            {"kind": kind, "text": text, "tags": tags or [], "meta": meta 
or {}}
        )
        return True

    # 「新シグネチャ」で呼ばれるパターン
    def search(self, query: str, k: int = 10, kinds=None, min_sim: float = 
0.0):
        self.search_calls.append(
            {"query": query, "k": k, "kinds": kinds, "min_sim": min_sim}
        )
        # テストでは空リストを返して KVS フォールバックさせる
        return []


class DummyStore:
    def __init__(self):
        self.put_records: List[Dict[str, Any]] = []

    def put(self, user_id: str, key: str, value: Any) -> bool:
        self.put_records.append(
            {"user_id": user_id, "key": key, "value": value, "ts": 
time.time()}
        )
        return True

    def get(self, user_id: str, key: str) -> Any:
        for r in self.put_records:
            if r["user_id"] == user_id and r["key"] == key:
                return r["value"]
        return None

    def list_all(self, user_id: str | None = None) -> List[Dict[str, 
Any]]:
        if user_id is None:
            return list(self.put_records)
        return [r for r in self.put_records if r["user_id"] == user_id]

    def recent(self, user_id: str, limit: int = 20, contains: str | None = 
None):
        items = [r for r in self.put_records if r["user_id"] == user_id]
        items.sort(key=lambda r: r["ts"], reverse=True)
        if contains:
            items = [r for r in items if contains in str(r["value"])]
        return items[:limit]

    def search(self, query: str, k: int = 10, **kwargs):
        # MemoryStore.search と同じ形 {"episodic": [...]}
        results = []
        for r in self.put_records:
            value = r["value"]
            if not isinstance(value, dict):
                continue
            text = str(value.get("text") or "")
            if query in text:
                results.append(
                    {
                        "id": r["key"],
                        "text": text,
                        "score": 0.9,
                        "tags": value.get("tags", []),
                        "ts": r["ts"],
                        "meta": {
                            "user_id": r["user_id"],
                            "kind": value.get("kind", "episodic"),
                        },
                    }
                )
        return {"episodic": results[:k]}

    def append_history(self, user_id: str, record: Dict[str, Any]) -> bool:
        key = f"history_{int(time.time())}"
        return self.put(user_id, key, record)

    def add_usage(self, user_id: str, cited_ids=None) -> bool:
        key = f"usage_{int(time.time())}"
        return self.put(user_id, key, {"cited_ids": cited_ids or []})


def test_memory_add_and_search_kvs_fallback(monkeypatch):
    store = DummyStore()
    vec = DummyVec()

    monkeypatch.setattr(memory, "MEM", store)
    monkeypatch.setattr(memory, "MEM_VEC", vec)

    rec = memory.add(
        user_id="u1",
        text="VERITAS OS の memory.add テスト",
        kind="note",
        source_label="test",
        tags=["veritas"],
    )

    # KVS 保存されている
    assert store.put_records
    saved_val = store.put_records[0]["value"]
    assert saved_val["text"] == rec["text"]

    # MEM_VEC.add も呼ばれている
    assert vec.add_calls
    assert vec.add_calls[0]["text"].startswith("VERITAS OS")

    # vector search は空 → KVS search へフォールバック
    hits = memory.search("memory.add", k=5, user_id="u1")
    assert hits
    assert hits[0]["text"].startswith("VERITAS OS")


# -------------------------------------------------
# 6. Vector search: TypeError → 旧シグネチャフォールバック
# -------------------------------------------------


class DummyVecOldSig:
    def __init__(self):
        self.calls: List[Any] = []

    # キーワード引数を受け付けない古いシグネチャ
    def search(self, query, k):
        self.calls.append((query, k))
        return [
            {
                "id": "old1",
                "text": "old sig vector hit",
                "score": 0.8,
                "meta": {"user_id": "u1"},
            }
        ]


def test_memory_search_vector_old_signature(monkeypatch):
    # MEM.search が呼ばれないように簡単なダミーを差し込む
    store = DummyStore()
    monkeypatch.setattr(memory, "MEM", store)

    vec = DummyVecOldSig()
    monkeypatch.setattr(memory, "MEM_VEC", vec)

    hits = memory.search("old sig", k=3)
    assert hits
    assert hits[0]["text"] == "old sig vector hit"
    # 旧シグネチャで呼ばれている
    assert vec.calls == [("old sig", 3)]


# -------------------------------------------------
# 7. summarize_for_planner ラッパー
# -------------------------------------------------


def test_global_summarize_for_planner_wrapper(monkeypatch):
    called: Dict[str, Any] = {}

    class SummarizeStore:
        def summarize_for_planner(self, user_id: str, query: str, limit: 
int = 8):
            called["user_id"] = user_id
            called["query"] = query
            called["limit"] = limit
            return "dummy summary"

    monkeypatch.setattr(memory, "MEM", SummarizeStore())
    s = memory.summarize_for_planner("uX", "hello", limit=3)

    assert s == "dummy summary"
    assert called == {"user_id": "uX", "query": "hello", "limit": 3}


# -------------------------------------------------
# 8. Distill: _build_distill_prompt / distill_memory_for_user
# -------------------------------------------------


def test_build_distill_prompt_contains_episodes():
    episodes = [
        {"text": "VERITAS OS の設計をした", "tags": ["veritas"], "ts": 
1000.0},
        {"text": "労働紛争の証拠整理をした", "tags": ["labour"], "ts": 
2000.0},
    ]

    prompt = memory._build_distill_prompt("user123", episodes)
    assert "Target user_id: user123" in prompt
    assert "VERITAS OS" in prompt
    assert "労働紛争" in prompt
    assert "TODO / Next Actions" in prompt


def test_distill_memory_for_user_no_episodic(monkeypatch):
    class EmptyStore:
        def list_all(self, user_id: str):
            return []

    monkeypatch.setattr(memory, "MEM", EmptyStore())
    doc = memory.distill_memory_for_user("u1", max_items=10, 
min_text_len=1)
    assert doc is None


def test_distill_memory_for_user_success(monkeypatch):
    # 1) episodic レコードを返す MEM を差し込む
    class EpisodicStore:
        def list_all(self, user_id: str):
            return [
                {
                    "user_id": user_id,
                    "key": "ep1",
                    "value": {
                        "kind": "episodic",
                        "text": "VERITASと労働紛争の両方について考えていた",
                        "tags": ["veritas", "labour"],
                    },
                    "ts": time.time(),
                }
            ]

    monkeypatch.setattr(memory, "MEM", EpisodicStore())

    # 2) llm_client.chat_completion をダミーに
    def fake_chat_completion(system: str = None, user: str = None, 
**kwargs):
        # distill がちゃんとプロンプトを渡してきているか軽く確認
        assert "VERITAS" in (user or "")
        return {"text": "SUMMARY: VERITAS と労働紛争の要約テキスト"}

    monkeypatch.setattr(
        memory.llm_client, "chat_completion", fake_chat_completion, 
raising=False
    )

    # 3) put("semantic", doc) をスタブ
    saved: Dict[str, Any] = {}

    def fake_put(kind: str, doc: Dict[str, Any]) -> bool:
        saved["kind"] = kind
        saved["doc"] = doc
        return True

    monkeypatch.setattr(memory, "put", fake_put)

    doc = memory.distill_memory_for_user("uX", max_items=10, min_text_len=5)
    assert doc is not None
    assert doc["kind"] == "semantic"
    assert "SUMMARY:" in doc["text"]

    assert saved["kind"] == "semantic"
    assert "memory_distill" in saved["doc"]["tags"]


# -------------------------------------------------
# 9. rebuild_vector_index
# -------------------------------------------------


class DummyVecRebuild:
    def __init__(self):
        self.called_with: List[List[Dict[str, Any]]] = []

    def rebuild_index(self, documents: List[Dict[str, Any]]):
        self.called_with.append(documents)


def test_rebuild_vector_index_success(monkeypatch):
    class StoreForRebuild:
        def list_all(self, user_id: str | None = None):
            return [
                {
                    "user_id": "u1",
                    "value": {
                        "kind": "episodic",
                        "text": "hello episodic",
                        "tags": ["t1"],
                        "meta": {"foo": "bar"},
                    },
                    "ts": 111.0,
                },
                {
                    # text が空 → スキップされる
                    "user_id": "u2",
                    "value": {"kind": "episodic", "text": "", "tags": []},
                    "ts": 222.0,
                },
            ]

    store = StoreForRebuild()
    vec = DummyVecRebuild()

    monkeypatch.setattr(memory, "MEM", store)
    monkeypatch.setattr(memory, "MEM_VEC", vec)

    memory.rebuild_vector_index()

    assert vec.called_with
    docs = vec.called_with[0]
    assert len(docs) == 1
    d0 = docs[0]
    assert d0["text"] == "hello episodic"
    assert d0["meta"]["user_id"] == "u1"
    assert d0["meta"]["created_at"] == 111.0


def test_rebuild_vector_index_no_mem_vec(monkeypatch):
    monkeypatch.setattr(memory, "MEM_VEC", None)
    # 例外は出さずに静かに終わることだけ確認
    memory.rebuild_vector_index()


# -------------------------------------------------
# 10. モデルラッパ: predict_decision_status / predict_gate_label
# -------------------------------------------------


def test_predict_decision_status_with_dummy_model(monkeypatch):
    class DummyModel:
        def predict(self, X):
            return ["ok-status"]

    monkeypatch.setattr(memory, "MODEL", DummyModel())
    assert memory.predict_decision_status("hoge") == "ok-status"


def test_predict_gate_label_with_mem_clf(monkeypatch):
    class DummyClf:
        def __init__(self):
            self.classes_ = ["deny", "allow"]

        def predict_proba(self, X):
            # deny=0.1, allow=0.9
            return [[0.1, 0.9]]

    monkeypatch.setattr(memory, "MEM_CLF", DummyClf())
    label = memory.predict_gate_label("some text")
    assert 0.89 < label["allow"] < 0.91


def test_predict_gate_label_default(monkeypatch):
    monkeypatch.setattr(memory, "MEM_CLF", None)
    monkeypatch.setattr(memory, "MODEL", None)
    label = memory.predict_gate_label("anything")
    assert label["allow"] == 0.5

