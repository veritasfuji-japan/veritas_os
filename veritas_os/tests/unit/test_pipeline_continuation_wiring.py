# -*- coding: utf-8 -*-
"""Targeted wiring coverage for run_decide_pipeline continuation stages.

These tests intentionally stub unrelated pipeline stages.  Continuation
revalidation/enforcement already has dedicated behavior tests elsewhere; this
module proves that the public pipeline orchestrator wires the feature flag,
mode selection, event propagation, HALT flag, and best-effort failure boundary.
"""

from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace
from typing import Any

import pytest

pytestmark = pytest.mark.unit


class _Trace:
    @classmethod
    def start(cls, **_kwargs: Any) -> "_Trace":
        return cls()

    def stage(self, _name: str):
        return nullcontext()

    def finalize(self, **_kwargs: Any) -> None:
        return None


def _patch_pipeline_shell(monkeypatch):
    """Reduce run_decide_pipeline to its orchestration/wiring behavior."""
    from veritas_os.core import pipeline as pipeline_module
    from veritas_os.core.pipeline.pipeline_types import PipelineContext

    ctx = PipelineContext(
        request_id="req-continuation-wiring",
        user_id="user-1",
        query="continue governed action",
        body={"chain_id": "chain-1", "step_index": 2},
        context={},
        decision_status="allow",
    )

    monkeypatch.setattr(pipeline_module, "PipelineTraceSession", _Trace)
    monkeypatch.setattr(pipeline_module, "_check_required_modules", lambda: None)
    monkeypatch.setattr(
        pipeline_module,
        "normalize_pipeline_inputs",
        lambda *_args, **_kwargs: ctx,
    )
    monkeypatch.setattr(
        pipeline_module,
        "observe_pipeline_stage_duration",
        lambda *_args, **_kwargs: None,
    )

    sync_stage_names = (
        "stage_memory_retrieval",
        "stage_normalize_options",
        "stage_absorb_raw_results",
        "stage_fallback_alternatives",
        "stage_model_boost",
        "stage_debate_fn",
        "stage_fuji_precheck",
        "stage_value_core",
        "stage_gate_decision",
        "stage_value_learning_ema",
        "stage_compute_metrics",
        "stage_evidence_hardening",
    )
    for name in sync_stage_names:
        monkeypatch.setattr(
            pipeline_module,
            name,
            lambda *_args, **_kwargs: None,
        )

    async def _async_noop(*_args: Any, **_kwargs: Any) -> None:
        return None

    for name in (
        "stage_web_search_async",
        "stage_core_execute",
        "stage_critique_async",
    ):
        monkeypatch.setattr(pipeline_module, name, _async_noop)

    def _build_payload(current_ctx: PipelineContext) -> dict[str, Any]:
        return {
            "extras": {"metrics": {}},
            "_observed_continuation_snapshot": current_ctx.continuation_snapshot,
            "_observed_continuation_receipt": current_ctx.continuation_receipt,
            "_observed_continuation_events": current_ctx.continuation_enforcement_events,
            "_observed_continuation_halt": current_ctx.continuation_enforcement_halt,
        }

    monkeypatch.setattr(pipeline_module, "_build_decision_payload", _build_payload)
    monkeypatch.setattr(
        pipeline_module,
        "finalize_canonical_decision_artifact",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(
        pipeline_module,
        "require_stage_8_payload_without_canonical_artifact",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        pipeline_module,
        "_run_post_decision_persistence_phase",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        pipeline_module,
        "verify_canonical_decision_source_unchanged",
        lambda *_args, **_kwargs: None,
    )

    receipt = SimpleNamespace(
        model_dump=lambda **_kwargs: {"receipt": "test"},
    )
    monkeypatch.setattr(
        pipeline_module,
        "record_canonical_decision_trust_link",
        lambda *_args, **_kwargs: receipt,
    )
    monkeypatch.setattr(
        pipeline_module,
        "attach_canonical_decision_artifact",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        pipeline_module,
        "_persist_canonical_replay_source",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        pipeline_module,
        "set_degraded_subsystems",
        lambda *_args, **_kwargs: None,
    )

    return pipeline_module, ctx


def _install_revalidation(monkeypatch, *, raises: bool = False) -> None:
    from veritas_os.core.continuation_runtime import revalidator as revalidator_module

    if raises:
        def _raise(**_kwargs: Any):
            raise RuntimeError("continuation unavailable")

        monkeypatch.setattr(
            revalidator_module,
            "run_continuation_revalidation_shadow",
            _raise,
        )
        return

    snapshot = SimpleNamespace(
        claim_status=SimpleNamespace(value="live"),
        to_dict=lambda: {"snapshot_id": "snapshot-1", "claim_status": "live"},
    )
    receipt = SimpleNamespace(
        divergence_flag=False,
        to_dict=lambda: {"receipt_id": "receipt-1", "divergence_flag": False},
    )
    lineage = SimpleNamespace(chain_id="chain-1")

    monkeypatch.setattr(
        revalidator_module,
        "run_continuation_revalidation_shadow",
        lambda **_kwargs: (lineage, snapshot, receipt),
    )


def _set_continuation_config(monkeypatch, *, mode: str) -> None:
    from veritas_os.core import config as config_module

    monkeypatch.setattr(
        config_module.capability_cfg,
        "enable_continuation_runtime",
        True,
    )
    monkeypatch.setattr(
        config_module.capability_cfg,
        "continuation_enforcement_mode",
        mode,
    )


@pytest.mark.asyncio
async def test_pipeline_continuation_observe_wires_snapshot_without_events(
    monkeypatch,
) -> None:
    pipeline_module, _ctx = _patch_pipeline_shell(monkeypatch)
    _set_continuation_config(monkeypatch, mode="observe")
    _install_revalidation(monkeypatch)

    result = await pipeline_module.run_decide_pipeline(
        SimpleNamespace(request_id="req-1", user_id="user-1"),
        object(),
    )

    assert result["_observed_continuation_snapshot"]["snapshot_id"] == "snapshot-1"
    assert result["_observed_continuation_receipt"]["receipt_id"] == "receipt-1"
    assert result["_observed_continuation_events"] is None
    assert result["_observed_continuation_halt"] is False


@pytest.mark.asyncio
async def test_pipeline_continuation_advisory_records_event_without_halt(
    monkeypatch,
) -> None:
    pipeline_module, _ctx = _patch_pipeline_shell(monkeypatch)
    _set_continuation_config(monkeypatch, mode="advisory")
    _install_revalidation(monkeypatch)

    from veritas_os.core.continuation_runtime import enforcement as enforcement_module

    event = SimpleNamespace(
        action=enforcement_module.EnforcementAction.HALT_CHAIN,
        is_enforced=False,
        reasoning="advisory only",
        to_dict=lambda: {
            "action": "halt_chain",
            "is_enforced": False,
            "reasoning": "advisory only",
        },
    )

    class _Evaluator:
        def __init__(self, *, config):
            self.config = config

        def evaluate(self, **_kwargs: Any):
            return [event]

    monkeypatch.setattr(
        enforcement_module,
        "ContinuationEnforcementEvaluator",
        _Evaluator,
    )

    result = await pipeline_module.run_decide_pipeline(
        SimpleNamespace(request_id="req-2", user_id="user-1"),
        object(),
    )

    assert result["_observed_continuation_events"] == [
        {
            "action": "halt_chain",
            "is_enforced": False,
            "reasoning": "advisory only",
        }
    ]
    assert result["_observed_continuation_halt"] is False


@pytest.mark.asyncio
async def test_pipeline_continuation_enforce_propagates_halt_chain(
    monkeypatch,
) -> None:
    pipeline_module, _ctx = _patch_pipeline_shell(monkeypatch)
    _set_continuation_config(monkeypatch, mode="enforce")
    _install_revalidation(monkeypatch)

    from veritas_os.core.continuation_runtime import enforcement as enforcement_module

    event = SimpleNamespace(
        action=enforcement_module.EnforcementAction.HALT_CHAIN,
        is_enforced=True,
        reasoning="approval missing",
        to_dict=lambda: {
            "action": "halt_chain",
            "is_enforced": True,
            "reasoning": "approval missing",
        },
    )

    class _Evaluator:
        def __init__(self, *, config):
            self.config = config

        def evaluate(self, **_kwargs: Any):
            return [event]

    monkeypatch.setattr(
        enforcement_module,
        "ContinuationEnforcementEvaluator",
        _Evaluator,
    )

    result = await pipeline_module.run_decide_pipeline(
        SimpleNamespace(request_id="req-3", user_id="user-1"),
        object(),
    )

    assert result["_observed_continuation_events"][0]["is_enforced"] is True
    assert result["_observed_continuation_halt"] is True


@pytest.mark.asyncio
async def test_pipeline_continuation_failure_is_best_effort_and_observable(
    monkeypatch,
) -> None:
    pipeline_module, _ctx = _patch_pipeline_shell(monkeypatch)
    _set_continuation_config(monkeypatch, mode="observe")
    _install_revalidation(monkeypatch, raises=True)

    result = await pipeline_module.run_decide_pipeline(
        SimpleNamespace(request_id="req-4", user_id="user-1"),
        object(),
    )

    assert result["_observed_continuation_snapshot"] is None
    assert result["_observed_continuation_receipt"] is None
    assert result["_observed_continuation_events"] is None
    assert result["_observed_continuation_halt"] is False
    assert "continuation_shadow:RuntimeError" in result["extras"]["metrics"]["degraded_stages"]
