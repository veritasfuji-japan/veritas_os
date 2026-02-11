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

    result = ms.search("cache", k=3, kinds=["episodic"], min_sim=0.0)
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

    result = ms.search("first", k=3, kinds=["episodic"], min_sim=0.0)

    assert load_calls["count"] >= 1
    assert result["episodic"]
    assert result["episodic"][0]["id"] == first_id
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
