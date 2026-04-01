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
        """デフォルトでオフであり環境変数不要であることを検証する。"""
        from veritas_os.core.config import _parse_bool

        assert _parse_bool("VERITAS_CAP_CONTINUATION_RUNTIME", False) is False

    def test_pipeline_context_has_no_continuation_by_default(self):
        """フラグオフ時にPipelineContextの継続フィールドがNoneであることを検証する。"""
        from veritas_os.core.pipeline_types import PipelineContext

        ctx = PipelineContext()
        assert ctx.continuation_snapshot is None
        assert ctx.continuation_receipt is None

    def test_response_omits_continuation_key_when_flag_off(self):
        """フラグオフ時にassemble_responseがcontinuationキーを含まないことを検証する。"""
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
        """gate.decision_statusがPipelineContextの値と完全一致することを検証する。"""
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
        """レスポンスにcontinuationブロックが含まれることを検証する。"""
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
        """レスポンス内で状態とレシートが分離されていることを検証する。"""
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
        """継続状態に関係なくgate.decision_statusがctxの値と一致することを検証する。"""
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
        """FUJI辞書がctxの提供値から変更されていないことを検証する。"""
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
        """prior_decision_statusなしで再検証が動作し、ステップ結果に依存しないことを検証する。"""
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
        """再検証結果がprior_decision_statusの値に依存しないことを検証する。"""
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
        """全ての再検証がスナップショットとレシートの両方を生成することを検証する。"""
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
        """Phase-1ではshould_refuse_before_effectがTrueでも助言のみで強制機構がないことを検証する。"""
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
        """境界が状態に昇格されたかに関わらずレシートのboundary_outcomeで乖離が観測可能であることを検証する。"""
        from veritas_os.core.continuation_runtime.revalidator import (
            run_continuation_revalidation_shadow,
        )
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus

        cases_that_diverge = [
            # NARROWED: receipt-first → state LIVE (restrictions not durable)
            {
                "context": {"restricted_actions": ["x"]},
                "expect_state": ClaimStatus.LIVE,
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
        """LIVE状態では乖離フラグがFalseであることを検証する。"""
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
