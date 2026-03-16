# tests for veritas_os/core/pipeline_critique.py
"""Tests for pipeline critique module."""
from __future__ import annotations

import pytest

from veritas_os.core.pipeline_critique import (
    _chosen_to_option,
    _critique_fallback,
    _default_findings,
    _ensure_critique_required,
    _list_to_findings,
    _normalize_critique_payload,
    _pad_findings,
)


class TestDefaultFindings:
    def test_returns_3_items(self):
        findings = _default_findings()
        assert len(findings) == 3
        for f in findings:
            assert "severity" in f
            assert "message" in f


class TestPadFindings:
    def test_pads_to_minimum(self):
        result = _pad_findings([])
        assert len(result) >= 3

    def test_preserves_existing(self):
        items = [{"severity": "high", "message": "issue1", "code": "C1"}]
        result = _pad_findings(items, min_items=3)
        assert len(result) >= 3
        assert result[0]["message"] == "issue1"

    def test_normalizes_severity(self):
        items = [{"severity": "CRITICAL", "message": "x"}]
        result = _pad_findings(items)
        assert result[0]["severity"] in ("high", "med", "low")

    def test_dict_input(self):
        result = _pad_findings({"severity": "high", "message": "single"})
        assert len(result) >= 3

    def test_string_input(self):
        result = _pad_findings("text finding")
        assert len(result) >= 3

    def test_none_input(self):
        result = _pad_findings(None)
        assert len(result) >= 3

    def test_non_dict_item_in_list(self):
        result = _pad_findings(["text item", 42])
        assert len(result) >= 3

    def test_details_non_dict_wrapped(self):
        result = _pad_findings([{"message": "x", "details": "raw text"}])
        assert result[0]["details"] == {"raw": "raw text"}

    def test_fix_string(self):
        result = _pad_findings([{"message": "x", "fix": "do this"}])
        assert result[0]["fix"] == "do this"


class TestListToFindings:
    def test_dict_items(self):
        items = [
            {"issue": "bug found", "severity": "high", "code": "BUG1"},
            {"message": "warning", "severity": "low"},
        ]
        result = _list_to_findings(items)
        assert len(result) == 2
        assert result[0]["message"] == "bug found"

    def test_non_dict_items(self):
        result = _list_to_findings(["text", 123])
        assert len(result) == 2

    def test_empty(self):
        assert _list_to_findings([]) == []
        assert _list_to_findings(None) == []


class TestNormalizeCritiquePayload:
    def test_none_returns_empty(self):
        assert _normalize_critique_payload(None) == {}

    def test_dict_passthrough(self):
        result = _normalize_critique_payload({"ok": True, "findings": [{"message": "x"}]})
        assert result["ok"] is True
        assert len(result["findings"]) >= 3

    def test_list_input(self):
        result = _normalize_critique_payload([{"issue": "a"}])
        assert result["mode"] == "legacy_list"

    def test_string_input(self):
        result = _normalize_critique_payload("text critique")
        assert result["mode"] == "text"

    def test_dict_with_items(self):
        result = _normalize_critique_payload({"items": [{"issue": "x"}]})
        assert len(result["findings"]) >= 3

    def test_dict_with_issues(self):
        result = _normalize_critique_payload({"issues": [{"issue": "y"}]})
        assert len(result["findings"]) >= 3

    def test_recommendations_non_list(self):
        result = _normalize_critique_payload({"recommendations": "single"})
        assert isinstance(result["recommendations"], list)


class TestCritiqueFallback:
    def test_basic(self):
        result = _critique_fallback(reason="test")
        assert result["ok"] is False
        assert result["mode"] == "fallback"
        assert len(result["findings"]) >= 3

    def test_with_chosen_dict(self):
        result = _critique_fallback(reason="test", chosen={"title": "option A"})
        assert result["chosen_title"] == "option A"

    def test_with_chosen_string(self):
        result = _critique_fallback(reason="test", chosen="string option")
        assert result["chosen_title"] == "string option"


class TestEnsureCritiqueRequired:
    def test_with_valid_critique(self):
        extras: dict = {}
        result = _ensure_critique_required(
            response_extras=extras,
            query="test",
            chosen={"title": "opt"},
            critique_obj={"ok": True, "findings": [{"message": "x"}]},
        )
        assert len(result["findings"]) >= 3
        assert extras["metrics"]["critique_ok"] is True

    def test_with_none_critique(self):
        extras: dict = {}
        result = _ensure_critique_required(
            response_extras=extras,
            query="test",
            chosen=None,
            critique_obj=None,
        )
        assert result["mode"] == "fallback"
        assert extras.get("env_tools", {}).get("critique_degraded") is True


class TestChosenToOption:
    def test_dict(self):
        result = _chosen_to_option({"title": "Plan A", "risk": 0.5})
        assert result["title"] == "Plan A"
        assert result["risk"] == 0.5

    def test_string(self):
        result = _chosen_to_option("simple")
        assert result["title"] == "simple"

    def test_none(self):
        result = _chosen_to_option(None)
        assert result["title"] == "chosen"

    def test_dict_with_score(self):
        result = _chosen_to_option({"title": "X", "score": {"risk": 0.3, "value": 0.8}})
        assert result.get("risk") == 0.3
