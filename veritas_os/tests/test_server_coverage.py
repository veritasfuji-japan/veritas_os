# veritas_os/tests/test_server_coverage.py
"""Coverage-boosting tests for veritas_os/api/server.py."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from types import SimpleNamespace

# Set test API key before importing server
_TEST_KEY = "coverage-test-key-12345"
os.environ["VERITAS_API_KEY"] = _TEST_KEY
_AUTH = {"X-API-Key": _TEST_KEY}

import pytest
from fastapi.testclient import TestClient

import veritas_os.api.server as server

client = TestClient(server.app)


@pytest.fixture(autouse=True)
def _reset_rate_bucket(monkeypatch):
    monkeypatch.setenv("VERITAS_API_KEY", _TEST_KEY)
    server._rate_bucket.clear()
    yield
    server._rate_bucket.clear()


# ----------------------------------------------------------------
# 1. _effective_log_paths – default paths unchanged
# ----------------------------------------------------------------

def test_effective_log_paths_defaults():
    ld, lj, ljl = server._effective_log_paths()
    assert ld == server._DEFAULT_LOG_DIR
    assert lj == server._DEFAULT_LOG_JSON
    assert ljl == server._DEFAULT_LOG_JSONL


# 2. _effective_log_paths – LOG_DIR patched → json/jsonl follow
def test_effective_log_paths_follows_log_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "LOG_DIR", tmp_path)
    monkeypatch.setattr(server, "LOG_JSON", server._DEFAULT_LOG_JSON)
    monkeypatch.setattr(server, "LOG_JSONL", server._DEFAULT_LOG_JSONL)
    ld, lj, ljl = server._effective_log_paths()
    assert lj == tmp_path / "trust_log.json"
    assert ljl == tmp_path / "trust_log.jsonl"


# 3. _effective_log_paths – LOG_JSON explicitly patched is respected
def test_effective_log_paths_explicit_json(monkeypatch, tmp_path):
    custom = tmp_path / "custom.json"
    monkeypatch.setattr(server, "LOG_DIR", tmp_path)
    monkeypatch.setattr(server, "LOG_JSON", custom)
    monkeypatch.setattr(server, "LOG_JSONL", server._DEFAULT_LOG_JSONL)
    _, lj, _ = server._effective_log_paths()
    assert lj == custom


# ----------------------------------------------------------------
# 4. _effective_shadow_dir – default
# ----------------------------------------------------------------

def test_effective_shadow_dir_default():
    sd = server._effective_shadow_dir()
    assert sd == server._DEFAULT_SHADOW_DIR


# 5. _effective_shadow_dir – follows LOG_DIR
def test_effective_shadow_dir_follows_log_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "LOG_DIR", tmp_path)
    monkeypatch.setattr(server, "LOG_JSON", server._DEFAULT_LOG_JSON)
    monkeypatch.setattr(server, "LOG_JSONL", server._DEFAULT_LOG_JSONL)
    monkeypatch.setattr(server, "SHADOW_DIR", server._DEFAULT_SHADOW_DIR)
    assert server._effective_shadow_dir() == tmp_path / "DASH"


# 6. _effective_shadow_dir – explicit patch respected
def test_effective_shadow_dir_explicit(monkeypatch, tmp_path):
    custom = tmp_path / "my_shadow"
    monkeypatch.setattr(server, "SHADOW_DIR", custom)
    assert server._effective_shadow_dir() == custom


# ----------------------------------------------------------------
# 7-9. _is_placeholder
# ----------------------------------------------------------------

def test_is_placeholder_true():
    ns = SimpleNamespace(__veritas_placeholder__=True)
    assert server._is_placeholder(ns) is True


def test_is_placeholder_false_no_attr():
    assert server._is_placeholder(object()) is False


def test_is_placeholder_false_value():
    ns = SimpleNamespace(__veritas_placeholder__=False)
    assert server._is_placeholder(ns) is False


# ----------------------------------------------------------------
# 10-11. Stub functions
# ----------------------------------------------------------------

def test_fuji_validate_stub_returns_allow():
    r = server._fuji_validate_stub("test_action", {})
    assert r["status"] == "allow"
    assert r["action"] == "test_action"
    assert r["violations"] == []


def test_append_trust_log_stub_returns_none():
    assert server._append_trust_log_stub("a", b=1) is None


# ----------------------------------------------------------------
# 12-13. _LazyState
# ----------------------------------------------------------------

def test_lazy_state_defaults():
    ls = server._LazyState()
    assert ls.obj is None
    assert ls.err is None
    assert ls.attempted is False


def test_lazy_state_set():
    ls = server._LazyState(obj="x", err="e", attempted=True)
    assert ls.obj == "x"
    assert ls.err == "e"
    assert ls.attempted is True


# ----------------------------------------------------------------
# 14-15. _errstr / _log_decide_failure
# ----------------------------------------------------------------

def test_errstr():
    assert "ValueError" in server._errstr(ValueError("boom"))


def test_log_decide_failure_none(caplog):
    server._log_decide_failure("test msg", None)
    assert "test msg" in caplog.text


# ----------------------------------------------------------------
# 16-17. limit_body_size middleware
# ----------------------------------------------------------------

def test_limit_body_size_too_large():
    resp = client.get("/health", headers={"content-length": str(999_999_999_999)})
    assert resp.status_code == 413


def test_limit_body_size_invalid_content_length():
    resp = client.get("/health", headers={"content-length": "not-a-number"})
    assert resp.status_code == 400


# ----------------------------------------------------------------
# 18. add_security_headers middleware
# ----------------------------------------------------------------

def test_security_headers_present():
    resp = client.get("/health")
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert resp.headers.get("X-XSS-Protection") == "1; mode=block"
    assert (
        resp.headers.get("Content-Security-Policy")
        == "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    )
    assert (
        resp.headers.get("Permissions-Policy")
        == "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
        "magnetometer=(), microphone=(), payment=(), usb=()"
    )
    assert (
        resp.headers.get("Strict-Transport-Security")
        == "max-age=31536000; includeSubDomains"
    )
    assert resp.headers.get("Cache-Control") == "no-store"


# ----------------------------------------------------------------
# 19-21. require_api_key
# ----------------------------------------------------------------

def test_require_api_key_missing():
    resp = client.post("/v1/fuji/validate", json={"action": "x"})
    assert resp.status_code == 401


def test_require_api_key_wrong():
    resp = client.post("/v1/fuji/validate", json={"action": "x"}, headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401


def test_require_api_key_server_not_configured(monkeypatch):
    monkeypatch.setenv("VERITAS_API_KEY", "")
    monkeypatch.setattr(server, "API_KEY_DEFAULT", "")
    monkeypatch.setattr(server, "cfg", SimpleNamespace(api_key=""))
    resp = client.post("/v1/fuji/validate", json={"action": "x"}, headers={"X-API-Key": "any"})
    assert resp.status_code == 500


# ----------------------------------------------------------------
# 22-23. enforce_rate_limit
# ----------------------------------------------------------------

def test_enforce_rate_limit_missing_key():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        server.enforce_rate_limit(x_api_key=None)
    assert exc.value.status_code == 401


def test_enforce_rate_limit_exceeded(monkeypatch):
    key = "rl-test-key"
    server._rate_bucket.clear()
    server._rate_bucket[key] = (server._RATE_LIMIT, time.time())
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        server.enforce_rate_limit(x_api_key=key)
    assert exc.value.status_code == 429


def test_enforce_rate_limit_ok():
    server._rate_bucket.clear()
    result = server.enforce_rate_limit(x_api_key="fresh-key")
    assert result is True


# ----------------------------------------------------------------
# 24-26. verify_signature
# ----------------------------------------------------------------

class _FakeRequest:
    def __init__(self, body: bytes):
        self._body = body

    async def body(self) -> bytes:
        return self._body


def _run_async(coro):
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_verify_signature_missing_secret(monkeypatch):
    monkeypatch.setattr(server, "API_SECRET", b"")
    monkeypatch.setenv("VERITAS_API_SECRET", "")
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        _run_async(server.verify_signature(
            _FakeRequest(b"{}"), x_api_key="k", x_timestamp=str(int(time.time())),
            x_nonce="n1", x_signature="sig",
        ))
    assert exc.value.status_code == 500


def test_verify_signature_missing_headers(monkeypatch):
    monkeypatch.setattr(server, "API_SECRET", b"secret-for-test-1234567890abcdef")
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        _run_async(server.verify_signature(
            _FakeRequest(b""), x_api_key=None, x_timestamp=None, x_nonce=None, x_signature=None,
        ))
    assert exc.value.status_code == 401


def test_verify_signature_invalid_timestamp(monkeypatch):
    monkeypatch.setattr(server, "API_SECRET", b"secret-for-test-1234567890abcdef")
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        _run_async(server.verify_signature(
            _FakeRequest(b""), x_api_key="k", x_timestamp="not-int",
            x_nonce="n2", x_signature="sig",
        ))
    assert exc.value.status_code == 401


def test_verify_signature_timestamp_out_of_range(monkeypatch):
    monkeypatch.setattr(server, "API_SECRET", b"secret-for-test-1234567890abcdef")
    old_ts = str(int(time.time()) - 9999)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        _run_async(server.verify_signature(
            _FakeRequest(b""), x_api_key="k", x_timestamp=old_ts,
            x_nonce="n3", x_signature="sig",
        ))
    assert exc.value.status_code == 401


def test_verify_signature_valid(monkeypatch):
    secret = b"secret-for-test-1234567890abcdef"
    monkeypatch.setattr(server, "API_SECRET", secret)
    server._nonce_store.clear()
    ts = str(int(time.time()))
    nonce = "unique-nonce-valid"
    body = b'{"hello":"world"}'
    payload = f"{ts}\n{nonce}\n{body.decode()}"
    sig = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()
    result = _run_async(server.verify_signature(
        _FakeRequest(body), x_api_key="k", x_timestamp=ts,
        x_nonce=nonce, x_signature=sig,
    ))
    assert result is True


def test_verify_signature_replay(monkeypatch):
    secret = b"secret-for-test-1234567890abcdef"
    monkeypatch.setattr(server, "API_SECRET", secret)
    server._nonce_store.clear()
    ts = str(int(time.time()))
    nonce = "replay-nonce"
    body = b""
    payload = f"{ts}\n{nonce}\n"
    sig = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()
    # First call succeeds
    _run_async(server.verify_signature(
        _FakeRequest(body), x_api_key="k", x_timestamp=ts,
        x_nonce=nonce, x_signature=sig,
    ))
    # Second call is replay
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        _run_async(server.verify_signature(
            _FakeRequest(body), x_api_key="k", x_timestamp=ts,
            x_nonce=nonce, x_signature=sig,
        ))
    assert exc.value.status_code == 401


# ----------------------------------------------------------------
# 30-32. _coerce_decide_payload
# ----------------------------------------------------------------

def test_coerce_decide_payload_non_dict():
    r = server._coerce_decide_payload("just a string")
    assert r["ok"] is True
    assert r["alternatives"] == []
    assert "request_id" in r


def test_coerce_decide_payload_dict_minimal():
    r = server._coerce_decide_payload({"chosen": {"title": "A"}})
    assert r["ok"] is True
    assert "request_id" in r
    assert r["trust_log"] is None


def test_coerce_decide_payload_options_to_alternatives():
    r = server._coerce_decide_payload({"options": [{"title": "opt1"}]})
    assert len(r["alternatives"]) == 1
    assert r["alternatives"][0]["title"] == "opt1"


# ----------------------------------------------------------------
# 33-35. _coerce_fuji_payload
# ----------------------------------------------------------------

def test_coerce_fuji_payload_non_dict():
    r = server._coerce_fuji_payload("raw", action="act")
    assert r["status"] == "allow"
    assert r["action"] == "act"


def test_coerce_fuji_payload_empty_dict():
    r = server._coerce_fuji_payload({})
    assert r["status"] == "allow"
    assert r["reasons"] == []
    assert r["violations"] == []


def test_coerce_fuji_payload_preserves_status():
    r = server._coerce_fuji_payload({"status": "rejected", "reasons": ["r"], "violations": ["v"]})
    assert r["status"] == "rejected"
    assert r["reasons"] == ["r"]


# ----------------------------------------------------------------
# 36-38. _coerce_alt_list
# ----------------------------------------------------------------

def test_coerce_alt_list_none():
    assert server._coerce_alt_list(None) == []


def test_coerce_alt_list_single_dict():
    r = server._coerce_alt_list({"title": "A"})
    assert len(r) == 1
    assert r[0]["title"] == "A"


def test_coerce_alt_list_scalar():
    r = server._coerce_alt_list("hello")
    assert len(r) == 1
    assert r[0]["title"] == "hello"


# ----------------------------------------------------------------
# 39. _gen_request_id
# ----------------------------------------------------------------

def test_gen_request_id_length():
    rid = server._gen_request_id("seed")
    assert isinstance(rid, str)
    assert len(rid) == 24


# ----------------------------------------------------------------
# 40. _is_debug_mode
# ----------------------------------------------------------------

def test_is_debug_mode_off(monkeypatch):
    monkeypatch.delenv("VERITAS_DEBUG_MODE", raising=False)
    assert server._is_debug_mode() is False


def test_is_debug_mode_on(monkeypatch):
    monkeypatch.setenv("VERITAS_DEBUG_MODE", "1")
    assert server._is_debug_mode() is True


def test_is_debug_mode_with_spaces(monkeypatch):
    monkeypatch.setenv("VERITAS_DEBUG_MODE", "  TRUE  ")
    assert server._is_debug_mode() is True


def test_is_debug_mode_on_keyword(monkeypatch):
    monkeypatch.setenv("VERITAS_DEBUG_MODE", "on")
    assert server._is_debug_mode() is True


def test_is_debug_mode_unknown_value(monkeypatch):
    monkeypatch.setenv("VERITAS_DEBUG_MODE", "enabled")
    assert server._is_debug_mode() is False


# ----------------------------------------------------------------
# 42. _is_placeholder_secret
# ----------------------------------------------------------------

def test_is_placeholder_secret_true():
    assert server._is_placeholder_secret("YOUR_VERITAS_API_SECRET_HERE") is True


def test_is_placeholder_secret_false():
    assert server._is_placeholder_secret("real-secret") is False


# ----------------------------------------------------------------
# 44. _cleanup_nonces
# ----------------------------------------------------------------

def test_cleanup_nonces_removes_expired():
    server._nonce_store["old"] = time.time() - 9999
    server._cleanup_nonces()
    assert "old" not in server._nonce_store


# ----------------------------------------------------------------
# 45. _check_and_register_nonce
# ----------------------------------------------------------------

def test_check_and_register_nonce_new():
    nonce = f"fresh-{time.time()}"
    assert server._check_and_register_nonce(nonce) is True


def test_check_and_register_nonce_duplicate():
    nonce = f"dup-{time.time()}"
    server._check_and_register_nonce(nonce)
    assert server._check_and_register_nonce(nonce) is False


# ----------------------------------------------------------------
# 47. _cleanup_rate_bucket
# ----------------------------------------------------------------

def test_cleanup_rate_bucket_removes_old():
    server._rate_bucket["old_key"] = (1, time.time() - 9999)
    server._cleanup_rate_bucket()
    assert "old_key" not in server._rate_bucket


# ----------------------------------------------------------------
# 48. redact
# ----------------------------------------------------------------

def test_redact_empty():
    assert server.redact("") == ""


def test_redact_email():
    result = server.redact("contact user@example.com today")
    assert "user@example.com" not in result


# ----------------------------------------------------------------
# 50. _decide_example
# ----------------------------------------------------------------

def test_decide_example_format():
    ex = server._decide_example()
    assert "query" in ex
    assert "options" in ex


# ----------------------------------------------------------------
# 51-52. Endpoints via TestClient
# ----------------------------------------------------------------

def test_root_endpoint():
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["service"] == "veritas-api"


def test_health_endpoint():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_v1_health_endpoint():
    resp = client.get("/v1/health")
    assert resp.status_code == 200


def test_status_endpoint():
    resp = client.get("/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "version" in data
    assert "api_key_configured" in data


# ----------------------------------------------------------------
# 53. _call_fuji
# ----------------------------------------------------------------

def test_call_fuji_validate_action():
    fc = SimpleNamespace(validate_action=lambda action, context: {"status": "allow"})
    r = server._call_fuji(fc, "act", {})
    assert r["status"] == "allow"


def test_call_fuji_validate_fallback():
    fc = SimpleNamespace(validate=lambda action, context: {"status": "ok"})
    r = server._call_fuji(fc, "act", {})
    assert r["status"] == "ok"


def test_call_fuji_no_method():
    fc = SimpleNamespace()
    with pytest.raises(RuntimeError, match="neither"):
        server._call_fuji(fc, "act", {})


# ----------------------------------------------------------------
# 56. enforce_rate_limit window reset
# ----------------------------------------------------------------

def test_enforce_rate_limit_window_reset():
    key = "window-reset-key"
    server._rate_bucket[key] = (99, time.time() - server._RATE_WINDOW - 1)
    result = server.enforce_rate_limit(x_api_key=key)
    assert result is True
    assert server._rate_bucket[key][0] == 1


# ----------------------------------------------------------------
# 57. _get_expected_api_key paths
# ----------------------------------------------------------------

def test_get_expected_api_key_env(monkeypatch):
    monkeypatch.setenv("VERITAS_API_KEY", "envkey")
    assert server._get_expected_api_key() == "envkey"


def test_get_expected_api_key_fallback_default(monkeypatch):
    monkeypatch.setenv("VERITAS_API_KEY", "")
    monkeypatch.setattr(server, "API_KEY_DEFAULT", "default-key")
    assert server._get_expected_api_key() == "default-key"


# ----------------------------------------------------------------
# 58. _memory stubs
# ----------------------------------------------------------------

def test_memory_search_stub():
    assert server._memory_search_stub() == []


def test_memory_get_stub():
    assert server._memory_get_stub() is None
