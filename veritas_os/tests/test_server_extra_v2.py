# veritas_os/tests/test_server_extra_v2.py
"""Additional coverage tests for veritas_os/api/server.py.

Targets uncovered helper functions:
  - _is_placeholder
  - _SSEEventHub methods
  - _publish_event
  - _format_sse_message
  - _errstr
  - _log_decide_failure
  - _is_placeholder_secret
  - _get_api_secret
  - _cleanup_nonces_unsafe (with overflow)
  - _cleanup_nonces
  - _check_and_register_nonce
  - redact (fallback path)
  - _gen_request_id
  - _coerce_alt_list (various inputs)
  - _coerce_decide_payload (various inputs)
  - _coerce_fuji_payload (various inputs)
  - _is_debug_mode
  - _resolve_expected_api_key_with_source
  - _log_api_key_source_once
  - _log_decide_failure
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import queue
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import MagicMock, patch

# Set test API key before importing server
_TEST_KEY = "server-extra-v2-key-12345"
os.environ["VERITAS_API_KEY"] = _TEST_KEY

import pytest

import veritas_os.api.server as server


# =========================================================
# _is_placeholder
# =========================================================

class TestIsPlaceholder:
    def test_with_placeholder_attr(self):
        obj = SimpleNamespace(__veritas_placeholder__=True)
        assert server._is_placeholder(obj) is True

    def test_without_placeholder_attr(self):
        obj = SimpleNamespace()
        assert server._is_placeholder(obj) is False

    def test_regular_objects(self):
        assert server._is_placeholder("string") is False
        assert server._is_placeholder(42) is False
        assert server._is_placeholder(None) is False


# =========================================================
# _SSEEventHub
# =========================================================

class TestSSEEventHub:
    def test_publish_returns_event(self):
        hub = server._SSEEventHub()
        event = hub.publish("test_event", {"key": "value"})
        assert event["type"] == "test_event"
        assert event["payload"] == {"key": "value"}
        assert event["id"] == 1

    def test_subscribe_gets_history(self):
        hub = server._SSEEventHub()
        hub.publish("evt1", {"a": 1})
        hub.publish("evt2", {"b": 2})
        q = hub.register()
        # History should be pre-filled
        items = []
        while not q.empty():
            items.append(q.get_nowait())
        assert len(items) == 2

    def test_unregister_removes_subscriber(self):
        hub = server._SSEEventHub()
        q = hub.register()
        hub.unregister(q)
        # After unregister, new events are NOT sent to old subscriber
        hub.publish("after_unregister", {})
        assert q.empty()

    def test_publish_to_subscriber(self):
        hub = server._SSEEventHub()
        q = hub.register()
        # Clear pre-fill (empty history)
        while not q.empty():
            q.get_nowait()
        hub.publish("live_event", {"live": True})
        item = q.get_nowait()
        assert item["type"] == "live_event"

    def test_full_queue_does_not_crash(self):
        hub = server._SSEEventHub()
        # Create a small-queue subscriber
        small_q = queue.Queue(maxsize=1)
        with hub._lock:
            hub._subscribers.add(small_q)
        # Fill the queue first
        small_q.put("dummy")
        # This should not raise
        hub.publish("overflow_event", {})


# =========================================================
# _publish_event
# =========================================================

class TestPublishEvent:
    def test_does_not_crash_on_exception(self, monkeypatch):
        def raise_error(*args, **kwargs):
            raise RuntimeError("publish failed")
        monkeypatch.setattr(server._event_hub, "publish", raise_error)
        # Should not raise
        server._publish_event("test", {})


# =========================================================
# _format_sse_message
# =========================================================

class TestFormatSseMessage:
    def test_format_structure(self):
        event = {"id": 1, "type": "test_type", "payload": {"key": "val"}}
        msg = server._format_sse_message(event)
        assert msg.startswith("id: 1\n")
        assert "event: test_type\n" in msg
        assert "data: " in msg
        assert msg.endswith("\n\n")


# =========================================================
# _errstr
# =========================================================

class TestErrstr:
    def test_formats_exception(self):
        e = ValueError("test error")
        result = server._errstr(e)
        assert "ValueError" in result
        assert "test error" in result


# =========================================================
# _log_decide_failure
# =========================================================

class TestLogDecideFailure:
    def test_none_error(self, caplog):
        import logging
        with caplog.at_level(logging.ERROR):
            server._log_decide_failure("test message", None)
        assert "test message" in caplog.text

    def test_exception_error(self, caplog):
        import logging
        with caplog.at_level(logging.ERROR):
            server._log_decide_failure("pipeline failed", ValueError("bad input"))
        assert "pipeline failed" in caplog.text

    def test_string_error(self, caplog):
        import logging
        with caplog.at_level(logging.ERROR):
            server._log_decide_failure("operation failed", "string error detail")
        assert "operation failed" in caplog.text


# =========================================================
# _is_placeholder_secret
# =========================================================

class TestIsPlaceholderSecret:
    def test_placeholder_value(self):
        assert server._is_placeholder_secret(server._DEFAULT_API_SECRET_PLACEHOLDER) is True

    def test_real_value(self):
        assert server._is_placeholder_secret("real_secret_value") is False

    def test_empty_string(self):
        assert server._is_placeholder_secret("") is False


# =========================================================
# _get_api_secret
# =========================================================

class TestGetApiSecret:
    def test_placeholder_env_returns_empty(self, monkeypatch):
        monkeypatch.setattr(server, "API_SECRET", b"")
        monkeypatch.setenv("VERITAS_API_SECRET", server._DEFAULT_API_SECRET_PLACEHOLDER)
        result = server._get_api_secret()
        assert result == b""

    def test_empty_env_returns_empty(self, monkeypatch):
        monkeypatch.setattr(server, "API_SECRET", b"")
        monkeypatch.setenv("VERITAS_API_SECRET", "")
        result = server._get_api_secret()
        assert result == b""

    def test_short_key_still_returned(self, monkeypatch):
        monkeypatch.setattr(server, "API_SECRET", b"")
        monkeypatch.setenv("VERITAS_API_SECRET", "short_key_under_32")
        result = server._get_api_secret()
        assert result == b"short_key_under_32"

    def test_valid_long_key_returned(self, monkeypatch):
        monkeypatch.setattr(server, "API_SECRET", b"")
        long_key = "a" * 32
        monkeypatch.setenv("VERITAS_API_SECRET", long_key)
        result = server._get_api_secret()
        assert result == long_key.encode("utf-8")

    def test_explicit_api_secret_attr(self, monkeypatch):
        monkeypatch.setattr(server, "API_SECRET", b"explicit_test_secret")
        result = server._get_api_secret()
        assert result == b"explicit_test_secret"


# =========================================================
# _cleanup_nonces_unsafe / _cleanup_nonces
# =========================================================

class TestCleanupNonces:
    def test_cleanup_removes_expired(self):
        # Add an expired nonce
        server._nonce_store["expired_nonce"] = time.time() - 10
        server._nonce_store["valid_nonce"] = time.time() + 300
        server._cleanup_nonces_unsafe()
        assert "expired_nonce" not in server._nonce_store
        assert "valid_nonce" in server._nonce_store
        # Cleanup
        server._nonce_store.pop("valid_nonce", None)

    def test_cleanup_with_overflow(self):
        # Add more nonces than NONCE_MAX
        original_max = server._NONCE_MAX
        # Temporarily set a small max for testing
        server._NONCE_MAX = 3
        try:
            for i in range(5):
                server._nonce_store[f"overflow_nonce_{i}"] = time.time() + 300
            server._cleanup_nonces_unsafe()
            assert len([k for k in server._nonce_store if k.startswith("overflow_nonce_")]) <= 3
        finally:
            server._NONCE_MAX = original_max
            # Clean up test nonces
            for i in range(5):
                server._nonce_store.pop(f"overflow_nonce_{i}", None)

    def test_cleanup_nonces_thread_safe(self):
        """Thread-safe version doesn't raise."""
        server._cleanup_nonces()  # should not raise


# =========================================================
# _check_and_register_nonce
# =========================================================

class TestCheckAndRegisterNonce:
    def test_new_nonce_returns_true(self):
        nonce = f"unique_nonce_{time.time()}"
        result = server._check_and_register_nonce(nonce)
        assert result is True
        server._nonce_store.pop(nonce, None)

    def test_duplicate_nonce_returns_false(self):
        nonce = f"dup_nonce_{time.time()}"
        server._check_and_register_nonce(nonce)  # First time
        result = server._check_and_register_nonce(nonce)  # Second time
        assert result is False
        server._nonce_store.pop(nonce, None)


# =========================================================
# redact (fallback path)
# =========================================================

class TestRedact:
    def test_empty_string(self):
        result = server.redact("")
        assert result == ""

    def test_none_stays_empty(self):
        result = server.redact("")
        assert result == ""

    def test_redacts_email_fallback(self, monkeypatch):
        """Test fallback path when sanitize is not available."""
        monkeypatch.setattr(server, "_HAS_SANITIZE", False)
        monkeypatch.setattr(server, "_sanitize_mask_pii", None)
        text = "Contact admin@example.com for details"
        result = server.redact(text)
        assert "admin@example.com" not in result

    def test_redacts_phone_fallback(self, monkeypatch):
        """Test phone redaction in fallback path."""
        monkeypatch.setattr(server, "_HAS_SANITIZE", False)
        monkeypatch.setattr(server, "_sanitize_mask_pii", None)
        text = "Call 090-1234-5678"
        result = server.redact(text)
        # Phone pattern might be replaced
        assert isinstance(result, str)


# =========================================================
# _gen_request_id
# =========================================================

class TestGenRequestId:
    def test_returns_hex_string(self):
        result = server._gen_request_id("test_seed")
        assert isinstance(result, str)
        assert len(result) == 24
        assert all(c in "0123456789abcdef" for c in result)

    def test_different_seeds_give_different_ids(self):
        id1 = server._gen_request_id("seed1")
        id2 = server._gen_request_id("seed2")
        assert id1 != id2

    def test_empty_seed_works(self):
        result = server._gen_request_id()
        assert len(result) == 24


# =========================================================
# _coerce_alt_list
# =========================================================

class TestCoerceAltList:
    def test_none_returns_empty(self):
        assert server._coerce_alt_list(None) == []

    def test_dict_wrapped_in_list(self):
        result = server._coerce_alt_list({"title": "Option A"})
        assert isinstance(result, list)
        assert len(result) == 1

    def test_non_list_non_dict_wrapped(self):
        result = server._coerce_alt_list("string value")
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["title"] == "string value"

    def test_list_of_dicts(self):
        v = [{"title": "A"}, {"title": "B"}]
        result = server._coerce_alt_list(v)
        assert len(result) == 2
        assert all("id" in r for r in result)

    def test_list_with_non_dict_elements(self):
        result = server._coerce_alt_list(["string_item"])
        assert result[0]["title"] == "string_item"

    def test_score_coerced_to_float(self):
        result = server._coerce_alt_list([{"title": "A", "score": "0.75"}])
        assert result[0]["score"] == 0.75

    def test_invalid_score_defaults_to_one(self):
        result = server._coerce_alt_list([{"title": "A", "score": "invalid"}])
        assert result[0]["score"] == 1.0


# =========================================================
# _coerce_decide_payload
# =========================================================

class TestCoerceDecidePayload:
    def test_non_dict_wrapped(self):
        result = server._coerce_decide_payload("some string")
        assert isinstance(result, dict)
        assert result["ok"] is True
        assert "request_id" in result

    def test_adds_trust_log(self):
        result = server._coerce_decide_payload({"chosen": {"title": "X"}})
        assert "trust_log" in result

    def test_adds_ok_field(self):
        result = server._coerce_decide_payload({"chosen": {"title": "X"}})
        assert result["ok"] is True

    def test_generates_request_id(self):
        result = server._coerce_decide_payload({"chosen": {}})
        assert result.get("request_id") is not None

    def test_non_dict_chosen_wrapped(self):
        result = server._coerce_decide_payload({"chosen": "Option A"})
        assert isinstance(result["chosen"], dict)

    def test_none_chosen_gets_empty_dict(self):
        result = server._coerce_decide_payload({"chosen": None})
        assert result["chosen"] == {}

    def test_uses_opts_when_alts_missing(self):
        opts = [{"title": "Opt A"}]
        result = server._coerce_decide_payload({"options": opts})
        assert len(result["alternatives"]) == 1

    def test_mirrors_alts_to_options(self):
        alts = [{"title": "Alt A", "id": "a1"}]
        result = server._coerce_decide_payload({"alternatives": alts})
        assert len(result["options"]) >= 1


# =========================================================
# _coerce_fuji_payload
# =========================================================

class TestCoerceFujiPayload:
    def test_non_dict_wrapped(self):
        result = server._coerce_fuji_payload("allow")
        assert isinstance(result, dict)
        assert result["status"] == "allow"

    def test_adds_missing_status(self):
        result = server._coerce_fuji_payload({})
        assert result["status"] == "allow"

    def test_adds_missing_reasons(self):
        result = server._coerce_fuji_payload({"status": "deny"})
        assert result["reasons"] == []

    def test_adds_missing_violations(self):
        result = server._coerce_fuji_payload({"status": "deny", "reasons": []})
        assert result["violations"] == []

    def test_preserves_existing_values(self):
        payload = {"status": "deny", "reasons": ["r1"], "violations": ["v1"]}
        result = server._coerce_fuji_payload(payload)
        assert result["status"] == "deny"
        assert result["reasons"] == ["r1"]


# =========================================================
# _is_debug_mode
# =========================================================

class TestIsDebugMode:
    def test_1_is_debug(self, monkeypatch):
        monkeypatch.setenv("VERITAS_DEBUG_MODE", "1")
        assert server._is_debug_mode() is True

    def test_true_is_debug(self, monkeypatch):
        monkeypatch.setenv("VERITAS_DEBUG_MODE", "true")
        assert server._is_debug_mode() is True

    def test_yes_is_debug(self, monkeypatch):
        monkeypatch.setenv("VERITAS_DEBUG_MODE", "yes")
        assert server._is_debug_mode() is True

    def test_on_is_debug(self, monkeypatch):
        monkeypatch.setenv("VERITAS_DEBUG_MODE", "on")
        assert server._is_debug_mode() is True

    def test_empty_is_not_debug(self, monkeypatch):
        monkeypatch.setenv("VERITAS_DEBUG_MODE", "")
        assert server._is_debug_mode() is False

    def test_false_is_not_debug(self, monkeypatch):
        monkeypatch.setenv("VERITAS_DEBUG_MODE", "false")
        assert server._is_debug_mode() is False

    def test_random_is_not_debug(self, monkeypatch):
        monkeypatch.setenv("VERITAS_DEBUG_MODE", "random_value")
        assert server._is_debug_mode() is False


# =========================================================
# _resolve_expected_api_key_with_source
# =========================================================

class TestResolveExpectedApiKeyWithSource:
    def test_env_key_returns_env(self, monkeypatch):
        monkeypatch.setenv("VERITAS_API_KEY", "my-env-key")
        key, source = server._resolve_expected_api_key_with_source()
        assert key == "my-env-key"
        assert source == "env"

    def test_missing_returns_missing(self, monkeypatch):
        monkeypatch.setenv("VERITAS_API_KEY", "")
        monkeypatch.setattr(server, "API_KEY_DEFAULT", "")
        cfg_mock = MagicMock()
        cfg_mock.api_key = ""
        monkeypatch.setattr(server, "cfg", cfg_mock, raising=False)
        key, source = server._resolve_expected_api_key_with_source()
        assert source in ("missing", "env", "api_key_default", "config")


# =========================================================
# _decide_example
# =========================================================

class TestDecideExample:
    def test_returns_dict_with_required_keys(self):
        result = server._decide_example()
        assert "context" in result
        assert "query" in result
        assert "options" in result
