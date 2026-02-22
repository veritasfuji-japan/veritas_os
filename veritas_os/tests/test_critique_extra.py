# veritas_os/tests/test_critique_extra.py
"""Additional tests for critique.py to improve coverage."""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from veritas_os.core import critique as crit_mod


class TestEnsureMinItems:
    """Tests for ensure_min_items function."""

    def test_pads_empty_list_to_min(self):
        """Empty list should be padded to min_items."""
        result = crit_mod.ensure_min_items([], min_items=3)
        assert len(result) == 3
        # Check that defaults are used
        assert any("根拠の一次性" in str(c.get("issue", "")) for c in result)

    def test_pads_short_list(self):
        """Short list should be padded to min_items."""
        existing = [{"issue": "test issue", "severity": "high"}]
        result = crit_mod.ensure_min_items(existing, min_items=3)
        assert len(result) == 3
        # First item should be the original
        assert result[0]["issue"] == "test issue"

    def test_leaves_long_list_unchanged(self):
        """List longer than min_items should not be modified."""
        existing = [
            {"issue": f"issue{i}", "severity": "med"} for i in range(5)
        ]
        result = crit_mod.ensure_min_items(existing, min_items=3)
        assert len(result) == 5

    def test_none_critiques_treated_as_empty(self):
        """None critiques should be treated as empty list."""
        result = crit_mod.ensure_min_items(None, min_items=2)
        assert len(result) == 2

    def test_context_parameter_accepted(self):
        """Context parameter should be accepted."""
        result = crit_mod.ensure_min_items(
            [], min_items=1, context={"key": "value"}
        )
        assert len(result) == 1

    def test_cycles_through_defaults(self):
        """When needing more than 3 defaults, should cycle."""
        result = crit_mod.ensure_min_items([], min_items=5)
        assert len(result) == 5
        # Should have cycled (3 defaults, cycle through again)


class TestToFindings:
    """Tests for _to_findings function."""

    def test_converts_critiques_to_findings(self):
        """Critiques should be converted to findings format."""
        critiques = [
            {
                "issue": "Test issue",
                "severity": "high",
                "code": "TEST_CODE",
                "details": {"key": "value"},
                "fix": "Fix this",
            }
        ]
        result = crit_mod._to_findings(critiques)
        assert len(result) == 1
        assert result[0]["message"] == "Test issue"
        assert result[0]["code"] == "TEST_CODE"
        assert result[0]["severity"] == "high"
        assert result[0]["fix"] == "Fix this"
        assert result[0]["details"] == {"key": "value"}

    def test_handles_missing_fields(self):
        """Missing fields should get defaults."""
        critiques = [{}]
        result = crit_mod._to_findings(critiques)
        assert len(result) == 1
        assert result[0]["message"] == "Critique finding"
        assert result[0]["code"] == "CRITIQUE_RULE"
        assert result[0]["details"] == {}

    def test_skips_non_dict_items(self):
        """Non-dict items should be skipped."""
        critiques = [{"issue": "valid"}, "not a dict", None, 123]
        result = crit_mod._to_findings(critiques)
        assert len(result) == 1
        assert result[0]["message"] == "valid"

    def test_handles_none_critiques(self):
        """None critiques should return empty list."""
        result = crit_mod._to_findings(None)
        assert result == []

    def test_normalizes_severity(self):
        """Severity should be normalized."""
        critiques = [
            {"issue": "test", "severity": "HIGH"},
            {"issue": "test2", "severity": "unknown"},
        ]
        result = crit_mod._to_findings(critiques)
        assert result[0]["severity"] == "high"
        # Unknown severity should default
        assert result[1]["severity"] in ("med", "medium", "low", "high")

    def test_non_dict_details_becomes_empty_dict(self):
        """Non-dict details should become empty dict."""
        critiques = [{"issue": "test", "details": "not a dict"}]
        result = crit_mod._to_findings(critiques)
        assert result[0]["details"] == {}


class TestAnalyzeDict:
    """Tests for analyze_dict function."""

    def test_returns_dict_with_required_keys(self):
        """analyze_dict should return dict with required keys."""
        result = crit_mod.analyze_dict(
            option={"answer": "test answer"},
            evidence=None,
            context=None,
        )
        assert isinstance(result, dict)
        assert "ok" in result
        assert "mode" in result
        assert "summary" in result
        assert "findings" in result
        assert "recommendations" in result
        assert "ts" in result
        assert result["ok"] is True

    def test_min_items_affects_findings_count(self):
        """min_items should affect minimum findings count."""
        result = crit_mod.analyze_dict(
            option={"answer": "test"},
            min_items=5,
        )
        assert len(result["findings"]) >= 5

    def test_mode_parameter_passed_through(self):
        """mode parameter should be in result."""
        result = crit_mod.analyze_dict(
            option={"answer": "test"},
            mode="custom_mode",
        )
        assert result["mode"] == "custom_mode"

    def test_raw_critiques_included(self):
        """Raw critiques should be included in result."""
        result = crit_mod.analyze_dict(
            option={"answer": "test"},
        )
        assert "raw" in result

    def test_with_evidence(self):
        """Should work with evidence provided."""
        evidence = [
            {"snippet": "evidence 1", "source": "test"},
            {"snippet": "evidence 2", "source": "test"},
        ]
        result = crit_mod.analyze_dict(
            option={"answer": "test"},
            evidence=evidence,
        )
        assert result["ok"] is True

    def test_with_context(self):
        """Should work with context provided."""
        context = {"goals": ["test"], "constraints": ["limit"]}
        result = crit_mod.analyze_dict(
            option={"answer": "test"},
            context=context,
        )
        assert result["ok"] is True


class TestAnalyzeValidation:
    """Validation and edge-case tests for analyze/analyze_dict."""

    def test_min_evidence_invalid_string_is_safe(self):
        """Invalid min_evidence values should not raise parsing errors."""
        result = crit_mod.analyze(
            option={"title": "t"},
            evidence=[],
            context={"min_evidence": "not-a-number"},
        )
        assert isinstance(result, list)

    def test_min_evidence_negative_is_clamped(self):
        """Negative min_evidence should be clamped to zero."""
        result = crit_mod.analyze(
            option={"title": "t"},
            evidence=[],
            context={"min_evidence": -5},
        )
        issues = {item.get("issue") for item in result}
        assert "根拠不足" not in issues


class TestNormSeverity:
    """Tests for _norm_severity helper."""

    def test_normalizes_uppercase(self):
        """Uppercase severity should be lowercased."""
        assert crit_mod._norm_severity("HIGH") == "high"
        assert crit_mod._norm_severity("MED") == "med"
        assert crit_mod._norm_severity("LOW") == "low"

    def test_handles_none(self):
        """None should return default."""
        result = crit_mod._norm_severity(None)
        assert result in ("med", "medium", "low", "high")

    def test_handles_empty_string(self):
        """Empty string should return default."""
        result = crit_mod._norm_severity("")
        assert result in ("med", "medium", "low", "high")
