# -*- coding: utf-8 -*-
"""Unit tests for critique risk/value balance zero-division guard."""

from __future__ import annotations

from veritas_os.core import critique


def test_analyze_handles_zero_value_without_infinite_ratio() -> None:
    """When value=0, risk/value ratio should remain finite with floor value."""
    option = {
        "title": "high risk zero value",
        "risk": 0.8,
        "value": 0.0,
        "complexity": 0.3,
        "feasibility": 0.8,
        "timeline": 7,
    }
    evidence = [{"source": "s1", "confidence": 0.9}]
    ctx = {
        "risk_value_ratio_threshold": 2.0,
        "risk_threshold": 0.7,
        "min_evidence": 1,
    }

    findings = critique.analyze(option, evidence, ctx)
    rv_items = [item for item in findings if item.get("code") == "CRITIQUE_RISK_VALUE_IMBALANCE"]

    assert rv_items
    ratio = rv_items[0]["details"]["risk_value_ratio"]
    assert ratio != float("inf")
    assert ratio > 2.0
    assert rv_items[0]["details"]["value_floor"] == 0.01
