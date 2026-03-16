# tests for veritas_os/core/pipeline_web_adapter.py
"""Tests for web search payload normalization and extraction."""
from __future__ import annotations

import pytest

from veritas_os.core.pipeline_web_adapter import (
    _normalize_web_payload,
    _extract_web_results,
)


class TestNormalizeWebPayload:
    def test_none(self):
        assert _normalize_web_payload(None) is None

    def test_dict_with_results(self):
        result = _normalize_web_payload({"results": [{"title": "a"}]})
        assert result["ok"] is True
        assert len(result["results"]) == 1

    def test_dict_with_items(self):
        result = _normalize_web_payload({"items": [{"title": "b"}]})
        assert result["results"] == [{"title": "b"}]

    def test_dict_with_hits(self):
        result = _normalize_web_payload({"hits": [1, 2]})
        assert result["results"] == [1, 2]

    def test_dict_with_organic(self):
        result = _normalize_web_payload({"organic": [{"x": 1}]})
        assert len(result["results"]) == 1

    def test_dict_empty(self):
        result = _normalize_web_payload({})
        assert result["results"] == []

    def test_list(self):
        result = _normalize_web_payload([1, 2, 3])
        assert result["results"] == [1, 2, 3]

    def test_string(self):
        result = _normalize_web_payload("raw text")
        assert len(result["results"]) == 1


class TestExtractWebResults:
    def test_none(self):
        assert _extract_web_results(None) == []

    def test_list(self):
        assert _extract_web_results([1, 2]) == [1, 2]

    def test_non_dict(self):
        assert _extract_web_results(42) == []

    def test_dict_with_results(self):
        assert _extract_web_results({"results": [1]}) == [1]

    def test_dict_with_items(self):
        assert _extract_web_results({"items": [2]}) == [2]

    def test_nested_dict(self):
        assert _extract_web_results({"results": {"items": [3]}}) == [3]

    def test_deeply_nested(self):
        result = _extract_web_results({"wrapper": {"inner": {"results": [4]}}})
        assert result == [4]

    def test_3_levels_deep(self):
        # Only goes 2 levels deep via generic key scan
        result = _extract_web_results({"a": {"b": {"results": [5]}}})
        assert result == [5]

    def test_empty_dict(self):
        assert _extract_web_results({}) == []
