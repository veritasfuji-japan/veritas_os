# tests for veritas_os/api/rate_limiting.py
"""Tests for rate limiting and nonce management."""
from __future__ import annotations

import os
import time
from unittest import mock

import pytest

from veritas_os.api.rate_limiting import (
    _cleanup_nonces_unsafe,
    _cleanup_rate_bucket,
    _cleanup_rate_bucket_unsafe,
    _env_int_safe,
    _nonce_lock,
    _nonce_store,
    _rate_bucket,
    _rate_lock,
)


class TestEnvIntSafe:
    def test_default(self):
        assert _env_int_safe("NONEXISTENT_999", 10) == 10

    def test_valid(self):
        with mock.patch.dict(os.environ, {"TEST_RL_INT": "50"}):
            assert _env_int_safe("TEST_RL_INT", 0) == 50

    def test_invalid(self):
        with mock.patch.dict(os.environ, {"TEST_RL_INT": "xyz"}):
            assert _env_int_safe("TEST_RL_INT", 7) == 7


class TestCleanupRateBucket:
    def test_removes_expired(self):
        now = time.time()
        with _rate_lock:
            _rate_bucket["expired_key_test"] = (1, now - 500)
            _rate_bucket["fresh_key_test"] = (1, now)
            _cleanup_rate_bucket_unsafe()
        assert "expired_key_test" not in _rate_bucket
        assert "fresh_key_test" in _rate_bucket
        # Clean up
        with _rate_lock:
            _rate_bucket.pop("fresh_key_test", None)

    def test_thread_safe_cleanup(self):
        _cleanup_rate_bucket()  # Should not raise


class TestCleanupNonces:
    def test_removes_expired_nonces(self):
        now = time.time()
        with _nonce_lock:
            _nonce_store["expired_nonce_test"] = now - 100  # Expired
            _nonce_store["valid_nonce_test"] = now + 100   # Still valid
            _cleanup_nonces_unsafe()
        assert "expired_nonce_test" not in _nonce_store
        assert "valid_nonce_test" in _nonce_store
        # Clean up
        with _nonce_lock:
            _nonce_store.pop("valid_nonce_test", None)
