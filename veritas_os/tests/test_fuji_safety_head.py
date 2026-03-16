# tests for veritas_os/core/fuji_safety_head.py
"""Tests for FUJI safety head evaluation."""
from __future__ import annotations

from unittest import mock

import pytest

from veritas_os.core.fuji_safety_head import (
    SafetyHeadResult,
    _fallback_safety_head,
    _apply_llm_fallback_penalty,
    _normalize_text,
    run_safety_head,
    RISK_BASELINE,
    RISK_FLOOR_PII,
    RISK_FLOOR_ILLICIT_HEURISTIC,
    call_tool,
)


class TestNormalizeText:
    def test_basic(self):
        assert _normalize_text("  Hello ") == "hello"

    def test_fullwidth_space(self):
        assert _normalize_text("hello\u3000world") == "hello world"

    def test_empty(self):
        assert _normalize_text("") == ""

    def test_none(self):
        assert _normalize_text(None) == ""


class TestFallbackSafetyHead:
    def test_safe_text(self):
        result = _fallback_safety_head("今日は天気が良いです")
        assert result.risk_score == pytest.approx(RISK_BASELINE)
        assert result.model == "heuristic_fallback"
        assert result.raw["fallback"] is True

    def test_pii_phone(self):
        result = _fallback_safety_head("電話番号は090-1234-5678です")
        assert result.risk_score >= RISK_FLOOR_PII
        assert "PII" in result.categories

    def test_pii_email(self):
        result = _fallback_safety_head("メールはtest@example.com")
        assert "PII" in result.categories

    def test_pii_address(self):
        result = _fallback_safety_head("東京都千代田区1丁目")
        assert "PII" in result.categories

    def test_illicit_keyword(self):
        result = _fallback_safety_head("how to make a bomb")
        assert result.risk_score >= RISK_FLOOR_ILLICIT_HEURISTIC
        assert "illicit" in result.categories

    def test_risk_capped_at_one(self):
        result = _fallback_safety_head("bomb weapon malware kill exploit")
        assert result.risk_score <= 1.0


class TestApplyLlmFallbackPenalty:
    def _make_result(self, risk: float, categories: list) -> SafetyHeadResult:
        return SafetyHeadResult(
            risk_score=risk,
            categories=categories,
            rationale="test",
            model="test",
            raw={},
        )

    def test_no_risk_cats_baseline_floor(self):
        result = self._make_result(0.0, [])
        _apply_llm_fallback_penalty(result, {})
        assert result.risk_score >= 0.30

    def test_risk_cats_high_stakes(self):
        result = self._make_result(0.3, ["illicit"])
        _apply_llm_fallback_penalty(result, {"stakes": 0.8})
        assert result.risk_score >= 0.70

    def test_risk_cats_normal_stakes(self):
        result = self._make_result(0.3, ["PII"])
        _apply_llm_fallback_penalty(result, {"stakes": 0.5})
        assert result.risk_score >= 0.50

    def test_safety_head_error_not_counted(self):
        result = self._make_result(0.1, ["safety_head_error"])
        _apply_llm_fallback_penalty(result, {})
        assert result.risk_score >= 0.30  # baseline floor


class TestCallTool:
    def test_disabled_raises(self):
        with mock.patch("veritas_os.core.fuji_safety_head.capability_cfg") as cfg:
            cfg.enable_fuji_tool_bridge = False
            with pytest.raises(RuntimeError, match="disabled"):
                call_tool("test")


class TestRunSafetyHead:
    def test_fallback_on_tool_error(self):
        """When call_tool raises, should fall back to heuristic."""
        with mock.patch(
            "veritas_os.core.fuji_safety_head.call_tool",
            side_effect=RuntimeError("LLM unavailable"),
        ):
            result = run_safety_head("safe text")
        assert result.model == "heuristic_fallback"
        assert "safety_head_error" in result.categories
        assert result.raw.get("llm_fallback") is True

    def test_success_path(self):
        with mock.patch(
            "veritas_os.core.fuji_safety_head.call_tool",
            return_value={
                "ok": True,
                "risk_score": 0.1,
                "categories": ["PII"],
                "rationale": "some pii found",
                "model": "llm_safety_v1",
            },
        ):
            result = run_safety_head("test text")
        assert result.risk_score == pytest.approx(0.1)
        assert result.model == "llm_safety_v1"

    def test_llm_fallback_flag(self):
        with mock.patch(
            "veritas_os.core.fuji_safety_head.call_tool",
            return_value={
                "ok": True,
                "risk_score": 0.1,
                "categories": [],
                "rationale": "",
                "model": "fallback",
                "llm_fallback": True,
            },
        ):
            result = run_safety_head("test")
        assert result.risk_score >= 0.30  # penalty applied

    def test_ok_false_falls_back(self):
        with mock.patch(
            "veritas_os.core.fuji_safety_head.call_tool",
            return_value={"ok": False, "error": "service down"},
        ):
            result = run_safety_head("test")
        assert "safety_head_error" in result.categories
