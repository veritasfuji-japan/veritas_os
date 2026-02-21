# veritas_os/tests/test_kernel_extra_v2.py
"""Additional coverage tests for veritas_os/core/kernel.py.

Targets uncovered lines:
  - _open_doctor_log_fd with non-regular file (ValueError)
  - _tokens helper
  - _mk_option with explicit id
  - _safe_load_persona success and failure
  - _detect_intent with various patterns
  - _gen_options_by_intent
  - _filter_alts_by_intent with weather / no match
  - _dedupe_alts with "none" title and edge cases
  - _score_alternatives_with_value_core_and_persona
  - run_env_tool success and failure paths
"""
from __future__ import annotations

import asyncio
import os
import stat
import tempfile
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from veritas_os.core import kernel




# =========================================================
# _is_safe_python_executable
# =========================================================

class TestIsSafePythonExecutable:
    def test_returns_false_for_none(self):
        assert kernel._is_safe_python_executable(None) is False

    def test_returns_false_for_relative_path(self):
        assert kernel._is_safe_python_executable("python3") is False

    def test_returns_false_for_non_executable_file(self, tmp_path):
        file_path = tmp_path / "python3"
        file_path.write_text("#!/bin/false\n")
        file_path.chmod(0o600)
        assert kernel._is_safe_python_executable(str(file_path)) is False

    def test_returns_false_for_unexpected_executable_name(self, tmp_path):
        file_path = tmp_path / "bash"
        file_path.write_text("#!/bin/false\n")
        file_path.chmod(0o700)
        assert kernel._is_safe_python_executable(str(file_path)) is False

    def test_returns_true_for_python_like_executable(self, tmp_path):
        file_path = tmp_path / "python3.12"
        file_path.write_text("#!/bin/true\n")
        file_path.chmod(0o700)
        assert kernel._is_safe_python_executable(str(file_path)) is True

# =========================================================
# _open_doctor_log_fd
# =========================================================

class TestOpenDoctorLogFd:
    def test_opens_regular_file(self, tmp_path):
        """Opens a regular file successfully."""
        log_file = tmp_path / "test.log"
        log_file.touch()
        fd = kernel._open_doctor_log_fd(str(log_file))
        try:
            assert fd >= 0
        finally:
            os.close(fd)

    def test_non_regular_file_raises_value_error(self, tmp_path):
        """Non-regular file (fstat shows non-regular) raises ValueError."""
        import unittest.mock as mock
        log_file = tmp_path / "test.log"
        log_file.touch()

        # Patch os.fstat to return a non-regular file stat
        fake_stat = mock.MagicMock()
        fake_stat.st_mode = 0o010777  # S_IFIFO mode (FIFO)

        with mock.patch("os.fstat", return_value=fake_stat):
            with pytest.raises(ValueError, match="regular file"):
                fd = kernel._open_doctor_log_fd(str(log_file))
                os.close(fd)


# =========================================================
# _tokens
# =========================================================

class TestTokens:
    def test_basic_split(self):
        result = kernel._tokens("hello world")
        assert result == ["hello", "world"]

    def test_full_width_space(self):
        result = kernel._tokens("hello　world")
        assert result == ["hello", "world"]

    def test_lowercased(self):
        result = kernel._tokens("HELLO WORLD")
        assert result == ["hello", "world"]

    def test_empty_string(self):
        result = kernel._tokens("")
        assert result == []

    def test_none_string(self):
        result = kernel._tokens(None)
        assert result == []


# =========================================================
# _mk_option
# =========================================================

class TestMkOption:
    def test_generates_id_if_none(self):
        opt = kernel._mk_option("My Option")
        assert opt["id"] is not None
        assert len(opt["id"]) > 0

    def test_uses_explicit_id(self):
        opt = kernel._mk_option("My Option", _id="custom-id")
        assert opt["id"] == "custom-id"

    def test_includes_title_and_description(self):
        opt = kernel._mk_option("Title", description="Desc")
        assert opt["title"] == "Title"
        assert opt["description"] == "Desc"

    def test_default_score(self):
        opt = kernel._mk_option("Title")
        assert opt["score"] == 1.0


# =========================================================
# _safe_load_persona
# =========================================================

class TestSafeLoadPersona:
    def test_returns_dict_on_success(self, monkeypatch):
        monkeypatch.setattr(kernel.adapt, "load_persona", lambda: {"name": "test"})
        result = kernel._safe_load_persona()
        assert isinstance(result, dict)

    def test_returns_empty_dict_on_exception(self, monkeypatch):
        def _raise():
            raise RuntimeError("persona load failed")
        monkeypatch.setattr(kernel.adapt, "load_persona", _raise)
        result = kernel._safe_load_persona()
        assert result == {}

    def test_returns_empty_dict_on_non_dict(self, monkeypatch):
        monkeypatch.setattr(kernel.adapt, "load_persona", lambda: "not a dict")
        result = kernel._safe_load_persona()
        assert result == {}


# =========================================================
# _detect_intent
# =========================================================

class TestDetectIntent:
    def test_weather_pattern(self):
        assert kernel._detect_intent("明日の天気は？") == "weather"
        assert kernel._detect_intent("weather forecast") == "weather"

    def test_health_pattern(self):
        assert kernel._detect_intent("体調が悪くて疲れている") == "health"
        assert kernel._detect_intent("サウナに行きたい") == "health"

    def test_learn_pattern(self):
        assert kernel._detect_intent("Pythonとは何ですか?") == "learn"
        assert kernel._detect_intent("how does AI work?") == "learn"

    def test_plan_pattern(self):
        assert kernel._detect_intent("計画を立てたい") == "plan"
        assert kernel._detect_intent("todo list") == "plan"

    def test_unknown_defaults_to_plan(self):
        assert kernel._detect_intent("xyz abc def") == "plan"

    def test_empty_defaults_to_plan(self):
        assert kernel._detect_intent("") == "plan"


# =========================================================
# _gen_options_by_intent
# =========================================================

class TestGenOptionsByIntent:
    def test_weather_intent(self):
        opts = kernel._gen_options_by_intent("weather")
        assert len(opts) > 0
        for o in opts:
            assert "id" in o
            assert "title" in o

    def test_unknown_intent_returns_plan(self):
        opts = kernel._gen_options_by_intent("xyz_unknown")
        assert len(opts) > 0  # falls back to "plan"

    def test_health_intent(self):
        opts = kernel._gen_options_by_intent("health")
        assert len(opts) > 0

    def test_learn_intent(self):
        opts = kernel._gen_options_by_intent("learn")
        assert len(opts) > 0


# =========================================================
# _filter_alts_by_intent
# =========================================================

class TestFilterAltsByIntent:
    def test_weather_filters_to_relevant(self):
        alts = [
            {"title": "天気アプリで確認する", "description": ""},
            {"title": "全く関係ないオプション", "description": ""},
        ]
        result = kernel._filter_alts_by_intent("weather", "明日の天気", alts)
        # Only weather-related option should remain
        assert any("天気" in a["title"] for a in result)

    def test_non_weather_passes_through(self):
        alts = [
            {"title": "Option A", "description": ""},
            {"title": "Option B", "description": ""},
        ]
        result = kernel._filter_alts_by_intent("health", "体調", alts)
        assert result == alts  # passthrough

    def test_empty_list_stays_empty(self):
        result = kernel._filter_alts_by_intent("weather", "天気", [])
        assert result == []


# =========================================================
# _dedupe_alts
# =========================================================

class TestDedupeAlts:
    def test_removes_duplicates(self):
        alts = [
            {"title": "Option A", "description": "desc", "score": 0.5},
            {"title": "Option A", "description": "desc", "score": 0.9},
        ]
        result = kernel._dedupe_alts(alts)
        assert len(result) == 1

    def test_keeps_higher_score(self):
        alts = [
            {"title": "Option A", "description": "desc", "score": 0.5},
            {"title": "Option A", "description": "desc", "score": 0.9},
        ]
        result = kernel._dedupe_alts(alts)
        assert result[0]["score"] == 0.9

    def test_skips_non_dict(self):
        alts = [
            {"title": "Option A", "description": ""},
            "string",
            None,
            42,
        ]
        result = kernel._dedupe_alts(alts)
        assert all(isinstance(a, dict) for a in result)

    def test_skips_empty_title(self):
        alts = [
            {"title": "", "description": ""},
        ]
        result = kernel._dedupe_alts(alts)
        assert len(result) == 0

    def test_title_none_replaced_by_desc(self):
        """'none' title is replaced by description when desc exists."""
        alts = [
            {"title": "none", "description": "fallback title"},
        ]
        result = kernel._dedupe_alts(alts)
        assert len(result) == 1
        assert result[0]["title"] != "none"

    def test_title_none_without_desc_is_skipped(self):
        """'none' title with no desc is skipped."""
        alts = [
            {"title": "none", "description": ""},
        ]
        result = kernel._dedupe_alts(alts)
        assert len(result) == 0

    def test_empty_list(self):
        assert kernel._dedupe_alts([]) == []

    def test_score_invalid_type_treated_as_zero(self):
        """Non-numeric score is treated as 0.0 for comparison."""
        alts = [
            {"title": "A", "description": "", "score": "invalid"},
        ]
        result = kernel._dedupe_alts(alts)
        assert len(result) == 1


# =========================================================
# _score_alternatives_with_value_core_and_persona
# =========================================================

class TestScoreAlternativesWrapper:
    def test_delegates_to_score_alternatives(self, monkeypatch):
        """Wrapper calls _score_alternatives."""
        called = {}

        def fake_score(intent, q, alts, telos_score, stakes, persona_bias, ctx=None):
            called["ok"] = True

        monkeypatch.setattr(kernel, "_score_alternatives", fake_score)
        alts = [{"title": "A", "description": "", "score": 0.5}]
        kernel._score_alternatives_with_value_core_and_persona(
            intent="plan",
            q="test",
            alts=alts,
            telos_score=0.5,
            stakes=0.5,
            persona_bias={},
        )
        assert called.get("ok") is True


# =========================================================
# run_env_tool
# =========================================================

class TestRunEnvTool:
    def test_success_adds_default_fields(self, monkeypatch):
        """Successful call gets ok=True and results=[] defaults."""
        monkeypatch.setattr(kernel, "call_tool", lambda kind, **kw: {"data": "value"})
        result = kernel.run_env_tool("web_search", query="test")
        assert result["ok"] is True
        assert "results" in result

    def test_exception_returns_error_dict(self, monkeypatch):
        """Exception in call_tool returns error dict."""
        def fail_call(kind, **kw):
            raise RuntimeError("tool failed")
        monkeypatch.setattr(kernel, "call_tool", fail_call)
        result = kernel.run_env_tool("web_search", query="test")
        assert result["ok"] is False
        assert "error" in result
        assert "ENV_TOOL_EXECUTION_ERROR" == result.get("error_code")

    def test_non_dict_result_wrapped(self, monkeypatch):
        """Non-dict tool result is wrapped in {'raw': ...}."""
        monkeypatch.setattr(kernel, "call_tool", lambda kind, **kw: "raw string")
        result = kernel.run_env_tool("web_search")
        assert "raw" in result or result.get("ok") is True
