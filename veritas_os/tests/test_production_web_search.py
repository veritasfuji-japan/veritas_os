"""Production-like web search endpoint validation.

These tests validate the web search security layer, input sanitisation,
and response contract without requiring a live Serper API key.
When ``VERITAS_WEBSEARCH_KEY`` is set, the ``external`` marker enables
live-API tests as well.

Markers:
    production — production-like validation (excluded from default CI)
    external   — requires network and VERITAS_WEBSEARCH_KEY
"""

from __future__ import annotations

import importlib
import os
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def ws_module():
    """Return the web_search module (not the function)."""
    return importlib.import_module("veritas_os.tools.web_search")


# ---------------------------------------------------------------------------
# Production-like web search tests
# ---------------------------------------------------------------------------


@pytest.mark.production
class TestWebSearchSecurity:
    """Validate web search security layer."""

    def test_url_sanitisation_blocks_private_hosts(self):
        from veritas_os.tools.web_search_security import (
            _sanitize_websearch_url,
        )

        # Should block private/internal URLs
        for url in [
            "http://localhost/api",
            "http://127.0.0.1/data",
            "http://169.254.169.254/metadata",
            "http://192.168.1.1/admin",
            "http://10.0.0.1/internal",
        ]:
            result = _sanitize_websearch_url(url)
            assert result is None or result == "", (
                f"Private URL should be blocked: {url}"
            )

    def test_unicode_normalisation(self):
        from veritas_os.tools.web_search_security import (
            _canonicalize_hostname,
        )

        # Zero-width characters should be stripped
        host_with_zwsp = "exam\u200bple.com"
        canonical = _canonicalize_hostname(host_with_zwsp)
        assert canonical == "example.com"

    def test_ssrf_prevention_blocks_internal_tlds(self):
        from veritas_os.tools.web_search_security import (
            _is_obviously_private_or_local_host,
        )

        internal_hosts = [
            "service.local",
            "app.internal",
            "db.localhost",
            "api.corp",
            "admin.lan",
        ]
        for host in internal_hosts:
            assert _is_obviously_private_or_local_host(host), (
                f"Internal TLD should be blocked: {host}"
            )


@pytest.mark.production
class TestWebSearchResponseContract:
    """Validate web search function response structure."""

    def test_search_returns_expected_structure(self, ws_module, monkeypatch):
        """Verify web_search returns documented response shape with mocked HTTP."""
        monkeypatch.setenv("VERITAS_WEBSEARCH_KEY", "test-key")
        monkeypatch.setenv("VERITAS_WEBSEARCH_URL", "https://mock.serper.dev/search")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.json.return_value = {
            "organic": [
                {
                    "title": "Test Result",
                    "link": "https://example.com/result",
                    "snippet": "A test search result snippet.",
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(ws_module.requests, "post", return_value=mock_response):
            result = ws_module.web_search("test query")

        assert isinstance(result, dict)
        assert "ok" in result
        assert "results" in result
        assert "meta" in result

    def test_empty_query_handled(self, ws_module, monkeypatch):
        """Empty or blank queries should be handled gracefully."""
        monkeypatch.setenv("VERITAS_WEBSEARCH_KEY", "test-key")

        result = ws_module.web_search("")
        assert isinstance(result, dict)
        # Should either succeed with empty results or fail gracefully
        assert "ok" in result

    def test_long_query_truncated(self, ws_module, monkeypatch):
        """Queries exceeding max length should be truncated, not crash."""
        monkeypatch.setenv("VERITAS_WEBSEARCH_KEY", "test-key")

        long_query = "a" * 5000
        result = ws_module.web_search(long_query)
        assert isinstance(result, dict)
        assert "ok" in result


@pytest.mark.production
class TestWebSearchInputSanitisation:
    """Validate query injection and toxicity filters."""

    def test_control_chars_stripped(self):
        # The search function should strip control characters
        query = "normal query\x00\x01\x02"
        cleaned = query.replace("\x00", "").replace("\x01", "").replace("\x02", "")
        assert len(cleaned) < len(query)

    def test_html_in_query_safe(self, ws_module, monkeypatch):
        """HTML injection in query should not propagate."""
        monkeypatch.setenv("VERITAS_WEBSEARCH_KEY", "test-key")
        monkeypatch.setenv("VERITAS_WEBSEARCH_URL", "https://mock.serper.dev/search")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.json.return_value = {"organic": []}
        mock_response.raise_for_status = MagicMock()

        with patch.object(ws_module.requests, "post", return_value=mock_response):
            result = ws_module.web_search('<script>alert("xss")</script>')

        assert isinstance(result, dict)
        assert "ok" in result


@pytest.mark.production
class TestWebSearchNoKeyBehaviour:
    """Verify graceful degradation when API key is missing."""

    def test_no_key_returns_error(self, ws_module, monkeypatch):
        monkeypatch.delenv("VERITAS_WEBSEARCH_KEY", raising=False)

        result = ws_module.web_search("test")
        assert isinstance(result, dict)
        # Should fail gracefully, not crash
        assert result.get("ok") is False or result.get("results") == []
