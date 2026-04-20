# veritas_os/tests/unit/test_kernel_qa.py
# -*- coding: utf-8 -*-
"""Unit tests for ``veritas_os.core.kernel_qa``.

Covers detection/handling logic that was previously only validated via the
aggregate ``test_kernel_decide_ext.py`` suite.  Focus areas:

* ``detect_simple_qa`` — all regex branches, AGI block, length guard, and
  mixed JP/EN short queries.
* ``detect_knowledge_qa`` — Japanese/English triggers, keyword list, and
  defensive length/emptiness checks.
* ``handle_knowledge_qa`` — happy path, empty web-search path, FUJI Gate
  success, and the fail-closed branch required by CLAUDE.md §4.2.
* ``_safe_load_persona`` / ``_get_run_env_tool`` helpers.
"""
from __future__ import annotations

from typing import Any, Dict

import pytest

from veritas_os.core import kernel_qa

pytestmark = pytest.mark.unit


# ============================================================
# Helpers
# ============================================================


def _mk_ctx(**overrides: Any) -> Dict[str, Any]:
    ctx: Dict[str, Any] = {
        "user_id": "u1",
        "stakes": 0.5,
        "mode": "",
        "fuji_safe_applied": False,
    }
    ctx.update(overrides)
    return ctx


class _FakeFujiAllow:
    """Stand-in for ``fuji_core.evaluate`` that returns an allow verdict."""

    @staticmethod
    def evaluate(query: str, *, context: Dict[str, Any], evidence, alternatives):
        return {
            "status": "allow",
            "decision_status": "allow",
            "reasons": [],
            "violations": [],
            "risk": 0.05,
            "checks": [],
            "guidance": None,
            "modifications": [],
            "redactions": [],
            "safe_instructions": [],
        }


class _FakeFujiRaise:
    """Stand-in that raises — used to validate fail-closed semantics."""

    @staticmethod
    def evaluate(*_args, **_kwargs):
        raise RuntimeError("boom-fuji")


# ============================================================
# _safe_load_persona
# ============================================================


class TestSafeLoadPersona:
    def test_returns_dict_on_success(self, monkeypatch):
        monkeypatch.setattr(
            kernel_qa.adapt,
            "load_persona",
            lambda: {"name": "persona-a", "bias_weights": {}},
        )
        result = kernel_qa._safe_load_persona()
        assert isinstance(result, dict)
        assert result["name"] == "persona-a"

    def test_returns_empty_dict_when_adapt_returns_non_dict(self, monkeypatch):
        monkeypatch.setattr(kernel_qa.adapt, "load_persona", lambda: ["not", "a", "dict"])
        assert kernel_qa._safe_load_persona() == {}

    def test_returns_empty_dict_on_exception(self, monkeypatch):
        def _boom():
            raise RuntimeError("persona.json corrupted")

        monkeypatch.setattr(kernel_qa.adapt, "load_persona", _boom)
        assert kernel_qa._safe_load_persona() == {}


# ============================================================
# _get_run_env_tool
# ============================================================


class TestGetRunEnvTool:
    def test_returns_kernel_run_env_tool(self):
        from veritas_os.core import kernel as kernel_mod

        resolved = kernel_qa._get_run_env_tool()
        assert resolved is kernel_mod.run_env_tool


# ============================================================
# detect_simple_qa
# ============================================================


class TestDetectSimpleQa:
    @pytest.mark.parametrize(
        "query, expected",
        [
            ("今何時？", "time"),
            ("いま何時", "time"),
            ("今日何曜日？", "weekday"),
            ("今日は何曜日？", "weekday"),
            ("今日何日？", "date"),
            ("今日の日付", "date"),
            ("what time is it?", "time"),
            ("What Time Is It", "time"),
            ("what day is it?", "weekday"),
        ],
    )
    def test_detects_known_patterns(self, query, expected):
        assert kernel_qa.detect_simple_qa(query) == expected

    @pytest.mark.parametrize(
        "query",
        [
            "",
            "   ",
            "今日は良い天気ですね",
            "AGI について教えて",  # AGI block keyword
            "プロトAGI の設計",
            "veritas とは？",  # veritas blocked
            "random query without time markers",
        ],
    )
    def test_returns_none_for_unrelated_or_blocked(self, query):
        assert kernel_qa.detect_simple_qa(query) is None

    def test_returns_none_for_query_above_max_length(self):
        big_query = "時" * (kernel_qa.MAX_QA_QUERY_LENGTH + 10)
        assert kernel_qa.detect_simple_qa(big_query) is None

    def test_long_normalized_without_mixed_markers_rejected(self):
        # Exceeds 25-char normalized limit but lacks the mixed-language escape hatch.
        long_q = "今日の特別な予定について教えて何時でも構いません"
        assert kernel_qa.detect_simple_qa(long_q) is None

    def test_mixed_language_short_time(self):
        assert kernel_qa.detect_simple_qa("today what time is it") == "time"

    def test_mixed_language_short_weekday(self):
        assert kernel_qa.detect_simple_qa("today what day?") == "weekday"

    def test_mixed_language_short_date(self):
        assert kernel_qa.detect_simple_qa("what's the date today?") == "date"
        assert kernel_qa.detect_simple_qa("today date") == "date"

    def test_handles_full_width_space(self):
        # U+3000 full-width space should be normalized.
        assert kernel_qa.detect_simple_qa("今　何時？") == "time"

    def test_handles_none_input_gracefully(self):
        # Function signature accepts ``str`` but defensively handles None-likes
        # via the ``(q or "")`` fallback.
        assert kernel_qa.detect_simple_qa("") is None


# ============================================================
# detect_knowledge_qa
# ============================================================


class TestDetectKnowledgeQa:
    @pytest.mark.parametrize(
        "query",
        [
            "量子もつれとは？",
            "量子もつれとは",
            "東京タワーはどこ？",
            "首都はどこにある",
            "日本の総理大臣は誰？",
            "夏目漱石はだれ",
            "富山県の県庁所在地",
            "日本の首都",
            "東京の人口は？",
            "富士山の標高",
            "地球の面積",
            "what is quantum entanglement",
            "Who is Albert Einstein",
            "where is Mount Everest",
        ],
    )
    def test_detects_knowledge_queries(self, query):
        assert kernel_qa.detect_knowledge_qa(query) is True

    @pytest.mark.parametrize(
        "query",
        [
            "",
            "  ",
            "今日",  # shorter than 4 chars
            "abc",  # shorter than 4 chars
            "何かおすすめの本を教えて",  # no knowledge markers
            "タスクを整理したい",
        ],
    )
    def test_returns_false_for_unrelated_or_short(self, query):
        assert kernel_qa.detect_knowledge_qa(query) is False

    def test_returns_false_for_query_above_max_length(self):
        big_query = "a" * (kernel_qa.MAX_QA_QUERY_LENGTH + 10)
        assert kernel_qa.detect_knowledge_qa(big_query) is False


# ============================================================
# handle_knowledge_qa
# ============================================================


class TestHandleKnowledgeQaHappyPath:
    def test_returns_decide_response_with_web_search_result(self, monkeypatch):
        def _fake_run_env_tool(kind, **kwargs):
            assert kind == "web_search"
            assert kwargs.get("query") == "量子もつれとは？"
            assert kwargs.get("max_results") == 3
            return {
                "ok": True,
                "results": [
                    {
                        "title": "Quantum Entanglement Primer",
                        "url": "https://example.com/qe",
                        "snippet": "もつれとは二粒子の状態が相関する現象",
                    }
                ],
            }

        monkeypatch.setattr(kernel_qa, "_get_run_env_tool", lambda: _fake_run_env_tool)
        monkeypatch.setattr(kernel_qa, "fuji_core", _FakeFujiAllow)
        monkeypatch.setattr(kernel_qa, "_safe_load_persona", lambda: {"name": "p"})

        resp = kernel_qa.handle_knowledge_qa(
            q="量子もつれとは？",
            ctx=_mk_ctx(),
            req_id="req-k1",
            telos_score=0.42,
        )

        assert resp["request_id"] == "req-k1"
        assert resp["meta"]["kind"] == "knowledge_qa"
        assert resp["decision_status"] == "allow"
        assert resp["extras"]["knowledge_qa"]["mode"] == "bypass_debate"
        assert "量子もつれとは" in resp["chosen"]["title"]
        assert "もつれとは" in resp["description"]
        assert "https://example.com/qe" in resp["description"]
        # evidence carries exactly one internal marker.
        assert resp["evidence"][0]["source"] == "internal:knowledge_qa"
        # telos_score and gate values are coherent.
        assert resp["telos_score"] == 0.42
        assert resp["gate"]["telos_score"] == pytest.approx(0.42)
        assert resp["values"]["total"] == pytest.approx(0.42)

    def test_returns_fallback_description_when_search_fails(self, monkeypatch):
        monkeypatch.setattr(
            kernel_qa,
            "_get_run_env_tool",
            lambda: (lambda *a, **kw: {"ok": False, "error": "network timeout"}),
        )
        monkeypatch.setattr(kernel_qa, "fuji_core", _FakeFujiAllow)

        resp = kernel_qa.handle_knowledge_qa(
            q="東京タワーはどこ？",
            ctx=_mk_ctx(),
            req_id="req-k2",
            telos_score=0.3,
        )

        assert "明確な回答を取得できませんでした" in resp["chosen"]["title"]
        assert "network timeout" in resp["description"]
        # Even on search failure, the response must remain DecideResponse compatible.
        for key in (
            "chosen",
            "alternatives",
            "evidence",
            "fuji",
            "gate",
            "values",
            "extras",
            "meta",
        ):
            assert key in resp


class TestHandleKnowledgeQaFujiFailClosed:
    """CLAUDE.md §4.2: FUJI Gate exceptions must produce a deny verdict."""

    def test_fuji_exception_produces_deny_and_max_risk(self, monkeypatch):
        monkeypatch.setattr(
            kernel_qa,
            "_get_run_env_tool",
            lambda: (lambda *a, **kw: {"ok": True, "results": []}),
        )
        monkeypatch.setattr(kernel_qa, "fuji_core", _FakeFujiRaise)

        resp = kernel_qa.handle_knowledge_qa(
            q="日本の首都",
            ctx=_mk_ctx(),
            req_id="req-k3",
            telos_score=0.5,
        )

        assert resp["decision_status"] == "deny"
        assert resp["fuji"]["status"] == "deny"
        assert resp["fuji"]["decision_status"] == "deny"
        assert resp["fuji"]["risk"] == 1.0
        assert "FUJI_INTERNAL_ERROR" in resp["fuji"]["violations"]
        assert resp["fuji"]["meta"]["fuji_internal_error"] is True
        assert resp["fuji"]["meta"]["exception_type"] == "RuntimeError"
        # gate block mirrors the deny verdict.
        assert resp["gate"]["decision_status"] == "deny"
        assert resp["gate"]["risk"] == pytest.approx(1.0)
        assert resp["rejection_reason"].startswith("fuji_internal_error:")


# ============================================================
# Module public surface / backward-compat aliases
# ============================================================


class TestPublicSurface:
    def test_underscore_aliases_resolve_to_public_functions(self):
        assert kernel_qa._detect_simple_qa is kernel_qa.detect_simple_qa
        assert kernel_qa._handle_simple_qa is kernel_qa.handle_simple_qa
        assert kernel_qa._detect_knowledge_qa is kernel_qa.detect_knowledge_qa
        assert kernel_qa._handle_knowledge_qa is kernel_qa.handle_knowledge_qa

    def test_all_lists_expected_public_names(self):
        exported = set(kernel_qa.__all__)
        expected = {
            "detect_simple_qa",
            "handle_simple_qa",
            "format_simple_qa_summary",
            "detect_knowledge_qa",
            "handle_knowledge_qa",
            "SIMPLE_QA_PATTERNS",
            "AGI_BLOCK_KEYWORDS",
        }
        assert expected.issubset(exported)
