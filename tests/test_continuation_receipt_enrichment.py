# tests/test_continuation_receipt_enrichment.py
# -*- coding: utf-8 -*-
"""
Tests for receipt-first enrichment fields.

Verifies:
  - halt_occurred / narrowing_occurred explicit booleans
  - halt_classification categories (bounded_interruption, temporary_refusal,
    safety_pause, durable_state_transformation)
  - divergence_detail granular values
  - boundary_predicates populated from reason codes
  - prior_state_ref linkage
  - serialization round-trips for new fields
  - coherence guard strengthening (state-live + receipt-loss contradiction)
"""
from __future__ import annotations

import pytest


# =====================================================================
# Helpers (match existing test style)
# =====================================================================


def _make_revalidator():
    from veritas_os.core.continuation_runtime.revalidator import (
        ContinuationRevalidator,
    )
    return ContinuationRevalidator()


def _make_lineage(**kwargs):
    from veritas_os.core.continuation_runtime.lineage import (
        ContinuationClaimLineage,
    )
    defaults = {"chain_id": "test-chain", "origin_ref": "step:0"}
    defaults.update(kwargs)
    return ContinuationClaimLineage(**defaults)


def _make_condition(**kwargs):
    from veritas_os.core.continuation_runtime.revalidator import PresentCondition
    defaults = {
        "chain_id": "test-chain",
        "step_index": 1,
        "query": "test query",
        "context": {},
    }
    defaults.update(kwargs)
    return PresentCondition(**defaults)


# =====================================================================
# Halt / narrowing occurrence flags
# =====================================================================


class TestBoundaryOccurrenceFlags:
    """Explicit halt_occurred / narrowing_occurred booleans."""

    def test_live_no_halt_no_narrowing(self):
        """LIVE: neither halt nor narrowing occurred."""
        rv = _make_revalidator()
        lineage = _make_lineage()
        _, receipt = rv.revalidate(lineage, _make_condition())
        assert receipt.halt_occurred is False
        assert receipt.narrowing_occurred is False

    def test_halted_sets_halt_occurred(self):
        """Headroom collapse → halt_occurred=True."""
        rv = _make_revalidator()
        lineage = _make_lineage()
        condition = _make_condition(context={
            "required_evidence": ["doc_a"],
            "satisfied_evidence": [],
        })
        _, receipt = rv.revalidate(lineage, condition)
        assert receipt.halt_occurred is True
        assert receipt.narrowing_occurred is False

    def test_narrowed_sets_narrowing_occurred(self):
        """Scope restriction → narrowing_occurred=True."""
        rv = _make_revalidator()
        lineage = _make_lineage()
        condition = _make_condition(context={
            "restricted_actions": ["execute"],
        })
        _, receipt = rv.revalidate(lineage, condition)
        assert receipt.narrowing_occurred is True
        assert receipt.halt_occurred is False

    def test_degraded_no_halt_no_narrowing(self):
        """DEGRADED: neither halt nor narrowing."""
        rv = _make_revalidator()
        lineage = _make_lineage()
        condition = _make_condition(context={
            "required_evidence": ["doc_a", "doc_b"],
            "satisfied_evidence": ["doc_a"],
            "burden_threshold": 0.8,
        })
        _, receipt = rv.revalidate(lineage, condition)
        assert receipt.halt_occurred is False
        assert receipt.narrowing_occurred is False

    def test_escalated_no_halt_no_narrowing(self):
        """ESCALATED: neither halt nor narrowing."""
        rv = _make_revalidator()
        lineage = _make_lineage()
        condition = _make_condition(context={
            "escalation_required": True,
        })
        _, receipt = rv.revalidate(lineage, condition)
        assert receipt.halt_occurred is False
        assert receipt.narrowing_occurred is False

    def test_revoked_no_halt_no_narrowing(self):
        """REVOKED: neither halt nor narrowing (revocation is its own category)."""
        rv = _make_revalidator()
        lineage = _make_lineage()
        condition = _make_condition(
            chain_id="",
            context={"authorization": "", "policy_ref": ""},
        )
        _, receipt = rv.revalidate(lineage, condition)
        assert receipt.halt_occurred is False
        assert receipt.narrowing_occurred is False


# =====================================================================
# Halt classification
# =====================================================================


class TestHaltClassification:
    """Halt classification categories."""

    def test_durable_halt_classified_as_durable_state_transformation(self):
        """Headroom collapse → durable_state_transformation."""
        rv = _make_revalidator()
        lineage = _make_lineage()
        condition = _make_condition(context={
            "required_evidence": ["doc_a"],
            "satisfied_evidence": [],
        })
        _, receipt = rv.revalidate(lineage, condition)
        assert receipt.halt_classification == "durable_state_transformation"

    def test_no_halt_no_classification(self):
        """LIVE → no halt classification."""
        rv = _make_revalidator()
        lineage = _make_lineage()
        _, receipt = rv.revalidate(lineage, _make_condition())
        assert receipt.halt_classification is None

    def test_classify_halt_static_durable(self):
        """Direct static test: durable halt."""
        from veritas_os.core.continuation_runtime.revalidator import ContinuationRevalidator
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus
        from veritas_os.core.continuation_runtime.snapshot import HeadroomState

        result = ContinuationRevalidator._classify_halt(
            ClaimStatus.HALTED,
            HeadroomState(remaining=0.0, threshold_suspension=0.0),
            is_durable=True,
        )
        assert result == "durable_state_transformation"

    def test_classify_halt_static_safety_pause(self):
        """Direct static test: safety pause (near escalation)."""
        from veritas_os.core.continuation_runtime.revalidator import ContinuationRevalidator
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus
        from veritas_os.core.continuation_runtime.snapshot import HeadroomState

        result = ContinuationRevalidator._classify_halt(
            ClaimStatus.HALTED,
            HeadroomState(remaining=0.2, threshold_escalation=0.3),
            is_durable=False,
        )
        assert result == "safety_pause"

    def test_classify_halt_static_bounded_interruption(self):
        """Direct static test: bounded interruption (headroom partially used)."""
        from veritas_os.core.continuation_runtime.revalidator import ContinuationRevalidator
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus
        from veritas_os.core.continuation_runtime.snapshot import HeadroomState

        result = ContinuationRevalidator._classify_halt(
            ClaimStatus.HALTED,
            HeadroomState(remaining=0.5, threshold_escalation=0.3),
            is_durable=False,
        )
        assert result == "bounded_interruption"

    def test_classify_halt_static_temporary_refusal(self):
        """Direct static test: temporary refusal (headroom=1.0, full)."""
        from veritas_os.core.continuation_runtime.revalidator import ContinuationRevalidator
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus
        from veritas_os.core.continuation_runtime.snapshot import HeadroomState

        result = ContinuationRevalidator._classify_halt(
            ClaimStatus.HALTED,
            HeadroomState(remaining=1.0, threshold_escalation=0.3),
            is_durable=False,
        )
        assert result == "temporary_refusal"

    def test_classify_halt_non_halted_returns_none(self):
        """Non-HALTED boundary → None."""
        from veritas_os.core.continuation_runtime.revalidator import ContinuationRevalidator
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus
        from veritas_os.core.continuation_runtime.snapshot import HeadroomState

        result = ContinuationRevalidator._classify_halt(
            ClaimStatus.LIVE,
            HeadroomState(),
            is_durable=False,
        )
        assert result is None


# =====================================================================
# Divergence detail
# =====================================================================


class TestDivergenceDetail:
    """Granular divergence classification."""

    def test_live_no_divergence(self):
        """LIVE boundary, allow prior → no divergence."""
        rv = _make_revalidator()
        lineage = _make_lineage()
        condition = _make_condition(prior_decision_status="allow")
        _, receipt = rv.revalidate(lineage, condition)
        assert receipt.divergence_detail is None
        assert receipt.divergence_flag is False

    def test_halted_durable_divergence(self):
        """Durable halt → local_pass_durable_halt."""
        rv = _make_revalidator()
        lineage = _make_lineage()
        condition = _make_condition(
            prior_decision_status="allow",
            context={"required_evidence": ["doc_a"], "satisfied_evidence": []},
        )
        _, receipt = rv.revalidate(lineage, condition)
        assert receipt.divergence_detail == "local_pass_durable_halt"

    def test_narrowed_durable_divergence(self):
        """Durable narrowing → local_pass_durable_narrowing."""
        rv = _make_revalidator()
        lineage = _make_lineage()
        condition = _make_condition(
            prior_decision_status="allow",
            context={"restricted_actions": ["execute"]},
        )
        _, receipt = rv.revalidate(lineage, condition)
        assert receipt.divergence_detail == "local_pass_durable_narrowing"

    def test_revoked_divergence(self):
        """REVOKED → local_pass_revoked."""
        rv = _make_revalidator()
        lineage = _make_lineage()
        condition = _make_condition(
            chain_id="",
            prior_decision_status="allow",
            context={"authorization": "", "policy_ref": ""},
        )
        _, receipt = rv.revalidate(lineage, condition)
        assert receipt.divergence_detail == "local_pass_revoked"

    def test_degraded_divergence(self):
        """DEGRADED → local_pass_receipt_degraded."""
        rv = _make_revalidator()
        lineage = _make_lineage()
        condition = _make_condition(
            prior_decision_status="allow",
            context={
                "required_evidence": ["doc_a", "doc_b"],
                "satisfied_evidence": ["doc_a"],
                "burden_threshold": 0.8,
            },
        )
        _, receipt = rv.revalidate(lineage, condition)
        assert receipt.divergence_detail == "local_pass_receipt_degraded"

    def test_escalated_divergence(self):
        """ESCALATED → local_pass_receipt_escalated."""
        rv = _make_revalidator()
        lineage = _make_lineage()
        condition = _make_condition(
            prior_decision_status="allow",
            context={"escalation_required": True},
        )
        _, receipt = rv.revalidate(lineage, condition)
        assert receipt.divergence_detail == "local_pass_receipt_escalated"

    def test_local_fail_continuation_live(self):
        """Local deny + LIVE boundary → local_fail_continuation_live."""
        from veritas_os.core.continuation_runtime.revalidator import ContinuationRevalidator

        result = ContinuationRevalidator._compute_divergence_detail(
            boundary_status=__import__(
                "veritas_os.core.continuation_runtime.lineage",
                fromlist=["ClaimStatus"],
            ).ClaimStatus.LIVE,
            is_durable=False,
            local_step_result="deny",
        )
        assert result == "local_fail_continuation_live"

    def test_compute_divergence_static_halted_receipt(self):
        """Static: non-durable halt → local_pass_receipt_halt."""
        from veritas_os.core.continuation_runtime.revalidator import ContinuationRevalidator
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus

        result = ContinuationRevalidator._compute_divergence_detail(
            boundary_status=ClaimStatus.HALTED,
            is_durable=False,
            local_step_result="allow",
        )
        assert result == "local_pass_receipt_halt"

    def test_compute_divergence_static_narrowed_receipt(self):
        """Static: non-durable narrowing → local_pass_receipt_narrowing."""
        from veritas_os.core.continuation_runtime.revalidator import ContinuationRevalidator
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus

        result = ContinuationRevalidator._compute_divergence_detail(
            boundary_status=ClaimStatus.NARROWED,
            is_durable=False,
            local_step_result="allow",
        )
        assert result == "local_pass_receipt_narrowing"


# =====================================================================
# Boundary predicates
# =====================================================================


class TestBoundaryPredicates:
    """Boundary predicates populated from reason codes."""

    def test_live_empty_predicates(self):
        """LIVE → no predicates."""
        rv = _make_revalidator()
        lineage = _make_lineage()
        _, receipt = rv.revalidate(lineage, _make_condition())
        assert receipt.boundary_predicates == []

    def test_halted_carries_headroom_predicate(self):
        """Halted → HEADROOM_COLLAPSED predicate."""
        rv = _make_revalidator()
        lineage = _make_lineage()
        condition = _make_condition(context={
            "required_evidence": ["doc_a"],
            "satisfied_evidence": [],
        })
        _, receipt = rv.revalidate(lineage, condition)
        assert "HEADROOM_COLLAPSED" in receipt.boundary_predicates

    def test_narrowed_carries_scope_predicate(self):
        """Narrowed → ACTION_CLASS_NOT_ALLOWED predicate."""
        rv = _make_revalidator()
        lineage = _make_lineage()
        condition = _make_condition(context={
            "restricted_actions": ["execute"],
        })
        _, receipt = rv.revalidate(lineage, condition)
        assert "ACTION_CLASS_NOT_ALLOWED" in receipt.boundary_predicates

    def test_revoked_carries_support_predicates(self):
        """Revoked → SUPPORT_LOST predicates."""
        rv = _make_revalidator()
        lineage = _make_lineage()
        condition = _make_condition(
            chain_id="",
            context={"authorization": "", "policy_ref": ""},
        )
        _, receipt = rv.revalidate(lineage, condition)
        assert len(receipt.boundary_predicates) > 0


# =====================================================================
# Prior state reference
# =====================================================================


class TestPriorStateRef:
    """Prior state reference linkage."""

    def test_first_step_prior_state_ref_is_none(self):
        """First step: no prior snapshot → prior_state_ref is None."""
        rv = _make_revalidator()
        lineage = _make_lineage()
        _, receipt = rv.revalidate(lineage, _make_condition())
        # First step has no prior snapshot and no lineage snapshot yet
        assert receipt.prior_state_ref is None

    def test_second_step_prior_state_ref_is_set(self):
        """Second step: prior snapshot provides prior_state_ref."""
        rv = _make_revalidator()
        lineage = _make_lineage()
        snap1, receipt1 = rv.revalidate(lineage, _make_condition(step_index=0))
        # Second step: lineage now has latest_snapshot_id
        _, receipt2 = rv.revalidate(lineage, _make_condition(step_index=1))
        assert receipt2.prior_state_ref == snap1.snapshot_id


# =====================================================================
# Serialization round-trips
# =====================================================================


class TestReceiptEnrichmentSerialization:
    """New receipt fields survive serialization."""

    def test_enrichment_fields_roundtrip(self):
        """All new fields survive to_dict / from_dict."""
        from veritas_os.core.continuation_runtime.receipt import ContinuationReceipt

        receipt = ContinuationReceipt(
            halt_occurred=True,
            narrowing_occurred=False,
            halt_classification="durable_state_transformation",
            divergence_detail="local_pass_durable_halt",
            boundary_predicates=["HEADROOM_COLLAPSED"],
            prior_state_ref="snap_abc123",
        )
        d = receipt.to_dict()
        assert d["halt_occurred"] is True
        assert d["narrowing_occurred"] is False
        assert d["halt_classification"] == "durable_state_transformation"
        assert d["divergence_detail"] == "local_pass_durable_halt"
        assert d["boundary_predicates"] == ["HEADROOM_COLLAPSED"]
        assert d["prior_state_ref"] == "snap_abc123"

        restored = ContinuationReceipt.from_dict(d)
        assert restored.halt_occurred is True
        assert restored.narrowing_occurred is False
        assert restored.halt_classification == "durable_state_transformation"
        assert restored.divergence_detail == "local_pass_durable_halt"
        assert restored.boundary_predicates == ["HEADROOM_COLLAPSED"]
        assert restored.prior_state_ref == "snap_abc123"

    def test_backward_compat_missing_new_fields(self):
        """Old dicts without new fields still deserialize correctly."""
        from veritas_os.core.continuation_runtime.receipt import ContinuationReceipt

        old_dict = {
            "receipt_id": "abc",
            "revalidation_status": "renewed",
            "revalidation_outcome": "renewed",
            "revalidation_reason_codes": [],
        }
        restored = ContinuationReceipt.from_dict(old_dict)
        assert restored.halt_occurred is False
        assert restored.narrowing_occurred is False
        assert restored.halt_classification is None
        assert restored.divergence_detail is None
        assert restored.boundary_predicates == []
        assert restored.prior_state_ref is None


# =====================================================================
# Coherence guard strengthening
# =====================================================================


class TestCoherenceGuardStrengthened:
    """Strengthened coherence guard for state/receipt contradiction prevention."""

    def test_revoked_boundary_live_state_is_violation(self):
        """Receipt boundary_outcome=revoked + snapshot LIVE → violation."""
        from veritas_os.core.continuation_runtime.revalidator import ContinuationRevalidator
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus
        from veritas_os.core.continuation_runtime.receipt import (
            ContinuationReceipt,
            RevalidationStatus,
        )
        from veritas_os.core.continuation_runtime.snapshot import ClaimStateSnapshot

        snap = ClaimStateSnapshot(claim_status=ClaimStatus.LIVE)
        receipt = ContinuationReceipt(
            snapshot_id=snap.snapshot_id,
            revalidation_status=RevalidationStatus.REVOKED,
            boundary_outcome="revoked",
            is_durable_promotion=True,
        )
        with pytest.raises(ValueError, match="Coherence violation"):
            ContinuationRevalidator._assert_coherence(snap, receipt)

    def test_durable_promotion_with_live_state_is_violation(self):
        """Receipt claims durable promotion + snapshot LIVE → violation."""
        from veritas_os.core.continuation_runtime.revalidator import ContinuationRevalidator
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus
        from veritas_os.core.continuation_runtime.receipt import (
            ContinuationReceipt,
            RevalidationStatus,
        )
        from veritas_os.core.continuation_runtime.snapshot import ClaimStateSnapshot

        snap = ClaimStateSnapshot(claim_status=ClaimStatus.LIVE)
        receipt = ContinuationReceipt(
            snapshot_id=snap.snapshot_id,
            revalidation_status=RevalidationStatus.NARROWED,
            boundary_outcome="narrowed",
            is_durable_promotion=True,
        )
        with pytest.raises(ValueError, match="Coherence violation"):
            ContinuationRevalidator._assert_coherence(snap, receipt)

    def test_receipt_only_halt_with_live_state_is_valid(self):
        """Receipt-only halt (not durable) + snapshot LIVE → valid."""
        from veritas_os.core.continuation_runtime.revalidator import ContinuationRevalidator
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus
        from veritas_os.core.continuation_runtime.receipt import (
            ContinuationReceipt,
            RevalidationStatus,
        )
        from veritas_os.core.continuation_runtime.snapshot import ClaimStateSnapshot

        snap = ClaimStateSnapshot(claim_status=ClaimStatus.LIVE)
        receipt = ContinuationReceipt(
            snapshot_id=snap.snapshot_id,
            revalidation_status=RevalidationStatus.HALTED,
            boundary_outcome="halted",
            is_durable_promotion=False,
        )
        # Should NOT raise — halt is receipt-only (not durable)
        ContinuationRevalidator._assert_coherence(snap, receipt)

    def test_durable_promotion_with_matching_state_is_valid(self):
        """Receipt claims durable promotion + snapshot matches → valid."""
        from veritas_os.core.continuation_runtime.revalidator import ContinuationRevalidator
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus
        from veritas_os.core.continuation_runtime.receipt import (
            ContinuationReceipt,
            RevalidationStatus,
        )
        from veritas_os.core.continuation_runtime.snapshot import ClaimStateSnapshot

        snap = ClaimStateSnapshot(claim_status=ClaimStatus.HALTED)
        receipt = ContinuationReceipt(
            snapshot_id=snap.snapshot_id,
            revalidation_status=RevalidationStatus.HALTED,
            boundary_outcome="halted",
            is_durable_promotion=True,
        )
        # Should NOT raise — consistent
        ContinuationRevalidator._assert_coherence(snap, receipt)
