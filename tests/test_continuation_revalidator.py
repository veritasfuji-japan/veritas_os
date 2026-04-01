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
        """再検証が常にスナップショットとレシートの両方を返すことを検証する。"""
        from veritas_os.core.continuation_runtime.snapshot import ClaimStateSnapshot
        from veritas_os.core.continuation_runtime.receipt import ContinuationReceipt

        rv = self._make_revalidator()
        lineage = self._make_lineage()
        condition = self._make_condition()

        snapshot, receipt = rv.revalidate(lineage, condition)

        assert isinstance(snapshot, ClaimStateSnapshot)
        assert isinstance(receipt, ContinuationReceipt)

    def test_snapshot_receipt_share_snapshot_id(self):
        """スナップショットとレシートが同じsnapshot_idを参照することを検証する。"""
        rv = self._make_revalidator()
        lineage = self._make_lineage()
        condition = self._make_condition()

        snapshot, receipt = rv.revalidate(lineage, condition)

        assert receipt.snapshot_id == snapshot.snapshot_id

    def test_snapshot_receipt_share_lineage_id(self):
        """両方が同じclaim_lineage_idを参照することを検証する。"""
        rv = self._make_revalidator()
        lineage = self._make_lineage()
        condition = self._make_condition()

        snapshot, receipt = rv.revalidate(lineage, condition)

        assert snapshot.claim_lineage_id == lineage.claim_lineage_id
        assert receipt.claim_lineage_id == lineage.claim_lineage_id

    def test_live_status_yields_renewed(self):
        """デフォルト条件でLIVE/RENEWED、乖離なしとなることを検証する。"""
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
        """再検証後にリネージュの可変ポインタが更新されることを検証する。"""
        rv = self._make_revalidator()
        lineage = self._make_lineage()
        condition = self._make_condition()

        snapshot, receipt = rv.revalidate(lineage, condition)

        assert lineage.latest_snapshot_id == snapshot.snapshot_id
        assert lineage.current_claim_status == snapshot.claim_status

    def test_revoked_is_terminal(self):
        """一度取消されると新条件に関わらず取消状態のままであることを検証する。"""
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
        """権限もポリシーもない場合にREVOKEDとなることを検証する。"""
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
        """制限アクションクラスが存在する場合にレシートでNARROWED、状態はレシート優先でLIVEを検証する。"""
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus
        from veritas_os.core.continuation_runtime.receipt import RevalidationStatus

        rv = self._make_revalidator()
        lineage = self._make_lineage()
        condition = self._make_condition(
            context={"restricted_actions": ["execute"]},
        )

        snapshot, receipt = rv.revalidate(lineage, condition)

        # Receipt records boundary outcome
        assert receipt.revalidation_status == RevalidationStatus.NARROWED
        assert receipt.divergence_flag is True
        # State stays LIVE: restrictions are not marked durable
        assert snapshot.claim_status == ClaimStatus.LIVE

    def test_escalation_required_yields_escalated(self):
        """スコープのescalation_requiredによりレシートでESCALATEDとなることを検証する（レシート優先）。"""
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus
        from veritas_os.core.continuation_runtime.receipt import RevalidationStatus

        rv = self._make_revalidator()
        lineage = self._make_lineage()
        condition = self._make_condition(
            context={"escalation_required": True},
        )

        snapshot, receipt = rv.revalidate(lineage, condition)

        # Receipt-first: boundary outcome is ESCALATED
        assert receipt.revalidation_status == RevalidationStatus.ESCALATED
        assert receipt.boundary_outcome == "escalated"
        # State: receipt-only (no durable consequence)
        assert snapshot.claim_status == ClaimStatus.LIVE

    def test_burden_threshold_exceeded_yields_degraded(self):
        """負担が閾値以下でレシートにDEGRADEDとなることを検証する（レシート優先）。"""
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus
        from veritas_os.core.continuation_runtime.receipt import RevalidationStatus

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

        # Receipt-first: boundary outcome is DEGRADED
        assert receipt.revalidation_status == RevalidationStatus.DEGRADED
        assert receipt.boundary_outcome == "degraded"
        # State: receipt-only (no durable consequence)
        assert snapshot.claim_status == ClaimStatus.LIVE

    def test_snapshot_has_law_version(self):
        """スナップショットに適用されたlaw_versionが記録されることを検証する。"""
        rv = self._make_revalidator()
        lineage = self._make_lineage()
        condition = self._make_condition()

        snapshot, receipt = rv.revalidate(lineage, condition)

        assert snapshot.law_version != ""
        assert snapshot.law_version == "v0.1.0-shadow"

    def test_receipt_has_law_version_id(self):
        """レシートにlaw_version_idが記録されることを検証する。"""
        rv = self._make_revalidator()
        lineage = self._make_lineage()
        condition = self._make_condition()

        snapshot, receipt = rv.revalidate(lineage, condition)

        assert receipt.law_version_id == "v0.1.0-shadow"

    def test_snapshot_has_scope(self):
        """スナップショットのスコープが明示的であることを検証する。"""
        rv = self._make_revalidator()
        lineage = self._make_lineage()
        condition = self._make_condition()

        snapshot, receipt = rv.revalidate(lineage, condition)

        assert snapshot.scope is not None
        assert isinstance(snapshot.scope.allowed_action_classes, list)

    def test_snapshot_has_burden_state(self):
        """スナップショットがburden_stateを持つことを検証する（必須フィールド）。"""
        rv = self._make_revalidator()
        lineage = self._make_lineage()
        condition = self._make_condition()

        snapshot, receipt = rv.revalidate(lineage, condition)

        assert snapshot.burden_state is not None
        assert hasattr(snapshot.burden_state, "threshold")

    def test_snapshot_has_support_basis(self):
        """スナップショットが構造化されたsupport_basisを持つことを検証する。"""
        rv = self._make_revalidator()
        lineage = self._make_lineage()
        condition = self._make_condition()

        snapshot, receipt = rv.revalidate(lineage, condition)

        sb = snapshot.support_basis
        # At minimum, authority or policy should be present for LIVE
        assert sb.authority or sb.policy

    def test_receipt_has_digests(self):
        """レシートが監査用ダイジェスト要約を持つことを検証する。"""
        rv = self._make_revalidator()
        lineage = self._make_lineage()
        condition = self._make_condition()

        snapshot, receipt = rv.revalidate(lineage, condition)

        assert receipt.support_basis_digest is not None
        assert receipt.scope_digest is not None
        assert receipt.burden_headroom_digest is not None

    def test_snapshot_serialization_roundtrip(self):
        """スナップショットがto_dict→from_dictを経ても保持されることを検証する。"""
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
        """レシートがto_dict→from_dictを経ても保持されることを検証する。"""
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
        """整合性ガードがスナップショット/レシートの不整合を検出することを検証する。"""
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
        """境界がLIVE以外の場合にレシートの乖離フラグがTrueであることを検証する。"""
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus
        from veritas_os.core.continuation_runtime.receipt import RevalidationStatus

        rv = self._make_revalidator()
        lineage = self._make_lineage()
        condition = self._make_condition(
            context={"restricted_actions": ["execute"]},
        )

        snapshot, receipt = rv.revalidate(lineage, condition)

        # Receipt boundary is NARROWED (divergence from LIVE)
        assert receipt.revalidation_status == RevalidationStatus.NARROWED
        assert receipt.divergence_flag is True


# =====================================================================
# Convenience function tests
# =====================================================================


class TestRunContinuationRevalidationShadow:
    """Tests for the pipeline integration helper function."""

    def test_returns_three_objects(self):
        """3つのオブジェクト（リネージュ、スナップショット、レシート）を返すことを検証する。"""
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
        """リネージュが未提供の場合に自動生成されることを検証する。"""
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
        """状態側に全ての必須フィールドが含まれることを検証する。"""
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
        """レシート側に全ての必須フィールドが含まれることを検証する。"""
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
        """スナップショットとレシートが別々の辞書であり統合されていないことを検証する。"""
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
        """継続がbool/enumではなくリッチな構造体であることを検証する。"""
        snap_d, rcpt_d = self._run_revalidation()

        # Both must be dicts with multiple fields
        assert isinstance(snap_d, dict) and len(snap_d) > 5
        assert isinstance(rcpt_d, dict) and len(rcpt_d) > 5

    def test_law_version_present(self):
        """law_versionが空でないことを検証する。"""
        snap_d, rcpt_d = self._run_revalidation()

        assert snap_d["law_version"] != ""
        assert rcpt_d["law_version_id"] != ""


# =====================================================================
# Feature flag off — zero side effects
# =====================================================================


class TestFeatureFlagOff:
    """Verify that flag off → zero computation in PipelineContext."""

    def test_pipeline_context_defaults_none(self):
        """PipelineContextの継続フィールドがデフォルトでNoneであることを検証する。"""
        from veritas_os.core.pipeline_types import PipelineContext

        ctx = PipelineContext()

        assert ctx.continuation_snapshot is None
        assert ctx.continuation_receipt is None

    def test_flag_off_default(self):
        """VERITAS_CAP_CONTINUATION_RUNTIMEがデフォルトでFalseであることを検証する。"""
        # Ensure env var is not set
        env_val = os.environ.pop("VERITAS_CAP_CONTINUATION_RUNTIME", None)
        try:
            from veritas_os.core.config import _parse_bool
            assert _parse_bool("VERITAS_CAP_CONTINUATION_RUNTIME", False) is False
        finally:
            if env_val is not None:
                os.environ["VERITAS_CAP_CONTINUATION_RUNTIME"] = env_val

    def test_response_omits_continuation_when_flag_off(self):
        """ctxにスナップショットがない場合にassemble_responseがcontinuationキーを省略することを検証する。"""
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
        """スナップショット/レシートが設定されている場合にcontinuationが含まれることを検証する。"""
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
        """ローカルステップがallowだが継続がdegradedの場合にレシートで乖離が可視であることを検証する。"""
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

        # Receipt: boundary outcome is degraded
        assert receipt.boundary_outcome == "degraded"
        # State: receipt-first (not durable)
        assert snapshot.to_dict()["claim_status"] == "live"
        assert receipt.divergence_flag is True
        assert receipt.prior_decision_continuity_ref == "allow"
        # Advisory only — should_refuse is False for degraded
        assert receipt.should_refuse_before_effect is False

    def test_local_allow_with_continuation_revoked(self):
        """ローカルステップがallowだが継続がrevokedの場合に乖離と助言的拒否を検証する。"""
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


# =====================================================================
# Data model unit tests (Task 5 — snapshot/receipt boundary hardening)
# =====================================================================


class TestContinuationClaimLineageCreation:
    """ContinuationClaimLineage creation and invariants."""

    def test_creation_defaults(self):
        """リネージュのデフォルト値を検証する。"""
        from veritas_os.core.continuation_runtime.lineage import (
            ContinuationClaimLineage,
            ClaimStatus,
        )

        lineage = ContinuationClaimLineage()
        assert lineage.claim_lineage_id  # non-empty uuid
        assert lineage.current_claim_status == ClaimStatus.LIVE
        assert lineage.is_revoked is False
        assert lineage.revoked_at is None
        assert lineage.latest_snapshot_id is None

    def test_creation_with_chain_id(self):
        """chain_id指定でのリネージュ生成を検証する。"""
        from veritas_os.core.continuation_runtime.lineage import ContinuationClaimLineage

        lineage = ContinuationClaimLineage(chain_id="c-1", origin_ref="step:0")
        assert lineage.chain_id == "c-1"
        assert lineage.origin_ref == "step:0"

    def test_serialization_roundtrip(self):
        """リネージュのシリアライズ往復を検証する。"""
        from veritas_os.core.continuation_runtime.lineage import (
            ContinuationClaimLineage,
            ClaimStatus,
        )

        lineage = ContinuationClaimLineage(
            chain_id="c-rt",
            current_claim_status=ClaimStatus.NARROWED,
        )
        d = lineage.to_dict()
        restored = ContinuationClaimLineage.from_dict(d)

        assert restored.claim_lineage_id == lineage.claim_lineage_id
        assert restored.current_claim_status == ClaimStatus.NARROWED
        assert restored.chain_id == "c-rt"

    def test_claim_status_enum_values(self):
        """ClaimStatusの列挙値を検証する。"""
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus

        expected = {"live", "narrowed", "degraded", "escalated", "halted", "revoked"}
        actual = {s.value for s in ClaimStatus}
        assert actual == expected


class TestClaimStateSnapshotCreation:
    """ClaimStateSnapshot creation and structural invariants."""

    def test_creation_defaults(self):
        """スナップショットのデフォルト値を検証する。"""
        from veritas_os.core.continuation_runtime.snapshot import ClaimStateSnapshot
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus

        snap = ClaimStateSnapshot()
        assert snap.snapshot_id  # non-empty
        assert snap.claim_status == ClaimStatus.LIVE
        assert snap.support_basis is not None
        assert snap.scope is not None
        assert snap.burden_state is not None
        assert snap.headroom_state is not None
        assert snap.law_version == ""

    def test_snapshot_does_not_contain_receipt_fields(self):
        """スナップショットにrevalidation_statusやdivergence等のレシートフィールドが含まれないことを検証する。"""
        from veritas_os.core.continuation_runtime.snapshot import ClaimStateSnapshot

        snap = ClaimStateSnapshot()
        d = snap.to_dict()
        # These belong to receipt, not snapshot
        assert "revalidation_status" not in d
        assert "revalidation_outcome" not in d
        assert "divergence_flag" not in d
        assert "should_refuse_before_effect" not in d
        assert "local_step_result" not in d
        assert "prior_decision_continuity_ref" not in d
        assert "parent_receipt_ref" not in d
        assert "receipt_hash_or_attestation" not in d

    def test_support_basis_sub_structure(self):
        """SupportBasisのサブ構造体のシリアライズ往復を検証する。"""
        from veritas_os.core.continuation_runtime.snapshot import SupportBasis

        sb = SupportBasis(authority="chain:x", policy="default", evidence="ev:2")
        d = sb.to_dict()
        restored = SupportBasis.from_dict(d)
        assert restored.authority == "chain:x"
        assert restored.policy == "default"

    def test_scope_sub_structure(self):
        """Scopeのサブ構造体のシリアライズ往復を検証する。"""
        from veritas_os.core.continuation_runtime.snapshot import Scope

        scope = Scope(
            allowed_action_classes=["query"],
            restricted_action_classes=["execute"],
            escalation_required=True,
        )
        d = scope.to_dict()
        restored = Scope.from_dict(d)
        assert restored.escalation_required is True
        assert "execute" in restored.restricted_action_classes

    def test_burden_state_sub_structure(self):
        """BurdenStateのサブ構造体のシリアライズ往復を検証する。"""
        from veritas_os.core.continuation_runtime.snapshot import BurdenState

        bs = BurdenState(
            required_evidence=["e1", "e2"],
            satisfied_evidence=["e1"],
            threshold=1.0,
            current_level=0.5,
        )
        d = bs.to_dict()
        restored = BurdenState.from_dict(d)
        assert restored.current_level == 0.5
        assert len(restored.required_evidence) == 2

    def test_headroom_state_sub_structure(self):
        """HeadroomStateのサブ構造体のシリアライズ往復を検証する。"""
        from veritas_os.core.continuation_runtime.snapshot import HeadroomState

        hs = HeadroomState(remaining=0.7, threshold_escalation=0.3, threshold_suspension=0.0)
        d = hs.to_dict()
        restored = HeadroomState.from_dict(d)
        assert restored.remaining == 0.7

    def test_revocation_condition_sub_structure(self):
        """RevocationConditionのサブ構造体のシリアライズ往復を検証する。"""
        from veritas_os.core.continuation_runtime.snapshot import RevocationCondition

        rc = RevocationCondition(
            condition_id="auth", description="Must have auth", is_met=True
        )
        d = rc.to_dict()
        restored = RevocationCondition.from_dict(d)
        assert restored.is_met is True

    def test_full_serialization_roundtrip(self):
        """全フィールドを含むスナップショットの完全なシリアライズ往復を検証する。"""
        from veritas_os.core.continuation_runtime.snapshot import (
            ClaimStateSnapshot,
            SupportBasis,
            Scope,
            BurdenState,
            HeadroomState,
            RevocationCondition,
        )
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus

        snap = ClaimStateSnapshot(
            claim_lineage_id="lin-1",
            support_basis=SupportBasis(authority="a", policy="p"),
            scope=Scope(allowed_action_classes=["query"]),
            burden_state=BurdenState(required_evidence=["e1"], current_level=0.5),
            headroom_state=HeadroomState(remaining=0.5),
            law_version="v0.1.0-shadow",
            revocation_conditions=[
                RevocationCondition(condition_id="rc1", is_met=False)
            ],
            claim_status=ClaimStatus.DEGRADED,
        )
        d = snap.to_dict()
        restored = ClaimStateSnapshot.from_dict(d)

        assert restored.claim_lineage_id == "lin-1"
        assert restored.claim_status == ClaimStatus.DEGRADED
        assert restored.law_version == "v0.1.0-shadow"
        assert len(restored.revocation_conditions) == 1


class TestContinuationReceiptGeneration:
    """ContinuationReceipt generation and structural invariants."""

    def test_creation_defaults(self):
        """レシートのデフォルト値を検証する。"""
        from veritas_os.core.continuation_runtime.receipt import (
            ContinuationReceipt,
            RevalidationStatus,
            RevalidationOutcome,
        )

        rcpt = ContinuationReceipt()
        assert rcpt.receipt_id  # non-empty
        assert rcpt.revalidation_status == RevalidationStatus.RENEWED
        assert rcpt.revalidation_outcome == RevalidationOutcome.RENEWED
        assert rcpt.divergence_flag is False
        assert rcpt.should_refuse_before_effect is False

    def test_receipt_does_not_contain_state_fields(self):
        """レシートにsupport_basisやburden_state等の状態フィールドが含まれないことを検証する。"""
        from veritas_os.core.continuation_runtime.receipt import ContinuationReceipt

        rcpt = ContinuationReceipt()
        d = rcpt.to_dict()
        assert "support_basis" not in d
        assert "burden_state" not in d
        assert "headroom_state" not in d
        assert "scope" not in d
        assert "revocation_conditions" not in d

    def test_revalidation_status_on_receipt_side(self):
        """revalidation_statusがレシート側に属することを検証する。"""
        from veritas_os.core.continuation_runtime.receipt import (
            ContinuationReceipt,
            RevalidationStatus,
        )

        rcpt = ContinuationReceipt(
            revalidation_status=RevalidationStatus.DEGRADED,
        )
        assert rcpt.revalidation_status == RevalidationStatus.DEGRADED

    def test_revalidation_outcome_on_receipt_side(self):
        """revalidation_outcomeがレシート側に属することを検証する。"""
        from veritas_os.core.continuation_runtime.receipt import (
            ContinuationReceipt,
            RevalidationOutcome,
        )

        rcpt = ContinuationReceipt(
            revalidation_outcome=RevalidationOutcome.ESCALATED,
        )
        assert rcpt.revalidation_outcome == RevalidationOutcome.ESCALATED

    def test_prior_decision_continuity_on_receipt_side(self):
        """prior_decision_continuity_refがレシート側に属することを検証する。"""
        from veritas_os.core.continuation_runtime.receipt import ContinuationReceipt

        rcpt = ContinuationReceipt(
            prior_decision_continuity_ref="allow",
        )
        assert rcpt.prior_decision_continuity_ref == "allow"

    def test_receipt_serialization_roundtrip_with_reason_codes(self):
        """理由コード付きレシートのシリアライズ往復を検証する。"""
        from veritas_os.core.continuation_runtime.receipt import (
            ContinuationReceipt,
            RevalidationStatus,
            RevalidationOutcome,
        )
        from veritas_os.core.continuation_runtime.reason_codes import ReasonCode

        rcpt = ContinuationReceipt(
            revalidation_status=RevalidationStatus.REVOKED,
            revalidation_outcome=RevalidationOutcome.REVOKED,
            revalidation_reason_codes=[
                ReasonCode.SUPPORT_LOST_APPROVAL,
                ReasonCode.SUPPORT_LOST_POLICY_SCOPE,
            ],
            prior_decision_continuity_ref="allow",
            divergence_flag=True,
            should_refuse_before_effect=True,
        )
        d = rcpt.to_dict()
        restored = ContinuationReceipt.from_dict(d)

        assert restored.revalidation_status == RevalidationStatus.REVOKED
        assert len(restored.revalidation_reason_codes) == 2
        assert ReasonCode.SUPPORT_LOST_APPROVAL in restored.revalidation_reason_codes
        assert restored.divergence_flag is True

    def test_receipt_revalidation_status_enum_values(self):
        """RevalidationStatusの列挙値を検証する。"""
        from veritas_os.core.continuation_runtime.receipt import RevalidationStatus

        expected = {"renewed", "narrowed", "degraded", "escalated", "halted", "revoked", "failed"}
        actual = {s.value for s in RevalidationStatus}
        assert actual == expected


class TestContinuationLawPackResolution:
    """ContinuationLawPack resolution and invariants."""

    def test_default_law_pack(self):
        """デフォルトのlaw packの値を検証する。"""
        from veritas_os.core.continuation_runtime.lawpack import (
            ContinuationLawPack,
            EvaluationMode,
        )
        from veritas_os.core.continuation_runtime.revalidator import _default_law_pack

        pack = _default_law_pack()
        assert pack.law_version_id == "v0.1.0-shadow"
        assert pack.evaluation_mode == EvaluationMode.SHADOW
        assert len(pack.rule_refs) > 0

    def test_law_pack_serialization_roundtrip(self):
        """LawPackのシリアライズ往復を検証する。"""
        from veritas_os.core.continuation_runtime.lawpack import (
            ContinuationLawPack,
            EvaluationMode,
        )

        pack = ContinuationLawPack(
            law_version_id="v1.0.0",
            policy_family="test",
            evaluation_mode=EvaluationMode.ADVISORY,
            rule_refs=["rule_a", "rule_b"],
        )
        d = pack.to_dict()
        restored = ContinuationLawPack.from_dict(d)
        assert restored.law_version_id == "v1.0.0"
        assert restored.evaluation_mode == EvaluationMode.ADVISORY
        assert len(restored.rule_refs) == 2

    def test_evaluation_mode_enum_values(self):
        """EvaluationModeの列挙値を検証する。"""
        from veritas_os.core.continuation_runtime.lawpack import EvaluationMode

        expected = {"shadow", "advisory", "enforce"}
        actual = {m.value for m in EvaluationMode}
        assert actual == expected

    def test_law_pack_rule_refs_non_empty_in_default(self):
        """デフォルトlaw packのrule_refsが空でないことを検証する。"""
        from veritas_os.core.continuation_runtime.revalidator import _default_law_pack

        pack = _default_law_pack()
        assert "support_basis_present" in pack.rule_refs
        assert "scope_within_bounds" in pack.rule_refs
        assert "burden_below_threshold" in pack.rule_refs
        assert "headroom_positive" in pack.rule_refs


class TestReasonCodeMapping:
    """Reason code mapping and coverage."""

    def test_all_reason_codes_exist(self):
        """全ての理由コードが存在することを検証する。"""
        from veritas_os.core.continuation_runtime.reason_codes import ReasonCode

        expected = {
            "SUPPORT_LOST_POLICY_SCOPE",
            "SUPPORT_LOST_WORLD_STATE",
            "SUPPORT_LOST_APPROVAL",
            "BURDEN_THRESHOLD_EXCEEDED",
            "HEADROOM_COLLAPSED",
            "REVALIDATION_FAILED",
            "ACTION_CLASS_NOT_ALLOWED",
            "CLAIM_HALTED",
            "CLAIM_REVOKED",
        }
        actual = {rc.value for rc in ReasonCode}
        assert actual == expected

    def test_revoked_yields_support_lost_reason(self):
        """サポート喪失による取消が正しい理由コードを持つことを検証する。"""
        from veritas_os.core.continuation_runtime.revalidator import (
            run_continuation_revalidation_shadow,
        )
        from veritas_os.core.continuation_runtime.reason_codes import ReasonCode

        _, _, receipt = run_continuation_revalidation_shadow(
            chain_id="",
            step_index=0,
            query="test",
            context={"authorization": "", "policy_ref": ""},
        )

        assert any(
            rc in (ReasonCode.SUPPORT_LOST_APPROVAL, ReasonCode.SUPPORT_LOST_POLICY_SCOPE)
            for rc in receipt.revalidation_reason_codes
        )

    def test_burden_exceeded_yields_correct_reason(self):
        """負担超過が正しい理由コードを生成することを検証する。"""
        from veritas_os.core.continuation_runtime.revalidator import (
            run_continuation_revalidation_shadow,
        )
        from veritas_os.core.continuation_runtime.reason_codes import ReasonCode

        _, _, receipt = run_continuation_revalidation_shadow(
            chain_id="c-1",
            step_index=1,
            query="test",
            context={
                "required_evidence": ["e1", "e2", "e3"],
                "satisfied_evidence": ["e1"],
            },
        )

        assert ReasonCode.BURDEN_THRESHOLD_EXCEEDED in receipt.revalidation_reason_codes

    def test_escalation_yields_action_class_not_allowed(self):
        """エスカレーションがACTION_CLASS_NOT_ALLOWEDを生成することを検証する。"""
        from veritas_os.core.continuation_runtime.revalidator import (
            run_continuation_revalidation_shadow,
        )
        from veritas_os.core.continuation_runtime.reason_codes import ReasonCode

        _, _, receipt = run_continuation_revalidation_shadow(
            chain_id="c-1",
            step_index=1,
            query="test",
            context={"escalation_required": True},
        )

        assert ReasonCode.ACTION_CLASS_NOT_ALLOWED in receipt.revalidation_reason_codes

    def test_narrowed_yields_action_class_not_allowed(self):
        """縮小がACTION_CLASS_NOT_ALLOWEDを生成することを検証する。"""
        from veritas_os.core.continuation_runtime.revalidator import (
            run_continuation_revalidation_shadow,
        )
        from veritas_os.core.continuation_runtime.reason_codes import ReasonCode

        _, _, receipt = run_continuation_revalidation_shadow(
            chain_id="c-1",
            step_index=1,
            query="test",
            context={"restricted_actions": ["execute"]},
        )

        assert ReasonCode.ACTION_CLASS_NOT_ALLOWED in receipt.revalidation_reason_codes


class TestClaimStatusConsistency:
    """Verify claim_status consistency between snapshot, receipt, and lineage."""

    def _run(self, **ctx):
        from veritas_os.core.continuation_runtime.revalidator import (
            run_continuation_revalidation_shadow,
        )

        defaults = {"chain_id": "cons-test", "step_index": 1, "query": "q", "context": {}}
        defaults.update(ctx)
        return run_continuation_revalidation_shadow(**defaults)

    def test_live_consistency(self):
        """LIVE状態でのスナップショット・レシート・リネージュの整合性を検証する。"""
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus
        from veritas_os.core.continuation_runtime.receipt import RevalidationStatus

        lineage, snap, rcpt = self._run()
        assert snap.claim_status == ClaimStatus.LIVE
        assert rcpt.revalidation_status == RevalidationStatus.RENEWED
        assert lineage.current_claim_status == ClaimStatus.LIVE

    def test_narrowed_consistency(self):
        """NARROWED: レシート優先境界で状態はLIVE維持（永続マーカーなし）の整合性を検証する。"""
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus
        from veritas_os.core.continuation_runtime.receipt import RevalidationStatus

        lineage, snap, rcpt = self._run(
            context={"restricted_actions": ["execute"]},
        )
        # Receipt carries the boundary outcome
        assert rcpt.revalidation_status == RevalidationStatus.NARROWED
        assert rcpt.boundary_outcome == "narrowed"
        # State: receipt-first (restrictions not marked durable)
        assert snap.claim_status == ClaimStatus.LIVE
        assert lineage.current_claim_status == ClaimStatus.LIVE

    def test_degraded_consistency(self):
        """DEGRADED: レシート優先境界で状態はLIVEのままであることを検証する。"""
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus
        from veritas_os.core.continuation_runtime.receipt import RevalidationStatus

        lineage, snap, rcpt = self._run(
            context={
                "required_evidence": ["e1", "e2", "e3"],
                "satisfied_evidence": ["e1"],
            },
        )
        # Receipt carries the boundary outcome
        assert rcpt.revalidation_status == RevalidationStatus.DEGRADED
        assert rcpt.boundary_outcome == "degraded"
        # State: receipt-first (not durable)
        assert snap.claim_status == ClaimStatus.LIVE
        assert lineage.current_claim_status == ClaimStatus.LIVE

    def test_escalated_consistency(self):
        """ESCALATED: レシート優先境界で状態はLIVEのままであることを検証する。"""
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus
        from veritas_os.core.continuation_runtime.receipt import RevalidationStatus

        lineage, snap, rcpt = self._run(
            context={"escalation_required": True},
        )
        # Receipt carries the boundary outcome
        assert rcpt.revalidation_status == RevalidationStatus.ESCALATED
        assert rcpt.boundary_outcome == "escalated"
        # State: receipt-first (not durable)
        assert snap.claim_status == ClaimStatus.LIVE
        assert lineage.current_claim_status == ClaimStatus.LIVE

    def test_revoked_consistency(self):
        """REVOKED状態でのスナップショット・レシート・リネージュの整合性を検証する。"""
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus
        from veritas_os.core.continuation_runtime.receipt import RevalidationStatus

        lineage, snap, rcpt = self._run(
            chain_id="",
            context={"authorization": "", "policy_ref": ""},
        )
        assert snap.claim_status == ClaimStatus.REVOKED
        assert rcpt.revalidation_status == RevalidationStatus.REVOKED
        assert lineage.current_claim_status == ClaimStatus.REVOKED
        assert lineage.is_revoked is True
        assert lineage.revoked_at is not None

    def test_halted_consistency(self):
        """HALTED: レシート優先境界で状態はLIVE維持（不可逆マーカーなし）の整合性を検証する。"""
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus
        from veritas_os.core.continuation_runtime.receipt import RevalidationStatus

        lineage, snap, rcpt = self._run(
            context={
                "required_evidence": ["e1", "e2", "e3"],
                "satisfied_evidence": [],
                "burden_current_level": 0.0,
            },
        )
        # Receipt carries the boundary outcome
        assert rcpt.revalidation_status == RevalidationStatus.HALTED
        assert rcpt.boundary_outcome == "halted"
        # State: receipt-first (collapse not marked irreversible)
        assert snap.claim_status == ClaimStatus.LIVE
        assert lineage.current_claim_status == ClaimStatus.LIVE
