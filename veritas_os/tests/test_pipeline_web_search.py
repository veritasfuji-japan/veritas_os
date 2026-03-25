# veritas_os/tests/test_pipeline_web_search.py
# -*- coding: utf-8 -*-
"""
Tests for safe_web_search extracted to pipeline_web_adapter.py.

Verifies:
1. Core logic (sanitization, resolver pattern, error handling)
2. Backward-compat wrapper in pipeline.py (_safe_web_search)
3. Monkeypatch support through resolver pattern
"""
from __future__ import annotations

import asyncio
import logging
import pytest


# =========================================================
# safe_web_search (pipeline_web_adapter)
# =========================================================

class TestSafeWebSearchCore:
    """Tests for pipeline_web_adapter.safe_web_search."""

    @pytest.mark.asyncio
    async def test_empty_query_returns_none(self):
        from veritas_os.core.pipeline_web_adapter import safe_web_search
        assert await safe_web_search("") is None
        assert await safe_web_search("   ") is None

    @pytest.mark.asyncio
    async def test_no_resolver_returns_none(self):
        from veritas_os.core.pipeline_web_adapter import safe_web_search
        assert await safe_web_search("test query") is None

    @pytest.mark.asyncio
    async def test_resolver_returns_none_fn(self):
        from veritas_os.core.pipeline_web_adapter import safe_web_search
        result = await safe_web_search(
            "test", web_search_resolver=lambda: None
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_sync_search_fn(self):
        from veritas_os.core.pipeline_web_adapter import safe_web_search

        def mock_search(q, max_results=5):
            return {"ok": True, "results": [{"title": q}]}

        result = await safe_web_search(
            "hello", web_search_resolver=lambda: mock_search
        )
        assert result["ok"] is True
        assert result["results"][0]["title"] == "hello"

    @pytest.mark.asyncio
    async def test_async_search_fn(self):
        from veritas_os.core.pipeline_web_adapter import safe_web_search

        async def mock_search(q, max_results=5):
            return {"ok": True, "results": []}

        result = await safe_web_search(
            "hello", web_search_resolver=lambda: mock_search
        )
        assert result == {"ok": True, "results": []}

    @pytest.mark.asyncio
    async def test_max_results_clamped(self):
        from veritas_os.core.pipeline_web_adapter import safe_web_search

        captured = {}

        def mock_search(q, max_results=5):
            captured["max_results"] = max_results
            return {"ok": True, "results": []}

        await safe_web_search(
            "test", max_results=100, web_search_resolver=lambda: mock_search
        )
        assert captured["max_results"] == 20

        await safe_web_search(
            "test", max_results=-5, web_search_resolver=lambda: mock_search
        )
        assert captured["max_results"] == 1

    @pytest.mark.asyncio
    async def test_query_truncated_at_512(self):
        from veritas_os.core.pipeline_web_adapter import safe_web_search

        captured = {}

        def mock_search(q, max_results=5):
            captured["q"] = q
            return {"ok": True, "results": []}

        long_q = "a" * 1000
        await safe_web_search(
            long_q, web_search_resolver=lambda: mock_search
        )
        assert len(captured["q"]) <= 512

    @pytest.mark.asyncio
    async def test_control_chars_stripped(self):
        from veritas_os.core.pipeline_web_adapter import safe_web_search

        captured = {}

        def mock_search(q, max_results=5):
            captured["q"] = q
            return {"ok": True, "results": []}

        await safe_web_search(
            "hello\x00world\x1f!", web_search_resolver=lambda: mock_search
        )
        assert "\x00" not in captured["q"]
        assert "\x1f" not in captured["q"]

    @pytest.mark.asyncio
    async def test_exception_returns_none(self, caplog):
        from veritas_os.core.pipeline_web_adapter import safe_web_search

        def bad_search(q, max_results=5):
            raise RuntimeError("network error")

        with caplog.at_level(logging.DEBUG, logger="veritas_os.core.pipeline"):
            result = await safe_web_search(
                "test", web_search_resolver=lambda: bad_search
            )

        assert result is None
        assert any("_safe_web_search failed" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_non_dict_result_returns_none(self):
        from veritas_os.core.pipeline_web_adapter import safe_web_search

        def mock_search(q, max_results=5):
            return "not a dict"

        result = await safe_web_search(
            "test", web_search_resolver=lambda: mock_search
        )
        assert result is None


# =========================================================
# _safe_web_search wrapper (pipeline.py)
# =========================================================

class TestSafeWebSearchWrapper:
    """Tests for pipeline._safe_web_search backward-compat wrapper."""

    @pytest.mark.asyncio
    async def test_monkeypatch_web_search(self, monkeypatch):
        """Monkeypatching pipeline.web_search still works."""
        import veritas_os.core.pipeline as pipeline_mod

        def mock_ws(q, max_results=5):
            return {"ok": True, "results": [{"q": q}]}

        monkeypatch.setattr(pipeline_mod, "web_search", mock_ws, raising=False)
        result = await pipeline_mod._safe_web_search("hello")
        assert result is not None
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_monkeypatch_tool_web_search(self, monkeypatch):
        """Monkeypatching pipeline._tool_web_search still works."""
        import veritas_os.core.pipeline as pipeline_mod

        monkeypatch.setattr(pipeline_mod, "web_search", None, raising=False)

        def mock_ws(q, max_results=5):
            return {"ok": True, "results": []}

        monkeypatch.setattr(pipeline_mod, "_tool_web_search", mock_ws)
        result = await pipeline_mod._safe_web_search("test")
        assert result == {"ok": True, "results": []}

    @pytest.mark.asyncio
    async def test_no_web_search_returns_none(self, monkeypatch):
        """When no web_search function is available, returns None."""
        import veritas_os.core.pipeline as pipeline_mod
        monkeypatch.setattr(pipeline_mod, "web_search", None, raising=False)
        monkeypatch.setattr(pipeline_mod, "_tool_web_search", None)
        result = await pipeline_mod._safe_web_search("test")
        assert result is None


# =========================================================
# _resolve_web_search_fn (pipeline.py)
# =========================================================

class TestResolveWebSearchFn:
    """Tests for the resolver function in pipeline.py."""

    def test_prefers_web_search_over_tool(self, monkeypatch):
        import veritas_os.core.pipeline as pipeline_mod

        def ws1(q, **kw):
            return "ws1"

        def ws2(q, **kw):
            return "ws2"

        monkeypatch.setattr(pipeline_mod, "web_search", ws1, raising=False)
        monkeypatch.setattr(pipeline_mod, "_tool_web_search", ws2)
        fn = pipeline_mod._resolve_web_search_fn()
        assert fn is ws1

    def test_falls_back_to_tool_web_search(self, monkeypatch):
        import veritas_os.core.pipeline as pipeline_mod

        def ws2(q, **kw):
            return "ws2"

        monkeypatch.setattr(pipeline_mod, "web_search", None, raising=False)
        monkeypatch.setattr(pipeline_mod, "_tool_web_search", ws2)
        fn = pipeline_mod._resolve_web_search_fn()
        assert fn is ws2
