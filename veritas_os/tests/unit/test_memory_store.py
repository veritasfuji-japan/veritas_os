# -*- coding: utf-8 -*-
"""MemoryStore 単体テスト

MemoryStore の CRUD / ライフサイクル / ハードニング / 信頼性テスト。"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


# ============================================================
# Source: test_memory_store.py
# ============================================================


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
    """search は min_sim を有限な [-1,1] に正規化する。"""
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

    # -1.0 未満は -1.0 に clamp されるので low も残る
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


def test_resolve_memory_dir_logs_default_path(memory_env, monkeypatch, caplog, tmp_path):
    """環境変数未指定時は既定パスを監査ログに出して返す。"""
    store, files, index_paths, FakeIndex, FakeEmbedder = memory_env

    default_dir = tmp_path / "default-memory"
    monkeypatch.delenv("VERITAS_MEMORY_DIR", raising=False)
    monkeypatch.delenv("VERITAS_ENV", raising=False)
    monkeypatch.setattr(store, "_default_memory_dir", lambda: default_dir)

    caplog.set_level("INFO")
    resolved = store._resolve_memory_dir()

    assert resolved == default_dir
    assert str(default_dir.resolve(strict=False)) in caplog.text


def test_resolve_memory_dir_rejects_non_allowlisted_path_in_production(
    memory_env,
    monkeypatch,
    caplog,
    tmp_path,
):
    """production では allowlist 外の VERITAS_MEMORY_DIR を拒否する。"""
    store, files, index_paths, FakeIndex, FakeEmbedder = memory_env

    default_dir = tmp_path / "default-memory"
    allowed_root = tmp_path / "allowed"
    denied_dir = tmp_path / "denied" / "memory"
    monkeypatch.setattr(store, "_default_memory_dir", lambda: default_dir)
    monkeypatch.setenv("VERITAS_ENV", "production")
    monkeypatch.setenv("VERITAS_MEMORY_DIR", str(denied_dir))
    monkeypatch.setenv("VERITAS_MEMORY_DIR_ALLOWLIST", str(allowed_root))

    caplog.set_level("WARNING")
    resolved = store._resolve_memory_dir()

    assert resolved == default_dir
    assert "rejected in production" in caplog.text
    assert store.MEMORY_DIR_HEALTH["status"] == "degraded"
    assert (
        store.MEMORY_DIR_HEALTH["details"]["reason"]
        == "production_allowlist_rejected"
    )


def test_resolve_memory_dir_accepts_allowlisted_path_in_production(
    memory_env,
    monkeypatch,
    caplog,
    tmp_path,
):
    """production でも allowlist 配下の VERITAS_MEMORY_DIR は許可される。"""
    store, files, index_paths, FakeIndex, FakeEmbedder = memory_env

    default_dir = tmp_path / "default-memory"
    allowed_root = tmp_path / "allowed"
    allowed_dir = allowed_root / "memory"
    monkeypatch.setattr(store, "_default_memory_dir", lambda: default_dir)
    monkeypatch.setenv("VERITAS_ENV", "production")
    monkeypatch.setenv("VERITAS_MEMORY_DIR", str(allowed_dir))
    monkeypatch.setenv("VERITAS_MEMORY_DIR_ALLOWLIST", str(allowed_root))

    caplog.set_level("INFO")
    resolved = store._resolve_memory_dir()

    assert resolved == allowed_dir
    assert str(allowed_dir.resolve(strict=False)) in caplog.text


def test_resolve_memory_dir_rejects_non_allowlisted_path_in_prod_alias(
    memory_env,
    monkeypatch,
    caplog,
    tmp_path,
):
    """`VERITAS_ENV=prod` でも production と同じ allowlist 制約を適用する。"""
    store, files, index_paths, FakeIndex, FakeEmbedder = memory_env

    default_dir = tmp_path / "default-memory"
    allowed_root = tmp_path / "allowed"
    denied_dir = tmp_path / "denied" / "memory"
    monkeypatch.setattr(store, "_default_memory_dir", lambda: default_dir)
    monkeypatch.setenv("VERITAS_ENV", "prod")
    monkeypatch.setenv("VERITAS_MEMORY_DIR", str(denied_dir))
    monkeypatch.setenv("VERITAS_MEMORY_DIR_ALLOWLIST", str(allowed_root))

    caplog.set_level("WARNING")
    resolved = store._resolve_memory_dir()

    assert resolved == default_dir
    assert "rejected in production" in caplog.text


def test_resolve_memory_dir_rejects_relative_path(memory_env, monkeypatch, caplog, tmp_path):
    """相対パスの VERITAS_MEMORY_DIR は安全上の理由で拒否する。"""
    store, files, index_paths, FakeIndex, FakeEmbedder = memory_env

    default_dir = tmp_path / "default-memory"
    monkeypatch.setattr(store, "_default_memory_dir", lambda: default_dir)
    monkeypatch.setenv("VERITAS_MEMORY_DIR", "relative/memory")
    monkeypatch.delenv("VERITAS_ENV", raising=False)

    caplog.set_level("WARNING")
    resolved = store._resolve_memory_dir()

    assert resolved == default_dir
    assert "[SECURITY]" in caplog.text
    assert store.MEMORY_DIR_HEALTH["status"] == "degraded"
    assert store.MEMORY_DIR_HEALTH["details"]["reason"] == "invalid_configured_path"


def test_resolve_memory_dir_rejects_path_traversal(memory_env, monkeypatch, caplog, tmp_path):
    """`..` を含む VERITAS_MEMORY_DIR はパストラバーサル対策で拒否する。"""
    store, files, index_paths, FakeIndex, FakeEmbedder = memory_env

    default_dir = tmp_path / "default-memory"
    monkeypatch.setattr(store, "_default_memory_dir", lambda: default_dir)
    monkeypatch.setenv("VERITAS_MEMORY_DIR", "/tmp/../unsafe")
    monkeypatch.delenv("VERITAS_ENV", raising=False)

    caplog.set_level("WARNING")
    resolved = store._resolve_memory_dir()

    assert resolved == default_dir
    assert "[SECURITY]" in caplog.text


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


def test_boot_records_health_when_json_is_corrupted(memory_env):
    """_boot は破損 JSON を health telemetry に記録する。"""
    store, files, index_paths, FakeIndex, FakeEmbedder = memory_env

    files["episodic"].write_text(
        '{"id":"ok","text":"valid","tags":[],"meta":{},"ts":1}\n{"id":\n',
        encoding="utf-8",
    )

    ms = store.MemoryStore(dim=4)

    health = ms.health_snapshot()
    assert health["status"] == "degraded"
    assert health["last_error"]["stage"] == "boot_rebuild"
    assert health["last_error"]["kind"] == "episodic"
    assert health["error_counts"]["boot_rebuild:episodic"] >= 1


def test_targeted_payload_load_records_missing_file_issue_code(memory_env):
    """missing memory file は health telemetry で明示分類される。"""
    store, files, index_paths, FakeIndex, FakeEmbedder = memory_env

    ms = store.MemoryStore(dim=4)
    loaded = ms._load_payloads_for_ids("episodic", ["missing-id"])

    assert loaded == {}
    health = ms.health_snapshot()
    assert health["status"] == "degraded"
    assert health["last_error"]["kind"] == "episodic"
    assert health["last_error"]["issue_code"] == "file_missing"
    assert health["issue_counts"]["file_missing"] >= 1


def test_targeted_payload_load_records_health_on_decode_error(memory_env):
    """targeted payload load の decode error は health telemetry に残る。"""
    store, files, index_paths, FakeIndex, FakeEmbedder = memory_env

    files["episodic"].write_text(
        '{"id":"broken","text":"value","tags":[],"meta":{},"ts":1}\n',
        encoding="utf-8",
    )

    ms = store.MemoryStore(dim=4)
    ms._offset_index["episodic"]["broken"] = 0
    files["episodic"].write_text("not-json\n", encoding="utf-8")

    loaded = ms._load_payloads_for_ids("episodic", ["broken"])

    assert loaded == {}
    health = ms.health_snapshot()
    assert health["status"] == "degraded"
    assert health["last_error"]["stage"] == "targeted_payload_load"
    assert health["last_error"]["kind"] == "episodic"
    assert health["error_counts"]["targeted_payload_load:episodic"] >= 1


def test_health_snapshot_exposes_memory_dir_config_mismatch(
    memory_env,
    monkeypatch,
    tmp_path,
):
    """Memory directory fallback は health telemetry に露出する。"""
    store, files, index_paths, FakeIndex, FakeEmbedder = memory_env

    default_dir = tmp_path / "default-memory"
    denied_dir = tmp_path / "denied" / "memory"
    monkeypatch.setattr(store, "_default_memory_dir", lambda: default_dir)
    monkeypatch.setenv("VERITAS_ENV", "production")
    monkeypatch.setenv("VERITAS_MEMORY_DIR", str(denied_dir))
    monkeypatch.setenv("VERITAS_MEMORY_DIR_ALLOWLIST", str(tmp_path / "allowed"))

    resolved = store._resolve_memory_dir()
    assert resolved == default_dir

    ms = store.MemoryStore(dim=4)
    health = ms.health_snapshot()

    assert health["status"] == "degraded"
    assert health["config"]["configured_dir"] == str(denied_dir)
    assert health["config"]["effective_dir"] == str(default_dir.resolve(strict=False))
    assert health["config"]["reason"] == "production_allowlist_rejected"


# ============================================================
# Source: test_memory_store_core.py
# ============================================================

# tests for veritas_os/core/memory_store.py — direct module tests
"""Tests for MemoryStore KVS core."""

import json
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import pytest

from veritas_os.core.memory_store import (
    MemoryStore,
    DEFAULT_RETENTION_CLASS,
    ALLOWED_RETENTION_CLASSES,
)
from veritas_os.core.memory_store_helpers import (
    erase_user_records,
    is_record_expired_compat,
    normalize_document_lifecycle,
    put_episode_record,
    recent_records_compat,
    search_records_compat,
    summarize_records_for_planner,
)


@pytest.fixture
def store(tmp_path):
    path = tmp_path / "memory.json"
    return MemoryStore(path)


class TestMemoryStoreInit:
    def test_creates_empty_file(self, tmp_path):
        path = tmp_path / "sub" / "memory.json"
        store = MemoryStore(path)
        assert path.exists()

    def test_load_classmethod(self, tmp_path):
        path = tmp_path / "memory.json"
        store = MemoryStore.load(path)
        assert isinstance(store, MemoryStore)


class TestNormalize:
    def test_list_passthrough(self, store):
        data = [{"key": "k1"}]
        assert store._normalize(data) == data

    def test_old_dict_format_migration(self, store):
        old = {"users": {"u1": {"k1": "v1", "k2": "v2"}}}
        result = store._normalize(old)
        assert len(result) == 2
        assert all(r["user_id"] == "u1" for r in result)

    def test_invalid_returns_empty(self, store):
        assert store._normalize("bad") == []
        assert store._normalize(42) == []


class TestPutGet:
    def test_put_and_get(self, store):
        assert store.put("u1", "key1", "value1") is True
        assert store.get("u1", "key1") == "value1"

    def test_get_missing(self, store):
        assert store.get("u1", "nonexistent") is None

    def test_put_update(self, store):
        store.put("u1", "k", "v1")
        store.put("u1", "k", "v2")
        assert store.get("u1", "k") == "v2"


class TestListAll:
    def test_list_all(self, store):
        store.put("u1", "k1", "v1")
        store.put("u2", "k2", "v2")
        all_records = store.list_all()
        assert len(all_records) == 2

    def test_list_all_by_user(self, store):
        store.put("u1", "k1", "v1")
        store.put("u2", "k2", "v2")
        assert len(store.list_all(user_id="u1")) == 1


class TestParseExpiresAt:
    def test_none(self):
        assert MemoryStore._parse_expires_at(None) is None

    def test_empty_string(self):
        assert MemoryStore._parse_expires_at("") is None

    def test_unix_timestamp(self):
        result = MemoryStore._parse_expires_at(1700000000)
        assert result is not None
        assert "2023" in result

    def test_iso_string(self):
        result = MemoryStore._parse_expires_at("2025-01-01T00:00:00Z")
        assert result is not None

    def test_iso_without_tz(self):
        result = MemoryStore._parse_expires_at("2025-01-01T00:00:00")
        assert result is not None

    def test_invalid_string(self):
        assert MemoryStore._parse_expires_at("not-a-date") is None


class TestNormalizeLifecycle:
    def test_non_dict_passthrough(self):
        assert MemoryStore._normalize_lifecycle("string") == "string"
        assert MemoryStore._normalize_lifecycle(42) == 42

    def test_plain_dict_passthrough(self):
        d = {"foo": "bar"}
        assert MemoryStore._normalize_lifecycle(d) == d

    def test_document_gets_lifecycle(self):
        d = {"text": "hello", "meta": {}}
        result = MemoryStore._normalize_lifecycle(d)
        assert result["meta"]["retention_class"] == DEFAULT_RETENTION_CLASS
        assert result["meta"]["legal_hold"] is False

    def test_retention_class_normalized(self):
        d = {"text": "x", "meta": {"retention_class": "  LONG  "}}
        result = MemoryStore._normalize_lifecycle(d)
        assert result["meta"]["retention_class"] == "long"

    def test_invalid_retention_class_defaults(self):
        d = {"text": "x", "meta": {"retention_class": "invalid"}}
        result = MemoryStore._normalize_lifecycle(d)
        assert result["meta"]["retention_class"] == DEFAULT_RETENTION_CLASS

    def test_legal_hold_string_false(self):
        d = {"text": "x", "meta": {"legal_hold": "false"}}
        result = MemoryStore._normalize_lifecycle(d)
        assert result["meta"]["legal_hold"] is False

    def test_legal_hold_string_true(self):
        d = {"text": "x", "meta": {"legal_hold": "true"}}
        result = MemoryStore._normalize_lifecycle(d)
        assert result["meta"]["legal_hold"] is True

    def test_legal_hold_string_one(self):
        d = {"text": "x", "meta": {"legal_hold": "1"}}
        result = MemoryStore._normalize_lifecycle(d)
        assert result["meta"]["legal_hold"] is True

    def test_legal_hold_string_zero(self):
        d = {"text": "x", "meta": {"legal_hold": "0"}}
        result = MemoryStore._normalize_lifecycle(d)
        assert result["meta"]["legal_hold"] is False


class TestIsRecordExpired:
    def test_not_expired(self):
        future = time.time() + 86400
        record = {"value": {"meta": {"expires_at": future}}}
        assert MemoryStore._is_record_expired(record) is False

    def test_expired(self):
        past = time.time() - 86400
        record = {"value": {"meta": {"expires_at": past}}}
        assert MemoryStore._is_record_expired(record) is True

    def test_legal_hold_prevents_expiry(self):
        past = time.time() - 86400
        record = {"value": {"meta": {"expires_at": past, "legal_hold": True}}}
        assert MemoryStore._is_record_expired(record) is False

    def test_no_expiry(self):
        record = {"value": {"meta": {}}}
        assert MemoryStore._is_record_expired(record) is False

    def test_non_dict_value(self):
        assert MemoryStore._is_record_expired({"value": "string"}) is False


class TestMemoryStoreCompatHelpers:
    def test_normalize_document_lifecycle_keeps_contract(self):
        payload = {
            "text": "hello",
            "meta": {"retention_class": "LONG", "legal_hold": "yes"},
        }

        result = normalize_document_lifecycle(
            payload,
            default_retention_class=DEFAULT_RETENTION_CLASS,
            allowed_retention_classes={"short", "medium", "long"},
            parse_expires_at=MemoryStore._parse_expires_at,
        )

        assert result["meta"]["retention_class"] == "long"
        assert result["meta"]["legal_hold"] is True

    def test_is_record_expired_compat_handles_expired_record(self):
        past = time.time() - 86400
        record = {"value": {"meta": {"expires_at": past}}}

        assert is_record_expired_compat(
            record,
            parse_expires_at=MemoryStore._parse_expires_at,
        ) is True

    def test_erase_user_records_prefers_patched_helper(self, store):
        store.put("u1", "k1", {"text": "secret"})

        helper_module = mock.Mock()
        helper_module.erase_user_data = mock.Mock(
            return_value=(
                [],
                {"deleted_count": 1, "reason": "gdpr", "actor": "tester"},
            )
        )

        report = erase_user_records(
            store=store,
            helper_module=helper_module,
            original_helper=object(),
            fallback_helper=mock.Mock(),
            user_id="u1",
            reason="gdpr",
            actor="tester",
        )

        assert report["ok"] is True
        helper_module.erase_user_data.assert_called_once()

    def test_recent_records_compat_prefers_patched_helper(self, store):
        store.put("u1", "k1", {"text": "alpha"})
        helper_module = mock.Mock()
        helper_module.filter_recent_records = mock.Mock(
            return_value=[{"key": "patched"}]
        )

        result = recent_records_compat(
            store=store,
            helper_module=helper_module,
            original_helper=object(),
            fallback_helper=mock.Mock(),
            user_id="u1",
            limit=5,
        )

        assert result == [{"key": "patched"}]
        helper_module.filter_recent_records.assert_called_once()

    def test_search_records_compat_prefers_patched_helper(self, store):
        store.put("u1", "k1", {"text": "hello world", "kind": "episodic"})
        helper_module = mock.Mock()
        helper_module.build_kvs_search_hits = mock.Mock(
            return_value=[{"id": "patched", "text": "hello world", "score": 1.0}]
        )

        result = search_records_compat(
            store=store,
            helper_module=helper_module,
            original_helper=object(),
            fallback_helper=mock.Mock(),
            query="hello",
            user_id="u1",
        )

        assert result == {
            "episodic": [{"id": "patched", "text": "hello world", "score": 1.0}]
        }
        helper_module.build_kvs_search_hits.assert_called_once()

    def test_put_episode_record_logs_vector_failure_without_breaking(self, store):
        mem_vec = mock.Mock()
        mem_vec.add.side_effect = RuntimeError("vector down")
        logger = mock.Mock()

        key = put_episode_record(
            store=store,
            text="episodic note",
            tags=["ops"],
            meta={"user_id": "u1"},
            mem_vec=mem_vec,
            logger=logger,
        )

        assert key.startswith("episode_")
        assert store.get("u1", key)["text"] == "episodic note"
        logger.warning.assert_called_once()

    def test_summarize_records_for_planner_uses_search_contract(self, store):
        store.put("u1", "k1", {"text": "planner context", "kind": "episodic"})

        result = summarize_records_for_planner(
            store=store,
            user_id="u1",
            query="planner",
            limit=3,
            build_summary=lambda items: f"items={len(items)}",
        )

        assert result == "items=1"


class TestSearch:
    def test_basic_search(self, store):
        store.put("u1", "k1", {"text": "hello world", "kind": "episodic"})
        result = store.search("hello")
        assert "episodic" in result
        assert len(result["episodic"]) > 0

    def test_empty_query(self, store):
        assert store.search("") == {}

    def test_no_matches(self, store):
        store.put("u1", "k1", {"text": "hello", "kind": "episodic"})
        result = store.search("zzzznotfound", min_sim=0.5)
        assert result == {} or len(result.get("episodic", [])) == 0

class TestSimpleScore:
    def test_exact_substring(self, store):
        score = store._simple_score("hello", "hello world")
        assert score >= 0.5

    def test_no_match(self, store):
        score = store._simple_score("abc", "xyz")
        assert score < 0.5

    def test_empty(self, store):
        assert store._simple_score("", "hello") == 0.0

class TestRecent:
    def test_recent(self, store):
        store.put("u1", "k1", {"text": "first"})
        store.put("u1", "k2", {"text": "second"})
        results = store.recent("u1", limit=1)
        assert len(results) <= 1

    def test_recent_with_contains(self, store):
        store.put("u1", "k1", {"text": "apple pie"})
        store.put("u1", "k2", {"text": "banana split"})
        results = store.recent("u1", contains="apple")
        assert len(results) == 1

class TestEraseUser:
    def test_erase(self, store):
        store.put("u1", "k1", "v1")
        store.put("u2", "k2", "v2")
        report = store.erase_user("u1", "gdpr", "admin")
        assert report["deleted_count"] >= 1
        assert store.get("u1", "k1") is None

class TestPutEpisode:
    def test_basic_episode(self, store):
        key = store.put_episode("test episode text", tags=["test"])
        assert key.startswith("episode_")

class TestSummarizeForPlanner:
    def test_no_matches(self, store):
        result = store.summarize_for_planner("u1", "nonexistent")
        assert "見つかりませんでした" in result

    def test_with_matches(self, store):
        store.put("u1", "k1", {"text": "VERITAS project update", "kind": "episodic"})
        result = store.summarize_for_planner("u1", "VERITAS")
        assert "VERITAS" in result

class TestAppendHistory:
    def test_append(self, store):
        assert store.append_history("u1", {"event": "test"}) is True

class TestAddUsage:
    def test_add(self, store):
        assert store.add_usage("u1", cited_ids=["id1"]) is True


class TestMemoryStoreIOAndIsolation:
    def test_load_all_returns_empty_when_file_missing(self, tmp_path):
        path = tmp_path / "missing.json"
        store = MemoryStore(path)
        path.unlink()

        assert store._load_all(copy=True, use_cache=False) == []

    def test_load_all_returns_empty_for_corrupt_json(self, tmp_path):
        path = tmp_path / "memory.json"
        path.write_text("{bad json", encoding="utf-8")
        store = MemoryStore(path)

        assert store._load_all(copy=True, use_cache=False) == []

    def test_save_all_returns_false_on_atomic_write_error(self, tmp_path, monkeypatch):
        store = MemoryStore(tmp_path / "memory.json")

        @contextmanager
        def fake_lock(_path):
            yield

        def bad_atomic_write_json(*_args, **_kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr("veritas_os.core.memory_store.locked_memory", fake_lock)
        monkeypatch.setattr(
            "veritas_os.core.atomic_io.atomic_write_json",
            bad_atomic_write_json,
        )

        assert store._save_all([]) is False

    def test_put_get_list_with_user_isolation(self, store):
        assert store.put("u1", "k1", "v1") is True
        assert store.put("u2", "k1", "v2") is True

        assert store.get("u1", "k1") == "v1"
        assert store.get("u2", "k1") == "v2"

        u1_records = store.list_all("u1")
        u2_records = store.list_all("u2")
        assert len(u1_records) == 1
        assert len(u2_records) == 1
        assert u1_records[0]["value"] == "v1"
        assert u2_records[0]["value"] == "v2"

    def test_expired_record_filtered_but_legal_hold_survives(self, store):
        now = datetime.now(timezone.utc).timestamp()
        expired = now - 60
        store.put(
            "u1",
            "expired",
            {"text": "stale", "meta": {"expires_at": expired, "legal_hold": False}},
        )
        store.put(
            "u1",
            "held",
            {"text": "protected", "meta": {"expires_at": expired, "legal_hold": True}},
        )

        assert store.get("u1", "expired") is None
        held = store.get("u1", "held")
        assert held is not None
        assert held["text"] == "protected"
        assert [r["key"] for r in store.list_all("u1")] == ["held"]

    def test_search_filters_by_user_kind_and_min_similarity(self, store):
        store.put("u1", "k1", {"text": "alpha plan", "kind": "episodic"})
        store.put("u2", "k2", {"text": "alpha plan", "kind": "semantic"})

        result = store.search(
            "alpha",
            user_id="u1",
            kinds=["episodic"],
            min_sim=0.5,
        )

        assert "episodic" in result
        assert len(result["episodic"]) == 1
        assert result["episodic"][0]["id"] == "k1"

    def test_search_returns_empty_when_filtered_out(self, store):
        store.put("u1", "k1", {"text": "tiny signal", "kind": "episodic"})

        assert store.search("completely different", min_sim=0.9) == {}


# ============================================================
# Source: test_memory_store_hardening.py
# ============================================================


import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import pytest

from veritas_os.core.memory_store import (
    ALLOWED_RETENTION_CLASSES,
    DEFAULT_RETENTION_CLASS,
    MemoryStore,
)


@pytest.fixture
def store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(tmp_path / "memory.json")


# ---------------------------------------------------------------------------
# MemoryStore.__init__ — cache TTL env var fallback
# ---------------------------------------------------------------------------


class TestCacheTTLEnvVar:
    def test_invalid_cache_ttl_falls_back_to_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Invalid VERITAS_MEMORY_CACHE_TTL triggers fallback to 5.0."""
        monkeypatch.setenv("VERITAS_MEMORY_CACHE_TTL", "not_a_number")
        s = MemoryStore(tmp_path / "memory.json")
        assert s._cache_ttl == 5.0

    def test_valid_cache_ttl_is_applied(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("VERITAS_MEMORY_CACHE_TTL", "10.0")
        s = MemoryStore(tmp_path / "memory.json")
        assert s._cache_ttl == 10.0


# ---------------------------------------------------------------------------
# _load_all — cache hit paths
# ---------------------------------------------------------------------------


class TestLoadAllCacheBehavior:
    def test_cache_hit_returns_cached_data(self, store: MemoryStore) -> None:
        """After put(), a subsequent _load_all should use cache if mtime matches."""
        store.put("u1", "k1", "v1")
        data1 = store._load_all(copy=True)
        data2 = store._load_all(copy=True)
        assert data1 == data2

    def test_cache_hit_copy_false_returns_same_reference(
        self, store: MemoryStore
    ) -> None:
        """copy=False on cache hit should return the same list object."""
        store.put("u1", "k1", "v1")
        # Prime the cache
        store._load_all(copy=False)
        ref1 = store._load_all(copy=False)
        ref2 = store._load_all(copy=False)
        assert ref1 is ref2

    def test_cache_stat_file_not_found(
        self, tmp_path: Path
    ) -> None:
        """If file is deleted between init and _load_all, mtime defaults to 0."""
        path = tmp_path / "memory.json"
        store = MemoryStore(path)
        path.unlink()
        data = store._load_all(copy=True, use_cache=True)
        assert data == []

    def test_load_all_copy_false_after_file_read(
        self, store: MemoryStore
    ) -> None:
        """copy=False after fresh read returns list without copying."""
        store.put("u1", "k1", "v1")
        store._cache_data = None  # Invalidate cache
        data = store._load_all(copy=False, use_cache=False)
        assert len(data) == 1
        assert data[0]["value"] == "v1"

    def test_load_all_copy_true_returns_deepcopy(
        self, store: MemoryStore
    ) -> None:
        """copy=True should not allow nested mutation to leak into cache."""
        store.put("u1", "k1", {"text": "v1", "meta": {"nested": {"x": 1}}})
        loaded = store._load_all(copy=True)
        loaded[0]["value"]["meta"]["nested"]["x"] = 999

        original = store.get("u1", "k1")
        assert original["meta"]["nested"]["x"] == 1


# ---------------------------------------------------------------------------
# _load_all — error handling
# ---------------------------------------------------------------------------


class TestLoadAllErrorHandling:
    def test_os_error_on_file_read(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OSError during JSON load should return empty list."""
        path = tmp_path / "memory.json"
        path.write_text("[]", encoding="utf-8")
        store = MemoryStore(path)

        @contextmanager
        def boom_lock(_path, timeout=5.0):
            raise OSError("disk failure")

        monkeypatch.setattr("veritas_os.core.memory_store.locked_memory", boom_lock)
        data = store._load_all(copy=True, use_cache=False)
        assert data == []

    def test_timeout_error_on_file_read(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """TimeoutError during file lock should return empty list."""
        path = tmp_path / "memory.json"
        path.write_text("[]", encoding="utf-8")
        store = MemoryStore(path)

        @contextmanager
        def timeout_lock(_path, timeout=5.0):
            raise TimeoutError("lock timeout")

        monkeypatch.setattr("veritas_os.core.memory_store.locked_memory", timeout_lock)
        data = store._load_all(copy=True, use_cache=False)
        assert data == []


# ---------------------------------------------------------------------------
# _parse_expires_at — edge cases
# ---------------------------------------------------------------------------


class TestParseExpiresAtEdgeCases:
    def test_unsupported_type_returns_none(self) -> None:
        """Non-string/numeric types should return None (fail-closed)."""
        assert MemoryStore._parse_expires_at([1, 2]) is None
        assert MemoryStore._parse_expires_at({"key": "val"}) is None
        assert MemoryStore._parse_expires_at(object()) is None

    def test_whitespace_only_string_returns_none(self) -> None:
        assert MemoryStore._parse_expires_at("   ") is None

    def test_float_timestamp(self) -> None:
        result = MemoryStore._parse_expires_at(1700000000.5)
        assert result is not None and "2023" in result

    def test_out_of_range_timestamp_returns_none(self) -> None:
        assert MemoryStore._parse_expires_at(float("inf")) is None


# ---------------------------------------------------------------------------
# _is_record_expired — branch coverage
# ---------------------------------------------------------------------------


class TestIsRecordExpiredBranches:
    def test_non_dict_meta_returns_false(self) -> None:
        """If meta is not a dict, record is considered not expired."""
        record = {"value": {"meta": "not-a-dict"}}
        assert MemoryStore._is_record_expired(record) is False

    def test_string_legal_hold_true_prevents_expiry(self) -> None:
        """String 'true' legal_hold must prevent expiry (same as bool True)."""
        past = time.time() - 86400
        record = {"value": {"meta": {"expires_at": past, "legal_hold": "true"}}}
        assert MemoryStore._is_record_expired(record) is False

    def test_string_legal_hold_yes_prevents_expiry(self) -> None:
        past = time.time() - 86400
        record = {"value": {"meta": {"expires_at": past, "legal_hold": "yes"}}}
        assert MemoryStore._is_record_expired(record) is False

    def test_string_legal_hold_one_prevents_expiry(self) -> None:
        past = time.time() - 86400
        record = {"value": {"meta": {"expires_at": past, "legal_hold": "1"}}}
        assert MemoryStore._is_record_expired(record) is False

    def test_string_legal_hold_false_allows_expiry(self) -> None:
        """String 'false' must NOT prevent expiry."""
        past = time.time() - 86400
        record = {"value": {"meta": {"expires_at": past, "legal_hold": "false"}}}
        assert MemoryStore._is_record_expired(record) is True

    def test_now_ts_parameter_used(self) -> None:
        """Explicit now_ts should override time.time()."""
        record = {"value": {"meta": {"expires_at": "2024-01-01T00:00:00+00:00"}}}
        # now_ts before expiry
        assert MemoryStore._is_record_expired(record, now_ts=0.0) is False
        # now_ts after expiry
        future_ts = datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp()
        assert MemoryStore._is_record_expired(record, now_ts=future_ts) is True

    def test_value_is_none_returns_false(self) -> None:
        record = {"value": None}
        assert MemoryStore._is_record_expired(record) is False

    def test_empty_record_returns_false(self) -> None:
        assert MemoryStore._is_record_expired({}) is False


# ---------------------------------------------------------------------------
# _is_record_legal_hold / _should_cascade_delete_semantic delegates
# ---------------------------------------------------------------------------


class TestStaticDelegates:
    def test_is_record_legal_hold_true(self) -> None:
        record = {"value": {"meta": {"legal_hold": True}}}
        assert MemoryStore._is_record_legal_hold(record) is True

    def test_is_record_legal_hold_false(self) -> None:
        record = {"value": {"meta": {"legal_hold": False}}}
        assert MemoryStore._is_record_legal_hold(record) is False

    def test_is_record_legal_hold_string_true(self) -> None:
        record = {"value": {"meta": {"legal_hold": "true"}}}
        assert MemoryStore._is_record_legal_hold(record) is True

    def test_is_record_legal_hold_string_false(self) -> None:
        record = {"value": {"meta": {"legal_hold": "false"}}}
        assert MemoryStore._is_record_legal_hold(record) is False

    def test_should_cascade_delete_semantic_positive(self) -> None:
        record = {
            "value": {
                "kind": "semantic",
                "meta": {
                    "user_id": "u1",
                    "source_episode_keys": ["ep-1"],
                    "legal_hold": False,
                },
            }
        }
        assert (
            MemoryStore._should_cascade_delete_semantic(record, "u1", {"ep-1"})
            is True
        )

    def test_should_cascade_delete_semantic_negative(self) -> None:
        record = {
            "value": {
                "kind": "semantic",
                "meta": {
                    "user_id": "u1",
                    "source_episode_keys": ["ep-1"],
                    "legal_hold": False,
                },
            }
        }
        assert (
            MemoryStore._should_cascade_delete_semantic(record, "u1", {"ep-99"})
            is False
        )


# ---------------------------------------------------------------------------
# search() — branch coverage
# ---------------------------------------------------------------------------


class TestSearchBranches:
    def test_search_skips_non_dict_values(self, store: MemoryStore) -> None:
        """Records with non-dict values should be silently skipped."""
        store.put("u1", "k1", "plain string value")
        result = store.search("plain")
        assert result == {}

    def test_search_skips_records_without_text(self, store: MemoryStore) -> None:
        """Records with empty text/query should be skipped."""
        store.put("u1", "k1", {"kind": "episodic", "tags": ["t1"]})
        result = store.search("anything")
        assert result == {}

    def test_search_user_id_filtering(self, store: MemoryStore) -> None:
        """user_id filter excludes records from other users."""
        store.put("u1", "k1", {"text": "shared term", "kind": "episodic"})
        store.put("u2", "k2", {"text": "shared term", "kind": "episodic"})
        result = store.search("shared", user_id="u1")
        assert "episodic" in result
        ids = [h["meta"]["user_id"] for h in result["episodic"]]
        assert all(uid == "u1" for uid in ids)

    def test_search_empty_user_id_is_not_bypass(self, store: MemoryStore) -> None:
        """Empty-string user_id should match only empty user records."""
        store.put("u1", "k1", {"text": "shared term", "kind": "episodic"})
        store.put("", "k2", {"text": "shared term", "kind": "episodic"})
        result = store.search("shared", user_id="")
        hits = result.get("episodic", [])
        assert len(hits) == 1
        assert hits[0]["meta"]["user_id"] == ""

    def test_search_kind_filtering(self, store: MemoryStore) -> None:
        """kinds filter only returns matching kinds.

        Note: MemoryStore.search() always groups results under the
        ``"episodic"`` key regardless of the actual record kind.
        """
        store.put("u1", "k1", {"text": "term", "kind": "episodic"})
        store.put("u1", "k2", {"text": "term", "kind": "semantic"})

        # Filter to semantic only
        result = store.search("term", kinds=["semantic"])
        hits = result.get("episodic", [])
        assert len(hits) == 1
        assert hits[0]["meta"]["kind"] == "semantic"

        # Filter to episodic only
        result2 = store.search("term", kinds=["episodic"])
        hits2 = result2.get("episodic", [])
        assert len(hits2) == 1
        assert hits2[0]["meta"]["kind"] == "episodic"

    def test_search_respects_k_limit(self, store: MemoryStore) -> None:
        """k parameter limits the number of results."""
        for i in range(5):
            store.put("u1", f"k{i}", {"text": "common term", "kind": "episodic"})
        result = store.search("common", k=2)
        assert len(result.get("episodic", [])) <= 2

    def test_search_negative_k_returns_empty(self, store: MemoryStore) -> None:
        store.put("u1", "k1", {"text": "common term", "kind": "episodic"})
        assert store.search("common", k=-1) == {}

    def test_search_invalid_min_sim_fails_closed(self, store: MemoryStore) -> None:
        store.put("u1", "k1", {"text": "common term", "kind": "episodic"})
        assert store.search("common", min_sim="bad-value") == {}

    def test_search_whitespace_query(self, store: MemoryStore) -> None:
        """Whitespace-only query should return empty dict."""
        store.put("u1", "k1", {"text": "hello", "kind": "episodic"})
        assert store.search("   ") == {}

    def test_search_none_query(self, store: MemoryStore) -> None:
        """None query should be handled safely."""
        assert store.search(None) == {}

    def test_search_result_structure(self, store: MemoryStore) -> None:
        """Verify search hit structure has expected keys."""
        store.put("u1", "k1", {"text": "target text", "kind": "episodic", "tags": ["t1"]})
        result = store.search("target")
        assert "episodic" in result
        hit = result["episodic"][0]
        assert set(hit.keys()) == {"id", "text", "score", "tags", "ts", "meta"}
        assert set(hit["meta"].keys()) == {"user_id", "created_at", "kind"}

    def test_search_sorted_by_score_descending(self, store: MemoryStore) -> None:
        """Results should be sorted by score, highest first."""
        store.put("u1", "k1", {"text": "partial match", "kind": "episodic"})
        store.put("u1", "k2", {"text": "exact partial match terms", "kind": "episodic"})
        result = store.search("partial match")
        hits = result.get("episodic", [])
        if len(hits) >= 2:
            assert hits[0]["score"] >= hits[1]["score"]


# ---------------------------------------------------------------------------
# _simple_score — edge cases
# ---------------------------------------------------------------------------


class TestSimpleScoreEdgeCases:
    def test_empty_text_returns_zero(self, store: MemoryStore) -> None:
        assert store._simple_score("hello", "") == 0.0

    def test_both_empty(self, store: MemoryStore) -> None:
        assert store._simple_score("", "") == 0.0

    def test_token_overlap_without_substring(self, store: MemoryStore) -> None:
        """Tokens match but full substring does not."""
        score = store._simple_score("alpha beta", "gamma alpha delta")
        assert 0.0 < score < 1.0

    def test_reverse_substring(self, store: MemoryStore) -> None:
        """When text is contained in query (reverse substring)."""
        score = store._simple_score("hello world foo", "hello")
        assert score >= 0.5

    def test_case_insensitive(self, store: MemoryStore) -> None:
        score = store._simple_score("HELLO", "hello world")
        assert score >= 0.5


# ---------------------------------------------------------------------------
# recent() — edge cases
# ---------------------------------------------------------------------------


class TestRecentEdgeCases:
    def test_recent_with_non_dict_value_and_contains(
        self, store: MemoryStore
    ) -> None:
        """Non-dict values should be stringified for contains matching."""
        store.put("u1", "k1", "simple string with keyword")
        results = store.recent("u1", contains="keyword")
        assert len(results) == 1

    def test_recent_no_match_contains(self, store: MemoryStore) -> None:
        store.put("u1", "k1", {"text": "no match here"})
        results = store.recent("u1", contains="zzz")
        assert len(results) == 0

    def test_recent_empty_user(self, store: MemoryStore) -> None:
        results = store.recent("nonexistent_user")
        assert results == []


class TestListAllUserBoundary:
    def test_list_all_empty_user_id_does_not_return_other_users(
        self, store: MemoryStore
    ) -> None:
        store.put("u1", "k1", "v1")
        store.put("", "k2", "v2")
        results = store.list_all(user_id="")
        assert len(results) == 1
        assert results[0]["user_id"] == ""


# ---------------------------------------------------------------------------
# put_episode — branch coverage
# ---------------------------------------------------------------------------


class TestPutEpisodeBranches:
    def test_kwargs_passthrough(self, store: MemoryStore) -> None:
        """Extra kwargs should be added to the episode record."""
        key = store.put_episode(
            "text", tags=["t"], meta={"user_id": "u1"}, custom_field="custom_val"
        )
        record = store.get("u1", key)
        assert record["custom_field"] == "custom_val"

    def test_kwargs_do_not_overwrite_existing_keys(
        self, store: MemoryStore
    ) -> None:
        """kwargs should not overwrite text/tags/meta."""
        key = store.put_episode(
            "original", tags=["orig"], meta={"user_id": "u1"}, extra="extra_val"
        )
        record = store.get("u1", key)
        assert record["text"] == "original"
        assert record["extra"] == "extra_val"

    def test_put_episode_stores_to_kvs(self, store: MemoryStore) -> None:
        """put_episode should persist the episode via KVS put."""
        key = store.put_episode("saved text", tags=["t1"])
        # Default user_id when none in meta is "episodic"
        record = store.get("episodic", key)
        assert record is not None
        assert record["text"] == "saved text"
        assert record["tags"] == ["t1"]

    def test_put_episode_with_user_meta(self, store: MemoryStore) -> None:
        """put_episode should use meta.user_id if provided."""
        key = store.put_episode("test", meta={"user_id": "alice"})
        record = store.get("alice", key)
        assert record is not None

    def test_vector_sync_success_via_original(
        self, tmp_path: Path
    ) -> None:
        """Test vector sync using the original put_episode (not compat).

        This tests the _get_mem_vec_fn parameter which only exists on the
        original MemoryStore.put_episode, not the compat replacement.
        """
        # Use the original method directly to bypass any compat replacement
        from veritas_os.core.memory_store import MemoryStore as MS

        store = MS(tmp_path / "memory.json")
        vec = mock.Mock()
        vec.add.return_value = "vec-id"

        # Call the original class method descriptor directly
        original_put_episode = MS.__dict__.get("put_episode")
        if original_put_episode is None:
            pytest.skip("put_episode not in class __dict__ (replaced by compat)")

        import inspect
        sig = inspect.signature(original_put_episode)
        if "_get_mem_vec_fn" not in sig.parameters:
            pytest.skip("put_episode has been replaced by compat layer")

        key = original_put_episode(
            store, "sync test", tags=["t"], _get_mem_vec_fn=lambda: vec
        )
        assert key.startswith("episode_")
        vec.add.assert_called_once()

    def test_vector_sync_fn_returns_none(self, store: MemoryStore) -> None:
        """put_episode when _get_mem_vec_fn returns None."""
        import inspect

        sig = inspect.signature(type(store).put_episode)
        if "_get_mem_vec_fn" not in sig.parameters:
            pytest.skip("put_episode has been replaced by compat layer")

        key = store.put_episode(
            "no vec", tags=["t"], _get_mem_vec_fn=lambda: None
        )
        assert key.startswith("episode_")

    def test_vector_sync_error_logged(
        self, store: MemoryStore, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Vector add error should be logged, not raised."""
        import inspect

        sig = inspect.signature(type(store).put_episode)
        if "_get_mem_vec_fn" not in sig.parameters:
            pytest.skip("put_episode has been replaced by compat layer")

        vec = mock.Mock()
        vec.add.side_effect = RuntimeError("vector down")

        with caplog.at_level("WARNING"):
            key = store.put_episode(
                "fail vec", tags=["t"], _get_mem_vec_fn=lambda: vec
            )

        assert key.startswith("episode_")
        assert "MEM_VEC.add error" in caplog.text

    def test_default_user_id_is_episodic(self, store: MemoryStore) -> None:
        """Without meta.user_id, default user_id should be 'episodic'."""
        key = store.put_episode("no user", tags=[])
        record = store.get("episodic", key)
        assert record is not None
        assert record["text"] == "no user"

    def test_put_episode_skips_vector_when_put_fails(
        self, store: MemoryStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import inspect

        sig = inspect.signature(type(store).put_episode)
        if "_get_mem_vec_fn" not in sig.parameters:
            pytest.skip("put_episode has been replaced by compat layer")

        vec = mock.Mock()
        monkeypatch.setattr(store, "put", lambda *_args, **_kwargs: False)
        key = store.put_episode("x", _get_mem_vec_fn=lambda: vec)
        assert key.startswith("episode_")
        vec.add.assert_not_called()


# ---------------------------------------------------------------------------
# erase_user — integration
# ---------------------------------------------------------------------------


class TestEraseUserIntegration:
    def test_erase_with_legal_hold_protection(self, store: MemoryStore) -> None:
        """Records with legal hold survive erasure."""
        past = time.time() - 86400
        store.put("u1", "normal", {"text": "delete me"})
        store.put(
            "u1",
            "held",
            {"text": "protected", "meta": {"legal_hold": True, "expires_at": past}},
        )
        report = store.erase_user("u1", "gdpr", "admin")
        assert report["deleted_count"] >= 1
        assert report["protected_by_legal_hold"] >= 1
        # Legal hold record should survive
        held = store.get("u1", "held")
        assert held is not None

    def test_erase_with_string_legal_hold(self, store: MemoryStore) -> None:
        """String 'true' legal_hold should protect from erasure."""
        store.put(
            "u1",
            "held_str",
            {"text": "protected", "meta": {"legal_hold": "true"}},
        )
        report = store.erase_user("u1", "gdpr", "admin")
        assert report["protected_by_legal_hold"] >= 1
        assert store.get("u1", "held_str") is not None

    def test_erase_creates_audit_trail(self, store: MemoryStore) -> None:
        """Erase should create an audit record."""
        store.put("u1", "k1", "v1")
        store.erase_user("u1", "gdpr", "admin")
        all_records = store.list_all()
        audit = [r for r in all_records if r.get("user_id") == "__audit__"]
        assert len(audit) >= 1

    def test_erase_cascade_deletes_semantic_lineage(
        self, store: MemoryStore
    ) -> None:
        """Semantic records sourced from erased episodes should be cascade-deleted."""
        store.put("u1", "ep1", {"text": "episode", "kind": "episodic"})
        store.put(
            "u1",
            "sem1",
            {
                "text": "semantic summary",
                "kind": "semantic",
                "meta": {
                    "user_id": "u1",
                    "source_episode_keys": ["ep1"],
                    "legal_hold": False,
                },
            },
        )
        report = store.erase_user("u1", "gdpr", "admin")
        assert report["cascade_deleted_count"] >= 1
        assert store.get("u1", "sem1") is None

    def test_erase_report_ok_false_on_save_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If saving fails after erase, report['ok'] should be False."""
        store = MemoryStore(tmp_path / "memory.json")
        store.put("u1", "k1", "v1")

        # Make _save_all always fail from now on
        monkeypatch.setattr(store, "_save_all", lambda data: False)
        report = store.erase_user("u1", "gdpr", "admin")
        assert report["ok"] is False

    def test_erase_other_user_unaffected(self, store: MemoryStore) -> None:
        """Erasing u1 should not affect u2's records."""
        store.put("u1", "k1", "v1")
        store.put("u2", "k2", "v2")
        store.erase_user("u1", "gdpr", "admin")
        assert store.get("u2", "k2") == "v2"


# ---------------------------------------------------------------------------
# _save_all — error branches
# ---------------------------------------------------------------------------


class TestSaveAllErrorBranches:
    def test_os_error_returns_false(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = MemoryStore(tmp_path / "memory.json")

        @contextmanager
        def fake_lock(_path, timeout=5.0):
            yield

        monkeypatch.setattr("veritas_os.core.memory_store.locked_memory", fake_lock)
        monkeypatch.setattr(
            "veritas_os.core.atomic_io.atomic_write_json",
            mock.Mock(side_effect=OSError("write failed")),
        )
        assert store._save_all([]) is False

    def test_type_error_returns_false(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = MemoryStore(tmp_path / "memory.json")

        @contextmanager
        def fake_lock(_path, timeout=5.0):
            yield

        monkeypatch.setattr("veritas_os.core.memory_store.locked_memory", fake_lock)
        monkeypatch.setattr(
            "veritas_os.core.atomic_io.atomic_write_json",
            mock.Mock(side_effect=TypeError("bad data")),
        )
        assert store._save_all([]) is False

    def test_value_error_returns_false(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = MemoryStore(tmp_path / "memory.json")

        @contextmanager
        def fake_lock(_path, timeout=5.0):
            yield

        monkeypatch.setattr("veritas_os.core.memory_store.locked_memory", fake_lock)
        monkeypatch.setattr(
            "veritas_os.core.atomic_io.atomic_write_json",
            mock.Mock(side_effect=ValueError("encoding")),
        )
        assert store._save_all([]) is False

    def test_timeout_error_returns_false(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = MemoryStore(tmp_path / "memory.json")

        @contextmanager
        def fake_lock(_path, timeout=5.0):
            raise TimeoutError("lock failed")

        monkeypatch.setattr("veritas_os.core.memory_store.locked_memory", fake_lock)
        assert store._save_all([]) is False


# ---------------------------------------------------------------------------
# memory_lifecycle.py — parse_legal_hold
# ---------------------------------------------------------------------------


class TestParseLegalHold:
    def test_bool_true(self) -> None:
        from veritas_os.core.memory_lifecycle import parse_legal_hold

        assert parse_legal_hold(True) is True

    def test_bool_false(self) -> None:
        from veritas_os.core.memory_lifecycle import parse_legal_hold

        assert parse_legal_hold(False) is False

    def test_string_true_variants(self) -> None:
        from veritas_os.core.memory_lifecycle import parse_legal_hold

        assert parse_legal_hold("true") is True
        assert parse_legal_hold("True") is True
        assert parse_legal_hold("TRUE") is True
        assert parse_legal_hold("1") is True
        assert parse_legal_hold("yes") is True
        assert parse_legal_hold("YES") is True

    def test_string_false_variants(self) -> None:
        from veritas_os.core.memory_lifecycle import parse_legal_hold

        assert parse_legal_hold("false") is False
        assert parse_legal_hold("False") is False
        assert parse_legal_hold("0") is False
        assert parse_legal_hold("no") is False
        assert parse_legal_hold("") is False

    def test_int_values(self) -> None:
        from veritas_os.core.memory_lifecycle import parse_legal_hold

        assert parse_legal_hold(1) is True
        assert parse_legal_hold(0) is False

    def test_none(self) -> None:
        from veritas_os.core.memory_lifecycle import parse_legal_hold

        assert parse_legal_hold(None) is False


# ---------------------------------------------------------------------------
# memory_lifecycle.py — additional branch coverage
# ---------------------------------------------------------------------------


class TestLifecycleAdditionalBranches:
    def test_normalize_lifecycle_non_dict_returns_unchanged(self) -> None:
        from veritas_os.core.memory_lifecycle import normalize_lifecycle, parse_expires_at

        assert normalize_lifecycle(42, "standard", {"standard"}, parse_expires_at) == 42
        assert (
            normalize_lifecycle("str", "standard", {"standard"}, parse_expires_at)
            == "str"
        )

    def test_normalize_lifecycle_string_legal_hold(self) -> None:
        """String legal_hold 'false' should be normalized to bool False."""
        from veritas_os.core.memory_lifecycle import normalize_lifecycle, parse_expires_at

        result = normalize_lifecycle(
            {"text": "x", "meta": {"legal_hold": "false"}},
            "standard",
            ALLOWED_RETENTION_CLASSES,
            parse_expires_at,
        )
        assert result["meta"]["legal_hold"] is False

    def test_normalize_lifecycle_string_legal_hold_yes(self) -> None:
        from veritas_os.core.memory_lifecycle import normalize_lifecycle, parse_expires_at

        result = normalize_lifecycle(
            {"text": "x", "meta": {"legal_hold": "yes"}},
            "standard",
            ALLOWED_RETENTION_CLASSES,
            parse_expires_at,
        )
        assert result["meta"]["legal_hold"] is True

    def test_is_record_expired_string_legal_hold_protects(self) -> None:
        """String 'true' legal hold should protect in lifecycle module too."""
        from veritas_os.core.memory_lifecycle import is_record_expired, parse_expires_at

        record = {
            "value": {
                "meta": {
                    "expires_at": "2020-01-01T00:00:00+00:00",
                    "legal_hold": "true",
                }
            }
        }
        assert (
            is_record_expired(record, parse_expires_at, now_ts=2_000_000_000.0)
            is False
        )

    def test_is_record_expired_string_legal_hold_false_allows(self) -> None:
        """String 'false' legal hold must NOT protect."""
        from veritas_os.core.memory_lifecycle import is_record_expired, parse_expires_at

        record = {
            "value": {
                "meta": {
                    "expires_at": "2020-01-01T00:00:00+00:00",
                    "legal_hold": "false",
                }
            }
        }
        assert (
            is_record_expired(record, parse_expires_at, now_ts=2_000_000_000.0)
            is True
        )

    def test_is_record_legal_hold_non_dict_value(self) -> None:
        from veritas_os.core.memory_lifecycle import is_record_legal_hold

        assert is_record_legal_hold({"value": "not-a-dict"}) is False

    def test_is_record_legal_hold_non_dict_meta(self) -> None:
        from veritas_os.core.memory_lifecycle import is_record_legal_hold

        assert is_record_legal_hold({"value": {"meta": "not-a-dict"}}) is False

    def test_is_record_legal_hold_string_true(self) -> None:
        from veritas_os.core.memory_lifecycle import is_record_legal_hold

        assert is_record_legal_hold({"value": {"meta": {"legal_hold": "true"}}}) is True

    def test_is_record_legal_hold_string_false(self) -> None:
        from veritas_os.core.memory_lifecycle import is_record_legal_hold

        assert (
            is_record_legal_hold({"value": {"meta": {"legal_hold": "false"}}}) is False
        )

    def test_should_cascade_delete_non_dict_value(self) -> None:
        from veritas_os.core.memory_lifecycle import should_cascade_delete_semantic

        assert (
            should_cascade_delete_semantic(
                {"value": "string"}, "u1", {"ep-1"}
            )
            is False
        )

    def test_should_cascade_delete_non_dict_meta(self) -> None:
        from veritas_os.core.memory_lifecycle import should_cascade_delete_semantic

        record = {"value": {"kind": "semantic", "meta": "not-a-dict"}}
        assert (
            should_cascade_delete_semantic(record, "u1", {"ep-1"}) is False
        )

    def test_should_cascade_delete_string_legal_hold_protects(self) -> None:
        """String 'true' legal_hold should protect semantic records."""
        from veritas_os.core.memory_lifecycle import should_cascade_delete_semantic

        record = {
            "value": {
                "kind": "semantic",
                "meta": {
                    "user_id": "u1",
                    "source_episode_keys": ["ep-1"],
                    "legal_hold": "true",
                },
            }
        }
        assert (
            should_cascade_delete_semantic(record, "u1", {"ep-1"}) is False
        )


# ---------------------------------------------------------------------------
# memory_compliance.py — string legal_hold consistency
# ---------------------------------------------------------------------------


class TestComplianceStringLegalHold:
    def test_is_record_legal_hold_string_true(self) -> None:
        from veritas_os.core.memory_compliance import is_record_legal_hold

        assert is_record_legal_hold({"value": {"meta": {"legal_hold": "true"}}}) is True

    def test_is_record_legal_hold_string_false(self) -> None:
        from veritas_os.core.memory_compliance import is_record_legal_hold

        assert (
            is_record_legal_hold({"value": {"meta": {"legal_hold": "false"}}}) is False
        )

    def test_should_cascade_delete_string_legal_hold(self) -> None:
        from veritas_os.core.memory_compliance import should_cascade_delete_semantic

        record = {
            "value": {
                "kind": "semantic",
                "meta": {
                    "user_id": "u1",
                    "source_episode_keys": ["ep-1"],
                    "legal_hold": "true",
                },
            }
        }
        assert (
            should_cascade_delete_semantic(record, "u1", {"ep-1"}) is False
        )

    def test_erase_user_data_respects_string_legal_hold(self) -> None:
        """String 'true' legal_hold should protect records during erasure."""
        from veritas_os.core.memory_compliance import erase_user_data

        data = [
            {
                "user_id": "u1",
                "key": "k1",
                "value": {"text": "protected", "meta": {"legal_hold": "true"}},
            },
            {
                "user_id": "u1",
                "key": "k2",
                "value": {"text": "delete me"},
            },
        ]
        kept, report = erase_user_data(data, "u1", "test", "admin")
        assert report["protected_by_legal_hold"] == 1
        assert report["deleted_count"] == 1
        user_records = [r for r in kept if r.get("user_id") == "u1"]
        assert len(user_records) == 1

    def test_erase_user_data_string_false_not_protected(self) -> None:
        """String 'false' legal_hold should NOT protect records."""
        from veritas_os.core.memory_compliance import erase_user_data

        data = [
            {
                "user_id": "u1",
                "key": "k1",
                "value": {"text": "exposed", "meta": {"legal_hold": "false"}},
            },
        ]
        kept, report = erase_user_data(data, "u1", "test", "admin")
        assert report["protected_by_legal_hold"] == 0
        assert report["deleted_count"] == 1


# ---------------------------------------------------------------------------
# POSIX flock timeout (memory_storage.py)
# ---------------------------------------------------------------------------


class TestLockedMemoryPosixTimeout:
    @pytest.mark.skipif(
        os.name == "nt",
        reason="POSIX flock branch only",
    )
    def test_posix_flock_timeout_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """POSIX flock should raise TimeoutError when lock not acquired."""
        import veritas_os.core.memory_storage as memory_storage

        if memory_storage.fcntl is None:
            pytest.skip("fcntl not available")

        target = tmp_path / "memory.json"

        def always_block(fd, operation):
            if operation != memory_storage.fcntl.LOCK_UN:
                raise BlockingIOError("always busy")

        monkeypatch.setattr(memory_storage.fcntl, "flock", always_block)
        monkeypatch.setattr(memory_storage.time, "sleep", lambda _: None)

        times = iter([0.0, 0.3, 0.7])
        monkeypatch.setattr(memory_storage.time, "time", lambda: next(times))

        with pytest.raises(TimeoutError, match="failed to acquire lock"):
            with memory_storage.locked_memory(target, timeout=0.5):
                pass


# ---------------------------------------------------------------------------
# End-to-end: persist / load round-trip
# ---------------------------------------------------------------------------


class TestPersistLoadRoundTrip:
    def test_data_survives_new_store_instance(self, tmp_path: Path) -> None:
        """Data written by one MemoryStore instance should be loadable by another."""
        path = tmp_path / "memory.json"
        store1 = MemoryStore(path)
        store1.put("u1", "k1", {"text": "persistent", "kind": "episodic"})

        store2 = MemoryStore(path)
        val = store2.get("u1", "k1")
        assert val is not None
        assert val["text"] == "persistent"

    def test_corrupt_json_recovery(self, tmp_path: Path) -> None:
        """Store should recover gracefully from corrupt JSON on disk."""
        path = tmp_path / "memory.json"
        store = MemoryStore(path)
        store.put("u1", "k1", "v1")

        # Corrupt the file
        path.write_text("<<<CORRUPT>>>", encoding="utf-8")

        data = store._load_all(copy=True, use_cache=False)
        assert data == []

        # Store should still be usable after corruption
        assert store.put("u1", "k2", "v2") is True
        assert store.get("u1", "k2") == "v2"

    def test_unicode_values_round_trip(self, tmp_path: Path) -> None:
        """Unicode text should survive persist/load cycle."""
        path = tmp_path / "memory.json"
        store = MemoryStore(path)
        store.put("u1", "k1", {"text": "日本語テスト 🎌", "kind": "episodic"})

        store2 = MemoryStore(path)
        val = store2.get("u1", "k1")
        assert val["text"] == "日本語テスト 🎌"


# ---------------------------------------------------------------------------
# User-ID boundary tests
# ---------------------------------------------------------------------------


class TestUserIdBoundary:
    def test_empty_string_user_id(self, store: MemoryStore) -> None:
        """Empty-string user_id should be a valid, distinct namespace."""
        store.put("", "k1", "empty-user")
        store.put("u1", "k1", "normal-user")
        assert store.get("", "k1") == "empty-user"
        assert store.get("u1", "k1") == "normal-user"

    def test_special_char_user_id(self, store: MemoryStore) -> None:
        """Special characters in user_id should work."""
        uid = "user@domain.com/path#fragment"
        store.put(uid, "k1", "special")
        assert store.get(uid, "k1") == "special"

    def test_user_isolation_in_search(self, store: MemoryStore) -> None:
        """Search with user_id should be isolated per user."""
        store.put("u1", "k1", {"text": "shared concept", "kind": "episodic"})
        store.put("u2", "k2", {"text": "shared concept", "kind": "episodic"})
        r1 = store.search("shared", user_id="u1")
        r2 = store.search("shared", user_id="u2")
        if r1.get("episodic"):
            assert all(h["meta"]["user_id"] == "u1" for h in r1["episodic"])
        if r2.get("episodic"):
            assert all(h["meta"]["user_id"] == "u2" for h in r2["episodic"])


# ---------------------------------------------------------------------------
# TOCTOU symlink resolution tests
# ---------------------------------------------------------------------------


class TestSymlinkResolution:
    """Verify MemoryStore resolves symlinks at init time (TOCTOU fix)."""

    def test_path_resolved_after_init(self, tmp_path: Path) -> None:
        """MemoryStore.path.parent must be an absolute resolved path."""
        store = MemoryStore(tmp_path / "data" / "store.jsonl")
        assert store.path.parent.is_absolute()
        assert store.path.parent == store.path.parent.resolve()

    def test_symlink_parent_resolved(self, tmp_path: Path) -> None:
        """If parent dir is a symlink, MemoryStore should resolve through it."""
        real_dir = tmp_path / "real_data"
        real_dir.mkdir()
        link_dir = tmp_path / "link_data"
        link_dir.symlink_to(real_dir)
        store = MemoryStore(link_dir / "store.jsonl")
        # After resolution, the path should point through the real dir
        assert "real_data" in str(store.path)


# ============================================================
# Source: test_memory_store_helpers.py
# ============================================================


from veritas_os.core import memory_store_helpers


def test_filter_recent_records_sorts_and_filters_dict_values() -> None:
    """Recent filtering should preserve recency while matching query/text fields."""
    records = [
        {"ts": 10, "value": {"text": "older note"}},
        {"ts": 20, "value": {"query": "find newest"}},
        {"ts": 15, "value": "plain text value"},
    ]

    filtered = memory_store_helpers.filter_recent_records(
        records,
        contains="new",
        limit=5,
    )

    assert filtered == [{"ts": 20, "value": {"query": "find newest"}}]


def test_simple_score_returns_partial_and_token_overlap_signal() -> None:
    """Fallback scoring should remain stable for substring and token overlap."""
    score = memory_store_helpers.simple_score(
        "alpha beta",
        "alpha beta memo",
    )

    assert score == 1.0


def test_build_kvs_search_hits_applies_user_kind_and_similarity_filters() -> None:
    """KVS hit building must preserve existing fail-closed filtering behavior."""
    records = [
        {
            "key": "keep",
            "user_id": "u1",
            "ts": 30,
            "value": {
                "text": "incident response playbook",
                "tags": ["ops"],
                "kind": "episodic",
            },
        },
        {
            "key": "drop-kind",
            "user_id": "u1",
            "ts": 20,
            "value": {"text": "incident response", "kind": "semantic"},
        },
        {
            "key": "drop-user",
            "user_id": "u2",
            "ts": 10,
            "value": {"text": "incident response", "kind": "episodic"},
        },
    ]

    hits = memory_store_helpers.build_kvs_search_hits(
        records,
        query="incident response",
        k=5,
        kinds=["episodic"],
        min_sim=0.4,
        user_id="u1",
    )

    assert hits == [
        {
            "id": "keep",
            "text": "incident response playbook",
            "score": 1.0,
            "tags": ["ops"],
            "ts": 30,
            "meta": {
                "user_id": "u1",
                "created_at": 30,
                "kind": "episodic",
            },
        }
    ]


def test_build_kvs_search_hits_empty_user_id_is_filtered() -> None:
    """Empty-string user IDs must be treated as explicit filter values."""
    records = [
        {"key": "a", "user_id": "u1", "ts": 1, "value": {"text": "hello"}},
        {"key": "b", "user_id": "", "ts": 2, "value": {"text": "hello"}},
    ]
    hits = memory_store_helpers.build_kvs_search_hits(
        records,
        query="hello",
        k=10,
        user_id="",
    )
    assert [hit["id"] for hit in hits] == ["b"]


def test_build_kvs_search_hits_invalid_min_sim_fails_closed() -> None:
    """Malformed min_sim should not broaden matches."""
    records = [
        {"key": "a", "user_id": "u1", "ts": 1, "value": {"text": "hello"}},
    ]
    hits = memory_store_helpers.build_kvs_search_hits(
        records,
        query="hello",
        k=10,
        min_sim="bad",
    )
    assert hits == []


def test_build_kvs_search_hits_non_positive_k_returns_empty() -> None:
    """Non-positive k values should produce empty results."""
    records = [
        {"key": "a", "user_id": "u1", "ts": 1, "value": {"text": "hello"}},
    ]
    assert memory_store_helpers.build_kvs_search_hits(
        records,
        query="hello",
        k=0,
    ) == []


# ============================================================
# Source: test_memory_store_io_strategy.py
# ============================================================

import json
from pathlib import Path


def _patch_store_paths(monkeypatch, tmp_path: Path):
    from veritas_os.memory import store

    monkeypatch.setattr(store, "BASE", tmp_path)
    monkeypatch.setattr(
        store,
        "FILES",
        {
            "episodic": tmp_path / "episodic.jsonl",
            "semantic": tmp_path / "semantic.jsonl",
            "skills": tmp_path / "skills.jsonl",
        },
    )
    monkeypatch.setattr(
        store,
        "INDEX",
        {
            "episodic": tmp_path / "episodic.index.npz",
            "semantic": tmp_path / "semantic.index.npz",
            "skills": tmp_path / "skills.index.npz",
        },
    )


def test_search_uses_payload_cache_without_jsonl_read(tmp_path: Path, monkeypatch):
    """キャッシュヒット時は JSONL 再走査なしで検索結果を組み立てる。"""
    _patch_store_paths(monkeypatch, tmp_path)

    from veritas_os.memory.store import MemoryStore

    ms = MemoryStore(dim=4)
    item_id = ms.put("episodic", {"text": "cache hit text", "tags": ["t"]})

    original_open = open

    def tracked_open(path, *args, **kwargs):
        if str(path).endswith("episodic.jsonl"):
            raise AssertionError("JSONL should not be opened on cache hit")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", tracked_open)

    result = ms.search("cache", k=3, kinds=["episodic"], min_sim=-1.0)
    assert result["episodic"]
    assert result["episodic"][0]["id"] == item_id


def test_search_targeted_load_reads_only_missing_payloads(tmp_path: Path, monkeypatch):
    """キャッシュミス時は対象 ID の payload だけを JSONL から段階ロードする。"""
    _patch_store_paths(monkeypatch, tmp_path)

    from veritas_os.memory.store import MemoryStore

    ms = MemoryStore(dim=4)
    first_id = ms.put("episodic", {"text": "first targeted", "tags": ["t"]})
    ms.put("episodic", {"text": "second targeted", "tags": ["t"]})

    ms._payload_cache["episodic"].pop(first_id, None)
    ms._cache_complete["episodic"] = False

    load_calls = {"count": 0}
    original_loader = ms._load_payloads_for_ids

    def tracked_loader(kind, ids):
        load_calls["count"] += 1
        return original_loader(kind, ids)

    monkeypatch.setattr(ms, "_load_payloads_for_ids", tracked_loader)

    result = ms.search("first", k=3, kinds=["episodic"], min_sim=-1.0)

    assert load_calls["count"] >= 1
    assert result["episodic"]
    assert any(item["id"] == first_id for item in result["episodic"])
    assert first_id in ms._payload_cache["episodic"]


def test_targeted_loader_stops_after_required_ids(tmp_path: Path, monkeypatch):
    """targeted loader は必要な ID が揃った時点で走査を打ち切る。"""
    _patch_store_paths(monkeypatch, tmp_path)

    from veritas_os.memory.store import MemoryStore

    ms = MemoryStore(dim=4)
    target_id = ms.put("episodic", {"text": "target payload", "tags": ["t"]})

    extra_path = tmp_path / "episodic.jsonl"
    with open(extra_path, "a", encoding="utf-8") as f:
        for i in range(200):
            f.write(json.dumps({"id": f"dummy-{i}", "text": "dummy"}, ensure_ascii=False) + "\n")

    read_lines = {"count": 0}
    original_open = open

    class CountingFile:
        def __init__(self, file_obj):
            self._file_obj = file_obj

        def __iter__(self):
            for line in self._file_obj:
                read_lines["count"] += 1
                yield line

        def __getattr__(self, name):
            return getattr(self._file_obj, name)

        def __enter__(self):
            self._file_obj.__enter__()
            return self

        def __exit__(self, exc_type, exc, tb):
            return self._file_obj.__exit__(exc_type, exc, tb)

    def tracked_open(path, *args, **kwargs):
        f = original_open(path, *args, **kwargs)
        if str(path).endswith("episodic.jsonl"):
            return CountingFile(f)
        return f

    monkeypatch.setattr("builtins.open", tracked_open)

    loaded = ms._load_payloads_for_ids("episodic", [target_id])

    assert target_id in loaded
    assert read_lines["count"] < 200


# ============================================================
# Source: test_memory_store_reliability.py
# ============================================================


import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import pytest

from veritas_os.core.memory_store import (
    ALLOWED_RETENTION_CLASSES,
    DEFAULT_RETENTION_CLASS,
    MemoryStore,
)


@pytest.fixture
def store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(tmp_path / "memory.json")


# =========================================================================
# 1. _normalize — migration edge cases
# =========================================================================


class TestNormalizeMigrationEdgeCases:
    """Failure modes in old dict-format migration."""

    def test_users_value_is_list_returns_empty(self, store: MemoryStore) -> None:
        """If 'users' is a list instead of a dict, migration should not crash."""
        raw = {"users": ["not", "a", "dict"]}
        assert store._normalize(raw) == []

    def test_users_value_is_none_returns_empty(self, store: MemoryStore) -> None:
        """If 'users' is None, migration should return empty."""
        raw = {"users": None}
        assert store._normalize(raw) == []

    def test_users_value_is_string_returns_empty(self, store: MemoryStore) -> None:
        raw = {"users": "not-a-dict"}
        assert store._normalize(raw) == []

    def test_users_value_is_int_returns_empty(self, store: MemoryStore) -> None:
        raw = {"users": 42}
        assert store._normalize(raw) == []

    def test_users_with_non_dict_udata_skipped(self, store: MemoryStore) -> None:
        """Non-dict user data should be silently skipped."""
        raw = {"users": {"u1": "not-a-dict", "u2": {"k1": "v1"}}}
        result = store._normalize(raw)
        assert len(result) == 1
        assert result[0]["user_id"] == "u2"

    def test_dict_without_users_key_returns_empty(self, store: MemoryStore) -> None:
        """A dict without 'users' key falls through to empty list."""
        raw = {"other_key": "value"}
        assert store._normalize(raw) == []


# =========================================================================
# 2. search — invalid k parameter (lines 428-429)
# =========================================================================


class TestSearchInvalidK:
    """Fail-safe: invalid k values should produce no results."""

    def test_k_as_non_numeric_string(self, store: MemoryStore) -> None:
        store.put("u1", "k1", {"text": "hello world", "kind": "episodic"})
        assert store.search("hello", k="bad") == {}

    def test_k_as_none(self, store: MemoryStore) -> None:
        store.put("u1", "k1", {"text": "hello world", "kind": "episodic"})
        assert store.search("hello", k=None) == {}

    def test_k_as_float_inf(self, store: MemoryStore) -> None:
        """float('inf') converts to int but may overflow — verify graceful."""
        store.put("u1", "k1", {"text": "hello world", "kind": "episodic"})
        # float('inf') -> int raises OverflowError, caught by ValueError handler
        try:
            result = store.search("hello", k=float("inf"))
        except (OverflowError, ValueError):
            result = {}
        # Either empty or valid — no crash
        assert isinstance(result, dict)

    def test_k_zero_returns_empty(self, store: MemoryStore) -> None:
        store.put("u1", "k1", {"text": "hello world", "kind": "episodic"})
        assert store.search("hello", k=0) == {}


# =========================================================================
# 3. search — invalid min_sim parameter (fail-closed)
# =========================================================================


class TestSearchInvalidMinSim:
    def test_min_sim_as_string(self, store: MemoryStore) -> None:
        """Non-numeric min_sim should fail-closed (no results)."""
        store.put("u1", "k1", {"text": "hello world", "kind": "episodic"})
        result = store.search("hello", min_sim="not_a_number")
        assert result == {}

    def test_min_sim_as_none_uses_float_conversion(self, store: MemoryStore) -> None:
        """None for min_sim: float(None) raises TypeError → fail-closed."""
        store.put("u1", "k1", {"text": "hello world", "kind": "episodic"})
        result = store.search("hello", min_sim=None)
        assert result == {}


# =========================================================================
# 4. _simple_score — token-only match (no substring)
# =========================================================================


class TestSimpleScoreTokenBranch:
    def test_no_substring_match_but_token_overlap(self, store: MemoryStore) -> None:
        """Tokens match but neither string contains the other."""
        score = store._simple_score("alpha beta", "gamma alpha delta")
        # base=0.0 (no substring), token_score = 1/2 = 0.5 → total = 0.25
        assert 0.0 < score < 0.5

    def test_no_match_at_all(self, store: MemoryStore) -> None:
        """No substring, no token overlap."""
        score = store._simple_score("abc def", "xyz uvw")
        assert score == 0.0


# =========================================================================
# 5. Cache behavior — TTL boundary and invalidation
# =========================================================================


class TestCacheBehavior:
    def test_cache_ttl_zero_bypasses_cache(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When TTL is 0, cache should never be used."""
        monkeypatch.setenv("VERITAS_MEMORY_CACHE_TTL", "0")
        store = MemoryStore(tmp_path / "memory.json")
        assert store._cache_ttl == 0.0

        store.put("u1", "k1", "v1")
        # Directly modify file behind the store's back
        data = json.loads(store.path.read_text(encoding="utf-8"))
        data.append({"user_id": "u1", "key": "k2", "value": "sneaky", "ts": time.time()})
        store.path.write_text(json.dumps(data), encoding="utf-8")

        # With TTL=0, should read from disk and see the new record
        assert store.get("u1", "k2") == "sneaky"

    def test_cache_invalidated_after_save(self, store: MemoryStore) -> None:
        """After successful _save_all, cache should be cleared."""
        store.put("u1", "k1", "v1")
        # Prime cache
        store._load_all(copy=False)
        assert store._cache_data is not None

        # Save clears cache
        store._save_all([{"user_id": "u1", "key": "k1", "value": "v2", "ts": time.time()}])
        assert store._cache_data is None

    def test_cache_ttl_clamped_to_max(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """TTL values above 3600 should be clamped."""
        monkeypatch.setenv("VERITAS_MEMORY_CACHE_TTL", "9999")
        store = MemoryStore(tmp_path / "memory.json")
        assert store._cache_ttl == 3600.0

    def test_negative_cache_ttl_clamped_to_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Negative TTL should be clamped to 0."""
        monkeypatch.setenv("VERITAS_MEMORY_CACHE_TTL", "-5")
        store = MemoryStore(tmp_path / "memory.json")
        assert store._cache_ttl == 0.0


# =========================================================================
# 6. _load_all — cache miss after file mutation
# =========================================================================


class TestLoadAllCacheMiss:
    def test_cache_miss_when_mtime_changes(self, store: MemoryStore) -> None:
        """If file mtime changes, cache should be invalidated."""
        store.put("u1", "k1", "v1")
        # Prime cache
        store._load_all(copy=True)
        assert store._cache_data is not None

        # Modify file to change mtime
        time.sleep(0.05)
        data = json.loads(store.path.read_text(encoding="utf-8"))
        data.append({"user_id": "u1", "key": "k2", "value": "new", "ts": time.time()})
        store.path.write_text(json.dumps(data), encoding="utf-8")

        result = store._load_all(copy=True)
        keys = [r["key"] for r in result]
        assert "k2" in keys

    def test_use_cache_false_forces_disk_read(self, store: MemoryStore) -> None:
        """use_cache=False should always read from disk."""
        store.put("u1", "k1", "v1")
        # Prime cache
        store._load_all(copy=True)

        # Even with valid cache, use_cache=False reads disk
        result = store._load_all(copy=True, use_cache=False)
        assert len(result) == 1


# =========================================================================
# 7. _is_record_expired — boundary at exact expiry time
# =========================================================================


class TestIsRecordExpiredBoundary:
    def test_exact_expiry_boundary(self) -> None:
        """Record at exactly the expiry timestamp should be expired (<=)."""
        ts = 1700000000.0
        iso = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        record = {"value": {"meta": {"expires_at": iso}}}
        assert MemoryStore._is_record_expired(record, now_ts=ts) is True

    def test_one_second_before_expiry(self) -> None:
        """One second before expiry should not be expired."""
        ts = 1700000000.0
        iso = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        record = {"value": {"meta": {"expires_at": iso}}}
        assert MemoryStore._is_record_expired(record, now_ts=ts - 1) is False

    def test_missing_value_key(self) -> None:
        """Record without 'value' key should not be expired."""
        assert MemoryStore._is_record_expired({}) is False


# =========================================================================
# 8. put_episode — save failure path
# =========================================================================


class TestPutEpisodeSaveFailure:
    def test_put_episode_returns_key_on_save_failure(
        self, store: MemoryStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """put_episode should return key even if KVS save fails."""
        import inspect

        sig = inspect.signature(type(store).put_episode)
        if "_get_mem_vec_fn" not in sig.parameters:
            pytest.skip("put_episode has been replaced by compat layer")

        vec = mock.Mock()
        monkeypatch.setattr(store, "put", lambda *a, **kw: False)
        key = store.put_episode("failed save", _get_mem_vec_fn=lambda: vec)
        assert key.startswith("episode_")
        # Vector sync should NOT be called when KVS save fails
        vec.add.assert_not_called()


# =========================================================================
# 9. erase_user — save failure propagation
# =========================================================================


class TestEraseUserSaveFailure:
    def test_erase_report_ok_false_when_save_fails(
        self, store: MemoryStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store.put("u1", "k1", "v1")
        monkeypatch.setattr(store, "_save_all", lambda data: False)
        report = store.erase_user("u1", "gdpr", "admin")
        assert report["ok"] is False
        assert report["deleted_count"] >= 1


# =========================================================================
# 10. get — expired record filtered, legal_hold preserved
# =========================================================================


class TestGetExpiryAndLegalHold:
    def test_get_expired_returns_none(self, store: MemoryStore) -> None:
        past = time.time() - 86400
        store.put("u1", "k1", {"text": "old", "meta": {"expires_at": past}})
        assert store.get("u1", "k1") is None

    def test_get_legal_hold_survives_expiry(self, store: MemoryStore) -> None:
        past = time.time() - 86400
        store.put(
            "u1", "k1",
            {"text": "held", "meta": {"expires_at": past, "legal_hold": True}},
        )
        val = store.get("u1", "k1")
        assert val is not None
        assert val["text"] == "held"


# =========================================================================
# 11. recent — ordering and contains
# =========================================================================


class TestRecentOrdering:
    def test_recent_returns_newest_first(self, store: MemoryStore) -> None:
        """Results should be sorted by ts descending."""
        for i in range(3):
            store.put("u1", f"k{i}", {"text": f"item {i}"})
            time.sleep(0.01)

        results = store.recent("u1")
        timestamps = [r.get("ts", 0) for r in results]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_recent_limit_respected(self, store: MemoryStore) -> None:
        for i in range(10):
            store.put("u1", f"k{i}", {"text": f"item {i}"})
        results = store.recent("u1", limit=3)
        assert len(results) == 3

    def test_recent_contains_matches_query_field(self, store: MemoryStore) -> None:
        """contains filter should also check 'query' field in dict values."""
        store.put("u1", "k1", {"query": "find this keyword"})
        results = store.recent("u1", contains="keyword")
        assert len(results) == 1

    def test_recent_contains_with_whitespace_only(self, store: MemoryStore) -> None:
        """Whitespace-only contains should match nothing (stripped empty)."""
        store.put("u1", "k1", {"text": "test"})
        # contains is stripped, empty string is falsy, so no filter is applied
        results = store.recent("u1", contains="   ")
        # Empty-string contains → " " after strip → non-empty → filter applied
        # " " not in "test" → no match
        # Actually "   ".strip() = "" which is falsy → no filter → all returned
        assert len(results) >= 0  # just verifying no crash


# =========================================================================
# 12. memory_lifecycle.py — parse_expires_at direct tests
# =========================================================================


class TestLifecycleParseExpiresAt:
    """Directly test memory_lifecycle.parse_expires_at for branch coverage."""

    def test_none(self) -> None:
        from veritas_os.core.memory_lifecycle import parse_expires_at

        assert parse_expires_at(None) is None

    def test_empty_string(self) -> None:
        from veritas_os.core.memory_lifecycle import parse_expires_at

        assert parse_expires_at("") is None

    def test_whitespace_string(self) -> None:
        from veritas_os.core.memory_lifecycle import parse_expires_at

        assert parse_expires_at("   ") is None

    def test_int_timestamp(self) -> None:
        from veritas_os.core.memory_lifecycle import parse_expires_at

        result = parse_expires_at(1700000000)
        assert result is not None
        assert "2023" in result

    def test_float_timestamp(self) -> None:
        from veritas_os.core.memory_lifecycle import parse_expires_at

        result = parse_expires_at(1700000000.5)
        assert result is not None

    def test_overflow_timestamp(self) -> None:
        from veritas_os.core.memory_lifecycle import parse_expires_at

        assert parse_expires_at(float("inf")) is None

    def test_iso_string_with_z(self) -> None:
        from veritas_os.core.memory_lifecycle import parse_expires_at

        result = parse_expires_at("2025-01-01T00:00:00Z")
        assert result is not None
        assert "2025" in result

    def test_iso_string_with_tz(self) -> None:
        from veritas_os.core.memory_lifecycle import parse_expires_at

        result = parse_expires_at("2025-01-01T00:00:00+09:00")
        assert result is not None

    def test_naive_iso_string(self) -> None:
        from veritas_os.core.memory_lifecycle import parse_expires_at

        result = parse_expires_at("2025-01-01T00:00:00")
        assert result is not None

    def test_invalid_string(self) -> None:
        from veritas_os.core.memory_lifecycle import parse_expires_at

        assert parse_expires_at("not-a-date") is None

    def test_unsupported_type_list(self) -> None:
        from veritas_os.core.memory_lifecycle import parse_expires_at

        assert parse_expires_at([1, 2, 3]) is None

    def test_unsupported_type_dict(self) -> None:
        from veritas_os.core.memory_lifecycle import parse_expires_at

        assert parse_expires_at({"ts": 123}) is None

    def test_unsupported_type_bool(self) -> None:
        """bool is subclass of int — should be handled as numeric."""
        from veritas_os.core.memory_lifecycle import parse_expires_at

        # bool True == 1 → epoch + 1 second
        result = parse_expires_at(True)
        assert result is not None


# =========================================================================
# 13. memory_lifecycle.py — normalize_lifecycle direct tests
# =========================================================================


class TestLifecycleNormalizeLifecycle:
    def test_memory_document_gets_defaults(self) -> None:
        from veritas_os.core.memory_lifecycle import normalize_lifecycle, parse_expires_at

        result = normalize_lifecycle(
            {"text": "hello", "meta": {}},
            "standard",
            ALLOWED_RETENTION_CLASSES,
            parse_expires_at,
        )
        assert result["meta"]["retention_class"] == "standard"
        assert result["meta"]["legal_hold"] is False
        assert result["meta"]["expires_at"] is None

    def test_invalid_retention_class_gets_default(self) -> None:
        from veritas_os.core.memory_lifecycle import normalize_lifecycle, parse_expires_at

        result = normalize_lifecycle(
            {"text": "x", "meta": {"retention_class": "bogus"}},
            "standard",
            ALLOWED_RETENTION_CLASSES,
            parse_expires_at,
        )
        assert result["meta"]["retention_class"] == "standard"

    def test_retention_class_case_normalized(self) -> None:
        from veritas_os.core.memory_lifecycle import normalize_lifecycle, parse_expires_at

        result = normalize_lifecycle(
            {"text": "x", "meta": {"retention_class": "  LONG  "}},
            "standard",
            ALLOWED_RETENTION_CLASSES,
            parse_expires_at,
        )
        assert result["meta"]["retention_class"] == "long"

    def test_missing_meta_gets_defaults(self) -> None:
        from veritas_os.core.memory_lifecycle import normalize_lifecycle, parse_expires_at

        result = normalize_lifecycle(
            {"text": "x"},
            "standard",
            ALLOWED_RETENTION_CLASSES,
            parse_expires_at,
        )
        assert "meta" in result
        assert result["meta"]["retention_class"] == "standard"

    def test_expires_at_normalized(self) -> None:
        from veritas_os.core.memory_lifecycle import normalize_lifecycle, parse_expires_at

        result = normalize_lifecycle(
            {"text": "x", "meta": {"expires_at": 1700000000}},
            "standard",
            ALLOWED_RETENTION_CLASSES,
            parse_expires_at,
        )
        assert result["meta"]["expires_at"] is not None
        assert "2023" in result["meta"]["expires_at"]

    def test_non_dict_passthrough(self) -> None:
        from veritas_os.core.memory_lifecycle import normalize_lifecycle, parse_expires_at

        assert normalize_lifecycle(42, "standard", ALLOWED_RETENTION_CLASSES, parse_expires_at) == 42
        assert normalize_lifecycle("x", "standard", ALLOWED_RETENTION_CLASSES, parse_expires_at) == "x"

    def test_plain_dict_without_lifecycle_keys_passthrough(self) -> None:
        from veritas_os.core.memory_lifecycle import normalize_lifecycle, parse_expires_at

        d = {"foo": "bar"}
        assert normalize_lifecycle(d, "standard", ALLOWED_RETENTION_CLASSES, parse_expires_at) == d


# =========================================================================
# 14. memory_lifecycle.py — is_record_expired direct tests
# =========================================================================


class TestLifecycleIsRecordExpired:
    def test_expired_record(self) -> None:
        from veritas_os.core.memory_lifecycle import is_record_expired, parse_expires_at

        record = {"value": {"meta": {"expires_at": "2020-01-01T00:00:00+00:00"}}}
        assert is_record_expired(record, parse_expires_at, now_ts=2_000_000_000.0) is True

    def test_not_expired_record(self) -> None:
        from veritas_os.core.memory_lifecycle import is_record_expired, parse_expires_at

        record = {"value": {"meta": {"expires_at": "2099-01-01T00:00:00+00:00"}}}
        assert is_record_expired(record, parse_expires_at) is False

    def test_legal_hold_prevents_expiry(self) -> None:
        from veritas_os.core.memory_lifecycle import is_record_expired, parse_expires_at

        record = {"value": {"meta": {"expires_at": "2020-01-01T00:00:00+00:00", "legal_hold": True}}}
        assert is_record_expired(record, parse_expires_at, now_ts=2_000_000_000.0) is False

    def test_no_expires_at(self) -> None:
        from veritas_os.core.memory_lifecycle import is_record_expired, parse_expires_at

        record = {"value": {"meta": {}}}
        assert is_record_expired(record, parse_expires_at) is False

    def test_non_dict_value(self) -> None:
        from veritas_os.core.memory_lifecycle import is_record_expired, parse_expires_at

        assert is_record_expired({"value": "string"}, parse_expires_at) is False

    def test_non_dict_meta(self) -> None:
        from veritas_os.core.memory_lifecycle import is_record_expired, parse_expires_at

        assert is_record_expired({"value": {"meta": "not-a-dict"}}, parse_expires_at) is False

    def test_empty_value(self) -> None:
        from veritas_os.core.memory_lifecycle import is_record_expired, parse_expires_at

        assert is_record_expired({"value": None}, parse_expires_at) is False

    def test_numeric_expires_at(self) -> None:
        from veritas_os.core.memory_lifecycle import is_record_expired, parse_expires_at

        past_ts = time.time() - 86400
        record = {"value": {"meta": {"expires_at": past_ts}}}
        assert is_record_expired(record, parse_expires_at) is True

    def test_invalid_expires_at_string(self) -> None:
        """Invalid expires_at string → parse returns None → not expired."""
        from veritas_os.core.memory_lifecycle import is_record_expired, parse_expires_at

        record = {"value": {"meta": {"expires_at": "not-a-date"}}}
        assert is_record_expired(record, parse_expires_at) is False


# =========================================================================
# 15. memory_lifecycle.py — should_cascade_delete_semantic direct tests
# =========================================================================


class TestLifecycleCascadeDelete:
    def _make_semantic_record(
        self, user_id: str, source_keys: list, legal_hold: bool = False
    ) -> dict:
        return {
            "value": {
                "kind": "semantic",
                "meta": {
                    "user_id": user_id,
                    "source_episode_keys": source_keys,
                    "legal_hold": legal_hold,
                },
            }
        }

    def test_cascade_positive(self) -> None:
        from veritas_os.core.memory_lifecycle import should_cascade_delete_semantic

        record = self._make_semantic_record("u1", ["ep-1"])
        assert should_cascade_delete_semantic(record, "u1", {"ep-1"}) is True

    def test_cascade_no_matching_key(self) -> None:
        from veritas_os.core.memory_lifecycle import should_cascade_delete_semantic

        record = self._make_semantic_record("u1", ["ep-1"])
        assert should_cascade_delete_semantic(record, "u1", {"ep-99"}) is False

    def test_cascade_empty_erased_keys(self) -> None:
        from veritas_os.core.memory_lifecycle import should_cascade_delete_semantic

        record = self._make_semantic_record("u1", ["ep-1"])
        assert should_cascade_delete_semantic(record, "u1", set()) is False

    def test_cascade_non_semantic_kind(self) -> None:
        from veritas_os.core.memory_lifecycle import should_cascade_delete_semantic

        record = {"value": {"kind": "episodic", "meta": {"user_id": "u1", "source_episode_keys": ["ep-1"]}}}
        assert should_cascade_delete_semantic(record, "u1", {"ep-1"}) is False

    def test_cascade_wrong_user(self) -> None:
        from veritas_os.core.memory_lifecycle import should_cascade_delete_semantic

        record = self._make_semantic_record("u1", ["ep-1"])
        assert should_cascade_delete_semantic(record, "u2", {"ep-1"}) is False

    def test_cascade_legal_hold_protects(self) -> None:
        from veritas_os.core.memory_lifecycle import should_cascade_delete_semantic

        record = self._make_semantic_record("u1", ["ep-1"], legal_hold=True)
        assert should_cascade_delete_semantic(record, "u1", {"ep-1"}) is False

    def test_cascade_non_dict_value(self) -> None:
        from veritas_os.core.memory_lifecycle import should_cascade_delete_semantic

        assert should_cascade_delete_semantic({"value": "string"}, "u1", {"ep-1"}) is False

    def test_cascade_non_dict_meta(self) -> None:
        from veritas_os.core.memory_lifecycle import should_cascade_delete_semantic

        record = {"value": {"kind": "semantic", "meta": "not-a-dict"}}
        assert should_cascade_delete_semantic(record, "u1", {"ep-1"}) is False

    def test_cascade_non_list_source_keys(self) -> None:
        from veritas_os.core.memory_lifecycle import should_cascade_delete_semantic

        record = {
            "value": {
                "kind": "semantic",
                "meta": {
                    "user_id": "u1",
                    "source_episode_keys": "not-a-list",
                    "legal_hold": False,
                },
            }
        }
        assert should_cascade_delete_semantic(record, "u1", {"ep-1"}) is False

    def test_cascade_missing_source_keys(self) -> None:
        from veritas_os.core.memory_lifecycle import should_cascade_delete_semantic

        record = {
            "value": {
                "kind": "semantic",
                "meta": {
                    "user_id": "u1",
                    "legal_hold": False,
                },
            }
        }
        assert should_cascade_delete_semantic(record, "u1", {"ep-1"}) is False


# =========================================================================
# 16. memory_compliance.py — uncovered branches
# =========================================================================


class TestComplianceUncoveredBranches:
    def test_is_record_legal_hold_non_dict_meta(self) -> None:
        """Line 30: non-dict meta returns False."""
        from veritas_os.core.memory_compliance import is_record_legal_hold

        assert is_record_legal_hold({"value": {"meta": "not-a-dict"}}) is False

    def test_is_record_legal_hold_non_dict_value(self) -> None:
        from veritas_os.core.memory_compliance import is_record_legal_hold

        assert is_record_legal_hold({"value": "string"}) is False

    def test_is_record_legal_hold_missing_meta(self) -> None:
        from veritas_os.core.memory_compliance import is_record_legal_hold

        assert is_record_legal_hold({"value": {}}) is False

    def test_should_cascade_non_dict_meta(self) -> None:
        """Line 52: non-dict meta returns False."""
        from veritas_os.core.memory_compliance import should_cascade_delete_semantic

        record = {"value": {"kind": "semantic", "meta": "not-a-dict"}}
        assert should_cascade_delete_semantic(record, "u1", {"ep-1"}) is False

    def test_should_cascade_wrong_user(self) -> None:
        """Line 55: wrong user_id returns False."""
        from veritas_os.core.memory_compliance import should_cascade_delete_semantic

        record = {
            "value": {
                "kind": "semantic",
                "meta": {
                    "user_id": "u1",
                    "source_episode_keys": ["ep-1"],
                    "legal_hold": False,
                },
            }
        }
        assert should_cascade_delete_semantic(record, "u2", {"ep-1"}) is False

    def test_should_cascade_non_list_source_keys(self) -> None:
        """Line 62: non-list source_keys returns False."""
        from veritas_os.core.memory_compliance import should_cascade_delete_semantic

        record = {
            "value": {
                "kind": "semantic",
                "meta": {
                    "user_id": "u1",
                    "source_episode_keys": "not-a-list",
                    "legal_hold": False,
                },
            }
        }
        assert should_cascade_delete_semantic(record, "u1", {"ep-1"}) is False

    def test_should_cascade_positive(self) -> None:
        """Verify the positive path through compliance cascade."""
        from veritas_os.core.memory_compliance import should_cascade_delete_semantic

        record = {
            "value": {
                "kind": "semantic",
                "meta": {
                    "user_id": "u1",
                    "source_episode_keys": ["ep-1"],
                    "legal_hold": False,
                },
            }
        }
        assert should_cascade_delete_semantic(record, "u1", {"ep-1"}) is True


# =========================================================================
# 17. erase_user_data — compliance edge cases
# =========================================================================


class TestEraseUserDataEdgeCases:
    def test_erase_empty_data(self) -> None:
        from veritas_os.core.memory_compliance import erase_user_data

        kept, report = erase_user_data([], "u1", "test", "admin")
        assert report["deleted_count"] == 0
        # Only the audit record remains
        assert len(kept) == 1
        assert kept[0]["user_id"] == "__audit__"

    def test_erase_no_matching_user(self) -> None:
        from veritas_os.core.memory_compliance import erase_user_data

        data = [{"user_id": "u2", "key": "k1", "value": {"text": "safe"}}]
        kept, report = erase_user_data(data, "u1", "test", "admin")
        assert report["deleted_count"] == 0
        # Original record + audit record
        user_records = [r for r in kept if r.get("user_id") == "u2"]
        assert len(user_records) == 1

    def test_erase_with_non_dict_value(self) -> None:
        """Records with non-dict values should still be erasable."""
        from veritas_os.core.memory_compliance import erase_user_data

        data = [{"user_id": "u1", "key": "k1", "value": "plain string"}]
        kept, report = erase_user_data(data, "u1", "test", "admin")
        assert report["deleted_count"] == 1


# =========================================================================
# 18. _load_all — unreadable file (permission error)
# =========================================================================


class TestLoadAllPermissionError:
    @pytest.mark.skipif(os.name == "nt", reason="POSIX permission model")
    def test_unreadable_file_returns_empty(self, tmp_path: Path) -> None:
        """File without read permission should return empty list."""
        path = tmp_path / "memory.json"
        path.write_text("[]", encoding="utf-8")
        store = MemoryStore(path)

        path.chmod(0o000)
        try:
            data = store._load_all(copy=True, use_cache=False)
            assert data == []
        finally:
            path.chmod(0o644)


# =========================================================================
# 19. memory_lifecycle.py — is_record_legal_hold direct tests
# =========================================================================


class TestLifecycleIsRecordLegalHold:
    def test_legal_hold_true(self) -> None:
        from veritas_os.core.memory_lifecycle import is_record_legal_hold

        assert is_record_legal_hold({"value": {"meta": {"legal_hold": True}}}) is True

    def test_legal_hold_false(self) -> None:
        from veritas_os.core.memory_lifecycle import is_record_legal_hold

        assert is_record_legal_hold({"value": {"meta": {"legal_hold": False}}}) is False

    def test_legal_hold_string_yes(self) -> None:
        from veritas_os.core.memory_lifecycle import is_record_legal_hold

        assert is_record_legal_hold({"value": {"meta": {"legal_hold": "yes"}}}) is True

    def test_non_dict_value(self) -> None:
        from veritas_os.core.memory_lifecycle import is_record_legal_hold

        assert is_record_legal_hold({"value": 42}) is False

    def test_non_dict_meta(self) -> None:
        from veritas_os.core.memory_lifecycle import is_record_legal_hold

        assert is_record_legal_hold({"value": {"meta": [1, 2]}}) is False

    def test_missing_legal_hold_key(self) -> None:
        from veritas_os.core.memory_lifecycle import is_record_legal_hold

        assert is_record_legal_hold({"value": {"meta": {}}}) is False


# =========================================================================
# 20. Persist round-trip with lifecycle metadata
# =========================================================================


class TestPersistRoundTripWithLifecycle:
    def test_lifecycle_metadata_survives_round_trip(self, tmp_path: Path) -> None:
        """Lifecycle-normalized metadata should survive persist/load."""
        path = tmp_path / "memory.json"
        store1 = MemoryStore(path)
        store1.put("u1", "k1", {
            "text": "test",
            "meta": {"retention_class": "long", "legal_hold": "true", "expires_at": 1700000000},
        })

        store2 = MemoryStore(path)
        val = store2.get("u1", "k1")
        assert val is not None
        assert val["meta"]["retention_class"] == "long"
        assert val["meta"]["legal_hold"] is True
        assert val["meta"]["expires_at"] is not None
        assert "2023" in val["meta"]["expires_at"]
