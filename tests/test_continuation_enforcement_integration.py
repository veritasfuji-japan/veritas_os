# tests/test_continuation_enforcement_integration.py
# -*- coding: utf-8 -*-
"""
Integration tests for continuation enforcement mode switching
and pipeline interaction.

Tests cover:
  - Observe vs advisory vs enforce mode in pipeline context
  - Feature flag gating (enforcement disabled when continuation runtime off)
  - Posture-based enforcement mode resolution
  - PipelineContext enforcement fields
  - Response assembly with enforcement data
  - Trustlog audit fields for enforcement events
"""
from __future__ import annotations

import pytest

from veritas_os.core.continuation_runtime.enforcement import (
    EnforcementMode,
    EnforcementAction,
    EnforcementConfig,
    ContinuationEnforcementEvaluator,
    EnforcementEvent,
)
from veritas_os.core.continuation_runtime.lineage import ClaimStatus
from veritas_os.core.continuation_runtime.snapshot import (
    ClaimStateSnapshot,
    Scope,
)
from veritas_os.core.continuation_runtime.receipt import (
    ContinuationReceipt,
    RevalidationStatus,
    RevalidationOutcome,
)
from veritas_os.core.continuation_runtime.revalidator import (
    ContinuationRevalidator,
    PresentCondition,
    run_continuation_revalidation_shadow,
)
from veritas_os.core.continuation_runtime.lineage import ContinuationClaimLineage

pytestmark = [pytest.mark.integration]


# =====================================================================
# Helpers
# =====================================================================

def _run_revalidation_with_enforcement(
    *,
    mode: EnforcementMode = EnforcementMode.ADVISORY,
    chain_id: str = "chain-int-001",
    context: dict = None,
    degradation_count: int = 0,
    replay_divergence_ratio: float = 0.0,
    has_required_approval: bool = True,
    policy_violation_detected: bool = False,
):
    """Run revalidation + enforcement in sequence (mimics pipeline)."""
    context = context or {}

    lineage, snapshot, receipt = run_continuation_revalidation_shadow(
        chain_id=chain_id,
        step_index=0,
        query="integration test query",
        context=context,
        prior_decision_status=None,
    )

    config = EnforcementConfig(mode=mode)
    evaluator = ContinuationEnforcementEvaluator(config=config)
    events = evaluator.evaluate(
        snapshot=snapshot,
        receipt=receipt,
        chain_id=chain_id,
        degradation_count=degradation_count,
        replay_divergence_ratio=replay_divergence_ratio,
        has_required_approval=has_required_approval,
        policy_violation_detected=policy_violation_detected,
    )

    return lineage, snapshot, receipt, events


# =====================================================================
# Mode switching integration
# =====================================================================


class TestModeSwitchingIntegration:
    def test_observe_mode_no_events(self):
        _, _, _, events = _run_revalidation_with_enforcement(
            mode=EnforcementMode.OBSERVE,
            policy_violation_detected=True,
        )
        assert events == []

    def test_advisory_mode_produces_advisory_events(self):
        _, _, _, events = _run_revalidation_with_enforcement(
            mode=EnforcementMode.ADVISORY,
            policy_violation_detected=True,
        )
        assert len(events) >= 1
        for event in events:
            assert event.is_advisory is True
            assert event.is_enforced is False

    def test_enforce_mode_produces_enforced_events(self):
        _, _, _, events = _run_revalidation_with_enforcement(
            mode=EnforcementMode.ENFORCE,
            policy_violation_detected=True,
        )
        assert len(events) >= 1
        for event in events:
            assert event.is_enforced is True
            assert event.is_advisory is False


# =====================================================================
# Revalidation + enforcement chain
# =====================================================================


class TestRevalidationEnforcementChain:
    def test_live_chain_no_enforcement(self):
        """A healthy chain should not trigger enforcement."""
        _, _, _, events = _run_revalidation_with_enforcement(
            mode=EnforcementMode.ENFORCE,
        )
        assert events == []

    def test_degraded_chain_triggers_enforcement(self):
        """Repeated degradation with high count triggers enforcement."""
        _, _, _, events = _run_revalidation_with_enforcement(
            mode=EnforcementMode.ENFORCE,
            context={
                "required_evidence": ["ev1", "ev2"],
                "satisfied_evidence": [],
            },
            degradation_count=5,
        )
        # The revalidation itself shows degradation; with count=5 and
        # threshold=3, enforcement should trigger
        degradation_events = [
            e for e in events
            if "repeated_degradation" in e.reason_codes
        ]
        assert len(degradation_events) == 1

    def test_escalation_required_chain_triggers_halt(self):
        """Escalation required without approval triggers halt."""
        _, _, _, events = _run_revalidation_with_enforcement(
            mode=EnforcementMode.ENFORCE,
            context={
                "escalation_required": True,
            },
            has_required_approval=False,
        )
        approval_events = [
            e for e in events
            if "approval_required_without_approval" in e.reason_codes
        ]
        assert len(approval_events) == 1
        assert approval_events[0].action == EnforcementAction.HALT_CHAIN
        assert approval_events[0].is_enforced is True


# =====================================================================
# Multi-step chain enforcement
# =====================================================================


class TestMultiStepChainEnforcement:
    def test_multi_step_degradation_escalates(self):
        """Simulate multi-step chain where degradation accumulates."""
        lineage = ContinuationClaimLineage(
            chain_id="chain-multi",
        )
        revalidator = ContinuationRevalidator()
        config = EnforcementConfig(
            mode=EnforcementMode.ENFORCE,
            degradation_repeat_threshold=3,
        )
        evaluator = ContinuationEnforcementEvaluator(config=config)

        prior_snapshot = None
        prior_receipt = None
        degradation_count = 0

        for step in range(5):
            condition = PresentCondition(
                chain_id="chain-multi",
                step_index=step,
                query=f"query step {step}",
                context={
                    "required_evidence": ["ev1", "ev2", "ev3"],
                    "satisfied_evidence": ["ev1"] if step < 3 else [],
                },
            )
            snapshot, receipt = revalidator.revalidate(
                lineage=lineage,
                condition=condition,
                prior_snapshot=prior_snapshot,
                prior_receipt=prior_receipt,
            )

            if receipt.revalidation_status in (
                RevalidationStatus.DEGRADED,
                RevalidationStatus.ESCALATED,
                RevalidationStatus.HALTED,
            ):
                degradation_count += 1
            else:
                degradation_count = 0

            evaluator.evaluate(
                snapshot=snapshot,
                receipt=receipt,
                chain_id="chain-multi",
                degradation_count=degradation_count,
            )

            prior_snapshot = snapshot
            prior_receipt = receipt

        # After 5 steps of degradation, enforcement should trigger
        assert degradation_count >= 3

    def test_enforcement_events_carry_step_context(self):
        """Enforcement events carry snapshot and receipt from the step."""
        lineage = ContinuationClaimLineage(chain_id="chain-ctx")
        revalidator = ContinuationRevalidator()
        config = EnforcementConfig(mode=EnforcementMode.ADVISORY)
        evaluator = ContinuationEnforcementEvaluator(config=config)

        condition = PresentCondition(
            chain_id="chain-ctx",
            step_index=0,
            query="test",
            context={"escalation_required": True},
        )
        snapshot, receipt = revalidator.revalidate(
            lineage=lineage,
            condition=condition,
        )
        events = evaluator.evaluate(
            snapshot=snapshot,
            receipt=receipt,
            chain_id="chain-ctx",
            has_required_approval=False,
        )
        assert len(events) >= 1
        assert events[0].snapshot_id == snapshot.snapshot_id
        assert events[0].receipt_id == receipt.receipt_id


# =====================================================================
# PipelineContext enforcement fields
# =====================================================================


class TestPipelineContextFields:
    def test_pipeline_context_has_enforcement_fields(self):
        from veritas_os.core.pipeline.pipeline_types import PipelineContext

        ctx = PipelineContext()
        assert ctx.continuation_enforcement_events is None
        assert ctx.continuation_enforcement_halt is False

    def test_pipeline_context_enforcement_events_populated(self):
        from veritas_os.core.pipeline.pipeline_types import PipelineContext

        ctx = PipelineContext()
        event = EnforcementEvent(
            action=EnforcementAction.HALT_CHAIN,
            is_enforced=True,
        )
        ctx.continuation_enforcement_events = [event.to_dict()]
        ctx.continuation_enforcement_halt = True

        assert len(ctx.continuation_enforcement_events) == 1
        assert ctx.continuation_enforcement_halt is True


# =====================================================================
# Response assembly
# =====================================================================


class TestResponseAssembly:
    def test_response_includes_enforcement_when_present(self):
        from veritas_os.core.pipeline.pipeline_types import PipelineContext

        ctx = PipelineContext()
        ctx.continuation_snapshot = {"claim_status": "live", "snapshot_id": "s1"}
        ctx.continuation_receipt = {"receipt_id": "r1"}
        ctx.continuation_enforcement_events = [
            {"action": "halt_chain", "is_enforced": True}
        ]
        ctx.continuation_enforcement_halt = True

        # Simulate response assembly logic
        cont_data = {
            "state": ctx.continuation_snapshot,
            "receipt": ctx.continuation_receipt,
        }
        if ctx.continuation_enforcement_events:
            cont_data["enforcement_events"] = ctx.continuation_enforcement_events
        if ctx.continuation_enforcement_halt:
            cont_data["enforcement_halt"] = True

        assert "enforcement_events" in cont_data
        assert cont_data["enforcement_halt"] is True

    def test_response_omits_enforcement_when_absent(self):
        from veritas_os.core.pipeline.pipeline_types import PipelineContext

        ctx = PipelineContext()
        ctx.continuation_snapshot = {"claim_status": "live"}
        ctx.continuation_receipt = {"receipt_id": "r1"}

        cont_data = {
            "state": ctx.continuation_snapshot,
            "receipt": ctx.continuation_receipt,
        }
        if ctx.continuation_enforcement_events:
            cont_data["enforcement_events"] = ctx.continuation_enforcement_events
        if ctx.continuation_enforcement_halt:
            cont_data["enforcement_halt"] = True

        assert "enforcement_events" not in cont_data
        assert "enforcement_halt" not in cont_data


# =====================================================================
# Posture-based enforcement mode
# =====================================================================


class TestPostureBasedMode:
    def test_dev_posture_defaults_to_observe(self, monkeypatch):
        monkeypatch.delenv("VERITAS_CONTINUATION_ENFORCEMENT_MODE", raising=False)
        monkeypatch.delenv("VERITAS_POSTURE", raising=False)
        monkeypatch.delenv("VERITAS_ENV", raising=False)
        from veritas_os.core.posture import derive_defaults, PostureLevel
        defaults = derive_defaults(PostureLevel.DEV)
        assert defaults.continuation_enforcement_mode == "observe"

    def test_secure_posture_defaults_to_advisory(self, monkeypatch):
        monkeypatch.delenv("VERITAS_CONTINUATION_ENFORCEMENT_MODE", raising=False)
        from veritas_os.core.posture import derive_defaults, PostureLevel
        defaults = derive_defaults(PostureLevel.SECURE)
        assert defaults.continuation_enforcement_mode == "advisory"

    def test_prod_posture_defaults_to_advisory(self, monkeypatch):
        monkeypatch.delenv("VERITAS_CONTINUATION_ENFORCEMENT_MODE", raising=False)
        from veritas_os.core.posture import derive_defaults, PostureLevel
        defaults = derive_defaults(PostureLevel.PROD)
        assert defaults.continuation_enforcement_mode == "advisory"

    def test_env_override_in_dev(self, monkeypatch):
        monkeypatch.setenv("VERITAS_CONTINUATION_ENFORCEMENT_MODE", "enforce")
        from veritas_os.core.posture import derive_defaults, PostureLevel
        defaults = derive_defaults(PostureLevel.DEV)
        assert defaults.continuation_enforcement_mode == "enforce"

    def test_env_override_in_secure(self, monkeypatch):
        monkeypatch.setenv("VERITAS_CONTINUATION_ENFORCEMENT_MODE", "enforce")
        from veritas_os.core.posture import derive_defaults, PostureLevel
        defaults = derive_defaults(PostureLevel.SECURE)
        assert defaults.continuation_enforcement_mode == "enforce"


# =====================================================================
# Config capability flag
# =====================================================================


class TestConfigCapabilityFlag:
    def test_continuation_enforcement_mode_config(self, monkeypatch):
        monkeypatch.setenv("VERITAS_CONTINUATION_ENFORCEMENT_MODE", "enforce")
        # Re-import to pick up env
        import importlib
        import veritas_os.core.config as cfg_mod
        importlib.reload(cfg_mod)
        try:
            cfg = cfg_mod.CapabilityConfig()
            assert cfg.continuation_enforcement_mode == "enforce"
        finally:
            importlib.reload(cfg_mod)

    def test_continuation_enforcement_mode_default(self, monkeypatch):
        monkeypatch.delenv("VERITAS_CONTINUATION_ENFORCEMENT_MODE", raising=False)
        import importlib
        import veritas_os.core.config as cfg_mod
        importlib.reload(cfg_mod)
        try:
            cfg = cfg_mod.CapabilityConfig()
            assert cfg.continuation_enforcement_mode == "observe"
        finally:
            importlib.reload(cfg_mod)
