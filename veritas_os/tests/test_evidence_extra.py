# veritas_os/tests/test_evidence_extra.py
"""Additional tests for evidence.py to improve coverage."""
from __future__ import annotations

from typing import Any, Dict

import pytest

from veritas_os.core import evidence as ev_mod


class TestMkHelper:
    """Tests for _mk helper function."""

    def test_basic_creation(self):
        """Test basic evidence creation."""
        result = ev_mod._mk(
            source="test_source",
            kind="test_kind",
            weight=0.8,
            snippet="test snippet",
            tags=["tag1", "tag2"],
        )
        assert result["source"] == "test_source"
        assert result["kind"] == "test_kind"
        assert result["weight"] == 0.8
        assert result["snippet"] == "test snippet"
        assert result["tags"] == ["tag1", "tag2"]

    def test_invalid_weight_defaults(self):
        """Invalid weight should default to 0.2."""
        result = ev_mod._mk(
            source="test",
            kind="test",
            weight="not a number",  # type: ignore
            snippet="test",
        )
        assert result["weight"] == 0.2
        assert result["confidence"] == 0.2

    def test_weight_clamped_to_range(self):
        """Weight should be clamped to 0.0-1.0 for confidence."""
        result_high = ev_mod._mk(
            source="test", kind="test", weight=1.5, snippet="test"
        )
        assert result_high["confidence"] == 1.0

        result_low = ev_mod._mk(
            source="test", kind="test", weight=-0.5, snippet="test"
        )
        assert result_low["confidence"] == 0.0

    def test_none_snippet_becomes_empty(self):
        """None snippet should become empty string."""
        result = ev_mod._mk(
            source="test", kind="test", weight=0.5, snippet=None  # type: ignore
        )
        assert result["snippet"] == ""

    def test_default_title_from_kind(self):
        """Missing title should default to local:kind."""
        result = ev_mod._mk(
            source="test", kind="mykind", weight=0.5, snippet="test"
        )
        assert result["title"] == "local:mykind"

    def test_default_uri_from_kind(self):
        """Missing uri should default to internal:evidence:kind."""
        result = ev_mod._mk(
            source="test", kind="mykind", weight=0.5, snippet="test"
        )
        assert result["uri"] == "internal:evidence:mykind"

    def test_empty_title_gets_default(self):
        """Empty string title should get default."""
        result = ev_mod._mk(
            source="test", kind="mykind", weight=0.5, snippet="test",
            title="   "  # whitespace only
        )
        assert result["title"] == "local:mykind"

    def test_empty_uri_gets_default(self):
        """Empty string uri should get default."""
        result = ev_mod._mk(
            source="test", kind="mykind", weight=0.5, snippet="test",
            uri=""
        )
        assert result["uri"] == "internal:evidence:mykind"

    def test_custom_title_and_uri(self):
        """Custom title and uri should be preserved."""
        result = ev_mod._mk(
            source="test", kind="mykind", weight=0.5, snippet="test",
            title="Custom Title", uri="https://example.com"
        )
        assert result["title"] == "Custom Title"
        assert result["uri"] == "https://example.com"


class TestCollectLocal:
    """Tests for collect_local function."""

    def test_stakes_invalid_value_handled(self):
        """Invalid stakes value should be handled gracefully."""
        result = ev_mod.collect_local(
            intent="test",
            query="test query",
            context={"stakes": "not a number"},
        )
        # Should not raise, just skip the stakes evidence
        # No stakes evidence when invalid
        assert not any(e["kind"] == "stakes" for e in result)

    def test_stakes_none_handled(self):
        """None stakes should be handled."""
        result = ev_mod.collect_local(
            intent="test",
            query="test query",
            context={"stakes": None},
        )
        assert not any(e["kind"] == "stakes" for e in result)

    def test_high_stakes_adds_evidence(self):
        """High stakes should add caution evidence."""
        result = ev_mod.collect_local(
            intent="test",
            query="test query",
            context={"stakes": 0.9},
        )
        stakes_ev = [e for e in result if e["kind"] == "stakes"]
        assert len(stakes_ev) == 1
        assert "慎重側" in stakes_ev[0]["snippet"]

    def test_low_stakes_no_extra_evidence(self):
        """Low stakes should not add stakes evidence."""
        result = ev_mod.collect_local(
            intent="test",
            query="test query",
            context={"stakes": 0.3},
        )
        assert not any(e["kind"] == "stakes" for e in result)


class TestStep1MinimumEvidence:
    """Tests for step1_minimum_evidence function."""

    def test_returns_two_evidence_items(self):
        """Should return exactly 2 evidence items."""
        result = ev_mod.step1_minimum_evidence({})
        assert len(result) == 2

    def test_includes_inventory_evidence(self):
        """Should include inventory evidence."""
        result = ev_mod.step1_minimum_evidence({})
        inventory = [e for e in result if e["kind"] == "inventory"]
        assert len(inventory) == 1
        assert "現状機能" in inventory[0]["snippet"]

    def test_includes_known_issues_evidence(self):
        """Should include known issues evidence."""
        result = ev_mod.step1_minimum_evidence({})
        issues = [e for e in result if e["kind"] == "known_issues"]
        assert len(issues) == 1
        assert "既知の課題" in issues[0]["snippet"]

    def test_test_summary_in_context(self):
        """test_summary in context should be included."""
        result = ev_mod.step1_minimum_evidence({"test_summary": "All tests pass"})
        issues = [e for e in result if e["kind"] == "known_issues"]
        assert len(issues) == 1
        assert "All tests pass" in issues[0]["snippet"]

    def test_none_context_handled(self):
        """None context should be handled gracefully."""
        result = ev_mod.step1_minimum_evidence(None)  # type: ignore
        assert len(result) == 2
