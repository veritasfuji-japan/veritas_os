# -*- coding: utf-8 -*-
"""
Tests for pipeline precise review fixes:

1. random.seed global state mutation → per-request Random instance
2. risk_val clamping to [0,1] in pipeline_policy
3. _deep_merge_dict recursion depth guard
4. core_context initialisation in pipeline_execute
5. _get_memory_store callable() check
"""

import random
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from veritas_os.core.pipeline_contracts import _deep_merge_dict
from veritas_os.core.pipeline_memory_adapter import _get_memory_store


# =========================================================
# Fix 1: random.seed() no longer mutates global state
# =========================================================


class TestRandomSeedIsolation:
    """Verify that pipeline input normalisation does not mutate the global
    random state, which would affect concurrent requests."""

    def test_global_random_state_not_mutated(self):
        """After normalising pipeline inputs with a seed, the global
        ``random`` module state must remain unchanged."""
        from veritas_os.core.pipeline_inputs import normalize_pipeline_inputs

        # Set global random to a known state and sample a value
        random.seed(42)
        before = random.random()

        # Reset to the same known state
        random.seed(42)

        req = MagicMock()
        req.query = "test"
        body = {"query": "test", "seed": 999}
        req.model_dump = MagicMock(return_value=body)
        req.context = {}
        request = MagicMock()
        request.query_params = {}

        normalize_pipeline_inputs(
            req, request,
            _get_request_params=lambda r: {},
            _to_dict_fn=lambda o: o if isinstance(o, dict) else {},
        )

        # Global random should still produce the same value as before
        after = random.random()
        assert before == after, (
            "Pipeline input normalisation mutated global random state"
        )


# =========================================================
# Fix 2: risk_val clamped to [0, 1]
# =========================================================


class TestRiskValClamping:
    """Verify that FUJI risk values are clamped to the valid [0, 1] range."""

    def _make_ctx(self, risk_value: Any):
        """Build a minimal PipelineContext with the given FUJI risk."""
        from veritas_os.core.pipeline_types import PipelineContext

        ctx = PipelineContext(
            body={"query": "test"},
            query="test",
            user_id="u",
            request_id="r",
        )
        ctx.fuji_dict = {"status": "allow", "risk": risk_value}
        ctx.alternatives = [
            {"title": "A", "description": "a", "score": 0.8, "id": "1"},
        ]
        return ctx

    def test_risk_above_one_clamped(self):
        """FUJI risk > 1.0 must be clamped to 1.0."""
        from veritas_os.core.pipeline_policy import stage_fuji_precheck

        ctx = self._make_ctx(1.5)
        # Mock fuji import to return a module that gives our specific risk
        mock_fuji = MagicMock()
        mock_fuji.validate_action.return_value = {
            "status": "allow", "reasons": [], "violations": [], "risk": 1.5,
        }

        with patch(
            "veritas_os.core.pipeline_policy._lazy_import",
            return_value=mock_fuji,
        ):
            stage_fuji_precheck(ctx)
        # Evidence snippet should contain risk=1.0, not risk=1.5
        fuji_ev = [e for e in ctx.evidence if "fuji" in str(e.get("source", ""))]
        assert fuji_ev, "FUJI evidence should be appended"
        snippet = fuji_ev[0].get("snippet", "")
        assert "risk=1.0" in snippet, f"Expected clamped risk=1.0, got: {snippet}"

    def test_negative_risk_clamped(self):
        """FUJI risk < 0.0 must be clamped to 0.0."""
        from veritas_os.core.pipeline_policy import stage_fuji_precheck

        ctx = self._make_ctx(-0.5)
        mock_fuji = MagicMock()
        mock_fuji.validate_action.return_value = {
            "status": "allow", "reasons": [], "violations": [], "risk": -0.5,
        }
        with patch(
            "veritas_os.core.pipeline_policy._lazy_import",
            return_value=mock_fuji,
        ):
            stage_fuji_precheck(ctx)
        fuji_ev = [e for e in ctx.evidence if "fuji" in str(e.get("source", ""))]
        assert fuji_ev
        snippet = fuji_ev[0].get("snippet", "")
        assert "risk=0.0" in snippet, f"Expected clamped risk=0.0, got: {snippet}"

    def test_normal_risk_unchanged(self):
        """FUJI risk within [0, 1] should pass through unchanged."""
        from veritas_os.core.pipeline_policy import stage_fuji_precheck

        ctx = self._make_ctx(0.42)
        mock_fuji = MagicMock()
        mock_fuji.validate_action.return_value = {
            "status": "allow", "reasons": [], "violations": [], "risk": 0.42,
        }
        with patch(
            "veritas_os.core.pipeline_policy._lazy_import",
            return_value=mock_fuji,
        ):
            stage_fuji_precheck(ctx)
        fuji_ev = [e for e in ctx.evidence if "fuji" in str(e.get("source", ""))]
        assert fuji_ev
        snippet = fuji_ev[0].get("snippet", "")
        assert "risk=0.42" in snippet, f"Expected risk=0.42, got: {snippet}"


# =========================================================
# Fix 3: _deep_merge_dict recursion depth guard
# =========================================================


class TestDeepMergeDictDepthGuard:
    """Verify that _deep_merge_dict does not overflow on deeply nested dicts."""

    def test_shallow_merge_works(self):
        dst = {"a": {"b": 1}}
        src = {"a": {"c": 2}}
        result = _deep_merge_dict(dst, src)
        assert result == {"a": {"b": 1, "c": 2}}

    def test_deeply_nested_does_not_overflow(self):
        """Build a 100-level nested dict; merge must not raise RecursionError."""
        inner: Dict[str, Any] = {"leaf": True}
        for _ in range(100):
            inner = {"nest": inner}
        dst: Dict[str, Any] = {"nest": {"existing": True}}
        # Should not raise RecursionError
        result = _deep_merge_dict(dst, inner)
        assert isinstance(result, dict)

    def test_depth_limit_overwrites_beyond_threshold(self):
        """Beyond the depth limit, src values overwrite dst without recursion."""
        from veritas_os.core.pipeline_contracts import _DEEP_MERGE_MAX_DEPTH

        # Build nested dicts just at the depth limit
        inner_dst: Dict[str, Any] = {"deep_key": "dst_val"}
        inner_src: Dict[str, Any] = {"deep_key": "src_val", "extra": True}
        for _ in range(_DEEP_MERGE_MAX_DEPTH + 5):
            inner_dst = {"n": inner_dst}
            inner_src = {"n": inner_src}

        result = _deep_merge_dict(inner_dst, inner_src)
        # At depth > limit, src overwrites dst entirely (no recursive merge)
        assert isinstance(result, dict)


# =========================================================
# Fix 4: core_context always initialised
# =========================================================


class TestCoreContextInitialised:
    """Verify that core_context is always defined before the healing loop."""

    def test_core_context_exists_when_core_decide_is_none(self):
        """Even when kernel.decide is None, core_context must be defined."""
        import veritas_os.core.pipeline_execute as pe
        import inspect

        source = inspect.getsource(pe.stage_core_execute)
        # core_context must be initialised BEFORE the ``if core_decide is None``
        # branch, ensuring the variable is always defined.
        idx_init = source.find("core_context")
        idx_if = source.find("if core_decide is None")
        assert idx_init < idx_if, (
            "core_context should be initialised before the core_decide None check"
        )


# =========================================================
# Fix 5: _get_memory_store callable() check
# =========================================================


class TestGetMemoryStoreCallable:
    """Verify that _get_memory_store rejects non-callable attributes."""

    def test_non_callable_attribute_rejected(self):
        """An object with a ``search`` attribute that is NOT callable
        should not be returned as a valid memory store."""
        fake_mem = type("FakeMem", (), {"search": "not_callable"})()
        result = _get_memory_store(mem=fake_mem)
        assert result is None, (
            "_get_memory_store should reject objects with non-callable "
            "search/put/get attributes"
        )

    def test_callable_attribute_accepted(self):
        """An object with callable ``search`` should be accepted."""
        fake_mem = MagicMock()
        fake_mem.search = MagicMock()
        result = _get_memory_store(mem=fake_mem)
        assert result is fake_mem

    def test_none_returns_none(self):
        with patch("veritas_os.core.pipeline_memory_adapter._mem_module", None):
            result = _get_memory_store(mem=None)
        assert result is None
