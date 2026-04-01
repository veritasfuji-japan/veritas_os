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
        """LIVE状態では停止も縮小も発生しないことを検証する。"""
        rv = _make_revalidator()
        lineage = _make_lineage()
        _, receipt = rv.revalidate(lineage, _make_condition())
        assert receipt.halt_occurred is False
        assert receipt.narrowing_occurred is False

    def test_halted_sets_halt_occurred(self):
        """ヘッドルーム崩壊時にhalt_occurred=Trueとなることを検証する。"""
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
        """スコープ制限時にnarrowing_occurred=Trueとなることを検証する。"""
        rv = _make_revalidator()
        lineage = _make_lineage()
        condition = _make_condition(context={
            "restricted_actions": ["execute"],
        })
        _, receipt = rv.revalidate(lineage, condition)
        assert receipt.narrowing_occurred is True
        assert receipt.halt_occurred is False

    def test_degraded_no_halt_no_narrowing(self):
        """DEGRADED状態では停止も縮小も発生しないことを検証する。"""
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
        """ESCALATED状態では停止も縮小も発生しないことを検証する。"""
        rv = _make_revalidator()
        lineage = _make_lineage()
        condition = _make_condition(context={
            "escalation_required": True,
        })
        _, receipt = rv.revalidate(lineage, condition)
        assert receipt.halt_occurred is False
        assert receipt.narrowing_occurred is False

    def test_revoked_no_halt_no_narrowing(self):
        """REVOKED状態では停止も縮小も発生しないことを検証する（取消は独立カテゴリ）。"""
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
        """ヘッドルーム崩壊がdurable_state_transformationに分類されることを検証する。"""
        rv = _make_revalidator()
        lineage = _make_lineage()
        condition = _make_condition(context={
            "required_evidence": ["doc_a"],
            "satisfied_evidence": [],
        })
        _, receipt = rv.revalidate(lineage, condition)
        assert receipt.halt_classification == "durable_state_transformation"

    def test_no_halt_no_classification(self):
        """LIVE状態では停止分類がないことを検証する。"""
        rv = _make_revalidator()
        lineage = _make_lineage()
        _, receipt = rv.revalidate(lineage, _make_condition())
        assert receipt.halt_classification is None

    def test_classify_halt_static_durable(self):
        """静的テスト: 永続的停止の分類を検証する。"""
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
        """静的テスト: 安全一時停止（エスカレーション付近）の分類を検証する。"""
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
        """静的テスト: 制限付き中断（ヘッドルーム部分使用）の分類を検証する。"""
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
        """静的テスト: 一時的拒否（ヘッドルーム=1.0、満杯）の分類を検証する。"""
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
        """非HALTED境界ではNoneが返ることを検証する。"""
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
        """LIVE境界でallow先行時に乖離がないことを検証する。"""
        rv = _make_revalidator()
        lineage = _make_lineage()
        condition = _make_condition(prior_decision_status="allow")
        _, receipt = rv.revalidate(lineage, condition)
        assert receipt.divergence_detail is None
        assert receipt.divergence_flag is False

    def test_halted_durable_divergence(self):
        """永続的停止がlocal_pass_durable_haltとなることを検証する。"""
        rv = _make_revalidator()
        lineage = _make_lineage()
        condition = _make_condition(
            prior_decision_status="allow",
            context={
                "required_evidence": ["doc_a"],
                "satisfied_evidence": [],
                "headroom_collapse_irreversible": True,
            },
        )
        _, receipt = rv.revalidate(lineage, condition)
        assert receipt.divergence_detail == "local_pass_durable_halt"

    def test_halted_receipt_only_divergence(self):
        """可逆的停止がlocal_pass_receipt_haltとなることを検証する。"""
        rv = _make_revalidator()
        lineage = _make_lineage()
        condition = _make_condition(
            prior_decision_status="allow",
            context={"required_evidence": ["doc_a"], "satisfied_evidence": []},
        )
        _, receipt = rv.revalidate(lineage, condition)
        assert receipt.divergence_detail == "local_pass_receipt_halt"

    def test_narrowed_durable_divergence(self):
        """永続的縮小がlocal_pass_durable_narrowingとなることを検証する。"""
        rv = _make_revalidator()
        lineage = _make_lineage()
        condition = _make_condition(
            prior_decision_status="allow",
            context={
                "restricted_actions": ["execute"],
                "restrictions_durable": True,
            },
        )
        _, receipt = rv.revalidate(lineage, condition)
        assert receipt.divergence_detail == "local_pass_durable_narrowing"

    def test_narrowed_receipt_only_divergence(self):
        """一時的縮小がlocal_pass_receipt_narrowingとなることを検証する。"""
        rv = _make_revalidator()
        lineage = _make_lineage()
        condition = _make_condition(
            prior_decision_status="allow",
            context={"restricted_actions": ["execute"]},
        )
        _, receipt = rv.revalidate(lineage, condition)
        assert receipt.divergence_detail == "local_pass_receipt_narrowing"

    def test_revoked_divergence(self):
        """REVOKED時にlocal_pass_revokedとなることを検証する。"""
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
        """DEGRADED時にlocal_pass_receipt_degradedとなることを検証する。"""
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
        """ESCALATED時にlocal_pass_receipt_escalatedとなることを検証する。"""
        rv = _make_revalidator()
        lineage = _make_lineage()
        condition = _make_condition(
            prior_decision_status="allow",
            context={"escalation_required": True},
        )
        _, receipt = rv.revalidate(lineage, condition)
        assert receipt.divergence_detail == "local_pass_receipt_escalated"

    def test_local_fail_continuation_live(self):
        """ローカルdeny + LIVE境界でlocal_fail_continuation_liveとなることを検証する。"""
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
        """静的テスト: 非永続的停止がlocal_pass_receipt_haltとなることを検証する。"""
        from veritas_os.core.continuation_runtime.revalidator import ContinuationRevalidator
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus

        result = ContinuationRevalidator._compute_divergence_detail(
            boundary_status=ClaimStatus.HALTED,
            is_durable=False,
            local_step_result="allow",
        )
        assert result == "local_pass_receipt_halt"

    def test_compute_divergence_static_narrowed_receipt(self):
        """静的テスト: 非永続的縮小がlocal_pass_receipt_narrowingとなることを検証する。"""
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
        """LIVE状態では述語が空であることを検証する。"""
        rv = _make_revalidator()
        lineage = _make_lineage()
        _, receipt = rv.revalidate(lineage, _make_condition())
        assert receipt.boundary_predicates == []

    def test_halted_carries_headroom_predicate(self):
        """停止時にHEADROOM_COLLAPSED述語が設定されることを検証する。"""
        rv = _make_revalidator()
        lineage = _make_lineage()
        condition = _make_condition(context={
            "required_evidence": ["doc_a"],
            "satisfied_evidence": [],
        })
        _, receipt = rv.revalidate(lineage, condition)
        assert "HEADROOM_COLLAPSED" in receipt.boundary_predicates

    def test_narrowed_carries_scope_predicate(self):
        """縮小時にACTION_CLASS_NOT_ALLOWED述語が設定されることを検証する。"""
        rv = _make_revalidator()
        lineage = _make_lineage()
        condition = _make_condition(context={
            "restricted_actions": ["execute"],
        })
        _, receipt = rv.revalidate(lineage, condition)
        assert "ACTION_CLASS_NOT_ALLOWED" in receipt.boundary_predicates

    def test_revoked_carries_support_predicates(self):
        """取消時にSUPPORT_LOST述語が設定されることを検証する。"""
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
        """最初のステップで先行スナップショットがなくprior_state_refがNoneであることを検証する。"""
        rv = _make_revalidator()
        lineage = _make_lineage()
        _, receipt = rv.revalidate(lineage, _make_condition())
        # First step has no prior snapshot and no lineage snapshot yet
        assert receipt.prior_state_ref is None

    def test_second_step_prior_state_ref_is_set(self):
        """2番目のステップで先行スナップショットがprior_state_refを提供することを検証する。"""
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
        """全ての新規フィールドがto_dict/from_dictを経ても保持されることを検証する。"""
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
        """新規フィールドのない古い辞書でも正しくデシリアライズされることを検証する。"""
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
        """レシートboundary_outcome=revoked + スナップショットLIVEが整合性違反となることを検証する。"""
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
        """レシートが永続昇格を主張しスナップショットがLIVEの場合に整合性違反となることを検証する。"""
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
        """レシートのみの停止（非永続）+ スナップショットLIVEが有効であることを検証する。"""
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
        """レシートが永続昇格を主張しスナップショットが一致する場合に有効であることを検証する。"""
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
