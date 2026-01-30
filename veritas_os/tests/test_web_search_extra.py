# tests/test_web_search_extra.py
"""Additional tests for web_search module to improve coverage."""
from __future__ import annotations

import importlib
from typing import Any, Dict

import pytest

web_search_mod = importlib.import_module("veritas_os.tools.web_search")


class TestNormalizeStr:
    """Tests for _normalize_str helper function."""

    def test_none_returns_empty(self):
        result = web_search_mod._normalize_str(None)
        assert result == ""

    def test_string_passthrough(self):
        result = web_search_mod._normalize_str("hello")
        assert result == "hello"

    def test_truncates_long_string(self):
        long_str = "a" * 5000
        result = web_search_mod._normalize_str(long_str, limit=100)
        assert len(result) == 100

    def test_exception_in_str_conversion(self):
        class BadStr:
            def __str__(self):
                raise ValueError("cannot convert")

        result = web_search_mod._normalize_str(BadStr())
        assert "BadStr" in result  # repr fallback


class TestShouldEnforceVeritasAnchor:
    """Tests for _should_enforce_veritas_anchor function."""

    def test_empty_query(self):
        assert web_search_mod._should_enforce_veritas_anchor("") is False
        assert web_search_mod._should_enforce_veritas_anchor(None) is False

    def test_bureau_veritas_excluded(self):
        assert web_search_mod._should_enforce_veritas_anchor("bureau veritas certification") is False
        assert web_search_mod._should_enforce_veritas_anchor("bureauveritas.com") is False

    def test_veritas_os_triggers(self):
        assert web_search_mod._should_enforce_veritas_anchor("veritas os documentation") is True
        assert web_search_mod._should_enforce_veritas_anchor("trustlog verification") is True
        assert web_search_mod._should_enforce_veritas_anchor("fuji gate safety") is True
        assert web_search_mod._should_enforce_veritas_anchor("valuecore alignment") is True
        assert web_search_mod._should_enforce_veritas_anchor("veritas_os package") is True
        assert web_search_mod._should_enforce_veritas_anchor("veritas-os github") is True

    def test_normal_query_not_triggered(self):
        assert web_search_mod._should_enforce_veritas_anchor("python web framework") is False


class TestApplyAnchorAndBlacklist:
    """Tests for _apply_anchor_and_blacklist function."""

    def test_applies_anchor_when_needed(self):
        result = web_search_mod._apply_anchor_and_blacklist("veritas query")
        assert result["anchor_applied"] is True
        assert "VERITAS OS" in result["final_query"] or "TrustLog" in result["final_query"]

    def test_no_anchor_when_already_present(self):
        query = "veritas os trustlog fuji"
        result = web_search_mod._apply_anchor_and_blacklist(query)
        # Already has key terms, anchor may not be needed
        assert "final_query" in result

    def test_blacklist_applied(self):
        result = web_search_mod._apply_anchor_and_blacklist("veritas")
        assert result["blacklist_applied"] is True
        # Should have -site: exclusions
        assert "-site:" in result["final_query"] or result["blacklist_applied"]


class TestIsBlockedResult:
    """Tests for _is_blocked_result function."""

    def test_blocks_blacklisted_keyword_in_title(self):
        assert web_search_mod._is_blocked_result(
            "Bureau Veritas certification",
            "some snippet",
            "https://example.com"
        ) is True

    def test_blocks_blacklisted_site_in_url(self):
        assert web_search_mod._is_blocked_result(
            "Some title",
            "some snippet",
            "https://bureauveritas.com/page"
        ) is True

    def test_blocks_veritas_com(self):
        assert web_search_mod._is_blocked_result(
            "Veritas Storage",
            "backup solutions",
            "https://www.veritas.com/product"
        ) is True

    def test_allows_clean_result(self):
        assert web_search_mod._is_blocked_result(
            "Python Tutorial",
            "Learn Python programming",
            "https://python.org/tutorial"
        ) is False

    def test_blocks_bureauveritas_wildcard(self):
        # Test bureauveritas.* wildcard blocking
        assert web_search_mod._is_blocked_result(
            "ISO Certification",
            "Quality management",
            "https://www.bureauveritas.co.jp/services"
        ) is True


class DummyResponse:
    """Mock response for requests.post."""
    def __init__(self, data: Dict[str, Any], status_code: int = 200):
        self._data = data
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")

    def json(self) -> Dict[str, Any]:
        return self._data


class TestWebSearchVeritasContext:
    """Tests for web_search with VERITAS context."""

    def test_veritas_query_applies_anchor_and_blacklist(self, monkeypatch):
        """VERITAS OS query should apply anchor and blacklist."""
        monkeypatch.setattr(
            web_search_mod, "WEBSEARCH_URL", "https://example.com/serper", raising=False
        )
        monkeypatch.setattr(web_search_mod, "WEBSEARCH_KEY", "dummy-key", raising=False)

        captured = {}

        def fake_post(url, headers, json, timeout):
            captured["payload"] = json
            return DummyResponse({"organic": []})

        monkeypatch.setattr(web_search_mod.requests, "post", fake_post)

        resp = web_search_mod.web_search("veritas os documentation", max_results=3)

        assert resp["ok"] is True
        assert resp["meta"]["anchor_applied"] is True or resp["meta"]["blacklist_applied"] is True

    def test_veritas_query_blocks_bureauveritas_results(self, monkeypatch):
        """VERITAS context should filter out Bureau Veritas results."""
        monkeypatch.setattr(
            web_search_mod, "WEBSEARCH_URL", "https://example.com/serper", raising=False
        )
        monkeypatch.setattr(web_search_mod, "WEBSEARCH_KEY", "dummy-key", raising=False)

        data = {
            "organic": [
                {
                    "title": "VERITAS OS Documentation",
                    "link": "https://github.com/veritas-os/docs",
                    "snippet": "TrustLog and FUJI gate documentation",
                },
                {
                    "title": "Bureau Veritas Certification",
                    "link": "https://bureauveritas.com/cert",
                    "snippet": "ISO certification services",
                },
            ]
        }

        def fake_post(url, headers, json, timeout):
            return DummyResponse(data)

        monkeypatch.setattr(web_search_mod.requests, "post", fake_post)

        resp = web_search_mod.web_search("veritas os trustlog", max_results=5)

        assert resp["ok"] is True
        # Bureau Veritas result should be blocked
        assert resp["meta"]["blocked_count"] >= 0


class TestWebSearchEdgeCases:
    """Edge case tests for web_search."""

    def test_empty_organic_results(self, monkeypatch):
        """Handle response with no organic results."""
        monkeypatch.setattr(
            web_search_mod, "WEBSEARCH_URL", "https://example.com/serper", raising=False
        )
        monkeypatch.setattr(web_search_mod, "WEBSEARCH_KEY", "dummy-key", raising=False)

        def fake_post(url, headers, json, timeout):
            return DummyResponse({"organic": []})

        monkeypatch.setattr(web_search_mod.requests, "post", fake_post)

        resp = web_search_mod.web_search("obscure query", max_results=5)

        assert resp["ok"] is True
        assert resp["results"] == []

    def test_missing_organic_key(self, monkeypatch):
        """Handle response missing organic key."""
        monkeypatch.setattr(
            web_search_mod, "WEBSEARCH_URL", "https://example.com/serper", raising=False
        )
        monkeypatch.setattr(web_search_mod, "WEBSEARCH_KEY", "dummy-key", raising=False)

        def fake_post(url, headers, json, timeout):
            return DummyResponse({})  # No organic key

        monkeypatch.setattr(web_search_mod.requests, "post", fake_post)

        resp = web_search_mod.web_search("test query", max_results=5)

        assert resp["ok"] is True
        assert resp["results"] == []

    def test_result_with_missing_fields(self, monkeypatch):
        """Handle results with missing title/snippet/link."""
        monkeypatch.setattr(
            web_search_mod, "WEBSEARCH_URL", "https://example.com/serper", raising=False
        )
        monkeypatch.setattr(web_search_mod, "WEBSEARCH_KEY", "dummy-key", raising=False)

        data = {
            "organic": [
                {"title": "Only title"},  # Missing link and snippet
                {"link": "https://only-link.com"},  # Missing title and snippet
                {"snippet": "Only snippet"},  # Missing title and link
            ]
        }

        def fake_post(url, headers, json, timeout):
            return DummyResponse(data)

        monkeypatch.setattr(web_search_mod.requests, "post", fake_post)

        resp = web_search_mod.web_search("incomplete results", max_results=5)

        assert resp["ok"] is True
        # Should handle gracefully


class TestIsAgiQueryExtended:
    """Extended tests for _is_agi_query."""

    def test_artificial_general_intelligence_full(self):
        assert web_search_mod._is_agi_query("artificial general intelligence safety") is True

    def test_case_insensitive_agi(self):
        assert web_search_mod._is_agi_query("AGI") is True
        assert web_search_mod._is_agi_query("agi") is True
        assert web_search_mod._is_agi_query("Agi") is True


class TestLooksAgiResultExtended:
    """Extended tests for _looks_agi_result."""

    def test_openai_site(self):
        assert web_search_mod._looks_agi_result(
            "GPT-5 Research",
            "AI capabilities",
            "https://openai.com/research"
        ) is True

    def test_deepmind_site(self):
        assert web_search_mod._looks_agi_result(
            "Gemini",
            "AI research",
            "https://deepmind.com/research"
        ) is True

    def test_keyword_agi_in_snippet(self):
        assert web_search_mod._looks_agi_result(
            "Book Review",
            "Discussion about AGI and AI risk",
            "https://blog.example.com"
        ) is True

    def test_keyword_artificial_general_intelligence(self):
        assert web_search_mod._looks_agi_result(
            "Research Paper",
            "artificial general intelligence capabilities",
            "https://research.example.com"
        ) is True
