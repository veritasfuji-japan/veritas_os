# tests/test_continuation_receipt_first.py
# -*- coding: utf-8 -*-
"""
Tests for receipt-first boundary semantics and proof-bearing receipt.

Verifies:
  - halted is receipt-first, state-second (durable only when promoted)
  - narrowed is receipt-first, state-second
  - degraded / escalated follow the same general rule
  - receipt carries proof-bearing fields (boundary_outcome,
    is_durable_promotion, provisional_vs_durable, reopening_eligible)
  - DurableConsequence is present in snapshot when promoted
  - snapshot is lighter (durable standing only)
  - coherence guard works with receipt-first semantics
  - serialization round-trips preserve new fields
"""
from __future__ import annotations

import pytest


class TestReceiptFirstBoundary:
    """Receipt-first boundary outcome semantics."""

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
            "query": "test query",
            "context": {},
        }
        defaults.update(kwargs)
        return PresentCondition(**defaults)

    # ------------------------------------------------------------------
    # LIVE outcome: no boundary, no promotion
    # ------------------------------------------------------------------

    def test_live_no_durable_consequence(self):
        """LIVE outcome: no durable consequence, no boundary_outcome promotion."""
        rv = self._make_revalidator()
        lineage = self._make_lineage()
        condition = self._make_condition()
        snap, receipt = rv.revalidate(lineage, condition)

        assert snap.claim_status.value == "live"
        assert snap.durable_consequence is None
        assert receipt.boundary_outcome == "live"
        assert receipt.is_durable_promotion is False
        assert receipt.provisional_vs_durable is None
        assert receipt.reopening_eligible is True

    # ------------------------------------------------------------------
    # HALTED: receipt-first, durable when headroom collapsed
    # ------------------------------------------------------------------

    def test_halted_is_receipt_first_and_durable_when_headroom_collapsed(self):
        """Headroom collapse → halted in receipt AND state (durable halt)."""
        rv = self._make_revalidator()
        lineage = self._make_lineage()
        # Set required_evidence with none satisfied → current_level=0.0 → headroom=0.0
        condition = self._make_condition(context={
            "required_evidence": ["doc_a"],
            "satisfied_evidence": [],
        })
        snap, receipt = rv.revalidate(lineage, condition)

        # Receipt is always the primary record
        assert receipt.boundary_outcome == "halted"
        assert receipt.revalidation_status.value == "halted"
        assert receipt.is_durable_promotion is True
        assert receipt.provisional_vs_durable == "durable_promotable"

        # State gets the halt because it's durable
        assert snap.claim_status.value == "halted"
        assert snap.durable_consequence is not None
        assert snap.durable_consequence.has_durable_halt is True
        assert snap.durable_consequence.promotion_reason != ""

    # ------------------------------------------------------------------
    # NARROWED: receipt-first, durable when scope restrictions present
    # ------------------------------------------------------------------

    def test_narrowed_receipt_first_with_durable_scope_reduction(self):
        """Scope restriction → narrowed in receipt AND state (durable narrowing)."""
        rv = self._make_revalidator()
        lineage = self._make_lineage()
        condition = self._make_condition(context={
            "restricted_actions": ["execute"],
        })
        snap, receipt = rv.revalidate(lineage, condition)

        # Receipt is primary
        assert receipt.boundary_outcome == "narrowed"
        assert receipt.revalidation_status.value == "narrowed"
        assert receipt.is_durable_promotion is True
        assert receipt.provisional_vs_durable == "durable_promotable"
        assert receipt.reopening_eligible is False  # durable = not reopenable

        # State gets narrowed because scope reduction is durable
        assert snap.claim_status.value == "narrowed"
        assert snap.durable_consequence is not None
        assert snap.durable_consequence.has_durable_scope_reduction is True

    def test_narrowed_reopening_eligible_when_not_durable(self):
        """Narrowed reopening test: durable → not reopenable."""
        from veritas_os.core.continuation_runtime.revalidator import (
            ContinuationRevalidator,
        )
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus
        from veritas_os.core.continuation_runtime.snapshot import Scope

        # Durable narrowing
        result = ContinuationRevalidator._assess_reopening_eligible(
            ClaimStatus.NARROWED, Scope(restricted_action_classes=["x"]), True
        )
        assert result is False

        # Non-durable narrowing
        result = ContinuationRevalidator._assess_reopening_eligible(
            ClaimStatus.NARROWED, Scope(), False
        )
        assert result is True

    # ------------------------------------------------------------------
    # DEGRADED: receipt-first by default
    # ------------------------------------------------------------------

    def test_degraded_receipt_first(self):
        """Burden exceeded → degraded in receipt; state reflects degraded."""
        rv = self._make_revalidator()
        lineage = self._make_lineage()
        # 2 required, 1 satisfied → current_level=0.5; threshold=0.8
        # headroom=0.5 > threshold_escalation(0.3) → not escalated
        # current_level(0.5) < threshold(0.8) → degraded
        condition = self._make_condition(context={
            "required_evidence": ["doc_a", "doc_b"],
            "satisfied_evidence": ["doc_a"],
            "burden_threshold": 0.8,
        })
        snap, receipt = rv.revalidate(lineage, condition)

        # Receipt carries the boundary outcome
        assert receipt.boundary_outcome == "degraded"
        assert receipt.revalidation_status.value == "degraded"
        # Degraded is not durable in phase-1
        assert receipt.is_durable_promotion is False
        assert receipt.provisional_vs_durable == "provisional"

    # ------------------------------------------------------------------
    # ESCALATED: receipt-first by default
    # ------------------------------------------------------------------

    def test_escalated_receipt_first(self):
        """Escalation required → escalated in receipt."""
        rv = self._make_revalidator()
        lineage = self._make_lineage()
        condition = self._make_condition(context={
            "escalation_required": True,
        })
        snap, receipt = rv.revalidate(lineage, condition)

        assert receipt.boundary_outcome == "escalated"
        assert receipt.revalidation_status.value == "escalated"
        # Escalated is not durable in phase-1
        assert receipt.is_durable_promotion is False
        assert receipt.provisional_vs_durable == "provisional"

    # ------------------------------------------------------------------
    # REVOKED: always durable (state and receipt)
    # ------------------------------------------------------------------

    def test_revoked_always_durable(self):
        """Support loss → revoked in both receipt and state (irreversible)."""
        rv = self._make_revalidator()
        lineage = self._make_lineage()
        # Empty chain_id so authority isn't auto-filled; empty policy_ref
        condition = self._make_condition(
            chain_id="",
            context={
                "authorization": "",
                "policy_ref": "",
            },
        )
        snap, receipt = rv.revalidate(lineage, condition)

        assert receipt.boundary_outcome == "revoked"
        assert receipt.is_durable_promotion is True
        assert receipt.provisional_vs_durable == "durable_promotable"
        assert snap.claim_status.value == "revoked"
        assert snap.durable_consequence is not None
        assert snap.durable_consequence.has_irreversible_revocation is True


class TestProofBearingReceipt:
    """Receipt carries proof-bearing fields for audit and replay."""

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
            "query": "test query",
            "context": {},
        }
        defaults.update(kwargs)
        return PresentCondition(**defaults)

    def test_receipt_has_boundary_outcome(self):
        """Every receipt must carry a boundary_outcome."""
        rv = self._make_revalidator()
        lineage = self._make_lineage()
        snap, receipt = rv.revalidate(lineage, self._make_condition())
        assert receipt.boundary_outcome is not None
        assert receipt.boundary_outcome == "live"

    def test_receipt_has_provisional_vs_durable(self):
        """Non-LIVE outcomes carry provisional_vs_durable assessment."""
        rv = self._make_revalidator()
        lineage = self._make_lineage()
        condition = self._make_condition(context={
            "escalation_required": True,
        })
        snap, receipt = rv.revalidate(lineage, condition)
        assert receipt.provisional_vs_durable in ("provisional", "durable_promotable")

    def test_receipt_has_digest_summaries(self):
        """Receipt carries digest summaries for audit."""
        rv = self._make_revalidator()
        lineage = self._make_lineage()
        snap, receipt = rv.revalidate(lineage, self._make_condition())
        assert receipt.support_basis_digest is not None
        assert receipt.scope_digest is not None
        assert receipt.burden_headroom_digest is not None

    def test_receipt_carries_reason_codes(self):
        """Non-LIVE receipts carry reason codes."""
        rv = self._make_revalidator()
        lineage = self._make_lineage()
        condition = self._make_condition(context={
            "escalation_required": True,
        })
        snap, receipt = rv.revalidate(lineage, condition)
        assert len(receipt.revalidation_reason_codes) > 0


class TestDurableConsequence:
    """DurableConsequence tracking in snapshot."""

    def test_durable_consequence_absent_for_live(self):
        """LIVE standing has no durable consequence."""
        from veritas_os.core.continuation_runtime.snapshot import (
            ClaimStateSnapshot,
        )
        snap = ClaimStateSnapshot()
        assert snap.durable_consequence is None

    def test_durable_consequence_serialization_roundtrip(self):
        """DurableConsequence survives to_dict / from_dict."""
        from veritas_os.core.continuation_runtime.snapshot import (
            ClaimStateSnapshot,
            DurableConsequence,
        )
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus
        snap = ClaimStateSnapshot(
            claim_status=ClaimStatus.HALTED,
            durable_consequence=DurableConsequence(
                has_durable_halt=True,
                promotion_reason="headroom collapsed",
            ),
        )
        d = snap.to_dict()
        assert d["durable_consequence"] is not None
        assert d["durable_consequence"]["has_durable_halt"] is True

        restored = ClaimStateSnapshot.from_dict(d)
        assert restored.durable_consequence is not None
        assert restored.durable_consequence.has_durable_halt is True
        assert restored.durable_consequence.promotion_reason == "headroom collapsed"

    def test_durable_consequence_none_serialization_roundtrip(self):
        """None durable_consequence survives roundtrip."""
        from veritas_os.core.continuation_runtime.snapshot import ClaimStateSnapshot
        snap = ClaimStateSnapshot()
        d = snap.to_dict()
        assert d["durable_consequence"] is None
        restored = ClaimStateSnapshot.from_dict(d)
        assert restored.durable_consequence is None


class TestReceiptSerialization:
    """Receipt proof-bearing fields survive serialization."""

    def test_receipt_new_fields_roundtrip(self):
        """New receipt fields survive to_dict / from_dict."""
        from veritas_os.core.continuation_runtime.receipt import ContinuationReceipt
        receipt = ContinuationReceipt(
            boundary_outcome="halted",
            is_durable_promotion=True,
            provisional_vs_durable="durable_promotable",
            reopening_eligible=False,
        )
        d = receipt.to_dict()
        assert d["boundary_outcome"] == "halted"
        assert d["is_durable_promotion"] is True
        assert d["provisional_vs_durable"] == "durable_promotable"
        assert d["reopening_eligible"] is False

        restored = ContinuationReceipt.from_dict(d)
        assert restored.boundary_outcome == "halted"
        assert restored.is_durable_promotion is True
        assert restored.provisional_vs_durable == "durable_promotable"
        assert restored.reopening_eligible is False


class TestCoherenceGuardReceiptFirst:
    """Coherence guard under receipt-first semantics."""

    def _make_snapshot(self, **kwargs):
        from veritas_os.core.continuation_runtime.snapshot import ClaimStateSnapshot
        return ClaimStateSnapshot(**kwargs)

    def _make_receipt(self, **kwargs):
        from veritas_os.core.continuation_runtime.receipt import ContinuationReceipt
        return ContinuationReceipt(**kwargs)

    def test_revoked_must_agree_bidirectionally(self):
        """REVOKED must be in both snapshot and receipt."""
        from veritas_os.core.continuation_runtime.revalidator import (
            ContinuationRevalidator,
        )
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus
        from veritas_os.core.continuation_runtime.receipt import RevalidationStatus

        # Snapshot REVOKED, receipt not REVOKED → violation
        snap = self._make_snapshot(claim_status=ClaimStatus.REVOKED)
        receipt = self._make_receipt(
            snapshot_id=snap.snapshot_id,
            revalidation_status=RevalidationStatus.RENEWED,
        )
        with pytest.raises(ValueError, match="Coherence violation"):
            ContinuationRevalidator._assert_coherence(snap, receipt)

    def test_halted_receipt_only_is_valid(self):
        """Receipt shows HALTED, snapshot shows LIVE → valid (receipt-first)."""
        from veritas_os.core.continuation_runtime.revalidator import (
            ContinuationRevalidator,
        )
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus
        from veritas_os.core.continuation_runtime.receipt import RevalidationStatus

        snap = self._make_snapshot(claim_status=ClaimStatus.LIVE)
        receipt = self._make_receipt(
            snapshot_id=snap.snapshot_id,
            revalidation_status=RevalidationStatus.HALTED,
            is_durable_promotion=False,
        )
        # Should NOT raise — halt is receipt-only (not durable)
        ContinuationRevalidator._assert_coherence(snap, receipt)

    def test_halted_durable_promotion_requires_snapshot_agreement(self):
        """Receipt claims durable HALTED but snapshot is LIVE → violation."""
        from veritas_os.core.continuation_runtime.revalidator import (
            ContinuationRevalidator,
        )
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus
        from veritas_os.core.continuation_runtime.receipt import RevalidationStatus

        snap = self._make_snapshot(claim_status=ClaimStatus.LIVE)
        receipt = self._make_receipt(
            snapshot_id=snap.snapshot_id,
            revalidation_status=RevalidationStatus.HALTED,
            is_durable_promotion=True,
        )
        with pytest.raises(ValueError, match="Coherence violation"):
            ContinuationRevalidator._assert_coherence(snap, receipt)

    def test_halted_snapshot_requires_receipt_evidence(self):
        """Snapshot HALTED without receipt HALTED → violation."""
        from veritas_os.core.continuation_runtime.revalidator import (
            ContinuationRevalidator,
        )
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus
        from veritas_os.core.continuation_runtime.receipt import RevalidationStatus

        snap = self._make_snapshot(claim_status=ClaimStatus.HALTED)
        receipt = self._make_receipt(
            snapshot_id=snap.snapshot_id,
            revalidation_status=RevalidationStatus.RENEWED,
        )
        with pytest.raises(ValueError, match="Coherence violation"):
            ContinuationRevalidator._assert_coherence(snap, receipt)


class TestDurabilityAssessment:
    """Direct tests for _assess_durability static method."""

    def test_live_no_durable(self):
        from veritas_os.core.continuation_runtime.revalidator import ContinuationRevalidator
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus
        from veritas_os.core.continuation_runtime.snapshot import Scope, HeadroomState

        dc, status = ContinuationRevalidator._assess_durability(
            boundary_status=ClaimStatus.LIVE,
            scope=Scope(),
            headroom_state=HeadroomState(),
            revocation_conditions=[],
        )
        assert dc is None
        assert status == ClaimStatus.LIVE

    def test_revoked_always_durable(self):
        from veritas_os.core.continuation_runtime.revalidator import ContinuationRevalidator
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus
        from veritas_os.core.continuation_runtime.snapshot import Scope, HeadroomState

        dc, status = ContinuationRevalidator._assess_durability(
            boundary_status=ClaimStatus.REVOKED,
            scope=Scope(),
            headroom_state=HeadroomState(),
            revocation_conditions=[],
        )
        assert dc is not None
        assert dc.has_irreversible_revocation is True
        assert status == ClaimStatus.REVOKED

    def test_halted_durable_when_collapsed(self):
        from veritas_os.core.continuation_runtime.revalidator import ContinuationRevalidator
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus
        from veritas_os.core.continuation_runtime.snapshot import Scope, HeadroomState

        dc, status = ContinuationRevalidator._assess_durability(
            boundary_status=ClaimStatus.HALTED,
            scope=Scope(),
            headroom_state=HeadroomState(remaining=0.0, threshold_suspension=0.0),
            revocation_conditions=[],
        )
        assert dc is not None
        assert dc.has_durable_halt is True
        assert status == ClaimStatus.HALTED

    def test_halted_not_durable_when_headroom_positive(self):
        """Halted with positive headroom → receipt-only, no durable consequence."""
        from veritas_os.core.continuation_runtime.revalidator import ContinuationRevalidator
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus
        from veritas_os.core.continuation_runtime.snapshot import Scope, HeadroomState

        dc, status = ContinuationRevalidator._assess_durability(
            boundary_status=ClaimStatus.HALTED,
            scope=Scope(),
            headroom_state=HeadroomState(remaining=0.5, threshold_suspension=0.0),
            revocation_conditions=[],
        )
        assert dc is None
        assert status == ClaimStatus.LIVE

    def test_narrowed_durable_when_restrictions_present(self):
        from veritas_os.core.continuation_runtime.revalidator import ContinuationRevalidator
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus
        from veritas_os.core.continuation_runtime.snapshot import Scope, HeadroomState

        dc, status = ContinuationRevalidator._assess_durability(
            boundary_status=ClaimStatus.NARROWED,
            scope=Scope(restricted_action_classes=["execute"]),
            headroom_state=HeadroomState(),
            revocation_conditions=[],
        )
        assert dc is not None
        assert dc.has_durable_scope_reduction is True
        assert status == ClaimStatus.NARROWED

    def test_degraded_receipt_only(self):
        from veritas_os.core.continuation_runtime.revalidator import ContinuationRevalidator
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus
        from veritas_os.core.continuation_runtime.snapshot import Scope, HeadroomState

        dc, status = ContinuationRevalidator._assess_durability(
            boundary_status=ClaimStatus.DEGRADED,
            scope=Scope(),
            headroom_state=HeadroomState(),
            revocation_conditions=[],
        )
        assert dc is None
        assert status == ClaimStatus.LIVE

    def test_escalated_receipt_only(self):
        from veritas_os.core.continuation_runtime.revalidator import ContinuationRevalidator
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus
        from veritas_os.core.continuation_runtime.snapshot import Scope, HeadroomState

        dc, status = ContinuationRevalidator._assess_durability(
            boundary_status=ClaimStatus.ESCALATED,
            scope=Scope(),
            headroom_state=HeadroomState(),
            revocation_conditions=[],
        )
        assert dc is None
        assert status == ClaimStatus.LIVE
