# tests/test_continuation_integration.py
# -*- coding: utf-8 -*-
"""
Integration tests for Continuation Runtime phase-1.

Verifies:
  - Feature flag off → zero side-effect, zero response mutation
  - Feature flag on → continuation artifacts appended
  - gate.decision_status unchanged regardless of continuation state
  - FUJI output unchanged regardless of continuation state
  - Continuation revalidation runs pre-merit (before FUJI)
  - Snapshot and receipt are separate objects in response
"""
from __future__ import annotations

import os
import importlib
import pytest


# =====================================================================
# Feature flag off — complete invariance
# =====================================================================


class TestFeatureFlagOffInvariance:
    """When VERITAS_CAP_CONTINUATION_RUNTIME is off (default),
    the continuation runtime must be fully inert."""

    def test_flag_defaults_to_false(self):
        """Default is off — no env var needed."""
        from veritas_os.core.config import _parse_bool

        assert _parse_bool("VERITAS_CAP_CONTINUATION_RUNTIME", False) is False

    def test_pipeline_context_has_no_continuation_by_default(self):
        """PipelineContext continuation fields are None when flag off."""
        from veritas_os.core.pipeline_types import PipelineContext

        ctx = PipelineContext()
        assert ctx.continuation_snapshot is None
        assert ctx.continuation_receipt is None

    def test_response_omits_continuation_key_when_flag_off(self):
        """assemble_response must not include 'continuation' when off."""
        from veritas_os.core.pipeline_types import PipelineContext
        from veritas_os.core.pipeline_response import assemble_response

        ctx = PipelineContext(
            request_id="flag-off-test",
            query="test query",
            response_extras={
                "metrics": {},
                "memory_citations": [],
                "memory_used_count": 0,
            },
        )
        res = assemble_response(
            ctx,
            load_persona_fn=lambda: {"name": "test"},
            plan={"steps": [], "raw": None, "source": "fallback"},
        )

        assert "continuation" not in res

    def test_gate_decision_status_unchanged_when_flag_off(self):
        """gate.decision_status is exactly what PipelineContext provides."""
        from veritas_os.core.pipeline_types import PipelineContext
        from veritas_os.core.pipeline_response import assemble_response

        ctx = PipelineContext(
            request_id="gate-test",
            query="test",
            decision_status="allow",
            response_extras={
                "metrics": {},
                "memory_citations": [],
                "memory_used_count": 0,
            },
        )
        res = assemble_response(
            ctx,
            load_persona_fn=lambda: {"name": "test"},
            plan={"steps": [], "raw": None, "source": "fallback"},
        )

        assert res["gate"]["decision_status"] == "allow"
        assert res["decision_status"] == "allow"


# =====================================================================
# Feature flag on — continuation artifacts present
# =====================================================================


class TestFeatureFlagOnAddsContinuation:
    """When flag is on and continuation data is set on ctx,
    response includes continuation with state/receipt separation."""

    def _make_ctx_with_continuation(self, claim_status="live", divergence=False):
        from veritas_os.core.pipeline_types import PipelineContext

        return PipelineContext(
            request_id="flag-on-test",
            query="test",
            decision_status="allow",
            response_extras={
                "metrics": {},
                "memory_citations": [],
                "memory_used_count": 0,
            },
            continuation_snapshot={
                "snapshot_id": "s-1",
                "claim_lineage_id": "lin-1",
                "claim_status": claim_status,
                "law_version": "v0.1.0-shadow",
                "support_basis": {"authority": "chain:x", "policy": "default"},
                "scope": {"allowed_action_classes": ["query"]},
                "burden_state": {"threshold": 1.0, "current_level": 1.0},
                "headroom_state": {"remaining": 1.0},
            },
            continuation_receipt={
                "receipt_id": "r-1",
                "revalidation_status": "renewed" if not divergence else "degraded",
                "revalidation_outcome": "renewed" if not divergence else "degraded",
                "divergence_flag": divergence,
                "should_refuse_before_effect": False,
                "revalidation_reason_codes": [],
                "prior_decision_continuity_ref": None,
            },
        )

    def test_response_includes_continuation_block(self):
        from veritas_os.core.pipeline_response import assemble_response

        ctx = self._make_ctx_with_continuation()
        res = assemble_response(
            ctx,
            load_persona_fn=lambda: {"name": "test"},
            plan={"steps": [], "raw": None, "source": "fallback"},
        )

        assert "continuation" in res
        assert "state" in res["continuation"]
        assert "receipt" in res["continuation"]

    def test_state_and_receipt_are_separate_in_response(self):
        from veritas_os.core.pipeline_response import assemble_response

        ctx = self._make_ctx_with_continuation()
        res = assemble_response(
            ctx,
            load_persona_fn=lambda: {"name": "test"},
            plan={"steps": [], "raw": None, "source": "fallback"},
        )

        state = res["continuation"]["state"]
        receipt = res["continuation"]["receipt"]

        # State fields must NOT bleed into receipt
        assert "support_basis" not in receipt
        assert "burden_state" not in receipt

        # Receipt fields must NOT bleed into state
        assert "divergence_flag" not in state
        assert "revalidation_status" not in state

    def test_gate_decision_status_unchanged_when_flag_on(self):
        """gate.decision_status must remain exactly as ctx provides,
        regardless of continuation state."""
        from veritas_os.core.pipeline_response import assemble_response

        ctx = self._make_ctx_with_continuation(
            claim_status="revoked", divergence=True
        )
        res = assemble_response(
            ctx,
            load_persona_fn=lambda: {"name": "test"},
            plan={"steps": [], "raw": None, "source": "fallback"},
        )

        # Even with continuation revoked, gate.decision_status is untouched
        assert res["gate"]["decision_status"] == "allow"
        assert res["decision_status"] == "allow"

    def test_fuji_output_unchanged_when_continuation_present(self):
        """FUJI dict is exactly what ctx provides, unmodified."""
        from veritas_os.core.pipeline_types import PipelineContext
        from veritas_os.core.pipeline_response import assemble_response

        fuji_dict = {"status": "allow", "reasons": [], "violations": []}
        ctx = PipelineContext(
            request_id="fuji-test",
            query="test",
            fuji_dict=fuji_dict,
            decision_status="allow",
            response_extras={
                "metrics": {},
                "memory_citations": [],
                "memory_used_count": 0,
            },
            continuation_snapshot={
                "snapshot_id": "s-1",
                "claim_status": "revoked",
            },
            continuation_receipt={
                "receipt_id": "r-1",
                "divergence_flag": True,
            },
        )
        res = assemble_response(
            ctx,
            load_persona_fn=lambda: {"name": "test"},
            plan={"steps": [], "raw": None, "source": "fallback"},
        )

        assert res["fuji"] == fuji_dict


# =====================================================================
# Pre-merit revalidation evidence
# =====================================================================


class TestPreMeritRevalidation:
    """Verify that continuation revalidation runs before step-level
    merit evaluation and produces its own artifacts independently."""

    def test_revalidation_produces_snapshot_before_any_decision(self):
        """run_continuation_revalidation_shadow works without any
        prior_decision_status — proving it doesn't need step outcome."""
        from veritas_os.core.continuation_runtime.revalidator import (
            run_continuation_revalidation_shadow,
        )

        lineage, snap, rcpt = run_continuation_revalidation_shadow(
            chain_id="pre-merit-test",
            step_index=0,
            query="first step",
            context={},
            prior_decision_status=None,  # no prior step
        )

        assert snap.snapshot_id
        assert rcpt.receipt_id
        assert rcpt.prior_decision_continuity_ref is None

    def test_revalidation_does_not_read_or_modify_decision_status(self):
        """Revalidation result is independent of prior_decision_status value."""
        from veritas_os.core.continuation_runtime.revalidator import (
            run_continuation_revalidation_shadow,
        )

        # Same conditions, different prior_decision_status
        _, snap_allow, _ = run_continuation_revalidation_shadow(
            chain_id="c-1",
            step_index=1,
            query="test",
            context={},
            prior_decision_status="allow",
        )
        _, snap_block, _ = run_continuation_revalidation_shadow(
            chain_id="c-1",
            step_index=1,
            query="test",
            context={},
            prior_decision_status="block",
        )

        # Continuation standing must be identical — it doesn't derive from step result
        assert snap_allow.claim_status == snap_block.claim_status

    def test_snapshot_receipt_pair_always_emitted(self):
        """Every revalidation must produce both snapshot and receipt."""
        from veritas_os.core.continuation_runtime.revalidator import (
            run_continuation_revalidation_shadow,
        )
        from veritas_os.core.continuation_runtime.snapshot import ClaimStateSnapshot
        from veritas_os.core.continuation_runtime.receipt import ContinuationReceipt

        _, snap, rcpt = run_continuation_revalidation_shadow(
            chain_id="pair-test",
            step_index=0,
            query="test",
            context={},
        )

        assert isinstance(snap, ClaimStateSnapshot)
        assert isinstance(rcpt, ContinuationReceipt)
        assert rcpt.snapshot_id == snap.snapshot_id

    def test_continuation_does_not_enforce(self):
        """Phase-1: even when should_refuse_before_effect is True,
        this is advisory only — no enforcement mechanism exists."""
        from veritas_os.core.continuation_runtime.revalidator import (
            run_continuation_revalidation_shadow,
        )

        _, snap, rcpt = run_continuation_revalidation_shadow(
            chain_id="",
            step_index=0,
            query="test",
            context={"authorization": "", "policy_ref": ""},
        )

        # Advisory flag is set
        assert rcpt.should_refuse_before_effect is True
        # But no enforcement mechanism — the function simply returns
        # (no exception, no side effect, no pipeline mutation)


# =====================================================================
# Continuation divergence is observable in structured output
# =====================================================================


class TestDivergenceObservability:
    """Divergence between step pass and continuation weakening
    must be observable in structured output."""

    def test_divergence_flag_true_when_not_live(self):
        """Divergence observable via receipt boundary_outcome regardless
        of whether boundary was promoted to state.
        """
        from veritas_os.core.continuation_runtime.revalidator import (
            run_continuation_revalidation_shadow,
        )
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus

        cases_that_diverge = [
            # NARROWED: durable scope reduction → state NARROWED
            {
                "context": {"restricted_actions": ["x"]},
                "expect_state": ClaimStatus.NARROWED,
                "expect_boundary": "narrowed",
            },
            # DEGRADED: receipt-first → state LIVE
            {
                "context": {
                    "required_evidence": ["e1", "e2", "e3"],
                    "satisfied_evidence": ["e1"],
                },
                "expect_state": ClaimStatus.LIVE,
                "expect_boundary": "degraded",
            },
            # ESCALATED: receipt-first → state LIVE
            {
                "context": {"escalation_required": True},
                "expect_state": ClaimStatus.LIVE,
                "expect_boundary": "escalated",
            },
        ]

        for case in cases_that_diverge:
            _, snap, rcpt = run_continuation_revalidation_shadow(
                chain_id="div-obs",
                step_index=1,
                query="test",
                context=case["context"],
                prior_decision_status="allow",
            )
            assert snap.claim_status == case["expect_state"], (
                f"State expected {case['expect_state']}"
            )
            assert rcpt.boundary_outcome == case["expect_boundary"], (
                f"Receipt boundary expected {case['expect_boundary']}"
            )
            assert rcpt.divergence_flag is True

    def test_divergence_flag_false_when_live(self):
        from veritas_os.core.continuation_runtime.revalidator import (
            run_continuation_revalidation_shadow,
        )

        _, snap, rcpt = run_continuation_revalidation_shadow(
            chain_id="no-div",
            step_index=1,
            query="test",
            context={},
        )

        assert rcpt.divergence_flag is False
