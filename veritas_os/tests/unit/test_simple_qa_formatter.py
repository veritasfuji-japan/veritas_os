# veritas_os/tests/unit/test_simple_qa_formatter.py
# -*- coding: utf-8 -*-
"""
simple_qa ユーザー向けフォーマッタのテスト

Tests:
  Case 1: simple_qa レスポンスが直接的な結論で始まり、
          生JSONダンプや内部score/meta/worldフィールドを含まないこと
  Case 2: 内部構造化データが監査/デバッグ用に保持されていること
  Case 3: format_simple_qa_summary の各分岐（time, weekday, date, unknown）
"""
from __future__ import annotations

import pytest

from veritas_os.core.kernel_qa import (
    format_simple_qa_summary,
    handle_simple_qa,
)


# ============================================================
# Case 3: format_simple_qa_summary 各分岐
# ============================================================

class TestFormatSimpleQaSummary:
    """format_simple_qa_summary の出力品質テスト"""

    def test_time_direct_conclusion(self):
        """time: 直接的な結論で始まること"""
        result = format_simple_qa_summary("time", "14:30")
        assert result.startswith("現在時刻は 14:30")
        assert "UTC" in result
        assert "\n" in result

    def test_weekday_direct_conclusion(self):
        """weekday: 直接的な結論で始まること"""
        result = format_simple_qa_summary("weekday", "月曜日")
        assert result.startswith("今日は月曜日です")
        assert "\n" in result

    def test_date_direct_conclusion(self):
        """date: 直接的な結論で始まること"""
        result = format_simple_qa_summary("date", "2026-04-13")
        assert result.startswith("今日の日付は 2026-04-13")
        assert "\n" in result

    def test_unknown_kind_fallback(self):
        """不明な種別: フォールバックメッセージ"""
        result = format_simple_qa_summary("unknown", "")
        assert "回答を生成できませんでした" in result

    def test_no_internal_jargon_in_time(self):
        """time: 内部用語が含まれないこと"""
        result = format_simple_qa_summary("time", "09:00")
        jargon = [
            "AGI", "world model", "planner step", "utility score",
            "value score", "debate step", "score_raw", "meta",
            "pipeline", "planning", "bypass_debate",
        ]
        for term in jargon:
            assert term.lower() not in result.lower(), f"Jargon '{term}' found in user summary"

    def test_no_json_in_output(self):
        """出力にJSONダンプが含まれないこと"""
        for kind, answer in [("time", "10:00"), ("weekday", "火曜日"), ("date", "2026-01-01")]:
            result = format_simple_qa_summary(kind, answer)
            assert "{" not in result
            assert "}" not in result
            assert '"id"' not in result
            assert '"score"' not in result


# ============================================================
# Case 1: handle_simple_qa user_summary の品質
# ============================================================

class TestHandleSimpleQaUserSummary:
    """handle_simple_qa が生成する user_summary の品質テスト"""

    def test_time_response_has_user_summary(self):
        """time: user_summary が存在し、直接的な結論で始まること"""
        result = handle_simple_qa(
            kind="time", q="今何時？", ctx={}, req_id="test-1", telos_score=0.5,
        )
        assert "user_summary" in result
        summary = result["user_summary"]
        assert isinstance(summary, str)
        assert summary.startswith("現在時刻は")
        assert len(summary) > 0

    def test_weekday_response_has_user_summary(self):
        """weekday: user_summary が存在し、直接的な結論で始まること"""
        result = handle_simple_qa(
            kind="weekday", q="今日何曜日？", ctx={}, req_id="test-2", telos_score=0.5,
        )
        summary = result["user_summary"]
        assert isinstance(summary, str)
        assert "今日は" in summary
        assert "曜日" in summary

    def test_date_response_has_user_summary(self):
        """date: user_summary が存在し、直接的な結論で始まること"""
        result = handle_simple_qa(
            kind="date", q="今日は何日？", ctx={}, req_id="test-3", telos_score=0.5,
        )
        summary = result["user_summary"]
        assert isinstance(summary, str)
        assert "今日の日付は" in summary

    def test_user_summary_no_raw_json_dump(self):
        """user_summary に生JSONダンプが含まれないこと"""
        result = handle_simple_qa(
            kind="time", q="今何時？", ctx={}, req_id="test-4", telos_score=0.5,
        )
        summary = result["user_summary"]
        assert "{" not in summary
        assert "}" not in summary
        assert '"id"' not in summary
        assert '"score"' not in summary
        assert '"score_raw"' not in summary

    def test_user_summary_no_internal_fields(self):
        """user_summary に内部フィールド名が含まれないこと"""
        result = handle_simple_qa(
            kind="time", q="今何時？", ctx={}, req_id="test-5", telos_score=0.5,
        )
        summary = result["user_summary"]
        internal_fields = [
            "score_raw", "avg_value", "avg_risk", "plan_progress",
            "utility", "confidence", "world",
        ]
        for field in internal_fields:
            assert field not in summary, f"Internal field '{field}' found in user_summary"

    def test_user_summary_no_planner_jargon(self):
        """user_summary にプランナー/AGI用語が含まれないこと"""
        for kind in ["time", "weekday", "date"]:
            result = handle_simple_qa(
                kind=kind, q="テスト", ctx={}, req_id="test-6", telos_score=0.5,
            )
            summary = result["user_summary"]
            jargon = ["AGI", "long-term planning", "world model",
                       "planner step", "utility score", "debate step"]
            for term in jargon:
                assert term.lower() not in summary.lower(), (
                    f"Jargon '{term}' found in user_summary for kind={kind}"
                )


# ============================================================
# Case 2: 内部構造化データの保持
# ============================================================

class TestHandleSimpleQaInternalDataPreserved:
    """内部データが監査/デバッグ用に完全に保持されていることの確認"""

    def test_chosen_still_has_internal_fields(self):
        """chosen に id, title, description, score, score_raw が残っていること"""
        result = handle_simple_qa(
            kind="time", q="今何時？", ctx={}, req_id="test-7", telos_score=0.5,
        )
        chosen = result["chosen"]
        assert "id" in chosen
        assert "title" in chosen
        assert "description" in chosen
        assert "score" in chosen
        assert "score_raw" in chosen

    def test_meta_preserved(self):
        """meta.kind が simple_qa のままであること"""
        result = handle_simple_qa(
            kind="time", q="今何時？", ctx={}, req_id="test-8", telos_score=0.5,
        )
        assert result["meta"]["kind"] == "simple_qa"

    def test_evidence_preserved(self):
        """evidence が保持されていること"""
        result = handle_simple_qa(
            kind="time", q="今何時？", ctx={}, req_id="test-9", telos_score=0.5,
        )
        assert len(result["evidence"]) > 0
        assert result["evidence"][0]["source"] == "internal:simple_qa"

    def test_fuji_gate_preserved(self):
        """fuji と gate が保持されていること"""
        result = handle_simple_qa(
            kind="time", q="今何時？", ctx={}, req_id="test-10", telos_score=0.5,
        )
        assert result["fuji"]["decision_status"] == "allow"
        assert result["gate"]["decision_status"] == "allow"

    def test_values_preserved(self):
        """values が保持されていること"""
        result = handle_simple_qa(
            kind="time", q="今何時？", ctx={}, req_id="test-11", telos_score=0.5,
        )
        assert result["values"]["rationale"] == "simple QA"
        assert result["values"]["total"] == 0.5

    def test_extras_preserved(self):
        """extras.simple_qa が保持されていること"""
        result = handle_simple_qa(
            kind="time", q="今何時？", ctx={}, req_id="test-12", telos_score=0.5,
        )
        assert result["extras"]["simple_qa"]["kind"] == "time"
        assert result["extras"]["simple_qa"]["mode"] == "bypass_debate"

    def test_request_id_preserved(self):
        """request_id が保持されていること"""
        result = handle_simple_qa(
            kind="time", q="今何時？", ctx={}, req_id="req-abc", telos_score=0.5,
        )
        assert result["request_id"] == "req-abc"

    def test_all_decide_response_keys_present(self):
        """DecideResponse 互換のキーがすべて存在すること"""
        result = handle_simple_qa(
            kind="time", q="今何時？", ctx={}, req_id="test-13", telos_score=0.5,
        )
        required_keys = [
            "request_id", "chosen", "alternatives", "evidence",
            "critique", "debate", "telos_score", "fuji",
            "rsi_note", "summary", "description", "user_summary",
            "extras", "gate", "values", "persona", "version",
            "decision_status", "rejection_reason",
            "memory_citations", "memory_used_count",
            "memory_evidence_count", "meta",
        ]
        for key in required_keys:
            assert key in result, f"Required key '{key}' missing from response"
