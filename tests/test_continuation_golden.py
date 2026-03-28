# tests/test_continuation_golden.py
# -*- coding: utf-8 -*-
"""
Golden scenario tests for Continuation Runtime phase-1.

These are the most important test cases: situations where the local step
passes (or would pass) but the continuation runtime detects chain-level
problems invisible to step-level evaluation.

Priority: divergence > normal flow.

Golden scenarios:
  1. Local correct, support lost
  2. Local correct, burden/headroom collapse
  3. Local correct, scope narrowing needed
  4. Local correct, escalation needed
  5. Local correct, halted
  6. Local correct, revoked
  7. Local correct, receipt chain shows continuity weakening
"""
from __future__ import annotations

import pytest

from veritas_os.core.continuation_runtime.revalidator import (
    ContinuationRevalidator,
    PresentCondition,
    run_continuation_revalidation_shadow,
)
from veritas_os.core.continuation_runtime.lineage import (
    ContinuationClaimLineage,
    ClaimStatus,
)
from veritas_os.core.continuation_runtime.receipt import (
    RevalidationStatus,
    RevalidationOutcome,
)
from veritas_os.core.continuation_runtime.reason_codes import ReasonCode


def _run_golden(context, *, chain_id="golden-chain", prior_decision_status="allow"):
    """Run a single-step golden scenario: local step 'allow', continuation may diverge."""
    lineage, snap, rcpt = run_continuation_revalidation_shadow(
        chain_id=chain_id,
        step_index=1,
        query="golden scenario query",
        context=context,
        prior_decision_status=prior_decision_status,
    )
    return lineage, snap, rcpt


# =====================================================================
# Golden 1: Local correct, support lost
# =====================================================================


class TestGolden1SupportLost:
    """The local step would be allowed, but the chain's support basis
    has evaporated — authority and policy are gone."""

    def test_claim_revoked_despite_local_allow(self):
        _, snap, rcpt = _run_golden(
            {"authorization": "", "policy_ref": ""},
            chain_id="",  # no chain_id → no authority fallback
        )

        assert snap.claim_status == ClaimStatus.REVOKED
        assert rcpt.prior_decision_continuity_ref == "allow"
        assert rcpt.divergence_flag is True
        assert rcpt.should_refuse_before_effect is True

    def test_reason_codes_indicate_support_loss(self):
        _, _, rcpt = _run_golden(
            {"authorization": "", "policy_ref": ""},
            chain_id="",
        )

        assert any(
            rc in (ReasonCode.SUPPORT_LOST_APPROVAL, ReasonCode.SUPPORT_LOST_POLICY_SCOPE)
            for rc in rcpt.revalidation_reason_codes
        )

    def test_support_basis_empty_in_snapshot(self):
        _, snap, _ = _run_golden(
            {"authorization": "", "policy_ref": ""},
            chain_id="",
        )

        # Both authority and policy should be empty/absent
        assert snap.support_basis.authority == ""
        assert snap.support_basis.policy == ""


# =====================================================================
# Golden 2: Local correct, burden/headroom collapse
# =====================================================================


class TestGolden2BurdenHeadroomCollapse:
    """The local step would be allowed, but evidentiary burden is unmet
    and headroom has collapsed to zero."""

    def test_halted_due_to_headroom_collapse(self):
        _, snap, rcpt = _run_golden({
            "required_evidence": ["e1", "e2", "e3", "e4", "e5"],
            "satisfied_evidence": [],
            "burden_current_level": 0.0,
        })

        assert snap.claim_status == ClaimStatus.HALTED
        assert rcpt.divergence_flag is True
        assert rcpt.should_refuse_before_effect is True

    def test_burden_state_reflects_unmet_evidence(self):
        _, snap, _ = _run_golden({
            "required_evidence": ["e1", "e2", "e3"],
            "satisfied_evidence": [],
            "burden_current_level": 0.0,
        })

        assert snap.burden_state.current_level == 0.0
        assert len(snap.burden_state.required_evidence) == 3
        assert len(snap.burden_state.satisfied_evidence) == 0

    def test_headroom_zero_in_snapshot(self):
        _, snap, _ = _run_golden({
            "required_evidence": ["e1", "e2"],
            "satisfied_evidence": [],
            "burden_current_level": 0.0,
        })

        assert snap.headroom_state.remaining == 0.0

    def test_reason_code_headroom_collapsed(self):
        _, _, rcpt = _run_golden({
            "required_evidence": ["e1", "e2"],
            "satisfied_evidence": [],
            "burden_current_level": 0.0,
        })

        assert ReasonCode.HEADROOM_COLLAPSED in rcpt.revalidation_reason_codes


# =====================================================================
# Golden 3: Local correct, scope narrowing needed
# =====================================================================


class TestGolden3ScopeNarrowing:
    """The local step is fine, but the chain's scope has been restricted."""

    def test_narrowed_due_to_restricted_actions(self):
        _, snap, rcpt = _run_golden({
            "restricted_actions": ["execute", "deploy"],
        })

        assert snap.claim_status == ClaimStatus.NARROWED
        assert rcpt.divergence_flag is True
        assert rcpt.should_refuse_before_effect is False  # narrowed, not halted

    def test_scope_reflects_restrictions(self):
        _, snap, _ = _run_golden({
            "restricted_actions": ["execute", "deploy"],
        })

        assert "execute" in snap.scope.restricted_action_classes
        assert "deploy" in snap.scope.restricted_action_classes

    def test_reason_code_action_class(self):
        _, _, rcpt = _run_golden({
            "restricted_actions": ["execute"],
        })

        assert ReasonCode.ACTION_CLASS_NOT_ALLOWED in rcpt.revalidation_reason_codes


# =====================================================================
# Golden 4: Local correct, escalation needed
# =====================================================================


class TestGolden4EscalationNeeded:
    """The local step is fine, but escalation is required."""

    def test_escalated_despite_local_allow(self):
        _, snap, rcpt = _run_golden({
            "escalation_required": True,
        })

        assert snap.claim_status == ClaimStatus.ESCALATED
        assert rcpt.divergence_flag is True

    def test_scope_escalation_flag(self):
        _, snap, _ = _run_golden({
            "escalation_required": True,
        })

        assert snap.scope.escalation_required is True


# =====================================================================
# Golden 5: Local correct, halted
# =====================================================================


class TestGolden5Halted:
    """The local step passes, but headroom is at threshold_suspension."""

    def test_halted_with_zero_headroom(self):
        _, snap, rcpt = _run_golden({
            "required_evidence": ["e1", "e2", "e3"],
            "satisfied_evidence": [],
            "burden_current_level": 0.0,
        })

        assert snap.claim_status == ClaimStatus.HALTED
        assert rcpt.revalidation_status == RevalidationStatus.HALTED
        assert rcpt.revalidation_outcome == RevalidationOutcome.HALTED
        assert rcpt.should_refuse_before_effect is True

    def test_halted_receipt_has_audit_digests(self):
        _, _, rcpt = _run_golden({
            "required_evidence": ["e1", "e2"],
            "satisfied_evidence": [],
            "burden_current_level": 0.0,
        })

        assert rcpt.support_basis_digest is not None
        assert rcpt.scope_digest is not None
        assert rcpt.burden_headroom_digest is not None


# =====================================================================
# Golden 6: Local correct, revoked
# =====================================================================


class TestGolden6Revoked:
    """Local step passes, but continuation is fully revoked."""

    def test_revoked_with_full_support_loss(self):
        lineage, snap, rcpt = _run_golden(
            {"authorization": "", "policy_ref": ""},
            chain_id="",
        )

        assert snap.claim_status == ClaimStatus.REVOKED
        assert rcpt.revalidation_status == RevalidationStatus.REVOKED
        assert rcpt.revalidation_outcome == RevalidationOutcome.REVOKED
        assert rcpt.should_refuse_before_effect is True
        assert lineage.is_revoked is True

    def test_revoked_lineage_has_timestamp(self):
        lineage, _, _ = _run_golden(
            {"authorization": "", "policy_ref": ""},
            chain_id="",
        )

        assert lineage.revoked_at is not None

    def test_revoked_is_terminal_in_chain(self):
        """After revocation, subsequent steps remain revoked."""
        rv = ContinuationRevalidator()
        lineage = ContinuationClaimLineage(chain_id="", origin_ref="step:0")

        # Step 0: revoke
        cond0 = PresentCondition(
            chain_id="",
            step_index=0,
            query="revoke",
            context={"authorization": "", "policy_ref": ""},
        )
        snap0, rcpt0 = rv.revalidate(lineage, cond0)
        assert snap0.claim_status == ClaimStatus.REVOKED

        # Step 1: good conditions, but revoked is terminal
        cond1 = PresentCondition(
            chain_id="golden-chain",
            step_index=1,
            query="good step",
            context={},
        )
        snap1, rcpt1 = rv.revalidate(lineage, cond1, prior_snapshot=snap0, prior_receipt=rcpt0)
        assert snap1.claim_status == ClaimStatus.REVOKED
        assert rcpt1.revalidation_status == RevalidationStatus.REVOKED


# =====================================================================
# Golden 7: Receipt chain shows continuity weakening
# =====================================================================


class TestGolden7ReceiptChainContinuityWeakening:
    """A multi-step chain where local steps all pass but the receipt
    chain reveals progressive continuation weakening."""

    def _run_weakening_chain(self):
        rv = ContinuationRevalidator()
        lineage = ContinuationClaimLineage(chain_id="weaken-chain", origin_ref="step:0")
        steps = [
            # Step 0: LIVE (healthy)
            PresentCondition(
                chain_id="weaken-chain", step_index=0, query="step-0",
                context={}, prior_decision_status="allow",
            ),
            # Step 1: NARROWED (scope restriction appears)
            PresentCondition(
                chain_id="weaken-chain", step_index=1, query="step-1",
                context={"restricted_actions": ["execute"]},
                prior_decision_status="allow",
            ),
            # Step 2: ESCALATED (escalation required)
            PresentCondition(
                chain_id="weaken-chain", step_index=2, query="step-2",
                context={"escalation_required": True},
                prior_decision_status="allow",
            ),
            # Step 3: REVOKED (support fully lost)
            PresentCondition(
                chain_id="", step_index=3, query="step-3",
                context={"authorization": "", "policy_ref": ""},
                prior_decision_status="allow",
            ),
        ]

        results = []
        prior_snap = None
        prior_rcpt = None
        for cond in steps:
            snap, rcpt = rv.revalidate(
                lineage, cond,
                prior_snapshot=prior_snap,
                prior_receipt=prior_rcpt,
            )
            results.append((snap, rcpt))
            prior_snap = snap
            prior_rcpt = rcpt

        return lineage, results

    def test_progressive_status_weakening(self):
        _, results = self._run_weakening_chain()

        statuses = [snap.claim_status for snap, _ in results]
        assert statuses[0] == ClaimStatus.LIVE
        assert statuses[1] == ClaimStatus.NARROWED
        assert statuses[2] == ClaimStatus.ESCALATED
        assert statuses[3] == ClaimStatus.REVOKED

    def test_divergence_flags_track_weakening(self):
        _, results = self._run_weakening_chain()

        divergences = [rcpt.divergence_flag for _, rcpt in results]
        assert divergences == [False, True, True, True]

    def test_receipt_chain_is_linked(self):
        _, results = self._run_weakening_chain()

        for i in range(1, len(results)):
            _, prev_rcpt = results[i - 1]
            _, curr_rcpt = results[i]
            assert curr_rcpt.parent_receipt_ref == prev_rcpt.receipt_id

    def test_all_prior_decisions_were_allow(self):
        """Every step had prior_decision_status='allow', proving
        local step outcome did not influence continuation standing."""
        _, results = self._run_weakening_chain()

        for _, rcpt in results:
            assert rcpt.prior_decision_continuity_ref == "allow"

    def test_snapshot_replaced_at_each_step(self):
        """Only latest snapshot is authoritative — each step creates new."""
        lineage, results = self._run_weakening_chain()

        snapshot_ids = [snap.snapshot_id for snap, _ in results]
        assert len(set(snapshot_ids)) == len(results)  # all unique

        # Lineage points to the last snapshot
        assert lineage.latest_snapshot_id == results[-1][0].snapshot_id

    def test_law_version_consistent_across_chain(self):
        _, results = self._run_weakening_chain()

        for snap, rcpt in results:
            assert snap.law_version == "v0.1.0-shadow"
            assert rcpt.law_version_id == "v0.1.0-shadow"

    def test_audit_digests_present_in_every_receipt(self):
        _, results = self._run_weakening_chain()

        for _, rcpt in results:
            assert rcpt.support_basis_digest is not None
            assert rcpt.scope_digest is not None
            assert rcpt.burden_headroom_digest is not None

    def test_advisory_only_for_non_terminal_steps(self):
        """Phase-1: should_refuse_before_effect is advisory only for
        non-terminal statuses. HALTED/REVOKED set it True (advisory)."""
        _, results = self._run_weakening_chain()

        for snap, rcpt in results:
            if snap.claim_status in (ClaimStatus.HALTED, ClaimStatus.REVOKED):
                assert rcpt.should_refuse_before_effect is True
            else:
                assert rcpt.should_refuse_before_effect is False
