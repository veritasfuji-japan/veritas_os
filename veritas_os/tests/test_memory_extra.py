# -*- coding: utf-8 -*-
# veritas_os/tests/test_memory_extra.py

from datetime import datetime

import pytest

from veritas_os.core import memory as mem_mod


# ============================
# _hits_to_evidence / Evidence 系
# ============================


def test_hits_to_evidence_basic_and_filters_invalid():
    hits = [
        {"id": "1", "text": "hello", "score": 0.9, "tags": ["a"], "meta": {"x": 1}},
        "not dict",
        {"id": "2", "text": "", "score": 0.1},
        {"id": "3"},  # text なし
    ]

    ev = mem_mod._hits_to_evidence(hits)
    assert len(ev) == 1
    e = ev[0]
    assert e["source"] == "memory:1"
    assert e["text"] == "hello"
    assert e["score"] == 0.9
    assert e["tags"] == ["a"]
    assert e["meta"] == {"x": 1}

    # prefix 指定パターン
    ev2 = mem_mod._hits_to_evidence(hits, source_prefix="custom")
    assert ev2[0]["source"] == "custom:1"


def test_get_evidence_for_decision_uses_chosen_title_and_search(monkeypatch):
    called = {}

    def fake_search(query, k, user_id=None, **kwargs):
        called["query"] = query
        called["k"] = k
        called["user_id"] = user_id
        return [
            {"id": "x", "text": "evidence text", "score": 0.5, "tags": [], "meta": {}},
        ]

    monkeypatch.setattr(mem_mod, "search", fake_search)

    decision = {
        # "query" は空 → chosen.title が使われる
        "query": "",
        "chosen": {"title": "TITLE QUERY"},
        "context": {"user_id": "user-1"},
    }

    ev = mem_mod.get_evidence_for_decision(decision, user_id="override", top_k=3)

    # search 呼び出しパラメータ確認
    assert called["query"] == "TITLE QUERY"
    assert called["k"] == 3
    # 明示 user_id 引数が優先
    assert called["user_id"] == "override"

    assert len(ev) == 1
    assert ev[0]["text"] == "evidence text"
    assert ev[0]["source"] == "memory:x"


def test_get_evidence_for_decision_empty_query_returns_empty(monkeypatch):
    called = {"count": 0}

    def fake_search(*args, **kwargs):
        called["count"] += 1
        return []

    monkeypatch.setattr(mem_mod, "search", fake_search)

    decision = {}
    ev = mem_mod.get_evidence_for_decision(decision)
    assert ev == []
    assert called["count"] == 0  # search は呼ばれない


def test_get_evidence_for_query_empty_does_not_search(monkeypatch):
    called = {"count": 0}

    def fake_search(*args, **kwargs):
        called["count"] += 1
        return []

    monkeypatch.setattr(mem_mod, "search", fake_search)

    assert mem_mod.get_evidence_for_query("   ") == []
    assert called["count"] == 0


def test_get_evidence_for_query_basic(monkeypatch):
    def fake_search(query, k, user_id=None, **kwargs):
        return [{"id": "1", "text": "q hit", "score": 0.8}]

    monkeypatch.setattr(mem_mod, "search", fake_search)
    ev = mem_mod.get_evidence_for_query("hello", user_id="u")
    assert len(ev) == 1
    assert ev[0]["text"] == "q hit"
    assert ev[0]["source"] == "memory:1"


# ============================
# _dedup_hits
# ============================


def test_dedup_hits_deduplicates_by_text_and_user():
    hits = [
        {"text": "same", "meta": {"user_id": "u1"}},
        {"text": "same", "meta": {"user_id": "u1"}},  # duplicate
        {"text": "same", "meta": {"user_id": "u2"}},  # 別 user →別扱い
        {"text": "other", "meta": {"user_id": "u1"}},
    ]

    out = mem_mod._dedup_hits(hits, k=10)
    # ("same","u1"),("same","u2"),("other","u1") の3件になる
    assert len(out) == 3
    texts_users = {(h["text"], (h.get("meta") or {}).get("user_id")) for h in out}
    assert ("same", "u1") in texts_users
    assert ("same", "u2") in texts_users
    assert ("other", "u1") in texts_users


def test_dedup_hits_limit_k():
    hits = [
        {"text": "t1", "meta": {"user_id": "u"}},
        {"text": "t2", "meta": {"user_id": "u"}},
        {"text": "t3", "meta": {"user_id": "u"}},
    ]
    out = mem_mod._dedup_hits(hits, k=2)
    assert len(out) == 2


# ============================
# search ベクトル + KVS fallback
# ============================


class DummyVecSearch:
    def __init__(self):
        self.calls = []

    def search(self, query, k, kinds=None, min_sim=0.0):
        self.calls.append((query, k, kinds, min_sim))
        return [
            {"text": "A", "meta": {"user_id": "target"}},
            {"text": "A", "meta": {"user_id": "target"}},  # duplicate
            {"text": "B", "meta": {"user_id": "other"}},
        ]


def test_search_vector_path_with_user_filter_and_dedup(monkeypatch):
    vec = DummyVecSearch()
    monkeypatch.setattr(mem_mod, "MEM_VEC", vec)

    class DummyMem:
        def search(self, **kwargs):
            raise AssertionError("KVS search should not be called")

    monkeypatch.setattr(mem_mod, "MEM", DummyMem())

    hits = mem_mod.search("hello", k=5, user_id="target")
    # ベクトル検索が呼ばれている
    assert vec.calls
    # user_id=target の "A" だけが残る（duplicate除去）
    assert len(hits) == 1
    assert hits[0]["text"] == "A"
    assert (hits[0].get("meta") or {}).get("user_id") == "target"


class DummyVecOldSig:
    def __init__(self):
        self.calls = []

    # 旧シグネチャ: キーワードを受けられない → TypeError を誘発
    def search(self, query, k):
        self.calls.append((query, k))
        return [
            {"text": "X", "meta": {"user_id": None}},
            {"text": "X", "meta": {"user_id": None}},
            {"text": "Y", "meta": {"user_id": None}},
        ]


def test_search_vector_old_signature_typeerror_fallback(monkeypatch):
    vec = DummyVecOldSig()
    monkeypatch.setattr(mem_mod, "MEM_VEC", vec)

    class DummyMem:
        def search(self, **kwargs):
            raise AssertionError("KVS search should not be called")

    monkeypatch.setattr(mem_mod, "MEM", DummyMem())

    hits = mem_mod.search("q", k=3)
    # 旧シグネチャ用 search が呼ばれている
    assert vec.calls
    # duplicate 除去で 2 件になる
    assert len(hits) == 2
    texts = {h["text"] for h in hits}
    assert texts == {"X", "Y"}


class DummyMemKVS:
    def __init__(self, res):
        self.res = res
        self.calls = []

    def search(self, **kwargs):
        self.calls.append(kwargs)
        return self.res


def test_search_kvs_fallback_dict_episodic(monkeypatch):
    monkeypatch.setattr(mem_mod, "MEM_VEC", None)

    res = {
        "episodic": [
            {"text": "E1"},
            {"text": "E1"},  # duplicate
            {"text": "E2"},
        ]
    }
    mem = DummyMemKVS(res)
    monkeypatch.setattr(mem_mod, "MEM", mem)

    hits = mem_mod.search("q", k=10)
    # KVS search が呼ばれている
    assert mem.calls
    # duplicate 除去済み
    assert len(hits) == 2
    texts = {h["text"] for h in hits}
    assert texts == {"E1", "E2"}


def test_search_kvs_fallback_list_result(monkeypatch):
    monkeypatch.setattr(mem_mod, "MEM_VEC", None)

    res = [
        {"text": "L1"},
        {"text": "L1"},
        {"text": "L2"},
    ]
    mem = DummyMemKVS(res)
    monkeypatch.setattr(mem_mod, "MEM", mem)

    hits = mem_mod.search("q", k=5)
    assert mem.calls
    assert len(hits) == 2
    texts = {h["text"] for h in hits}
    assert texts == {"L1", "L2"}


# ============================
# predict_decision_status / predict_gate_label
# ============================


def test_predict_decision_status_without_model_returns_unknown(monkeypatch):
    monkeypatch.setattr(mem_mod, "MODEL", None)
    assert mem_mod.predict_decision_status("anything") == "unknown"


class DummyClfAllowHigh:
    def __init__(self, prob):
        # classes_ に "allow" を含める
        self.classes_ = ["deny", "allow"]
        self._prob = prob

    def predict_proba(self, X):
        # X の長さに関係なく単一行を返す
        return [[1.0 - self._prob, self._prob]]


def test_predict_gate_label_uses_mem_clf_when_available(monkeypatch):
    # MEM_CLF を優先して使うパス
    monkeypatch.setattr(mem_mod, "MEM_CLF", DummyClfAllowHigh(0.9))
    monkeypatch.setattr(mem_mod, "MODEL", None)

    probs = mem_mod.predict_gate_label("some text")
    assert "allow" in probs
    assert abs(probs["allow"] - 0.9) < 1e-6


def test_predict_gate_label_falls_back_to_model_when_mem_clf_none(monkeypatch):
    monkeypatch.setattr(mem_mod, "MEM_CLF", None)
    monkeypatch.setattr(mem_mod, "MODEL", DummyClfAllowHigh(0.8))

    probs = mem_mod.predict_gate_label("other text")
    assert "allow" in probs
    assert abs(probs["allow"] - 0.8) < 1e-6


# ============================
# add / put / ラッパー系
# ============================


class DummyMemAdd:
    def __init__(self):
        self.put_calls = []

    def put(self, user_id, key, value):
        self.put_calls.append((user_id, key, value))
        return True

    # 以下は wrapper 用に最低限
    def add_usage(self, user_id, cited_ids=None):
        self.last_add_usage = (user_id, cited_ids)
        return True

    def get(self, user_id, key):
        self.last_get = (user_id, key)
        return {"ok": True}

    def list_all(self, user_id=None):
        self.last_list_all = user_id
        return [{"user_id": user_id or "none"}]

    def append_history(self, user_id, record):
        self.last_append_history = (user_id, record)
        return True

    def recent(self, user_id, limit=20, contains=None):
        self.last_recent = (user_id, limit, contains)
        return [{"user_id": user_id, "text": "recent"}]

    def summarize_for_planner(self, user_id, query, limit=8):
        self.last_summarize = (user_id, query, limit)
        return "SUMMARY_FOR_PLANNER"


class DummyVecAdd:
    def __init__(self):
        self.add_calls = []

    def add(self, kind, text, tags, meta):
        self.add_calls.append((kind, text, tags, meta))
        return True


def test_add_sends_to_mem_and_mem_vec(monkeypatch):
    mem = DummyMemAdd()
    vec = DummyVecAdd()
    monkeypatch.setattr(mem_mod, "MEM", mem)
    monkeypatch.setattr(mem_mod, "MEM_VEC", vec)

    record = mem_mod.add(
        user_id="u1",
        text="  chunk text  ",
        kind="doc",
        source_label="SRC",
        meta={"page": 3},
        tags=["t1"],
    )

    # record 構造チェック
    assert record["kind"] == "doc"
    assert record["text"] == "  chunk text  "
    assert record["tags"] == ["t1"]
    assert record["meta"]["user_id"] == "u1"
    assert record["meta"]["source_label"] == "SRC"
    assert record["meta"]["page"] == 3

    # MEM.put が呼ばれている
    assert len(mem.put_calls) == 1
    user_id, key, value = mem.put_calls[0]
    assert user_id == "u1"
    assert isinstance(key, str)
    assert value == record

    # MEM_VEC.add も呼ばれている
    assert len(vec.add_calls) == 1
    kind, text, tags, meta = vec.add_calls[0]
    assert kind == "doc"
    assert text.strip() == "chunk text"
    assert tags == ["t1"]
    assert meta["user_id"] == "u1"


def test_add_rejects_empty_text(monkeypatch):
    mem = DummyMemAdd()
    monkeypatch.setattr(mem_mod, "MEM", mem)
    monkeypatch.setattr(mem_mod, "MEM_VEC", None)

    with pytest.raises(ValueError):
        mem_mod.add(user_id="u1", text="   ")


def test_put_kvs_mode_positional(monkeypatch):
    mem = DummyMemAdd()
    monkeypatch.setattr(mem_mod, "MEM", mem)
    monkeypatch.setattr(mem_mod, "MEM_VEC", None)

    ok = mem_mod.put("u1", "key1", {"v": 1})
    assert ok is True
    assert mem.put_calls[0][0] == "u1"
    assert mem.put_calls[0][1] == "key1"
    assert mem.put_calls[0][2] == {"v": 1}


def test_put_kvs_mode_kwargs(monkeypatch):
    mem = DummyMemAdd()
    monkeypatch.setattr(mem_mod, "MEM", mem)
    monkeypatch.setattr(mem_mod, "MEM_VEC", None)

    ok = mem_mod.put(user_id="u1", key="k2", value={"x": 2})
    assert ok is True
    assert mem.put_calls[0][0] == "u1"
    assert mem.put_calls[0][1] == "k2"
    assert mem.put_calls[0][2] == {"x": 2}


def test_put_vector_mode(monkeypatch):
    mem = DummyMemAdd()
    vec = DummyVecAdd()
    monkeypatch.setattr(mem_mod, "MEM", mem)
    monkeypatch.setattr(mem_mod, "MEM_VEC", vec)

    ok = mem_mod.put(
        "semantic",
        {"text": "hello", "tags": ["a"], "meta": {"user_id": "u1"}},
    )
    assert ok is True

    # ベクトル側
    assert len(vec.add_calls) == 1
    kind, text, tags, meta = vec.add_calls[0]
    assert kind == "semantic"
    assert text == "hello"
    assert tags == ["a"]
    assert meta["user_id"] == "u1"

    # KVS 側
    assert len(mem.put_calls) == 1
    user_id, key, value = mem.put_calls[0]
    assert user_id == "u1"  # meta.user_id が user_id になる
    assert isinstance(key, str)
    assert value["text"] == "hello"


def test_put_invalid_signature_raises():
    with pytest.raises(TypeError):
        mem_mod.put()  # type: ignore[call-arg]


def test_wrapper_functions_forward_to_mem(monkeypatch):
    mem = DummyMemAdd()
    monkeypatch.setattr(mem_mod, "MEM", mem)

    assert mem_mod.add_usage("u1", ["a", "b"]) is True
    assert mem.last_add_usage == ("u1", ["a", "b"])

    v = mem_mod.get("u1", "k")
    assert v == {"ok": True}
    assert mem.last_get == ("u1", "k")

    all_ = mem_mod.list_all("u2")
    assert all_[0]["user_id"] == "u2"
    assert mem.last_list_all == "u2"

    assert mem_mod.append_history("u1", {"x": 1}) is True
    assert mem.last_append_history == ("u1", {"x": 1})

    recent = mem_mod.recent("u3", limit=5, contains="foo")
    assert recent[0]["user_id"] == "u3"
    assert mem.last_recent == ("u3", 5, "foo")

    s = mem_mod.summarize_for_planner("u1", "query", limit=7)
    assert s == "SUMMARY_FOR_PLANNER"
    assert mem.last_summarize == ("u1", "query", 7)


# ============================
# _build_distill_prompt / distill_memory_for_user
# ============================


def test_build_distill_prompt_format():
    episodes = [
        {
            "text": "short text",
            "tags": ["tag1"],
            "ts": 1_700_000_000,
        },
        {
            "text": "x" * 400,  # 長文 → 300文字にトリムされるはず
            "tags": [],
            "ts": 1_700_000_100,
        },
    ]
    prompt = mem_mod._build_distill_prompt("userX", episodes)

    # user_id が含まれる
    assert "Target user_id: userX" in prompt
    # episodic records header
    assert "Here are recent episodic records" in prompt

    # トリムされた "..." が少なくとも1回含まれる
    assert "..." in prompt

    # 日本語フォーマット説明が含まれる
    assert "「概要」セクション" in prompt
    assert "「TODO / Next Actions」セクション" in prompt


class DummyLLMChatCompletion:
    def chat_completion(self, *args, **kwargs):
        # LLM スタブ
        return "これは要約です。"


class DummyMemListAll(DummyMemAdd):
    def __init__(self, records):
        super().__init__()
        self._records = records

    def list_all(self, user_id=None):
        # distill_memory_for_user では user_id は必ず指定される
        assert user_id == "user-1"
        return self._records


def test_distill_memory_for_user_happy_path(monkeypatch):
    # episodic レコード2件 + semantic 1件（無視される）
    records = [
        {
            "user_id": "user-1",
            "ts": 1_700_000_000.0,
            "value": {
                "kind": "episodic",
                "text": "VERITAS の開発について話した。",
                "tags": ["veritas"],
            },
        },
        {
            "user_id": "user-1",
            "ts": 1_700_000_100.0,
            "value": {
                "kind": "episodic",
                "text": "労働紛争の証拠整理と TODO をまとめた。",
                "tags": ["labour"],
            },
        },
        {
            "user_id": "user-1",
            "ts": 1_700_000_200.0,
            "value": {
                "kind": "semantic",
                "text": "古い長期メモ",
                "tags": [],
            },
        },
    ]

    mem = DummyMemListAll(records)
    monkeypatch.setattr(mem_mod, "MEM", mem)

    # llm_client スタブ
    monkeypatch.setattr(mem_mod, "llm_client", DummyLLMChatCompletion())

    saved = {}

    def fake_put(kind, doc):
        saved["kind"] = kind
        saved["doc"] = doc
        return True

    monkeypatch.setattr(mem_mod, "put", fake_put)

    doc = mem_mod.distill_memory_for_user("user-1")

    # semantic メモが返ってくる
    assert doc is not None
    assert doc["kind"] == "semantic"
    assert "これは要約です" in doc["text"]
    assert "memory_distill" in doc["tags"]
    assert doc["meta"]["user_id"] == "user-1"
    assert doc["meta"]["item_count"] == 2
    # put に渡されたものと一致
    assert saved["kind"] == "semantic"
    assert saved["doc"] == doc

    # created_at が ISO8601 で入っている
    created_at = doc["meta"]["created_at"]
    dt = datetime.fromisoformat(created_at)
    assert dt.tzinfo is not None


def test_distill_memory_for_user_no_episodic_returns_none(monkeypatch):
    mem = DummyMemListAll(
        [
            # kind != episodic
            {
                "user_id": "user-1",
                "ts": 1_700_000_000.0,
                "value": {"kind": "semantic", "text": "old", "tags": []},
            },
            # text が短すぎる
            {
                "user_id": "user-1",
                "ts": 1_700_000_100.0,
                "value": {"kind": "episodic", "text": "x", "tags": []},
            },
        ]
    )
    monkeypatch.setattr(mem_mod, "MEM", mem)

    # put/llm_client は呼ばれないはずなのでダミーでOK
    monkeypatch.setattr(mem_mod, "llm_client", DummyLLMChatCompletion())

    def fake_put(*args, **kwargs):
        raise AssertionError("put should not be called when no episodic records")

    monkeypatch.setattr(mem_mod, "put", fake_put)

    doc = mem_mod.distill_memory_for_user("user-1")
    assert doc is None


# ============================
# rebuild_vector_index
# ============================


def test_rebuild_vector_index_mem_vec_none(monkeypatch):
    monkeypatch.setattr(mem_mod, "MEM_VEC", None)

    class DummyMem(DummyMemAdd):
        def list_all(self, user_id=None):
            raise AssertionError("list_all should not be called when MEM_VEC is None")

    monkeypatch.setattr(mem_mod, "MEM", DummyMem())

    # MEM_VEC が None の場合は何もせず return される
    mem_mod.rebuild_vector_index()


def test_rebuild_vector_index_no_rebuild_index(monkeypatch):
    class NoRebuild:
        pass

    monkeypatch.setattr(mem_mod, "MEM_VEC", NoRebuild())

    class DummyMem(DummyMemAdd):
        def list_all(self, user_id=None):
            raise AssertionError(
                "list_all should not be called when MEM_VEC has no rebuild_index"
            )

    monkeypatch.setattr(mem_mod, "MEM", DummyMem())

    # rebuild_index メソッドがない場合も何もせず return
    mem_mod.rebuild_vector_index()


class DummyVecRebuild:
    def __init__(self):
        self.docs = None

    def rebuild_index(self, documents):
        self.docs = documents


def test_rebuild_vector_index_happy_path(monkeypatch):
    vec = DummyVecRebuild()
    monkeypatch.setattr(mem_mod, "MEM_VEC", vec)

    records = [
        {
            "user_id": "u1",
            "ts": 1_700_000_000.0,
            "value": {
                "kind": "episodic",
                "text": "text 1",
                "tags": ["a"],
                "meta": {"extra": 1},
            },
        },
        {
            "user_id": "u2",
            "ts": 1_700_000_100.0,
            "value": {
                "kind": "semantic",
                "text": "text 2",
                "tags": [],
                "meta": {},
            },
        },
        {
            "user_id": "u3",
            "ts": 1_700_000_200.0,
            "value": {
                "kind": "episodic",
                "text": "   ",  # 空白 → スキップされるはず
                "tags": [],
                "meta": {},
            },
        },
    ]

    class DummyMem(DummyMemAdd):
        def __init__(self, records):
            super().__init__()
            self._records = records

        def list_all(self, user_id=None):
            # user_id なしで全件返ってくるパス
            return self._records

    monkeypatch.setattr(mem_mod, "MEM", DummyMem(records))

    mem_mod.rebuild_vector_index()

    # rebuild_index に渡された documents を検証
    assert vec.docs is not None
    docs = vec.docs
    assert len(docs) == 2  # 空白テキストのレコードは除外される
    kinds = {d["kind"] for d in docs}
    texts = {d["text"] for d in docs}
    assert kinds == {"episodic", "semantic"}
    assert texts == {"text 1", "text 2"}

    # meta が user_id / created_at を含む
    for rec, doc in zip(records[:2], docs):
        meta = doc["meta"]
        assert meta["user_id"] == rec["user_id"]
        assert meta["created_at"] == rec["ts"]



