from __future__ import annotations

import asyncio

from veritas_os.storage.jsonl import JsonlTrustLogStore


def test_jsonl_trust_log_store_append_and_get(monkeypatch, tmp_path) -> None:
    from veritas_os.logging import trust_log
    from veritas_os.logging.encryption import generate_key

    monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", generate_key())
    monkeypatch.setattr(trust_log, "LOG_DIR", tmp_path, raising=False)
    monkeypatch.setattr(trust_log, "LOG_JSON", tmp_path / "trust_log.json", raising=False)
    monkeypatch.setattr(trust_log, "LOG_JSONL", tmp_path / "trust_log.jsonl", raising=False)

    def _open_for_append():
        trust_log.LOG_JSONL.parent.mkdir(parents=True, exist_ok=True)
        return open(trust_log.LOG_JSONL, "a", encoding="utf-8")

    monkeypatch.setattr(trust_log, "open_trust_log_for_append", _open_for_append)

    store = JsonlTrustLogStore()

    async def _run() -> tuple[str, dict | None]:
        entry_id = await store.append({"request_id": "req-1", "action": "allow"})
        loaded = await store.get_by_id("req-1")
        return entry_id, loaded

    entry_id, loaded = asyncio.run(_run())
    assert entry_id == "req-1"
    assert loaded is not None
    assert loaded.get("action") == "allow"


def test_jsonl_trust_log_store_iter_entries(monkeypatch, tmp_path) -> None:
    from veritas_os.logging import trust_log
    from veritas_os.logging.encryption import generate_key

    monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", generate_key())
    monkeypatch.setattr(trust_log, "LOG_DIR", tmp_path, raising=False)
    monkeypatch.setattr(trust_log, "LOG_JSON", tmp_path / "trust_log.json", raising=False)
    monkeypatch.setattr(trust_log, "LOG_JSONL", tmp_path / "trust_log.jsonl", raising=False)

    def _open_for_append():
        trust_log.LOG_JSONL.parent.mkdir(parents=True, exist_ok=True)
        return open(trust_log.LOG_JSONL, "a", encoding="utf-8")

    monkeypatch.setattr(trust_log, "open_trust_log_for_append", _open_for_append)

    store = JsonlTrustLogStore()

    async def _run() -> list[dict]:
        await store.append({"request_id": "req-a", "seq": 1})
        await store.append({"request_id": "req-b", "seq": 2})
        rows = []
        async for entry in store.iter_entries(limit=1, offset=0):
            rows.append(entry)
        return rows

    rows = asyncio.run(_run())
    assert len(rows) == 1
    assert rows[0].get("request_id") == "req-b"
