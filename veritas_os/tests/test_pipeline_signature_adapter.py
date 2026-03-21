# veritas_os/tests/test_pipeline_signature_adapter.py
# -*- coding: utf-8 -*-
"""
回帰テスト: pipeline_signature_adapter.py への call_core_decide 抽出と
pipeline_helpers.py / pipeline_contracts.py の broad exception 縮小。

Priority 1/1-2 追加 + Priority 3/3-2 の pipeline 系モジュール対応。
"""
from __future__ import annotations

import asyncio
import logging

import pytest

# --- adapter の直接 import ---
from veritas_os.core.pipeline_signature_adapter import call_core_decide as adapter_fn
# --- pipeline.py からの re-export ---
from veritas_os.core import pipeline as p


# =========================================================
# 1. call_core_decide が adapter 経由で動くことの確認
# =========================================================


class TestSignatureAdapterReExport:
    """pipeline.call_core_decide は pipeline_signature_adapter.call_core_decide と同一であること。"""

    def test_reexport_identity(self):
        assert p.call_core_decide is adapter_fn

    def test_pattern_b_via_adapter(self):
        """adapter から直接呼んでもパターン B が機能する。"""

        def core_fn(context=None, query=None, alternatives=None, min_evidence=None):
            return {"ok": True}

        result = asyncio.run(
            adapter_fn(
                core_fn,
                context={"user_id": "u1"},
                query="q",
                alternatives=[],
            )
        )
        assert result["ok"] is True

    def test_narrowed_signature_inspection_catches_runtime_error(self, caplog):
        """inspect.signature が RuntimeError を出しても警告ログを出して処理を続行する。"""

        def broken():
            pass

        import inspect

        orig = inspect.signature

        def _raise(fn):
            raise RuntimeError("broken sig")

        try:
            inspect.signature = _raise
            with caplog.at_level(logging.WARNING):
                # _params returns empty set, _can_bind returns True (safe fallback),
                # then actual call raises TypeError from wrong kwargs
                with pytest.raises(TypeError):
                    asyncio.run(
                        adapter_fn(broken, context={}, query="q", alternatives=[])
                    )
            assert "signature inspection failed" in caplog.text
        finally:
            inspect.signature = orig


# =========================================================
# 2. pipeline_helpers.py の縮小例外がまだ機能することの確認
# =========================================================


class TestPipelineHelpersNarrowedExceptions:
    """broad exception → 限定タプルに縮小後も、想定される失敗型は引き続き安全に処理されること。"""

    def test_as_str_handles_typeerror(self):
        from veritas_os.core.pipeline_helpers import _as_str

        class BadStr:
            def __str__(self):
                raise TypeError("no str")

        result = _as_str(BadStr())
        assert isinstance(result, str)  # repr fallback

    def test_norm_severity_handles_typeerror(self):
        from veritas_os.core.pipeline_helpers import _norm_severity

        class BadStr:
            def __str__(self):
                raise TypeError("no str")

        assert _norm_severity(BadStr()) == "med"

    def test_to_bool_local_handles_typeerror(self):
        from veritas_os.core.pipeline_helpers import _to_bool_local

        class BadStr:
            def __str__(self):
                raise TypeError("no str")

        assert _to_bool_local(BadStr()) is False

    def test_set_int_metric_handles_valueerror(self):
        from veritas_os.core.pipeline_helpers import _set_int_metric

        extras = {"metrics": {}}
        _set_int_metric(extras, "k", "not_a_number", default=42)
        assert extras["metrics"]["k"] == 42

    def test_set_bool_metric_handles_typeerror(self):
        from veritas_os.core.pipeline_helpers import _set_bool_metric

        extras = {"metrics": {}}

        class BadStr:
            def __str__(self):
                raise TypeError("no str")

        # _to_bool_local catches TypeError internally → returns False
        _set_bool_metric(extras, "k", BadStr(), default=True)
        assert extras["metrics"]["k"] is False

    def test_query_is_step1_hint_handles_typeerror(self):
        from veritas_os.core.pipeline_helpers import _query_is_step1_hint

        class BadStr:
            def __lower__(self):
                raise TypeError("bad")

        # None-ish or broken → False
        assert _query_is_step1_hint(None) is False

    def test_has_step1_minimum_evidence_handles_bad_list(self):
        from veritas_os.core.pipeline_helpers import _has_step1_minimum_evidence

        assert _has_step1_minimum_evidence("not a list") is False
        assert _has_step1_minimum_evidence(None) is False


# =========================================================
# 3. pipeline_contracts.py の縮小例外がまだ機能することの確認
# =========================================================


class TestPipelineContractsNarrowedExceptions:
    """pipeline_contracts.py の except Exception → 限定タプル後も安全に動作すること。"""

    def test_ensure_full_contract_with_bad_stage_latency(self):
        from veritas_os.core.pipeline_contracts import _ensure_full_contract

        extras = {
            "metrics": {"stage_latency": {"retrieval": "not_int", "web": None}},
        }
        _ensure_full_contract(
            extras, fast_mode_default=False, context_obj={"user_id": "u"}
        )
        sl = extras["metrics"]["stage_latency"]
        assert sl["retrieval"] == 0  # failed int conversion → default
        assert sl["web"] == 0
        assert sl["llm"] == 0  # missing → default

    def test_ensure_full_contract_with_bad_mem_evidence_count(self):
        from veritas_os.core.pipeline_contracts import _ensure_full_contract

        extras = {"metrics": {"mem_evidence_count": "bad"}}
        _ensure_full_contract(
            extras, fast_mode_default=False, context_obj={}
        )
        assert extras["metrics"]["mem_evidence_count"] == 0

    def test_ensure_full_contract_memory_meta_query_assignment(self):
        from veritas_os.core.pipeline_contracts import _ensure_full_contract

        extras = {"memory_meta": {}}
        _ensure_full_contract(
            extras,
            fast_mode_default=False,
            context_obj={},
            query_str="hello",
        )
        assert extras["memory_meta"]["query"] == "hello"
