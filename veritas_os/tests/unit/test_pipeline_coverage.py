# -*- coding: utf-8 -*-
"""Tests for low-coverage pipeline modules.

Targets:
  - pipeline_response: finalize_evidence edge cases, coerce fallback,
    continuation output, _build_response_layers
  - pipeline_gate: _load_memory_model branches, _save_valstats failures,
    _dedupe_alts edge cases, _allow_prob error paths
  - pipeline_contracts: _ensure_full_contract boundary inputs,
    _merge_extras_preserving_contract recovery, _deep_merge_dict depth guard
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


# =========================================================
# pipeline_response
# =========================================================


class TestFinalizeEvidenceEdgeCases:
    """finalize_evidence boundary and abnormal inputs."""

    def test_evidence_is_none(self) -> None:
        from veritas_os.core.pipeline.pipeline_response import finalize_evidence

        payload: Dict[str, Any] = {"evidence": None}
        finalize_evidence(payload, web_evidence=[], evidence_max=10)
        assert isinstance(payload["evidence"], list)

    def test_evidence_fallback_to_pipeline_evidence(self) -> None:
        from veritas_os.core.pipeline.pipeline_response import finalize_evidence

        ev = {"source": "web", "uri": "http://a.com", "title": "A", "snippet": "s"}
        payload: Dict[str, Any] = {"evidence": [], "_pipeline_evidence": [ev]}
        finalize_evidence(payload, web_evidence=[], evidence_max=10)
        assert len(payload["evidence"]) == 1

    def test_web_evidence_dedup(self) -> None:
        from veritas_os.core.pipeline.pipeline_response import finalize_evidence

        ev = {"source": "web", "uri": "http://a.com", "title": "T", "snippet": "s"}
        payload: Dict[str, Any] = {"evidence": [ev]}
        finalize_evidence(payload, web_evidence=[ev], evidence_max=10)
        # Duplicate should not be added
        assert len(payload["evidence"]) <= 1

    def test_evidence_cap(self) -> None:
        from veritas_os.core.pipeline.pipeline_response import finalize_evidence

        items = [
            {"source": f"s{i}", "uri": f"http://{i}.com", "title": f"T{i}", "snippet": f"s{i}"}
            for i in range(20)
        ]
        payload: Dict[str, Any] = {"evidence": items}
        finalize_evidence(payload, web_evidence=[], evidence_max=5)
        assert len(payload["evidence"]) <= 5

    def test_evidence_non_dict_items_skipped(self) -> None:
        from veritas_os.core.pipeline.pipeline_response import finalize_evidence

        payload: Dict[str, Any] = {"evidence": ["not_a_dict", 42, None]}
        finalize_evidence(payload, web_evidence=["also_not_dict"], evidence_max=10)
        assert isinstance(payload["evidence"], list)

    def test_evidence_iterable_non_list(self) -> None:
        """Non-list iterables (e.g. tuple) should be converted to list."""
        from veritas_os.core.pipeline.pipeline_response import finalize_evidence

        ev = {"source": "web", "uri": "http://a.com", "title": "T", "snippet": "s"}
        payload: Dict[str, Any] = {"evidence": (ev,)}
        finalize_evidence(payload, web_evidence=[], evidence_max=10)
        assert isinstance(payload["evidence"], list)

    def test_web_evidence_none(self) -> None:
        from veritas_os.core.pipeline.pipeline_response import finalize_evidence

        payload: Dict[str, Any] = {"evidence": []}
        finalize_evidence(payload, web_evidence=None, evidence_max=10)
        assert isinstance(payload["evidence"], list)

    def test_pipeline_evidence_non_list(self) -> None:
        from veritas_os.core.pipeline.pipeline_response import finalize_evidence

        payload: Dict[str, Any] = {"evidence": [], "_pipeline_evidence": "not_a_list"}
        finalize_evidence(payload, web_evidence=[], evidence_max=10)
        assert isinstance(payload["evidence"], list)


class TestCoerceToDecideResponse:
    """coerce_to_decide_response error paths."""

    def test_validation_error_returns_original(self) -> None:
        from veritas_os.core.pipeline.pipeline_response import coerce_to_decide_response

        mock_model = MagicMock()
        mock_model.model_validate.side_effect = ValueError("bad data")
        res = {"ok": True, "query": "test"}
        result = coerce_to_decide_response(res, DecideResponse=mock_model)
        assert result is res

    def test_type_error_returns_original(self) -> None:
        from veritas_os.core.pipeline.pipeline_response import coerce_to_decide_response

        mock_model = MagicMock()
        mock_model.model_validate.side_effect = TypeError("bad type")
        res = {"ok": True}
        result = coerce_to_decide_response(res, DecideResponse=mock_model)
        assert result is res

    def test_success_path(self) -> None:
        from veritas_os.core.pipeline.pipeline_response import coerce_to_decide_response

        mock_model = MagicMock()
        mock_instance = MagicMock()
        mock_instance.model_dump.return_value = {"ok": True, "coerced": True}
        mock_model.model_validate.return_value = mock_instance
        result = coerce_to_decide_response({"ok": True}, DecideResponse=mock_model)
        assert result == {"ok": True, "coerced": True}


class TestAssembleResponse:
    """assemble_response continuation output branches."""

    def _make_ctx(self, **kwargs: Any) -> Any:
        from veritas_os.core.pipeline.pipeline_types import PipelineContext

        return PipelineContext(**kwargs)

    def test_continuation_present(self) -> None:
        from veritas_os.core.pipeline.pipeline_response import assemble_response

        ctx = self._make_ctx(
            continuation_snapshot={"state": "LIVE"},
            continuation_receipt={"outcome": "DEGRADED"},
            continuation_enforcement_events=[{"type": "test"}],
            continuation_enforcement_halt=True,
        )
        result = assemble_response(
            ctx,
            load_persona_fn=lambda: {"name": "test"},
            plan={"steps": []},
        )
        assert "continuation" in result
        assert result["continuation"]["enforcement_halt"] is True
        assert result["continuation"]["enforcement_events"] == [{"type": "test"}]

    def test_continuation_absent(self) -> None:
        from veritas_os.core.pipeline.pipeline_response import assemble_response

        ctx = self._make_ctx()
        result = assemble_response(
            ctx,
            load_persona_fn=lambda: None,
            plan={},
        )
        assert "continuation" not in result

    def test_continuation_snapshot_only(self) -> None:
        """Only snapshot without receipt should not add continuation."""
        from veritas_os.core.pipeline.pipeline_response import assemble_response

        ctx = self._make_ctx(
            continuation_snapshot={"state": "LIVE"},
        )
        result = assemble_response(
            ctx,
            load_persona_fn=lambda: None,
            plan={},
        )
        assert "continuation" not in result

    def test_continuation_no_enforcement(self) -> None:
        """Continuation without enforcement events omits those keys."""
        from veritas_os.core.pipeline.pipeline_response import assemble_response

        ctx = self._make_ctx(
            continuation_snapshot={"state": "LIVE"},
            continuation_receipt={"outcome": "ok"},
        )
        result = assemble_response(
            ctx,
            load_persona_fn=lambda: None,
            plan={},
        )
        assert "continuation" in result
        assert "enforcement_events" not in result["continuation"]
        assert "enforcement_halt" not in result["continuation"]


class TestBuildResponseLayers:
    """_build_response_layers structure verification."""

    def test_layers_contain_expected_groups(self) -> None:
        from veritas_os.core.pipeline.pipeline_response import _build_response_layers
        from veritas_os.core.pipeline.pipeline_types import PipelineContext

        ctx = PipelineContext(query="test query", request_id="req-123")
        layers = _build_response_layers(
            ctx,
            load_persona_fn=lambda: {"name": "persona"},
            plan={"steps": ["a"]},
        )
        assert "core" in layers
        assert "audit_debug_internal" in layers
        assert "backward_compat" in layers
        assert layers["core"]["request_id"] == "req-123"
        assert layers["core"]["query"] == "test query"

    def test_backward_compat_options(self) -> None:
        from veritas_os.core.pipeline.pipeline_response import _build_response_layers
        from veritas_os.core.pipeline.pipeline_types import PipelineContext

        ctx = PipelineContext(alternatives=[{"title": "alt1"}])
        layers = _build_response_layers(
            ctx,
            load_persona_fn=lambda: None,
            plan={},
        )
        assert layers["backward_compat"]["options"] == [{"title": "alt1"}]


# =========================================================
# pipeline_gate
# =========================================================


class TestAllowProb:
    """_allow_prob edge cases."""

    def test_default_predict_returns_half(self) -> None:
        from veritas_os.core.pipeline.pipeline_gate import _default_predict_gate_label

        result = _default_predict_gate_label("anything")
        assert result == {"allow": 0.5}

    def test_allow_prob_normal(self) -> None:
        from veritas_os.core.pipeline.pipeline_gate import _allow_prob

        with patch(
            "veritas_os.core.pipeline.pipeline_gate.predict_gate_label",
            return_value={"allow": 0.85},
        ):
            result = _allow_prob("test text")
            assert abs(result - 0.85) < 1e-6

    def test_allow_prob_missing_key(self) -> None:
        from veritas_os.core.pipeline.pipeline_gate import _allow_prob

        with patch(
            "veritas_os.core.pipeline.pipeline_gate.predict_gate_label",
            return_value={},
        ):
            assert _allow_prob("test") == 0.0

    def test_allow_prob_invalid_value(self) -> None:
        from veritas_os.core.pipeline.pipeline_gate import _allow_prob

        with patch(
            "veritas_os.core.pipeline.pipeline_gate.predict_gate_label",
            return_value={"allow": "not_a_number"},
        ):
            assert _allow_prob("test") == 0.0

    def test_allow_prob_none_value(self) -> None:
        from veritas_os.core.pipeline.pipeline_gate import _allow_prob

        with patch(
            "veritas_os.core.pipeline.pipeline_gate.predict_gate_label",
            return_value={"allow": None},
        ):
            assert _allow_prob("test") == 0.0


class TestLoadValstats:
    """_load_valstats file I/O edge cases."""

    def test_nonexistent_file(self) -> None:
        from veritas_os.core.pipeline.pipeline_gate import _load_valstats

        result = _load_valstats(Path("/nonexistent/path/stats.json"))
        assert result == {"ema": 0.5, "alpha": 0.2, "n": 0, "history": []}

    def test_valid_json(self, tmp_path: Path) -> None:
        from veritas_os.core.pipeline.pipeline_gate import _load_valstats

        data = {"ema": 0.7, "alpha": 0.3, "n": 5, "history": [1, 2]}
        f = tmp_path / "stats.json"
        f.write_text(json.dumps(data))
        result = _load_valstats(f)
        assert result["ema"] == 0.7

    def test_invalid_json(self, tmp_path: Path) -> None:
        from veritas_os.core.pipeline.pipeline_gate import _load_valstats

        f = tmp_path / "bad.json"
        f.write_text("{invalid json")
        result = _load_valstats(f)
        assert result == {"ema": 0.5, "alpha": 0.2, "n": 0, "history": []}

    def test_json_non_dict(self, tmp_path: Path) -> None:
        from veritas_os.core.pipeline.pipeline_gate import _load_valstats

        f = tmp_path / "array.json"
        f.write_text("[1, 2, 3]")
        result = _load_valstats(f)
        assert result == {"ema": 0.5, "alpha": 0.2, "n": 0, "history": []}


class TestSaveValstats:
    """_save_valstats edge cases."""

    def test_save_creates_file(self, tmp_path: Path) -> None:
        from veritas_os.core.pipeline.pipeline_gate import _save_valstats

        f = tmp_path / "subdir" / "stats.json"
        data = {"ema": 0.6, "alpha": 0.2, "n": 1, "history": [0.6]}
        _save_valstats(data, f)
        assert f.exists()
        loaded = json.loads(f.read_text())
        assert loaded["ema"] == 0.6

    def test_save_with_atomic_io(self, tmp_path: Path) -> None:
        from veritas_os.core.pipeline.pipeline_gate import _save_valstats

        f = tmp_path / "atomic.json"
        mock_writer = MagicMock()
        data = {"ema": 0.5}
        _save_valstats(data, f, _HAS_ATOMIC_IO=True, _atomic_write_json=mock_writer)
        mock_writer.assert_called_once_with(f, data, indent=2)

    def test_save_oserror_does_not_raise(self, tmp_path: Path) -> None:
        from veritas_os.core.pipeline.pipeline_gate import _save_valstats

        # Writing to a path that doesn't exist AND can't be created
        f = Path("/proc/nonexistent/impossible/stats.json")
        data = {"ema": 0.5}
        # Should not raise
        _save_valstats(data, f)


class TestDedupeAlts:
    """_dedupe_alts and _dedupe_alts_fallback edge cases."""

    def test_empty_list(self) -> None:
        from veritas_os.core.pipeline.pipeline_gate import _dedupe_alts_fallback

        assert _dedupe_alts_fallback([]) == []

    def test_none_input(self) -> None:
        from veritas_os.core.pipeline.pipeline_gate import _dedupe_alts_fallback

        assert _dedupe_alts_fallback(None) == []  # type: ignore[arg-type]

    def test_non_dict_items_filtered(self) -> None:
        from veritas_os.core.pipeline.pipeline_gate import _dedupe_alts_fallback

        result = _dedupe_alts_fallback(["not_a_dict", 42, None, {"title": "ok"}])
        assert len(result) == 1
        assert result[0]["title"] == "ok"

    def test_duplicate_removal(self) -> None:
        from veritas_os.core.pipeline.pipeline_gate import _dedupe_alts_fallback

        alts = [
            {"title": "A", "description": "D"},
            {"title": "A", "description": "D"},
            {"title": "B", "description": "E"},
        ]
        result = _dedupe_alts_fallback(alts)
        assert len(result) == 2

    def test_dedupe_alts_with_kernel_helper(self) -> None:
        from veritas_os.core.pipeline.pipeline_gate import _dedupe_alts

        mock_core = MagicMock()
        mock_core._dedupe_alts.return_value = [{"title": "from_kernel"}]
        result = _dedupe_alts([{"title": "A"}], veritas_core=mock_core)
        assert result == [{"title": "from_kernel"}]

    def test_dedupe_alts_kernel_returns_non_list(self) -> None:
        from veritas_os.core.pipeline.pipeline_gate import _dedupe_alts

        mock_core = MagicMock()
        mock_core._dedupe_alts.return_value = "not_a_list"
        result = _dedupe_alts([{"title": "A", "description": "D"}], veritas_core=mock_core)
        assert len(result) == 1  # Falls back to _dedupe_alts_fallback

    def test_dedupe_alts_kernel_raises(self) -> None:
        from veritas_os.core.pipeline.pipeline_gate import _dedupe_alts

        mock_core = MagicMock()
        mock_core._dedupe_alts.side_effect = RuntimeError("kernel error")
        result = _dedupe_alts([{"title": "A", "description": "D"}], veritas_core=mock_core)
        assert len(result) == 1  # Falls back to _dedupe_alts_fallback

    def test_dedupe_alts_no_core(self) -> None:
        from veritas_os.core.pipeline.pipeline_gate import _dedupe_alts

        result = _dedupe_alts([{"title": "A", "description": "D"}])
        assert len(result) == 1


class TestMemModelPath:
    """_mem_model_path edge cases."""

    def test_import_fails(self) -> None:
        from veritas_os.core.pipeline.pipeline_gate import _mem_model_path

        with patch.dict("sys.modules", {"veritas_os.core.models": None}):
            result = _mem_model_path()
            # Should return empty string on import failure
            assert isinstance(result, str)


# =========================================================
# pipeline_contracts
# =========================================================


class TestEnsureFullContract:
    """_ensure_full_contract boundary and abnormal inputs."""

    def test_non_dict_extras_noop(self) -> None:
        from veritas_os.core.pipeline.pipeline_contracts import _ensure_full_contract

        extras = "not_a_dict"
        _ensure_full_contract(extras, fast_mode_default=False, context_obj={})  # type: ignore[arg-type]
        # Non-dict input is unchanged (early return, no mutation)
        assert extras == "not_a_dict"

    def test_metrics_not_dict_reset(self) -> None:
        from veritas_os.core.pipeline.pipeline_contracts import _ensure_full_contract

        extras: Dict[str, Any] = {"metrics": "corrupted"}
        _ensure_full_contract(extras, fast_mode_default=False, context_obj={})
        assert isinstance(extras["metrics"], dict)

    def test_env_tools_not_dict_reset(self) -> None:
        from veritas_os.core.pipeline.pipeline_contracts import _ensure_full_contract

        extras: Dict[str, Any] = {"env_tools": "corrupted"}
        _ensure_full_contract(extras, fast_mode_default=False, context_obj={})
        assert isinstance(extras["env_tools"], dict)

    def test_memory_meta_not_dict_reset(self) -> None:
        from veritas_os.core.pipeline.pipeline_contracts import _ensure_full_contract

        extras: Dict[str, Any] = {"memory_meta": 42}
        _ensure_full_contract(extras, fast_mode_default=False, context_obj={})
        assert isinstance(extras["memory_meta"], dict)

    def test_stage_latency_invalid_values(self) -> None:
        from veritas_os.core.pipeline.pipeline_contracts import _ensure_full_contract

        extras: Dict[str, Any] = {
            "metrics": {"stage_latency": {"retrieval": "bad", "web": None}},
        }
        _ensure_full_contract(extras, fast_mode_default=False, context_obj={})
        sl = extras["metrics"]["stage_latency"]
        assert sl["retrieval"] == 0
        assert sl["web"] == 0
        for stage in ("llm", "gate", "persist"):
            assert stage in sl

    def test_stage_latency_not_dict(self) -> None:
        from veritas_os.core.pipeline.pipeline_contracts import _ensure_full_contract

        extras: Dict[str, Any] = {"metrics": {"stage_latency": "not_dict"}}
        _ensure_full_contract(extras, fast_mode_default=False, context_obj={})
        assert isinstance(extras["metrics"]["stage_latency"], dict)

    def test_context_obj_not_dict(self) -> None:
        from veritas_os.core.pipeline.pipeline_contracts import _ensure_full_contract

        extras: Dict[str, Any] = {}
        _ensure_full_contract(extras, fast_mode_default=True, context_obj="bad")  # type: ignore[arg-type]
        assert isinstance(extras["memory_meta"]["context"], dict)

    def test_memory_meta_context_merge(self) -> None:
        from veritas_os.core.pipeline.pipeline_contracts import _ensure_full_contract

        extras: Dict[str, Any] = {
            "memory_meta": {"context": {"existing": "value"}},
        }
        _ensure_full_contract(
            extras,
            fast_mode_default=False,
            context_obj={"new_key": "new_val", "existing": "should_not_overwrite"},
        )
        ctx = extras["memory_meta"]["context"]
        assert ctx["existing"] == "value"  # setdefault preserves existing
        assert ctx["new_key"] == "new_val"  # new key added
        assert "fast" in ctx

    def test_query_str_fills_empty(self) -> None:
        from veritas_os.core.pipeline.pipeline_contracts import _ensure_full_contract

        extras: Dict[str, Any] = {"memory_meta": {}}
        _ensure_full_contract(
            extras, fast_mode_default=False, context_obj={}, query_str="hello"
        )
        assert extras["memory_meta"]["query"] == "hello"

    def test_query_str_does_not_overwrite(self) -> None:
        from veritas_os.core.pipeline.pipeline_contracts import _ensure_full_contract

        extras: Dict[str, Any] = {"memory_meta": {"query": "original"}}
        _ensure_full_contract(
            extras, fast_mode_default=False, context_obj={}, query_str="new"
        )
        assert extras["memory_meta"]["query"] == "original"

    def test_fast_mode_default_true(self) -> None:
        from veritas_os.core.pipeline.pipeline_contracts import _ensure_full_contract

        extras: Dict[str, Any] = {}
        _ensure_full_contract(extras, fast_mode_default=True, context_obj={})
        assert extras["fast_mode"] is True

    def test_mem_evidence_count_invalid(self) -> None:
        from veritas_os.core.pipeline.pipeline_contracts import _ensure_full_contract

        extras: Dict[str, Any] = {"metrics": {"mem_evidence_count": "invalid"}}
        _ensure_full_contract(extras, fast_mode_default=False, context_obj={})
        assert extras["metrics"]["mem_evidence_count"] == 0


class TestEnsureMetricsContract:
    """_ensure_metrics_contract minimal invariants."""

    def test_empty_extras(self) -> None:
        from veritas_os.core.pipeline.pipeline_contracts import _ensure_metrics_contract

        extras: Dict[str, Any] = {}
        _ensure_metrics_contract(extras)
        assert extras["metrics"]["mem_hits"] == 0
        assert extras["metrics"]["memory_evidence_count"] == 0
        assert extras["metrics"]["web_hits"] == 0
        assert extras["metrics"]["web_evidence_count"] == 0
        assert extras["metrics"]["fast_mode"] is False
        assert extras["fast_mode"] is False

    def test_preserves_existing_values(self) -> None:
        from veritas_os.core.pipeline.pipeline_contracts import _ensure_metrics_contract

        extras: Dict[str, Any] = {"metrics": {"mem_hits": 5}}
        _ensure_metrics_contract(extras)
        assert extras["metrics"]["mem_hits"] == 5


class TestDeepMergeDict:
    """_deep_merge_dict recursive merge with depth guard."""

    def test_basic_merge(self) -> None:
        from veritas_os.core.pipeline.pipeline_contracts import _deep_merge_dict

        dst = {"a": 1, "b": {"c": 2}}
        src = {"b": {"d": 3}, "e": 4}
        result = _deep_merge_dict(dst, src)
        assert result["a"] == 1
        assert result["b"]["c"] == 2
        assert result["b"]["d"] == 3
        assert result["e"] == 4

    def test_non_dict_inputs(self) -> None:
        from veritas_os.core.pipeline.pipeline_contracts import _deep_merge_dict

        result = _deep_merge_dict("not_dict", {"a": 1})  # type: ignore[arg-type]
        assert result == "not_dict"

    def test_depth_guard(self) -> None:
        from veritas_os.core.pipeline.pipeline_contracts import (
            _deep_merge_dict,
            _DEEP_MERGE_MAX_DEPTH,
        )

        # At max depth, src value overwrites without recursion
        dst: Dict[str, Any] = {"k": {"inner": "dst"}}
        src: Dict[str, Any] = {"k": {"inner": "src"}}
        result = _deep_merge_dict(dst, src, _depth=_DEEP_MERGE_MAX_DEPTH)
        assert result["k"] == {"inner": "src"}  # Overwritten, not merged

    def test_src_value_overwrites_non_dict(self) -> None:
        from veritas_os.core.pipeline.pipeline_contracts import _deep_merge_dict

        dst = {"a": "string_value"}
        src = {"a": {"nested": True}}
        result = _deep_merge_dict(dst, src)
        assert result["a"] == {"nested": True}


class TestMergeExtrasPreservingContract:
    """_merge_extras_preserving_contract recovery and edge cases."""

    def test_incoming_non_dict(self) -> None:
        from veritas_os.core.pipeline.pipeline_contracts import (
            _merge_extras_preserving_contract,
        )

        base = {"fast_mode": True}
        result = _merge_extras_preserving_contract(
            base, "not_dict", fast_mode_default=False, context_obj={}  # type: ignore[arg-type]
        )
        assert isinstance(result, dict)
        assert "metrics" in result  # Contract should be ensured

    def test_base_non_dict(self) -> None:
        from veritas_os.core.pipeline.pipeline_contracts import (
            _merge_extras_preserving_contract,
        )

        result = _merge_extras_preserving_contract(
            "not_dict", {"a": 1}, fast_mode_default=False, context_obj={}  # type: ignore[arg-type]
        )
        assert isinstance(result, dict)

    def test_metrics_overwritten_by_non_dict_recovers(self) -> None:
        from veritas_os.core.pipeline.pipeline_contracts import (
            _merge_extras_preserving_contract,
        )

        base: Dict[str, Any] = {"metrics": {"mem_hits": 5}}
        incoming: Dict[str, Any] = {"metrics": "corrupted"}
        result = _merge_extras_preserving_contract(
            base, incoming, fast_mode_default=False, context_obj={}
        )
        assert isinstance(result["metrics"], dict)

    def test_memory_meta_overwritten_recovers(self) -> None:
        from veritas_os.core.pipeline.pipeline_contracts import (
            _merge_extras_preserving_contract,
        )

        base: Dict[str, Any] = {"memory_meta": {"context": {"old": True}}}
        incoming: Dict[str, Any] = {"memory_meta": 42}
        result = _merge_extras_preserving_contract(
            base, incoming, fast_mode_default=False, context_obj={"new": True}
        )
        assert isinstance(result["memory_meta"], dict)

    def test_preserves_fast_mode(self) -> None:
        from veritas_os.core.pipeline.pipeline_contracts import (
            _merge_extras_preserving_contract,
        )

        base: Dict[str, Any] = {"fast_mode": True}
        incoming: Dict[str, Any] = {}
        result = _merge_extras_preserving_contract(
            base, incoming, fast_mode_default=False, context_obj={}
        )
        assert result["fast_mode"] is True

    def test_normal_deep_merge(self) -> None:
        from veritas_os.core.pipeline.pipeline_contracts import (
            _merge_extras_preserving_contract,
        )

        base: Dict[str, Any] = {
            "metrics": {"mem_hits": 3},
            "env_tools": {"search": True},
        }
        incoming: Dict[str, Any] = {
            "metrics": {"web_hits": 2},
            "env_tools": {"github": True},
        }
        result = _merge_extras_preserving_contract(
            base, incoming, fast_mode_default=False, context_obj={}
        )
        assert result["metrics"]["mem_hits"] == 3
        assert result["metrics"]["web_hits"] == 2
        assert result["env_tools"]["search"] is True
        assert result["env_tools"]["github"] is True
