# veritas_os/tests/test_pipeline_submodules_coverage.py
# -*- coding: utf-8 -*-
"""
Coverage tests for new pipeline submodule files.

Targets uncovered branches in:
- pipeline_helpers.py
- pipeline_web_adapter.py
- pipeline_contracts.py
- pipeline_critique.py
- pipeline_evidence.py
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from veritas_os.core import pipeline_helpers as ph
from veritas_os.core import pipeline_web_adapter as pwa
from veritas_os.core import pipeline_contracts as pc
from veritas_os.core import pipeline_critique as pcrit
from veritas_os.core import pipeline_evidence as pev


# =========================================================
# pipeline_helpers: _as_str
# =========================================================

class TestAsStr:
    def test_none_returns_empty(self):
        assert ph._as_str(None) == ""

    def test_normal_string(self):
        assert ph._as_str("hello") == "hello"

    def test_long_string_truncated(self):
        s = "x" * 3000
        result = ph._as_str(s, limit=100)
        assert len(result) == 100

    def test_object_whose_str_raises(self):
        class Bad:
            def __str__(self):
                raise RuntimeError("no str")
        result = ph._as_str(Bad())
        assert isinstance(result, str)
        assert len(result) > 0  # repr(x) was used

    def test_int_converts(self):
        assert ph._as_str(42) == "42"


# =========================================================
# pipeline_helpers: _norm_severity
# =========================================================

class TestNormSeverity:
    def test_high_variants(self):
        assert ph._norm_severity("high") == "high"
        assert ph._norm_severity("h") == "high"
        assert ph._norm_severity("critical") == "high"
        assert ph._norm_severity("CRIT") == "high"

    def test_low_variants(self):
        assert ph._norm_severity("low") == "low"
        assert ph._norm_severity("L") == "low"

    def test_default_med(self):
        assert ph._norm_severity("medium") == "med"
        assert ph._norm_severity("anything") == "med"

    def test_exception_returns_med(self):
        class Bad:
            def __str__(self):
                raise RuntimeError("no str")
        assert ph._norm_severity(Bad()) == "med"


# =========================================================
# pipeline_helpers: _to_bool_local
# =========================================================

class TestToBoolLocal:
    def test_bool_passthrough(self):
        assert ph._to_bool_local(True) is True
        assert ph._to_bool_local(False) is False

    def test_none_is_false(self):
        assert ph._to_bool_local(None) is False

    def test_int_nonzero(self):
        assert ph._to_bool_local(1) is True
        assert ph._to_bool_local(0) is False

    def test_float(self):
        assert ph._to_bool_local(0.5) is True
        assert ph._to_bool_local(0.0) is False

    def test_truthy_strings(self):
        assert ph._to_bool_local("true") is True
        assert ph._to_bool_local("1") is True
        assert ph._to_bool_local("yes") is True
        assert ph._to_bool_local("y") is True
        assert ph._to_bool_local("on") is True

    def test_falsy_strings(self):
        assert ph._to_bool_local("false") is False
        assert ph._to_bool_local("0") is False
        assert ph._to_bool_local("random") is False

    def test_str_exception_returns_false(self):
        class BadStr:
            def __str__(self):
                raise RuntimeError("bad")
        assert ph._to_bool_local(BadStr()) is False


# =========================================================
# pipeline_helpers: _set_int_metric / _set_bool_metric
# =========================================================

class TestSetMetrics:
    def test_set_int_metric_normal(self):
        extras: Dict[str, Any] = {}
        ph._set_int_metric(extras, "mem_hits", 5)
        assert extras["metrics"]["mem_hits"] == 5

    def test_set_int_metric_non_dict_metrics_replaced(self):
        extras: Dict[str, Any] = {"metrics": "broken"}
        ph._set_int_metric(extras, "mem_hits", 3)
        assert isinstance(extras["metrics"], dict)
        assert extras["metrics"]["mem_hits"] == 3

    def test_set_int_metric_bad_value_uses_default(self):
        extras: Dict[str, Any] = {}
        ph._set_int_metric(extras, "count", "not_an_int", default=99)
        assert extras["metrics"]["count"] == 99

    def test_set_bool_metric_normal(self):
        extras: Dict[str, Any] = {}
        ph._set_bool_metric(extras, "fast_mode", True)
        assert extras["metrics"]["fast_mode"] is True

    def test_set_bool_metric_non_dict_metrics_replaced(self):
        extras: Dict[str, Any] = {"metrics": 42}
        ph._set_bool_metric(extras, "fast_mode", False)
        assert isinstance(extras["metrics"], dict)

    def test_set_bool_metric_string_value(self):
        extras: Dict[str, Any] = {}
        ph._set_bool_metric(extras, "fast_mode", "true")
        assert extras["metrics"]["fast_mode"] is True


# =========================================================
# pipeline_helpers: _lazy_import
# =========================================================

class TestLazyImport:
    def test_successful_import(self):
        result = ph._lazy_import("json")
        import json
        assert result is json

    def test_import_with_attr(self):
        result = ph._lazy_import("json", "dumps")
        import json
        assert result is json.dumps

    def test_failed_import_returns_none(self):
        result = ph._lazy_import("nonexistent_module_xyz_abc")
        assert result is None

    def test_failed_import_with_attr_returns_none(self):
        result = ph._lazy_import("nonexistent_module_xyz_abc", "some_attr")
        assert result is None


# =========================================================
# pipeline_helpers: _extract_rejection
# =========================================================

class TestExtractRejection:
    def test_no_fuji_key(self):
        assert ph._extract_rejection({}) is None

    def test_fuji_not_dict(self):
        assert ph._extract_rejection({"fuji": "not a dict"}) is None

    def test_no_rejection_key(self):
        assert ph._extract_rejection({"fuji": {}}) is None

    def test_rejection_not_dict(self):
        assert ph._extract_rejection({"fuji": {"rejection": "bad"}}) is None

    def test_rejection_status_not_rejected(self):
        payload = {"fuji": {"rejection": {"status": "APPROVED", "reason": "ok"}}}
        assert ph._extract_rejection(payload) is None

    def test_rejection_status_rejected(self):
        payload = {"fuji": {"rejection": {"status": "REJECTED", "reason": "unsafe"}}}
        result = ph._extract_rejection(payload)
        assert result is not None
        assert result["status"] == "REJECTED"

    def test_non_dict_payload(self):
        assert ph._extract_rejection("not a dict") is None


# =========================================================
# pipeline_helpers: _summarize_last_output
# =========================================================

class TestSummarizeLastOutput:
    def test_normal(self):
        payload = {"chosen": {"title": "A"}, "planner": {"steps": []}}
        plan = {"id": "p1"}
        result = ph._summarize_last_output(payload, plan)
        assert result["chosen"] == {"title": "A"}
        assert result["plan"] == {"id": "p1"}

    def test_non_dict_payload(self):
        result = ph._summarize_last_output("bad", {})
        assert result["chosen"] == {}
        assert result["planner"] == {}

    def test_non_dict_chosen(self):
        result = ph._summarize_last_output({"chosen": "string"}, {})
        assert result["chosen"] == {}


# =========================================================
# pipeline_helpers: _query_is_step1_hint
# =========================================================

class TestQueryIsStep1Hint:
    def test_step1_keyword(self):
        assert ph._query_is_step1_hint("step1 analysis") is True
        assert ph._query_is_step1_hint("step 1 review") is True

    def test_inventory_keyword(self):
        assert ph._query_is_step1_hint("inventory audit") is True

    def test_audit_keyword(self):
        assert ph._query_is_step1_hint("full audit") is True

    def test_japanese_keywords(self):
        assert ph._query_is_step1_hint("棚卸しを行う") is True
        assert ph._query_is_step1_hint("現状の棚卸整理") is True

    def test_no_match(self):
        assert ph._query_is_step1_hint("just a regular query") is False

    def test_none_input(self):
        assert ph._query_is_step1_hint(None) is False

    def test_exception_returns_false(self):
        class Bad:
            def lower(self):
                raise RuntimeError("broken")
            def __add__(self, other):
                return self
            def __contains__(self, item):
                raise RuntimeError("broken")
        assert ph._query_is_step1_hint(Bad()) is False


# =========================================================
# pipeline_helpers: _has_step1_minimum_evidence
# =========================================================

class TestHasStep1MinimumEvidence:
    def test_not_a_list(self):
        assert ph._has_step1_minimum_evidence("not a list") is False
        assert ph._has_step1_minimum_evidence(None) is False

    def test_empty_list(self):
        assert ph._has_step1_minimum_evidence([]) is False

    def test_non_dict_items_ignored(self):
        assert ph._has_step1_minimum_evidence(["string", 42]) is False

    def test_has_inventory_only(self):
        evs = [{"kind": "inventory", "title": "", "uri": "", "snippet": ""}]
        assert ph._has_step1_minimum_evidence(evs) is False

    def test_has_known_issues_only(self):
        evs = [{"kind": "known_issues", "title": "", "uri": "", "snippet": ""}]
        assert ph._has_step1_minimum_evidence(evs) is False

    def test_has_both(self):
        evs = [
            {"kind": "inventory", "title": "", "uri": "", "snippet": ""},
            {"kind": "known_issues", "title": "", "uri": "", "snippet": ""},
        ]
        assert ph._has_step1_minimum_evidence(evs) is True

    def test_match_via_title(self):
        evs = [
            {"kind": "", "title": "local:inventory", "uri": "", "snippet": ""},
            {"kind": "", "title": "local:known_issues", "uri": "", "snippet": ""},
        ]
        assert ph._has_step1_minimum_evidence(evs) is True

    def test_match_via_uri(self):
        evs = [
            {"kind": "", "title": "", "uri": "internal:evidence:inventory", "snippet": ""},
            {"kind": "", "title": "", "uri": "internal:evidence:known_issues", "snippet": ""},
        ]
        assert ph._has_step1_minimum_evidence(evs) is True

    def test_match_via_snippet_japanese(self):
        evs = [
            {"kind": "", "title": "", "uri": "", "snippet": "現状機能（棚卸し）の詳細"},
            {"kind": "", "title": "", "uri": "", "snippet": "既知の課題/注意 一覧"},
        ]
        assert ph._has_step1_minimum_evidence(evs) is True

    def test_returns_true_immediately_when_both_found(self):
        evs = [
            {"kind": "inventory"},
            {"kind": "known_issues"},
            {"kind": "extra"},
        ]
        assert ph._has_step1_minimum_evidence(evs) is True


# =========================================================
# pipeline_web_adapter: _extract_web_results
# =========================================================

class TestExtractWebResults:
    def test_none_returns_empty(self):
        assert pwa._extract_web_results(None) == []

    def test_list_returns_itself(self):
        lst = [{"title": "a"}]
        assert pwa._extract_web_results(lst) is lst

    def test_non_dict_non_list_returns_empty(self):
        assert pwa._extract_web_results("string") == []
        assert pwa._extract_web_results(42) == []

    def test_top_level_results_key(self):
        ws = {"results": [{"id": "1"}]}
        assert pwa._extract_web_results(ws) == [{"id": "1"}]

    def test_top_level_items_key(self):
        ws = {"items": [{"id": "2"}]}
        assert pwa._extract_web_results(ws) == [{"id": "2"}]

    def test_top_level_data_key(self):
        ws = {"data": [{"id": "3"}]}
        assert pwa._extract_web_results(ws) == [{"id": "3"}]

    def test_top_level_hits_key(self):
        ws = {"hits": [{"id": "4"}]}
        assert pwa._extract_web_results(ws) == [{"id": "4"}]

    def test_nested_dict_results(self):
        # 2nd pass: value is dict containing "results"
        ws = {"results": {"results": [{"id": "nested"}]}}
        result = pwa._extract_web_results(ws)
        assert result == [{"id": "nested"}]

    def test_nested_dict_items(self):
        ws = {"results": {"items": [{"id": "ni"}]}}
        result = pwa._extract_web_results(ws)
        assert result == [{"id": "ni"}]

    def test_third_pass_arbitrary_key(self):
        # 3rd pass: arbitrary top-level key -> dict -> list
        ws = {"search": {"results": [{"id": "3p"}]}}
        result = pwa._extract_web_results(ws)
        assert result == [{"id": "3p"}]

    def test_third_pass_deeply_nested(self):
        # 3rd pass: arbitrary key -> dict -> dict -> list
        ws = {"outer": {"inner": {"hits": [{"id": "deep"}]}}}
        result = pwa._extract_web_results(ws)
        assert result == [{"id": "deep"}]

    def test_no_list_found_returns_empty(self):
        ws = {"meta": {"count": 0}}
        assert pwa._extract_web_results(ws) == []

    def test_exception_returns_empty(self):
        class BadIter:
            def get(self, key, default=None):
                raise RuntimeError("broken get")
            def items(self):
                raise RuntimeError("broken items")
            def __iter__(self):
                raise RuntimeError("broken iter")
        ws = BadIter()
        assert pwa._extract_web_results(ws) == []


# =========================================================
# pipeline_contracts: _ensure_full_contract
# =========================================================

class TestEnsureFullContract:
    def test_non_dict_extras_returns_early(self):
        # Should not crash; returns without modifying
        pc._ensure_full_contract("not a dict", fast_mode_default=False, context_obj={})

    def test_replaces_non_dict_metrics(self):
        extras: Dict[str, Any] = {"metrics": "broken"}
        pc._ensure_full_contract(extras, fast_mode_default=False, context_obj={})
        assert isinstance(extras["metrics"], dict)

    def test_replaces_non_dict_env_tools(self):
        extras: Dict[str, Any] = {"env_tools": 42}
        pc._ensure_full_contract(extras, fast_mode_default=False, context_obj={})
        assert isinstance(extras["env_tools"], dict)

    def test_replaces_non_dict_memory_meta(self):
        extras: Dict[str, Any] = {"memory_meta": "broken"}
        pc._ensure_full_contract(extras, fast_mode_default=False, context_obj={})
        assert isinstance(extras["memory_meta"], dict)

    def test_stage_latency_initialized(self):
        extras: Dict[str, Any] = {}
        pc._ensure_full_contract(extras, fast_mode_default=False, context_obj={})
        sl = extras["metrics"]["stage_latency"]
        for stage in ("retrieval", "web", "llm", "gate", "persist"):
            assert stage in sl
            assert sl[stage] == 0

    def test_stage_latency_with_values(self):
        extras: Dict[str, Any] = {"metrics": {"stage_latency": {"retrieval": 10, "web": 5}}}
        pc._ensure_full_contract(extras, fast_mode_default=False, context_obj={})
        sl = extras["metrics"]["stage_latency"]
        assert sl["retrieval"] == 10
        assert sl["web"] == 5
        assert "llm" in sl

    def test_stage_latency_exception_path(self):
        class BadStageLatency(dict):
            def get(self, key, default=None):
                if key == "retrieval":
                    raise RuntimeError("broken")
                return default
        extras: Dict[str, Any] = {"metrics": {"stage_latency": BadStageLatency()}}
        pc._ensure_full_contract(extras, fast_mode_default=False, context_obj={})
        assert "stage_latency" in extras["metrics"]

    def test_memory_meta_context_merge(self):
        ctx = {"user_id": "u1", "fast": False}
        extras: Dict[str, Any] = {"memory_meta": {}}
        pc._ensure_full_contract(extras, fast_mode_default=True, context_obj=ctx)
        assert extras["memory_meta"]["context"]["user_id"] == "u1"
        assert "fast" in extras["memory_meta"]["context"]

    def test_existing_context_preserved(self):
        extras: Dict[str, Any] = {"memory_meta": {"context": {"existing": "value"}}}
        pc._ensure_full_contract(extras, fast_mode_default=False, context_obj={"new": "data"})
        assert extras["memory_meta"]["context"]["existing"] == "value"
        assert extras["memory_meta"]["context"]["new"] == "data"

    def test_query_filled_when_empty(self):
        extras: Dict[str, Any] = {}
        pc._ensure_full_contract(
            extras, fast_mode_default=False, context_obj={}, query_str="my query"
        )
        assert extras["memory_meta"]["query"] == "my query"

    def test_query_not_overwritten_when_exists(self):
        extras: Dict[str, Any] = {"memory_meta": {"query": "existing"}}
        pc._ensure_full_contract(
            extras, fast_mode_default=False, context_obj={}, query_str="new query"
        )
        assert extras["memory_meta"]["query"] == "existing"

    def test_fast_mode_set(self):
        extras: Dict[str, Any] = {}
        pc._ensure_full_contract(extras, fast_mode_default=True, context_obj={})
        assert extras["fast_mode"] is True
        assert extras["metrics"]["fast_mode"] is True


# =========================================================
# pipeline_contracts: _deep_merge_dict
# =========================================================

class TestDeepMergeDict:
    def test_basic_merge(self):
        dst = {"a": 1}
        src = {"b": 2}
        result = pc._deep_merge_dict(dst, src)
        assert result == {"a": 1, "b": 2}

    def test_nested_dict_merge(self):
        dst = {"metrics": {"hits": 1}}
        src = {"metrics": {"misses": 2}}
        pc._deep_merge_dict(dst, src)
        assert dst["metrics"] == {"hits": 1, "misses": 2}

    def test_non_dict_src_returns_dst(self):
        dst = {"a": 1}
        result = pc._deep_merge_dict(dst, "not a dict")
        assert result == {"a": 1}

    def test_non_dict_dst_returns_dst(self):
        dst = "not a dict"
        result = pc._deep_merge_dict(dst, {"b": 2})
        assert result == "not a dict"

    def test_overwrite_non_dict_value(self):
        dst = {"a": 1}
        src = {"a": {"nested": True}}
        pc._deep_merge_dict(dst, src)
        assert dst["a"] == {"nested": True}


# =========================================================
# pipeline_contracts: _merge_extras_preserving_contract
# =========================================================

class TestMergeExtrasPreservingContract:
    def test_non_dict_base_extras(self):
        result = pc._merge_extras_preserving_contract(
            "not a dict", {"key": "val"}, fast_mode_default=False, context_obj={}
        )
        assert isinstance(result, dict)

    def test_non_dict_incoming_extras(self):
        base = {"fast_mode": True}
        result = pc._merge_extras_preserving_contract(
            base, "not a dict", fast_mode_default=False, context_obj={}
        )
        assert isinstance(result, dict)

    def test_metrics_preserved_when_overwritten_by_non_dict(self):
        base = {"metrics": {"mem_hits": 5}}
        incoming = {"metrics": "broken"}
        result = pc._merge_extras_preserving_contract(
            base, incoming, fast_mode_default=False, context_obj={}
        )
        assert isinstance(result["metrics"], dict)

    def test_memory_meta_preserved_when_overwritten(self):
        base = {"memory_meta": {"query": "existing"}}
        incoming = {"memory_meta": "broken"}
        result = pc._merge_extras_preserving_contract(
            base, incoming, fast_mode_default=False, context_obj={}
        )
        assert isinstance(result["memory_meta"], dict)

    def test_normal_merge(self):
        base = {"fast_mode": False, "metrics": {"mem_hits": 1}}
        incoming = {"metrics": {"web_hits": 2}}
        result = pc._merge_extras_preserving_contract(
            base, incoming, fast_mode_default=False, context_obj={}
        )
        assert result["metrics"]["mem_hits"] == 1
        assert result["metrics"]["web_hits"] == 2


# =========================================================
# pipeline_critique: _pad_findings
# =========================================================

class TestPadFindings:
    def test_empty_list_padded_to_min(self):
        result = pcrit._pad_findings([], min_items=3)
        assert len(result) >= 3
        for f in result:
            assert isinstance(f, dict)
            assert "severity" in f
            assert "message" in f

    def test_non_dict_list_items(self):
        result = pcrit._pad_findings(["string item", 42], min_items=3)
        assert len(result) >= 3
        assert result[0]["code"] == "CRITIQUE_TEXT"

    def test_dict_with_non_dict_details(self):
        findings = [{"severity": "high", "message": "msg", "details": "not a dict"}]
        result = pcrit._pad_findings(findings, min_items=1)
        assert isinstance(result[0]["details"], dict)
        assert "raw" in result[0]["details"]

    def test_dict_with_fix(self):
        findings = [{"message": "test", "fix": "do something"}]
        result = pcrit._pad_findings(findings, min_items=1)
        assert isinstance(result[0]["fix"], str)

    def test_dict_input_single(self):
        finding = {"severity": "high", "message": "test", "code": "T001"}
        result = pcrit._pad_findings(finding, min_items=3)
        assert len(result) >= 3
        assert result[0]["code"] == "T001"

    def test_string_input(self):
        result = pcrit._pad_findings("raw text finding", min_items=3)
        assert len(result) >= 3
        assert result[0]["code"] == "CRITIQUE_TEXT"

    def test_none_input_padded(self):
        result = pcrit._pad_findings(None, min_items=3)
        assert len(result) == 3

    def test_uses_issue_field_as_message(self):
        findings = [{"issue": "something wrong", "severity": "low"}]
        result = pcrit._pad_findings(findings, min_items=1)
        assert result[0]["message"] == "something wrong"

    def test_uses_msg_field_as_message(self):
        findings = [{"msg": "fallback msg"}]
        result = pcrit._pad_findings(findings, min_items=1)
        assert result[0]["message"] == "fallback msg"


# =========================================================
# pipeline_critique: _critique_fallback
# =========================================================

class TestCritiqueFallback:
    def test_basic_fallback(self):
        result = pcrit._critique_fallback(reason="test", query="my query")
        assert result["ok"] is False
        assert result["mode"] == "fallback"
        assert len(result["findings"]) >= 3
        assert result["query"] == "my query"

    def test_chosen_dict(self):
        chosen = {"title": "Option A"}
        result = pcrit._critique_fallback(reason="missing", chosen=chosen)
        assert result["chosen_title"] == "Option A"

    def test_chosen_dict_name_fallback(self):
        chosen = {"name": "Option B"}
        result = pcrit._critique_fallback(reason="missing", chosen=chosen)
        assert result["chosen_title"] == "Option B"

    def test_chosen_string(self):
        result = pcrit._critique_fallback(reason="missing", chosen="plain string")
        assert result["chosen_title"] == "plain string"

    def test_no_chosen(self):
        result = pcrit._critique_fallback(reason="missing")
        assert result["chosen_title"] == ""

    def test_has_timestamp(self):
        result = pcrit._critique_fallback(reason="test")
        assert "ts" in result
        assert isinstance(result["ts"], str)


# =========================================================
# pipeline_critique: _chosen_to_option
# =========================================================

class TestChosenToOption:
    def test_dict_with_title(self):
        opt = pcrit._chosen_to_option({"title": "My Title", "risk": 0.3})
        assert opt["title"] == "My Title"
        assert opt["risk"] == 0.3

    def test_dict_uses_name_fallback(self):
        opt = pcrit._chosen_to_option({"name": "Alt Name"})
        assert opt["title"] == "Alt Name"

    def test_dict_uses_chosen_fallback(self):
        opt = pcrit._chosen_to_option({"chosen": "Chosen Value"})
        assert opt["title"] == "Chosen Value"

    def test_dict_with_score_fields(self):
        opt = pcrit._chosen_to_option({
            "title": "T",
            "score": {"risk": 0.8, "value": 0.9, "feasibility": 0.7}
        })
        assert opt["risk"] == 0.8
        assert opt["value"] == 0.9
        assert opt["feasibility"] == 0.7

    def test_dict_direct_fields_take_precedence_over_score(self):
        opt = pcrit._chosen_to_option({
            "title": "T",
            "risk": 0.5,
            "score": {"risk": 0.8}
        })
        assert opt["risk"] == 0.5

    def test_string_chosen(self):
        opt = pcrit._chosen_to_option("some string")
        assert opt["title"] == "some string"

    def test_none_chosen(self):
        opt = pcrit._chosen_to_option(None)
        assert opt["title"] == "chosen"

    def test_title_truncated_to_120(self):
        opt = pcrit._chosen_to_option({"title": "x" * 200})
        assert len(opt["title"]) == 120


# =========================================================
# pipeline_critique: _run_critique_best_effort
# =========================================================

class TestRunCritiqueBestEffort:
    def test_missing_module_returns_fallback(self):
        with patch("veritas_os.core.pipeline_critique._lazy_import", return_value=None):
            result = asyncio.run(
                pcrit._run_critique_best_effort(
                    query="test",
                    chosen={"title": "T"},
                    evidence=[],
                    debate={},
                    context={},
                    user_id="u1",
                )
            )
        assert result["ok"] is False
        assert result["mode"] == "fallback"

    def test_analyze_dict_called(self):
        mock_mod = MagicMock()
        mock_mod.analyze_dict = MagicMock(return_value={
            "ok": True,
            "findings": [
                {"severity": "med", "message": "m1", "code": "C1"},
                {"severity": "med", "message": "m2", "code": "C2"},
                {"severity": "med", "message": "m3", "code": "C3"},
            ],
            "summary": "ok",
        })
        mock_mod.analyze = None

        with patch("veritas_os.core.pipeline_critique._lazy_import", return_value=mock_mod):
            result = asyncio.run(
                pcrit._run_critique_best_effort(
                    query="test",
                    chosen={"title": "T"},
                    evidence=[],
                    debate={},
                    context={},
                    user_id="u1",
                )
            )
        assert result["ok"] is True
        assert len(result["findings"]) >= 3

    def test_analyze_list_called_when_no_dict(self):
        mock_mod = MagicMock()
        del mock_mod.analyze_dict
        mock_mod.analyze = MagicMock(return_value=[
            {"issue": "i1", "severity": "high"},
            {"issue": "i2", "severity": "med"},
            {"issue": "i3", "severity": "low"},
        ])

        with patch("veritas_os.core.pipeline_critique._lazy_import", return_value=mock_mod):
            result = asyncio.run(
                pcrit._run_critique_best_effort(
                    query="test",
                    chosen={"title": "T"},
                    evidence=[],
                    debate={},
                    context={},
                    user_id="u1",
                )
            )
        assert len(result["findings"]) >= 3

    def test_exception_returns_fallback(self):
        mock_mod = MagicMock()
        mock_mod.analyze_dict = MagicMock(side_effect=RuntimeError("crash"))

        with patch("veritas_os.core.pipeline_critique._lazy_import", return_value=mock_mod):
            result = asyncio.run(
                pcrit._run_critique_best_effort(
                    query="test",
                    chosen={"title": "T"},
                    evidence=[],
                    debate={},
                    context={},
                    user_id="u1",
                )
            )
        assert result["mode"] == "fallback"

    def test_none_result_returns_fallback(self):
        # analyze_dict returns None → _normalize_critique_payload(None) → {} → fallback
        mock_mod = MagicMock()
        mock_mod.analyze_dict = MagicMock(return_value=None)

        with patch("veritas_os.core.pipeline_critique._lazy_import", return_value=mock_mod):
            result = asyncio.run(
                pcrit._run_critique_best_effort(
                    query="test",
                    chosen={"title": "T"},
                    evidence=[],
                    debate={},
                    context={},
                    user_id="u1",
                )
            )
        assert result["mode"] == "fallback"


# =========================================================
# pipeline_evidence: _norm_evidence_item edge cases
# =========================================================

class TestNormEvidenceItemEdgeCases:
    def test_null_uri_stays_none(self):
        ev = {"source": "web", "uri": None, "confidence": 0.8}
        result = pev._norm_evidence_item(ev)
        assert result is not None
        assert result["uri"] is None

    def test_uri_with_bad_str(self):
        class BadUri:
            def __str__(self):
                raise RuntimeError("bad uri")
        ev = {"source": "web", "uri": BadUri(), "confidence": 0.5}
        result = pev._norm_evidence_item(ev)
        # Either returns None (outer exception) or uses repr
        assert result is None or isinstance(result["uri"], str)

    def test_confidence_clamped_high(self):
        ev = {"confidence": 99.0}
        result = pev._norm_evidence_item(ev)
        assert result is not None
        assert result["confidence"] == 1.0

    def test_confidence_clamped_low(self):
        ev = {"confidence": -5.0}
        result = pev._norm_evidence_item(ev)
        assert result is not None
        assert result["confidence"] == 0.0

    def test_snippet_with_bad_str(self):
        class BadSnippet:
            def __str__(self):
                raise RuntimeError("bad snippet")
        ev = {"snippet": BadSnippet(), "confidence": 0.5}
        result = pev._norm_evidence_item(ev)
        # snippet uses repr() fallback
        assert result is not None
        assert isinstance(result["snippet"], str)

    def test_weight_to_confidence_with_weight_none(self):
        ev = {"weight": None}
        result = pev._norm_evidence_item(ev)
        assert result is not None
        assert result["confidence"] == 0.7  # default

    def test_kind_field_used_for_title_and_uri(self):
        ev = {"kind": "episodic"}
        result = pev._norm_evidence_item(ev)
        assert result is not None
        assert "episodic" in result.get("title", "")
        assert "episodic" in result.get("uri", "")


# =========================================================
# pipeline_evidence: _dedupe_evidence edge cases
# =========================================================

class TestDedupeEvidenceEdgeCases:
    def test_non_dict_items_skipped(self):
        evs = [
            {"source": "a", "uri": "u1", "title": "t1", "snippet": "s1"},
            "not a dict",
            {"source": "b", "uri": "u2", "title": "t2", "snippet": "s2"},
        ]
        result = pev._dedupe_evidence(evs)
        assert len(result) == 2

    def test_duplicates_removed(self):
        ev = {"source": "a", "uri": "u1", "title": "t1", "snippet": "s1"}
        result = pev._dedupe_evidence([ev, dict(ev), ev])
        assert len(result) == 1

    def test_empty_list(self):
        assert pev._dedupe_evidence([]) == []
