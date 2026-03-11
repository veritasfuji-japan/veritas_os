# -*- coding: utf-8 -*-
"""
Tests for pipeline split review fixes:

1. PipelineContext._should_run_web field (was dynamically set via type: ignore)
2. _warn consolidation in pipeline_helpers.py
3. stage_web_search dead code removal
4. pipeline_inputs.py deferred import removal (inline fallbacks)
"""
from __future__ import annotations

import logging
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest

from veritas_os.core.pipeline_types import PipelineContext


# =========================================================
# Fix 1: PipelineContext._should_run_web field
# =========================================================


class TestPipelineContextShouldRunWeb:
    """_should_run_web is now a declared field on PipelineContext."""

    def test_default_false(self) -> None:
        ctx = PipelineContext()
        assert ctx._should_run_web is False

    def test_set_true(self) -> None:
        ctx = PipelineContext()
        ctx._should_run_web = True
        assert ctx._should_run_web is True

    def test_init_kwarg(self) -> None:
        ctx = PipelineContext(_should_run_web=True)
        assert ctx._should_run_web is True

    def test_no_type_ignore_needed(self) -> None:
        """Setting _should_run_web should work without type: ignore."""
        ctx = PipelineContext()
        ctx._should_run_web = True
        assert hasattr(ctx, "_should_run_web")


# =========================================================
# Fix 2: _warn consolidation
# =========================================================


class TestWarnConsolidation:
    """_warn is defined once in pipeline_helpers and imported in sub-modules."""

    def test_warn_in_helpers(self) -> None:
        from veritas_os.core.pipeline_helpers import _warn
        assert callable(_warn)

    def test_warn_info_prefix(self, caplog: pytest.LogCaptureFixture) -> None:
        from veritas_os.core.pipeline_helpers import _warn
        with caplog.at_level(logging.INFO, logger="veritas_os.core.pipeline_helpers"):
            _warn("[INFO] helpers test")
        assert "[INFO] helpers test" in caplog.text

    def test_warn_error_prefix(self, caplog: pytest.LogCaptureFixture) -> None:
        from veritas_os.core.pipeline_helpers import _warn
        with caplog.at_level(logging.ERROR, logger="veritas_os.core.pipeline_helpers"):
            _warn("[ERROR] helpers error")
        assert "[ERROR] helpers error" in caplog.text

    def test_warn_warning_default(self, caplog: pytest.LogCaptureFixture) -> None:
        from veritas_os.core.pipeline_helpers import _warn
        with caplog.at_level(logging.WARNING, logger="veritas_os.core.pipeline_helpers"):
            _warn("generic warning")
        assert "generic warning" in caplog.text

    def test_submodules_import_from_helpers(self) -> None:
        """Sub-modules should import _warn from pipeline_helpers, not define their own."""
        import veritas_os.core.pipeline_execute as pe
        import veritas_os.core.pipeline_policy as pp
        import veritas_os.core.pipeline_persist as ppr
        import veritas_os.core.pipeline_response as pr
        import veritas_os.core.pipeline_inputs as pi
        from veritas_os.core.pipeline_helpers import _warn as canonical_warn

        # pipeline_execute, pipeline_policy, pipeline_persist, pipeline_response
        # should all use the canonical _warn from pipeline_helpers
        assert pe._warn is canonical_warn
        assert pp._warn is canonical_warn
        assert ppr._warn is canonical_warn
        assert pr._warn is canonical_warn

        # pipeline_inputs imports _warn directly from pipeline_helpers
        assert pi._warn is canonical_warn


# =========================================================
# Fix 3: stage_web_search dead code removed
# =========================================================


class TestWebSearchDeadCodeRemoved:
    """The sync stage_web_search stub should not exist anymore."""

    def test_no_sync_stage_web_search(self) -> None:
        import veritas_os.core.pipeline_retrieval as pr
        assert not hasattr(pr, "stage_web_search")

    def test_async_still_exists(self) -> None:
        from veritas_os.core.pipeline_retrieval import stage_web_search_async
        assert callable(stage_web_search_async)


# =========================================================
# Fix 4: pipeline_inputs.py inline fallbacks
# =========================================================


class TestPipelineInputsNoCircularImport:
    """normalize_pipeline_inputs should work without deferred imports from pipeline.py."""

    def test_without_injected_to_dict_fn(self) -> None:
        """When _to_dict_fn is None, inline fallback should work."""
        from veritas_os.core.pipeline_inputs import normalize_pipeline_inputs

        class DummyReq:
            def model_dump(self) -> Dict[str, Any]:
                return {"query": "test", "context": {}}

        class DummyRequest:
            query_params: Dict[str, Any] = {}

        ctx = normalize_pipeline_inputs(
            DummyReq(),
            DummyRequest(),
            _to_dict_fn=None,
            _get_request_params=lambda r: {},
        )
        assert ctx.query == "test"

    def test_without_injected_get_request_params(self) -> None:
        """When _get_request_params is None, inline fallback should work."""
        from veritas_os.core.pipeline_inputs import normalize_pipeline_inputs

        class DummyReq:
            def model_dump(self) -> Dict[str, Any]:
                return {"query": "test2", "context": {}}

        class DummyRequest:
            query_params: Dict[str, Any] = {}

        ctx = normalize_pipeline_inputs(
            DummyReq(),
            DummyRequest(),
            _to_dict_fn=lambda o: o if isinstance(o, dict) else {},
            _get_request_params=None,
        )
        assert ctx.query == "test2"

    def test_both_none_fallbacks(self) -> None:
        """Both _to_dict_fn and _get_request_params as None should use inline fallbacks."""
        from veritas_os.core.pipeline_inputs import normalize_pipeline_inputs

        class DummyReq:
            def model_dump(self) -> Dict[str, Any]:
                return {"query": "fallback test", "context": {}}

        class DummyRequest:
            query_params: Dict[str, Any] = {}

        ctx = normalize_pipeline_inputs(
            DummyReq(),
            DummyRequest(),
            _to_dict_fn=None,
            _get_request_params=None,
        )
        assert ctx.query == "fallback test"

    def test_inline_to_dict_handles_dict(self) -> None:
        """Inline _to_dict_fn fallback should handle plain dict input."""
        from veritas_os.core.pipeline_inputs import normalize_pipeline_inputs

        class DummyRequest:
            query_params: Dict[str, Any] = {}

        ctx = normalize_pipeline_inputs(
            {"query": "raw dict", "context": {}},
            DummyRequest(),
            _to_dict_fn=None,
            _get_request_params=None,
        )
        assert ctx.query == "raw dict"

    def test_inline_get_request_params_reads_query_params(self) -> None:
        """Inline _get_request_params fallback should read request.query_params."""
        from veritas_os.core.pipeline_inputs import normalize_pipeline_inputs

        class DummyReq:
            def model_dump(self) -> Dict[str, Any]:
                return {"query": "params test", "context": {}}

        class DummyRequest:
            query_params = {"fast": "1"}

        ctx = normalize_pipeline_inputs(
            DummyReq(),
            DummyRequest(),
            _to_dict_fn=None,
            _get_request_params=None,
        )
        assert ctx.fast_mode is True
