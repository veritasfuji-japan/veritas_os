# tests/test_continuation_replay.py
# -*- coding: utf-8 -*-
"""
Replay tests for Continuation Runtime phase-1.

Simulates multi-step chains and verifies:
  - Receipt chain formation across steps
  - Status transitions: narrowed, degraded, escalated, halted, revoked
  - Receipt continuity grounding (parent_receipt_ref linkage)
  - Snapshot replacement semantics (only latest is authoritative)
  - Divergence tracking across chain steps
"""
from __future__ import annotations

import pytest


def _run_chain(steps, *, chain_id="replay-chain"):
    """Run a multi-step chain and return list of (lineage, snapshot, receipt)."""
    from veritas_os.core.continuation_runtime.revalidator import (
        ContinuationRevalidator,
        PresentCondition,
    )
    from veritas_os.core.continuation_runtime.lineage import ContinuationClaimLineage

    rv = ContinuationRevalidator()
    lineage = ContinuationClaimLineage(chain_id=chain_id, origin_ref="step:0")
    results = []
    prior_snapshot = None
    prior_receipt = None

    for i, step_ctx in enumerate(steps):
        condition = PresentCondition(
            chain_id=step_ctx.get("chain_id", chain_id),
            step_index=i,
            query=step_ctx.get("query", f"step-{i}"),
            context=step_ctx.get("context", {}),
            prior_decision_status=step_ctx.get("prior_decision_status"),
            prior_receipt_id=prior_receipt.receipt_id if prior_receipt else None,
        )
        snapshot, receipt = rv.revalidate(
            lineage=lineage,
            condition=condition,
            prior_snapshot=prior_snapshot,
            prior_receipt=prior_receipt,
        )
        results.append((lineage, snapshot, receipt))
        prior_snapshot = snapshot
        prior_receipt = receipt

    return results


class TestReplayStepPassClaimNarrowed:
    """Step passes but claim is narrowed due to scope restriction."""

    def test_narrowed_transition(self):
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus
        from veritas_os.core.continuation_runtime.receipt import RevalidationStatus

        results = _run_chain([
            {"context": {}},  # step 0: LIVE
            {"context": {"restricted_actions": ["execute"]}},  # step 1: NARROWED
        ])

        _, snap0, rcpt0 = results[0]
        _, snap1, rcpt1 = results[1]

        assert snap0.claim_status == ClaimStatus.LIVE
        assert snap1.claim_status == ClaimStatus.NARROWED
        assert rcpt1.revalidation_status == RevalidationStatus.NARROWED
        assert rcpt1.divergence_flag is True

    def test_receipt_chain_linkage(self):
        results = _run_chain([
            {"context": {}},
            {"context": {"restricted_actions": ["execute"]}},
        ])

        _, _, rcpt0 = results[0]
        _, _, rcpt1 = results[1]

        assert rcpt1.parent_receipt_ref == rcpt0.receipt_id


class TestReplayStepPassClaimDegraded:
    """Step passes but claim is degraded due to burden threshold."""

    def test_degraded_transition(self):
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus

        # Step 0 establishes burden; step 1 carries it forward unmet
        results = _run_chain([
            {
                "context": {
                    "required_evidence": ["e1", "e2", "e3"],
                    "satisfied_evidence": ["e1"],
                },
            },  # step 0: DEGRADED (1/3 = 0.33, below threshold)
            {
                "context": {},  # no new_evidence → carries forward
            },  # step 1: still DEGRADED
        ])

        _, snap0, _ = results[0]
        _, snap1, rcpt1 = results[1]

        assert snap0.claim_status == ClaimStatus.LIVE  # degraded is receipt-first
        assert snap1.claim_status == ClaimStatus.LIVE  # degraded is receipt-first
        assert rcpt1.divergence_flag is True

    def test_burden_state_carried_forward(self):
        results = _run_chain([
            {
                "context": {
                    "required_evidence": ["e1", "e2", "e3"],
                    "satisfied_evidence": ["e1"],
                },
            },
            {
                "context": {"new_evidence": ["e2"]},
            },
        ])

        _, snap0, _ = results[0]
        _, snap1, _ = results[1]

        # Step 1 should carry forward burden and add new evidence
        assert "e1" in snap1.burden_state.satisfied_evidence
        assert "e2" in snap1.burden_state.satisfied_evidence


class TestReplayStepPassClaimEscalated:
    """Step passes but claim is escalated."""

    def test_escalated_transition(self):
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus

        results = _run_chain([
            {"context": {}},
            {"context": {"escalation_required": True}},
        ])

        _, snap1, rcpt1 = results[1]
        assert snap1.claim_status == ClaimStatus.LIVE  # escalated is receipt-first
        assert rcpt1.divergence_flag is True


class TestReplayStepPassClaimHalted:
    """Step passes but claim is halted (headroom collapsed)."""

    def test_halted_transition(self):
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus

        # Step 0 establishes zero burden → HALTED
        results = _run_chain([
            {
                "context": {
                    "required_evidence": ["e1", "e2", "e3"],
                    "satisfied_evidence": [],
                    "burden_current_level": 0.0,
                },
            },  # step 0: HALTED (0/3 → headroom 0.0)
            {"context": {}},  # step 1: still HALTED (terminal)
        ])

        _, snap0, rcpt0 = results[0]
        _, snap1, rcpt1 = results[1]
        assert snap0.claim_status == ClaimStatus.HALTED
        assert snap1.claim_status == ClaimStatus.HALTED
        assert rcpt0.should_refuse_before_effect is True

    def test_halted_is_terminal(self):
        """Once halted, remains halted even with good conditions."""
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus

        results = _run_chain([
            {
                "context": {
                    "required_evidence": ["e1", "e2", "e3"],
                    "satisfied_evidence": [],
                    "burden_current_level": 0.0,
                },
            },
            {"context": {}},  # good conditions, but halted is terminal
        ])

        _, snap1, _ = results[1]
        assert snap1.claim_status == ClaimStatus.HALTED


class TestReplayStepPassClaimRevoked:
    """Step passes but claim is revoked (support fully lost)."""

    def test_revoked_transition(self):
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus

        # Use empty chain_id so authority fallback doesn't rescue support
        results = _run_chain([
            {"context": {}, "chain_id": "ok-chain"},  # step 0: LIVE
            {
                "context": {"authorization": "", "policy_ref": ""},
                "chain_id": "",  # no chain_id → no authority
                "query": "revoke-step",
            },
        ])

        _, snap0, _ = results[0]
        lineage, snap1, rcpt1 = results[1]
        assert snap0.claim_status == ClaimStatus.LIVE
        assert snap1.claim_status == ClaimStatus.REVOKED
        assert rcpt1.should_refuse_before_effect is True
        assert lineage.is_revoked is True

    def test_revoked_is_terminal(self):
        """Once revoked, stays revoked regardless of conditions."""
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus

        # Step 0 triggers revocation with empty chain_id
        results = _run_chain([
            {
                "context": {"authorization": "", "policy_ref": ""},
                "chain_id": "",
            },
            {"context": {}, "chain_id": "ok-chain"},  # good conditions, but revoked
        ], chain_id="")

        _, snap0, _ = results[0]
        _, snap1, _ = results[1]
        assert snap0.claim_status == ClaimStatus.REVOKED
        assert snap1.claim_status == ClaimStatus.REVOKED


class TestReplayReceiptChainContinuityGrounding:
    """Receipt chain must demonstrate continuity grounding across steps."""

    def test_receipt_chain_forms_linked_list(self):
        results = _run_chain([
            {"context": {}},
            {"context": {}},
            {"context": {"restricted_actions": ["execute"]}},
            {"context": {"escalation_required": True}},
        ])

        for i in range(1, len(results)):
            _, _, prev_rcpt = results[i - 1]
            _, _, curr_rcpt = results[i]
            assert curr_rcpt.parent_receipt_ref == prev_rcpt.receipt_id

    def test_snapshot_id_advances_each_step(self):
        results = _run_chain([
            {"context": {}},
            {"context": {}},
            {"context": {}},
        ])

        snapshot_ids = [snap.snapshot_id for _, snap, _ in results]
        assert len(set(snapshot_ids)) == 3  # all unique

    def test_lineage_tracks_latest_snapshot(self):
        results = _run_chain([
            {"context": {}},
            {"context": {}},
            {"context": {}},
        ])

        lineage, last_snap, _ = results[-1]
        assert lineage.latest_snapshot_id == last_snap.snapshot_id

    def test_prior_decision_continuity_carried_in_receipt(self):
        results = _run_chain([
            {"context": {}, "prior_decision_status": "allow"},
            {"context": {}, "prior_decision_status": "allow"},
            {
                "context": {"restricted_actions": ["x"]},
                "prior_decision_status": "allow",
            },
        ])

        for _, _, rcpt in results:
            assert rcpt.prior_decision_continuity_ref == "allow"

    def test_divergence_progressive_weakening(self):
        """Chain shows progressive weakening: state shows durable standing,
        receipt shows boundary progression."""
        from veritas_os.core.continuation_runtime.lineage import ClaimStatus

        results = _run_chain([
            {"context": {}},  # LIVE
            {"context": {"restricted_actions": ["x"]}},  # NARROWED (durable)
            {"context": {"escalation_required": True}},  # ESCALATED (receipt-only)
        ])

        # State (durable standing)
        statuses = [snap.claim_status for _, snap, _ in results]
        assert statuses[0] == ClaimStatus.LIVE
        assert statuses[1] == ClaimStatus.NARROWED  # durable scope reduction
        assert statuses[2] == ClaimStatus.LIVE      # escalated is receipt-only

        # Receipt boundary outcomes
        boundaries = [rcpt.boundary_outcome for _, _, rcpt in results]
        assert boundaries[0] == "live"
        assert boundaries[1] == "narrowed"
        assert boundaries[2] == "escalated"

        # Divergence should be observable from step 1 onward
        divergences = [rcpt.divergence_flag for _, _, rcpt in results]
        assert divergences == [False, True, True]

    def test_law_version_recorded_in_every_snapshot_and_receipt(self):
        results = _run_chain([
            {"context": {}},
            {"context": {}},
            {"context": {}},
        ])

        for _, snap, rcpt in results:
            assert snap.law_version == "v0.1.0-shadow"
            assert rcpt.law_version_id == "v0.1.0-shadow"
