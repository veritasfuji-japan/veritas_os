"""Distributed auth-store consistency and chaos tests (Roadmap #14).

These tests focus on nonce replay prevention and distributed rate-limit/auth-failure
consistency when multiple workers share the same Redis-like backend.
"""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from veritas_os.api import server


@dataclass
class _FakeSharedRedis:
    """Minimal Redis double that supports set/nx/px and transactional pipeline."""

    kv: dict[str, int] = field(default_factory=dict)
    fail_pipeline_calls: int = 0

    def set(self, name: str, value: str, nx: bool, px: int) -> bool:
        if nx and name in self.kv:
            return False
        self.kv[name] = int(value)
        return True

    def pipeline(self, transaction: bool = True) -> "_FakePipeline":
        return _FakePipeline(self)


class _FakePipeline:
    """Redis pipeline double with optional chaos injection."""

    def __init__(self, backend: _FakeSharedRedis) -> None:
        self._backend = backend
        self._ops: list[tuple[str, Any, Any]] = []

    def __enter__(self) -> "_FakePipeline":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        return None

    def incr(self, key: str) -> None:
        self._ops.append(("incr", key, None))

    def pexpire(self, key: str, ttl_ms: int, nx: bool = True) -> None:
        self._ops.append(("pexpire", key, (ttl_ms, nx)))

    def execute(self) -> list[int]:
        if self._backend.fail_pipeline_calls > 0:
            self._backend.fail_pipeline_calls -= 1
            raise RuntimeError("injected_redis_pipeline_failure")

        results: list[int] = []
        for op, key, _ in self._ops:
            if op == "incr":
                new_val = int(self._backend.kv.get(key, 0)) + 1
                self._backend.kv[key] = new_val
                results.append(new_val)
            elif op == "pexpire":
                results.append(1)
        return results


def test_distributed_nonce_consistency_across_workers() -> None:
    """Same nonce must be rejected across worker-local store instances."""
    shared = _FakeSharedRedis()
    worker_a = server.RedisAuthSecurityStore(shared)
    worker_b = server.RedisAuthSecurityStore(shared)

    assert worker_a.register_nonce("same-nonce", ttl_sec=10.0) is True
    assert worker_b.register_nonce("same-nonce", ttl_sec=10.0) is False


def test_distributed_rate_limit_consistency_across_workers() -> None:
    """Rate limit counters must accumulate globally in shared distributed mode."""
    shared = _FakeSharedRedis()
    worker_a = server.RedisAuthSecurityStore(shared)
    worker_b = server.RedisAuthSecurityStore(shared)

    assert worker_a.increment_rate_limit("tenant-a", limit=2, window_sec=30.0) is False
    assert worker_b.increment_rate_limit("tenant-a", limit=2, window_sec=30.0) is False
    assert worker_a.increment_rate_limit("tenant-a", limit=2, window_sec=30.0) is True


def test_chaos_redis_failure_respects_fail_closed_for_nonce(monkeypatch) -> None:
    """Fail-closed mode must reject nonce registration on backend failure."""
    shared = _FakeSharedRedis(fail_pipeline_calls=1)
    monkeypatch.setattr(server, "_AUTH_SECURITY_STORE", server.RedisAuthSecurityStore(shared))
    monkeypatch.setenv("VERITAS_AUTH_STORE_FAILURE_MODE", "closed")

    class _BrokenNonceStore:
        def register_nonce(self, nonce: str, ttl_sec: float) -> bool:
            raise RuntimeError("nonce_backend_down")

    monkeypatch.setattr(server, "_AUTH_SECURITY_STORE", _BrokenNonceStore())

    assert server._auth_store_register_nonce("n-chaos", ttl_sec=60.0) is False


def test_chaos_redis_failure_respects_fail_open_for_rate_limit(monkeypatch) -> None:
    """Fail-open mode should avoid false throttling during transient backend failure."""

    class _BrokenRateStore:
        def register_nonce(self, nonce: str, ttl_sec: float) -> bool:
            return True

        def increment_auth_failure(self, client_ip: str, limit: int, window_sec: float) -> bool:
            return False

        def increment_rate_limit(self, api_key: str, limit: int, window_sec: float) -> bool:
            raise RuntimeError("rate_backend_flap")

    monkeypatch.setattr(server, "_AUTH_SECURITY_STORE", _BrokenRateStore())
    monkeypatch.setenv("VERITAS_AUTH_STORE_FAILURE_MODE", "open")

    assert server._auth_store_increment_rate_limit("tenant-x", limit=1, window_sec=1.0) is False
