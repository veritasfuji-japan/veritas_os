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
        """LIVEアウトカムでは永続的結果も境界昇格もないことを検証する。"""
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
        """ヘッドルーム崩壊時にレシートと状態の両方で停止（永続的停止）となることを検証する。"""
        rv = self._make_revalidator()
        lineage = self._make_lineage()
        # Set required_evidence with none satisfied → current_level=0.0 → headroom=0.0
        # Mark collapse as irreversible to trigger durable promotion.
        condition = self._make_condition(context={
            "required_evidence": ["doc_a"],
            "satisfied_evidence": [],
            "headroom_collapse_irreversible": True,
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

    def test_halted_receipt_only_when_collapse_reversible(self):
        """可逆的ヘッドルーム崩壊ではレシートのみ停止（状態はLIVE維持）を検証する。"""
        rv = self._make_revalidator()
        lineage = self._make_lineage()
        # headroom=0 but collapse is NOT irreversible → receipt-only halt
        condition = self._make_condition(context={
            "required_evidence": ["doc_a"],
            "satisfied_evidence": [],
        })
        snap, receipt = rv.revalidate(lineage, condition)

        # Receipt records the halt
        assert receipt.boundary_outcome == "halted"
        assert receipt.revalidation_status.value == "halted"
        assert receipt.halt_occurred is True
        # But it's not promoted to state
        assert receipt.is_durable_promotion is False
        assert receipt.provisional_vs_durable == "provisional"
        # State remains LIVE (standing preserved)
        assert snap.claim_status.value == "live"
        assert snap.durable_consequence is None

    # ------------------------------------------------------------------
    # NARROWED: receipt-first, durable when scope restrictions present
    # ------------------------------------------------------------------

    def test_narrowed_receipt_first_with_durable_scope_reduction(self):
        """スコープ制限時にレシートと状態の両方で縮小（永続的縮小）となることを検証する。"""
        rv = self._make_revalidator()
        lineage = self._make_lineage()
        condition = self._make_condition(context={
            "restricted_actions": ["execute"],
            "restrictions_durable": True,
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

    def test_narrowed_receipt_only_when_restrictions_not_durable(self):
        """一時的スコープ制限ではレシートのみ縮小（状態はLIVE維持）を検証する。"""
        rv = self._make_revalidator()
        lineage = self._make_lineage()
        # Restricted actions present but NOT marked durable → receipt-only
        condition = self._make_condition(context={
            "restricted_actions": ["execute"],
        })
        snap, receipt = rv.revalidate(lineage, condition)

        # Receipt records the narrowing
        assert receipt.boundary_outcome == "narrowed"
        assert receipt.revalidation_status.value == "narrowed"
        assert receipt.narrowing_occurred is True
        # But it's not promoted to state
        assert receipt.is_durable_promotion is False
        assert receipt.provisional_vs_durable == "provisional"
        assert receipt.reopening_eligible is True  # provisional = reopenable
        # State remains LIVE (standing preserved)
        assert snap.claim_status.value == "live"
        assert snap.durable_consequence is None

    def test_narrowed_reopening_eligible_when_not_durable(self):
        """縮小再開テスト: 永続的なら再開不可であることを検証する。"""
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
        """負担超過時にレシートでdegradedとなることを検証する。"""
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
        """エスカレーション必要時にレシートでescalatedとなることを検証する。"""
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
        """サポート喪失時にレシートと状態の両方で取消（不可逆）となることを検証する。"""
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
        """全レシートがboundary_outcomeを持つことを検証する。"""
        rv = self._make_revalidator()
        lineage = self._make_lineage()
        snap, receipt = rv.revalidate(lineage, self._make_condition())
        assert receipt.boundary_outcome is not None
        assert receipt.boundary_outcome == "live"

    def test_receipt_has_provisional_vs_durable(self):
        """非LIVEアウトカムがprovisional_vs_durable評価を持つことを検証する。"""
        rv = self._make_revalidator()
        lineage = self._make_lineage()
        condition = self._make_condition(context={
            "escalation_required": True,
        })
        snap, receipt = rv.revalidate(lineage, condition)
        assert receipt.provisional_vs_durable in ("provisional", "durable_promotable")

    def test_receipt_has_digest_summaries(self):
        """レシートが監査用ダイジェスト要約を持つことを検証する。"""
        rv = self._make_revalidator()
        lineage = self._make_lineage()
        snap, receipt = rv.revalidate(lineage, self._make_condition())
        assert receipt.support_basis_digest is not None
        assert receipt.scope_digest is not None
        assert receipt.burden_headroom_digest is not None

    def test_receipt_carries_reason_codes(self):
        """非LIVEレシートが理由コードを持つことを検証する。"""
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
        """LIVE状態では永続的結果がないことを検証する。"""
        from veritas_os.core.continuation_runtime.snapshot import (
            ClaimStateSnapshot,
        )
        snap = ClaimStateSnapshot()
        assert snap.durable_consequence is None

    def test_durable_consequence_serialization_roundtrip(self):
        """DurableConsequenceがto_dict/from_dictを経ても保持されることを検証する。"""
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
        """None durable_consequenceがラウンドトリップを経ても保持されることを検証する。"""
        from veritas_os.core.continuation_runtime.snapshot import ClaimStateSnapshot
        snap = ClaimStateSnapshot()
        d = snap.to_dict()
        assert d["durable_consequence"] is None
        restored = ClaimStateSnapshot.from_dict(d)
        assert restored.durable_consequence is None


class TestReceiptSerialization:
    """Receipt proof-bearing fields survive serialization."""

    def test_receipt_new_fields_roundtrip(self):
        """新規レシートフィールドがto_dict/from_dictを経ても保持されることを検証する。"""
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
        """REVOKEDがスナップショットとレシートの両方に存在する必要があることを検証する。"""
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
        """レシートがHALTEDでスナップショットがLIVEの場合に有効であることを検証する（レシート優先）。"""
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
        """レシートが永続的HALTEDを主張しスナップショットがLIVEの場合に違反となることを検証する。"""
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
        """スナップショットがHALTEDでレシートがHALTEDでない場合に違反となることを検証する。"""
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
        """LIVE状態では永続性がないことを検証する。"""
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
        """REVOKEDは常に永続的であることを検証する。"""
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
        """ヘッドルーム不可逆崩壊時にHALTEDが永続的であることを検証する。"""
        from veritas_os.core.continuation_runtime.revalidator import ContinuationRevalidator
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus
        from veritas_os.core.continuation_runtime.snapshot import Scope, HeadroomState

        dc, status = ContinuationRevalidator._assess_durability(
            boundary_status=ClaimStatus.HALTED,
            scope=Scope(),
            headroom_state=HeadroomState(
                remaining=0.0, threshold_suspension=0.0,
                collapse_irreversible=True,
            ),
            revocation_conditions=[],
        )
        assert dc is not None
        assert dc.has_durable_halt is True
        assert status == ClaimStatus.HALTED

    def test_halted_not_durable_when_collapse_reversible(self):
        """可逆的ヘッドルーム崩壊での停止がレシートのみであることを検証する。"""
        from veritas_os.core.continuation_runtime.revalidator import ContinuationRevalidator
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus
        from veritas_os.core.continuation_runtime.snapshot import Scope, HeadroomState

        dc, status = ContinuationRevalidator._assess_durability(
            boundary_status=ClaimStatus.HALTED,
            scope=Scope(),
            headroom_state=HeadroomState(remaining=0.0, threshold_suspension=0.0),
            revocation_conditions=[],
        )
        assert dc is None
        assert status == ClaimStatus.LIVE

    def test_halted_not_durable_when_headroom_positive(self):
        """正のヘッドルームでの停止がレシートのみで永続的結果なしであることを検証する。"""
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
        """永続的制限がある場合にNARROWEDが永続的であることを検証する。"""
        from veritas_os.core.continuation_runtime.revalidator import ContinuationRevalidator
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus
        from veritas_os.core.continuation_runtime.snapshot import Scope, HeadroomState

        dc, status = ContinuationRevalidator._assess_durability(
            boundary_status=ClaimStatus.NARROWED,
            scope=Scope(
                restricted_action_classes=["execute"],
                restrictions_durable=True,
            ),
            headroom_state=HeadroomState(),
            revocation_conditions=[],
        )
        assert dc is not None
        assert dc.has_durable_scope_reduction is True
        assert status == ClaimStatus.NARROWED

    def test_narrowed_not_durable_when_restrictions_provisional(self):
        """一時的制限でのNARROWEDがレシートのみであることを検証する。"""
        from veritas_os.core.continuation_runtime.revalidator import ContinuationRevalidator
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus
        from veritas_os.core.continuation_runtime.snapshot import Scope, HeadroomState

        dc, status = ContinuationRevalidator._assess_durability(
            boundary_status=ClaimStatus.NARROWED,
            scope=Scope(restricted_action_classes=["execute"]),
            headroom_state=HeadroomState(),
            revocation_conditions=[],
        )
        assert dc is None
        assert status == ClaimStatus.LIVE

    def test_degraded_receipt_only(self):
        """DEGRADEDがレシートのみであることを検証する。"""
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
        """ESCALATEDがレシートのみであることを検証する。"""
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
