from __future__ import annotations

import pytest

from veritas_os.storage.factory import (
    create_memory_store,
    create_trust_log_store,
    get_backend_info,
    validate_backend_config,
)
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


class TestGetBackendInfo:
    """Verify get_backend_info returns active backend names."""

    def test_defaults(self, monkeypatch):
        monkeypatch.delenv("VERITAS_MEMORY_BACKEND", raising=False)
        monkeypatch.delenv("VERITAS_TRUSTLOG_BACKEND", raising=False)
        info = get_backend_info()
        assert info == {"memory": "json", "trustlog": "jsonl"}

    def test_postgresql(self, monkeypatch):
        monkeypatch.setenv("VERITAS_MEMORY_BACKEND", "postgresql")
        monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "postgresql")
        info = get_backend_info()
        assert info == {"memory": "postgresql", "trustlog": "postgresql"}


class TestValidateBackendConfig:
    """Verify fail-fast validation on misconfiguration."""

    def test_valid_json_defaults(self, monkeypatch):
        monkeypatch.delenv("VERITAS_MEMORY_BACKEND", raising=False)
        monkeypatch.delenv("VERITAS_TRUSTLOG_BACKEND", raising=False)
        monkeypatch.delenv("VERITAS_DATABASE_URL", raising=False)
        validate_backend_config()  # should not raise

    def test_valid_postgresql_with_url(self, monkeypatch):
        monkeypatch.setenv("VERITAS_MEMORY_BACKEND", "postgresql")
        monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "postgresql")
        monkeypatch.setenv("VERITAS_DATABASE_URL", "postgresql://x:x@localhost/x")
        validate_backend_config()  # should not raise

    def test_postgresql_memory_without_url(self, monkeypatch):
        monkeypatch.setenv("VERITAS_MEMORY_BACKEND", "postgresql")
        monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "jsonl")
        monkeypatch.delenv("VERITAS_DATABASE_URL", raising=False)
        with pytest.raises(RuntimeError, match="VERITAS_DATABASE_URL"):
            validate_backend_config()

    def test_postgresql_trustlog_without_url(self, monkeypatch):
        monkeypatch.setenv("VERITAS_MEMORY_BACKEND", "json")
        monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "postgresql")
        monkeypatch.delenv("VERITAS_DATABASE_URL", raising=False)
        with pytest.raises(RuntimeError, match="VERITAS_DATABASE_URL"):
            validate_backend_config()

    def test_unknown_memory_backend(self, monkeypatch):
        monkeypatch.setenv("VERITAS_MEMORY_BACKEND", "redis")
        with pytest.raises(ValueError, match="Unknown VERITAS_MEMORY_BACKEND"):
            validate_backend_config()

    def test_unknown_trustlog_backend(self, monkeypatch):
        monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "sqlite")
        with pytest.raises(ValueError, match="Unknown VERITAS_TRUSTLOG_BACKEND"):
            validate_backend_config()


class TestCreateStoreFailFast:
    """Verify factory create functions fail fast without DATABASE_URL."""

    def test_create_trust_log_postgresql_no_url(self, monkeypatch):
        monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "postgresql")
        monkeypatch.delenv("VERITAS_DATABASE_URL", raising=False)
        with pytest.raises(RuntimeError, match="VERITAS_DATABASE_URL"):
            create_trust_log_store()

    def test_create_memory_postgresql_no_url(self, monkeypatch):
        monkeypatch.setenv("VERITAS_MEMORY_BACKEND", "postgresql")
        monkeypatch.delenv("VERITAS_DATABASE_URL", raising=False)
        with pytest.raises(RuntimeError, match="VERITAS_DATABASE_URL"):
            create_memory_store()
