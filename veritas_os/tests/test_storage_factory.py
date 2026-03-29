from __future__ import annotations

from veritas_os.storage.factory import create_memory_store, create_trust_log_store
from veritas_os.storage.json_kv import JsonMemoryStore
from veritas_os.storage.jsonl import JsonlTrustLogStore
from veritas_os.storage.postgresql import PostgresMemoryStore, PostgresTrustLogStore


def test_factory_defaults_to_json_backends(monkeypatch):
    monkeypatch.delenv("VERITAS_TRUSTLOG_BACKEND", raising=False)
    monkeypatch.delenv("VERITAS_MEMORY_BACKEND", raising=False)

    trust_store = create_trust_log_store()
    memory_store = create_memory_store()

    assert isinstance(trust_store, JsonlTrustLogStore)
    assert isinstance(memory_store, JsonMemoryStore)


def test_factory_selects_postgresql_backends(monkeypatch):
    monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "postgresql")
    monkeypatch.setenv("VERITAS_MEMORY_BACKEND", "postgresql")

    trust_store = create_trust_log_store()
    memory_store = create_memory_store()

    assert isinstance(trust_store, PostgresTrustLogStore)
    assert isinstance(memory_store, PostgresMemoryStore)
