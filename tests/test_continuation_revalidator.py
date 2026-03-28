# tests/test_continuation_revalidator.py
# -*- coding: utf-8 -*-
"""
Tests for ContinuationRevalidator — phase-1 shadow revalidation engine.

Verifies:
  - Snapshot / receipt pair emission and coherence
  - Status determination (conservative logic)
  - Divergence detection
  - Flag off → zero side effects
  - Lineage mutable pointer updates
  - state/receipt separation
"""
from __future__ import annotations

import os
import pytest


# =====================================================================
# Revalidator unit tests
# =====================================================================


class TestContinuationRevalidator:
    """Core revalidator logic tests."""

    def _make_revalidator(self):
        from veritas_os.core.continuation_runtime.revalidator import (
            ContinuationRevalidator,
        )
        return ContinuationRevalidator()

    def _make_lineage(self, **kwargs):
        from veritas_os.core.continuation_runtime.lineage import (
            ContinuationClaimLineage,
        )
        defaults = {"chain_id": "test-chain", "origin_ref": "step:0"}
        defaults.update(kwargs)
        return ContinuationClaimLineage(**defaults)

    def _make_condition(self, **kwargs):
        from veritas_os.core.continuation_runtime.revalidator import PresentCondition
        defaults = {
            "chain_id": "test-chain",
            "step_index": 1,
            "query": "What is the weather?",
            "context": {},
        }
        defaults.update(kwargs)
        return PresentCondition(**defaults)

    def test_basic_revalidation_returns_snapshot_and_receipt(self):
        """Revalidation always returns both snapshot and receipt."""
        from veritas_os.core.continuation_runtime.snapshot import ClaimStateSnapshot
        from veritas_os.core.continuation_runtime.receipt import ContinuationReceipt

        rv = self._make_revalidator()
        lineage = self._make_lineage()
        condition = self._make_condition()

        snapshot, receipt = rv.revalidate(lineage, condition)

        assert isinstance(snapshot, ClaimStateSnapshot)
        assert isinstance(receipt, ContinuationReceipt)

    def test_snapshot_receipt_share_snapshot_id(self):
        """Snapshot and receipt must reference the same snapshot_id."""
        rv = self._make_revalidator()
        lineage = self._make_lineage()
        condition = self._make_condition()

        snapshot, receipt = rv.revalidate(lineage, condition)

        assert receipt.snapshot_id == snapshot.snapshot_id

    def test_snapshot_receipt_share_lineage_id(self):
        """Both reference the same claim_lineage_id."""
        rv = self._make_revalidator()
        lineage = self._make_lineage()
        condition = self._make_condition()

        snapshot, receipt = rv.revalidate(lineage, condition)

        assert snapshot.claim_lineage_id == lineage.claim_lineage_id
        assert receipt.claim_lineage_id == lineage.claim_lineage_id

    def test_live_status_yields_renewed(self):
        """Default conditions → LIVE / RENEWED, no divergence."""
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus
        from veritas_os.core.continuation_runtime.receipt import RevalidationStatus

        rv = self._make_revalidator()
        lineage = self._make_lineage()
        condition = self._make_condition()

        snapshot, receipt = rv.revalidate(lineage, condition)

        assert snapshot.claim_status == ClaimStatus.LIVE
        assert receipt.revalidation_status == RevalidationStatus.RENEWED
        assert receipt.divergence_flag is False
        assert receipt.should_refuse_before_effect is False

    def test_lineage_updated_after_revalidation(self):
        """Lineage mutable pointers are updated after revalidation."""
        rv = self._make_revalidator()
        lineage = self._make_lineage()
        condition = self._make_condition()

        snapshot, receipt = rv.revalidate(lineage, condition)

        assert lineage.latest_snapshot_id == snapshot.snapshot_id
        assert lineage.current_claim_status == snapshot.claim_status

    def test_revoked_is_terminal(self):
        """Once revoked, stays revoked regardless of new conditions."""
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus

        rv = self._make_revalidator()
        lineage = self._make_lineage()
        lineage.current_claim_status = ClaimStatus.REVOKED
        lineage.is_revoked = True

        condition = self._make_condition()
        snapshot, receipt = rv.revalidate(lineage, condition)

        assert snapshot.claim_status == ClaimStatus.REVOKED
        assert receipt.divergence_flag is True
        assert receipt.should_refuse_before_effect is True

    def test_support_basis_lost_yields_revoked(self):
        """No authority AND no policy → REVOKED."""
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus

        rv = self._make_revalidator()
        lineage = self._make_lineage()
        condition = self._make_condition(
            chain_id="",
            context={"authorization": "", "policy_ref": ""},
        )

        snapshot, receipt = rv.revalidate(lineage, condition)

        assert snapshot.claim_status == ClaimStatus.REVOKED
        assert receipt.divergence_flag is True
        assert receipt.should_refuse_before_effect is True

    def test_scope_restriction_yields_narrowed(self):
        """Restricted action classes present → NARROWED."""
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus

        rv = self._make_revalidator()
        lineage = self._make_lineage()
        condition = self._make_condition(
            context={"restricted_actions": ["execute"]},
        )

        snapshot, receipt = rv.revalidate(lineage, condition)

        assert snapshot.claim_status == ClaimStatus.NARROWED
        assert receipt.divergence_flag is True

    def test_escalation_required_yields_escalated(self):
        """escalation_required in scope → ESCALATED."""
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus

        rv = self._make_revalidator()
        lineage = self._make_lineage()
        condition = self._make_condition(
            context={"escalation_required": True},
        )

        snapshot, receipt = rv.revalidate(lineage, condition)

        assert snapshot.claim_status == ClaimStatus.ESCALATED

    def test_burden_threshold_exceeded_yields_degraded(self):
        """Burden below threshold → DEGRADED."""
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus

        rv = self._make_revalidator()
        lineage = self._make_lineage()
        condition = self._make_condition(
            context={
                "required_evidence": ["ev1", "ev2", "ev3"],
                "satisfied_evidence": ["ev1"],
                "burden_threshold": 1.0,
            },
        )

        snapshot, receipt = rv.revalidate(lineage, condition)

        assert snapshot.claim_status == ClaimStatus.DEGRADED

    def test_snapshot_has_law_version(self):
        """Snapshot records which law_version was applied."""
        rv = self._make_revalidator()
        lineage = self._make_lineage()
        condition = self._make_condition()

        snapshot, receipt = rv.revalidate(lineage, condition)

        assert snapshot.law_version != ""
        assert snapshot.law_version == "v0.1.0-shadow"

    def test_receipt_has_law_version_id(self):
        """Receipt records law_version_id."""
        rv = self._make_revalidator()
        lineage = self._make_lineage()
        condition = self._make_condition()

        snapshot, receipt = rv.revalidate(lineage, condition)

        assert receipt.law_version_id == "v0.1.0-shadow"

    def test_snapshot_has_scope(self):
        """Snapshot scope is explicit, not implicit."""
        rv = self._make_revalidator()
        lineage = self._make_lineage()
        condition = self._make_condition()

        snapshot, receipt = rv.revalidate(lineage, condition)

        assert snapshot.scope is not None
        assert isinstance(snapshot.scope.allowed_action_classes, list)

    def test_snapshot_has_burden_state(self):
        """Snapshot carries burden_state (not optional)."""
        rv = self._make_revalidator()
        lineage = self._make_lineage()
        condition = self._make_condition()

        snapshot, receipt = rv.revalidate(lineage, condition)

        assert snapshot.burden_state is not None
        assert hasattr(snapshot.burden_state, "threshold")

    def test_snapshot_has_support_basis(self):
        """Snapshot carries structured support_basis (not empty)."""
        rv = self._make_revalidator()
        lineage = self._make_lineage()
        condition = self._make_condition()

        snapshot, receipt = rv.revalidate(lineage, condition)

        sb = snapshot.support_basis
        # At minimum, authority or policy should be present for LIVE
        assert sb.authority or sb.policy

    def test_receipt_has_digests(self):
        """Receipt carries digest summaries for audit."""
        rv = self._make_revalidator()
        lineage = self._make_lineage()
        condition = self._make_condition()

        snapshot, receipt = rv.revalidate(lineage, condition)

        assert receipt.support_basis_digest is not None
        assert receipt.scope_digest is not None
        assert receipt.burden_headroom_digest is not None

    def test_snapshot_serialization_roundtrip(self):
        """Snapshot survives to_dict → from_dict."""
        from veritas_os.core.continuation_runtime.snapshot import ClaimStateSnapshot

        rv = self._make_revalidator()
        lineage = self._make_lineage()
        condition = self._make_condition()

        snapshot, _ = rv.revalidate(lineage, condition)

        d = snapshot.to_dict()
        restored = ClaimStateSnapshot.from_dict(d)

        assert restored.snapshot_id == snapshot.snapshot_id
        assert restored.claim_status == snapshot.claim_status
        assert restored.law_version == snapshot.law_version

    def test_receipt_serialization_roundtrip(self):
        """Receipt survives to_dict → from_dict."""
        from veritas_os.core.continuation_runtime.receipt import ContinuationReceipt

        rv = self._make_revalidator()
        lineage = self._make_lineage()
        condition = self._make_condition()

        _, receipt = rv.revalidate(lineage, condition)

        d = receipt.to_dict()
        restored = ContinuationReceipt.from_dict(d)

        assert restored.receipt_id == receipt.receipt_id
        assert restored.revalidation_status == receipt.revalidation_status
        assert restored.divergence_flag == receipt.divergence_flag

    def test_coherence_violation_raises(self):
        """Coherence guard detects snapshot/receipt mismatch."""
        from veritas_os.core.continuation_runtime.revalidator import (
            ContinuationRevalidator,
        )
        from veritas_os.core.continuation_runtime.snapshot import ClaimStateSnapshot
        from veritas_os.core.continuation_runtime.receipt import (
            ContinuationReceipt,
            RevalidationStatus,
        )
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus

        snap = ClaimStateSnapshot(
            claim_status=ClaimStatus.REVOKED,
            snapshot_id="snap-1",
        )
        rcpt = ContinuationReceipt(
            snapshot_id="snap-1",
            revalidation_status=RevalidationStatus.RENEWED,  # contradicts!
        )

        with pytest.raises(ValueError, match="Coherence violation"):
            ContinuationRevalidator._assert_coherence(snap, rcpt)

    def test_divergence_observable_when_claim_weakened(self):
        """Divergence flag is True when claim_status != LIVE."""
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus

        rv = self._make_revalidator()
        lineage = self._make_lineage()
        condition = self._make_condition(
            context={"restricted_actions": ["execute"]},
        )

        snapshot, receipt = rv.revalidate(lineage, condition)

        assert snapshot.claim_status != ClaimStatus.LIVE
        assert receipt.divergence_flag is True


# =====================================================================
# Convenience function tests
# =====================================================================


class TestRunContinuationRevalidationShadow:
    """Tests for the pipeline integration helper function."""

    def test_returns_three_objects(self):
        from veritas_os.core.continuation_runtime.revalidator import (
            run_continuation_revalidation_shadow,
        )
        from veritas_os.core.continuation_runtime.lineage import (
            ContinuationClaimLineage,
        )
        from veritas_os.core.continuation_runtime.snapshot import ClaimStateSnapshot
        from veritas_os.core.continuation_runtime.receipt import ContinuationReceipt

        lineage, snapshot, receipt = run_continuation_revalidation_shadow(
            chain_id="test-chain",
            step_index=0,
            query="test",
            context={},
        )

        assert isinstance(lineage, ContinuationClaimLineage)
        assert isinstance(snapshot, ClaimStateSnapshot)
        assert isinstance(receipt, ContinuationReceipt)

    def test_creates_lineage_when_none_provided(self):
        from veritas_os.core.continuation_runtime.revalidator import (
            run_continuation_revalidation_shadow,
        )

        lineage, _, _ = run_continuation_revalidation_shadow(
            chain_id="auto-chain",
            step_index=0,
            query="test",
            context={},
        )

        assert lineage.chain_id == "auto-chain"
        assert lineage.latest_snapshot_id is not None


# =====================================================================
# Output structure verification (against task requirements)
# =====================================================================


class TestOutputStructure:
    """Verify that output structures meet task requirements."""

    def _run_revalidation(self, **ctx_kwargs):
        from veritas_os.core.continuation_runtime.revalidator import (
            run_continuation_revalidation_shadow,
        )
        defaults = {
            "chain_id": "struct-test",
            "step_index": 1,
            "query": "test query",
            "context": {},
        }
        defaults.update(ctx_kwargs)
        _, snapshot, receipt = run_continuation_revalidation_shadow(**defaults)
        return snapshot.to_dict(), receipt.to_dict()

    def test_state_side_required_fields(self):
        """State side must contain all required fields."""
        snap_d, _ = self._run_revalidation()

        assert "claim_lineage_id" in snap_d
        assert "snapshot_id" in snap_d
        assert "claim_status" in snap_d
        assert "support_basis" in snap_d
        assert "scope" in snap_d
        assert "burden_state" in snap_d
        assert "headroom_state" in snap_d
        assert "law_version" in snap_d

    def test_receipt_side_required_fields(self):
        """Receipt side must contain all required fields."""
        _, rcpt_d = self._run_revalidation()

        assert "receipt_id" in rcpt_d
        assert "revalidation_status" in rcpt_d
        assert "revalidation_outcome" in rcpt_d
        assert "revalidation_reason_codes" in rcpt_d
        assert "prior_decision_continuity_ref" in rcpt_d
        assert "parent_receipt_ref" in rcpt_d
        assert "should_refuse_before_effect" in rcpt_d
        assert "divergence_flag" in rcpt_d

    def test_state_and_receipt_are_separate(self):
        """Snapshot and receipt are separate dicts, not merged."""
        snap_d, rcpt_d = self._run_revalidation()

        # Receipt fields must NOT appear in snapshot
        assert "revalidation_status" not in snap_d
        assert "divergence_flag" not in snap_d
        assert "should_refuse_before_effect" not in snap_d

        # State-specific fields must NOT appear in receipt
        assert "support_basis" not in rcpt_d
        assert "burden_state" not in rcpt_d
        assert "headroom_state" not in rcpt_d

    def test_continuation_is_not_bool_or_enum_only(self):
        """Continuation must be a rich structure, not a bool/enum."""
        snap_d, rcpt_d = self._run_revalidation()

        # Both must be dicts with multiple fields
        assert isinstance(snap_d, dict) and len(snap_d) > 5
        assert isinstance(rcpt_d, dict) and len(rcpt_d) > 5

    def test_law_version_present(self):
        """law_version must be non-empty."""
        snap_d, rcpt_d = self._run_revalidation()

        assert snap_d["law_version"] != ""
        assert rcpt_d["law_version_id"] != ""


# =====================================================================
# Feature flag off — zero side effects
# =====================================================================


class TestFeatureFlagOff:
    """Verify that flag off → zero computation in PipelineContext."""

    def test_pipeline_context_defaults_none(self):
        """PipelineContext continuation fields default to None."""
        from veritas_os.core.pipeline_types import PipelineContext

        ctx = PipelineContext()

        assert ctx.continuation_snapshot is None
        assert ctx.continuation_receipt is None

    def test_flag_off_default(self):
        """VERITAS_CAP_CONTINUATION_RUNTIME defaults to False."""
        # Ensure env var is not set
        env_val = os.environ.pop("VERITAS_CAP_CONTINUATION_RUNTIME", None)
        try:
            from veritas_os.core.config import _parse_bool
            assert _parse_bool("VERITAS_CAP_CONTINUATION_RUNTIME", False) is False
        finally:
            if env_val is not None:
                os.environ["VERITAS_CAP_CONTINUATION_RUNTIME"] = env_val

    def test_response_omits_continuation_when_flag_off(self):
        """assemble_response omits 'continuation' key when ctx has no snapshot."""
        from veritas_os.core.pipeline_types import PipelineContext
        from veritas_os.core.pipeline_response import assemble_response

        ctx = PipelineContext(
            request_id="test-req",
            query="test",
            response_extras={"metrics": {}, "memory_citations": [], "memory_used_count": 0},
        )

        res = assemble_response(
            ctx,
            load_persona_fn=lambda: {"name": "test"},
            plan={"steps": [], "raw": None, "source": "fallback"},
        )

        assert "continuation" not in res

    def test_response_includes_continuation_when_present(self):
        """assemble_response includes 'continuation' when snapshot/receipt set."""
        from veritas_os.core.pipeline_types import PipelineContext
        from veritas_os.core.pipeline_response import assemble_response

        ctx = PipelineContext(
            request_id="test-req",
            query="test",
            response_extras={"metrics": {}, "memory_citations": [], "memory_used_count": 0},
            continuation_snapshot={"snapshot_id": "s1", "claim_status": "live"},
            continuation_receipt={"receipt_id": "r1", "divergence_flag": False},
        )

        res = assemble_response(
            ctx,
            load_persona_fn=lambda: {"name": "test"},
            plan={"steps": [], "raw": None, "source": "fallback"},
        )

        assert "continuation" in res
        assert res["continuation"]["state"]["snapshot_id"] == "s1"
        assert res["continuation"]["receipt"]["receipt_id"] == "r1"


# =====================================================================
# Divergence observation tests
# =====================================================================


class TestDivergenceObservation:
    """Verify that divergence between local step pass and claim weakened
    is observable in the output."""

    def test_local_allow_with_continuation_degraded(self):
        """Local step allows, but continuation is degraded → divergence visible."""
        from veritas_os.core.continuation_runtime.revalidator import (
            run_continuation_revalidation_shadow,
        )

        _, snapshot, receipt = run_continuation_revalidation_shadow(
            chain_id="div-test",
            step_index=2,
            query="normal query",
            context={
                "required_evidence": ["ev1", "ev2", "ev3"],
                "satisfied_evidence": ["ev1"],
                "burden_threshold": 1.0,
            },
            prior_decision_status="allow",  # local step passed
        )

        # Continuation is degraded while local step was allow
        assert snapshot.to_dict()["claim_status"] == "degraded"
        assert receipt.divergence_flag is True
        assert receipt.prior_decision_continuity_ref == "allow"
        # Advisory only — should_refuse is False for degraded
        assert receipt.should_refuse_before_effect is False

    def test_local_allow_with_continuation_revoked(self):
        """Local step allows, but continuation is revoked → divergence + advisory refuse."""
        from veritas_os.core.continuation_runtime.revalidator import (
            run_continuation_revalidation_shadow,
        )

        _, snapshot, receipt = run_continuation_revalidation_shadow(
            chain_id="",  # no chain_id → no authority
            step_index=3,
            query="test",
            context={"authorization": "", "policy_ref": ""},
            prior_decision_status="allow",
        )

        assert snapshot.to_dict()["claim_status"] == "revoked"
        assert receipt.divergence_flag is True
        assert receipt.should_refuse_before_effect is True
        assert receipt.prior_decision_continuity_ref == "allow"
