# tests/test_continuation_enforcement_audit.py
# -*- coding: utf-8 -*-
"""
Audit, replay, and operator-visibility tests for continuation enforcement.

Tests cover:
  - TrustLog/audit fields for enforcement events
  - Replay visibility (events carry snapshot/receipt IDs)
  - Operator-visible enforcement reasoning
  - Event serialization round-trips for audit storage
  - Event emission logging
"""
from __future__ import annotations

import json
import logging
import pytest

from veritas_os.core.continuation_runtime.enforcement import (
    EnforcementMode,
    EnforcementAction,
    EnforcementConditionType,
    EnforcementCondition,
    EnforcementEvent,
    EnforcementConfig,
    ContinuationEnforcementEvaluator,
)
from veritas_os.core.continuation_runtime.lineage import (
    ClaimStatus,
    ContinuationClaimLineage,
)
from veritas_os.core.continuation_runtime.snapshot import (
    ClaimStateSnapshot,
    Scope,
)
from veritas_os.core.continuation_runtime.receipt import (
    ContinuationReceipt,
    RevalidationStatus,
    RevalidationOutcome,
)
from veritas_os.core.continuation_runtime.revalidator import (
    ContinuationRevalidator,
    PresentCondition,
)

pytestmark = [pytest.mark.unit]


# =====================================================================
# Helpers
# =====================================================================

def _make_snapshot(**overrides) -> ClaimStateSnapshot:
    defaults = {
        "claim_lineage_id": "lin-audit-001",
        "claim_status": ClaimStatus.LIVE,
        "law_version": "v0.1.0-shadow",
    }
    defaults.update(overrides)
    return ClaimStateSnapshot(**defaults)


def _make_receipt(**overrides) -> ContinuationReceipt:
    defaults = {
        "claim_lineage_id": "lin-audit-001",
        "snapshot_id": "snap-audit-001",
        "revalidation_status": RevalidationStatus.RENEWED,
        "revalidation_outcome": RevalidationOutcome.RENEWED,
    }
    defaults.update(overrides)
    return ContinuationReceipt(**defaults)


# =====================================================================
# Audit field completeness
# =====================================================================


class TestAuditFieldCompleteness:
    def test_event_dict_has_all_audit_fields(self):
        """Every enforcement event dict must have all fields needed for audit."""
        config = EnforcementConfig(mode=EnforcementMode.ENFORCE)
        evaluator = ContinuationEnforcementEvaluator(config=config)
        snap = _make_snapshot()
        rcpt = _make_receipt()

        events = evaluator.evaluate(
            snapshot=snap,
            receipt=rcpt,
            chain_id="chain-audit-001",
            policy_violation_detected=True,
            policy_violation_detail="test audit",
        )
        assert len(events) >= 1

        d = events[0].to_dict()
        audit_required_fields = [
            "event_id",
            "timestamp",
            "claim_lineage_id",
            "chain_id",
            "snapshot_id",
            "receipt_id",
            "law_version",
            "mode",
            "action",
            "is_enforced",
            "is_advisory",
            "conditions_evaluated",
            "conditions_met",
            "reasoning",
            "reason_codes",
            "claim_status",
            "boundary_outcome",
            "severity",
        ]
        for field in audit_required_fields:
            assert field in d, f"Audit field missing: {field}"

    def test_event_id_is_unique(self):
        config = EnforcementConfig(mode=EnforcementMode.ADVISORY)
        evaluator = ContinuationEnforcementEvaluator(config=config)

        events1 = evaluator.evaluate(
            snapshot=_make_snapshot(),
            receipt=_make_receipt(),
            policy_violation_detected=True,
        )
        events2 = evaluator.evaluate(
            snapshot=_make_snapshot(),
            receipt=_make_receipt(),
            policy_violation_detected=True,
        )
        assert events1[0].event_id != events2[0].event_id

    def test_timestamp_is_present(self):
        config = EnforcementConfig(mode=EnforcementMode.ADVISORY)
        evaluator = ContinuationEnforcementEvaluator(config=config)
        events = evaluator.evaluate(
            snapshot=_make_snapshot(),
            receipt=_make_receipt(),
            policy_violation_detected=True,
        )
        assert events[0].timestamp
        assert "T" in events[0].timestamp  # ISO format


# =====================================================================
# Replay visibility
# =====================================================================


class TestReplayVisibility:
    def test_event_carries_snapshot_id_for_replay(self):
        """Replay engine must be able to link enforcement event to snapshot."""
        config = EnforcementConfig(mode=EnforcementMode.ENFORCE)
        evaluator = ContinuationEnforcementEvaluator(config=config)
        snap = _make_snapshot()
        rcpt = _make_receipt()

        events = evaluator.evaluate(
            snapshot=snap,
            receipt=rcpt,
            chain_id="chain-replay-001",
            policy_violation_detected=True,
        )
        assert len(events) >= 1
        assert events[0].snapshot_id == snap.snapshot_id

    def test_event_carries_receipt_id_for_replay(self):
        config = EnforcementConfig(mode=EnforcementMode.ENFORCE)
        evaluator = ContinuationEnforcementEvaluator(config=config)
        snap = _make_snapshot()
        rcpt = _make_receipt()

        events = evaluator.evaluate(
            snapshot=snap,
            receipt=rcpt,
            policy_violation_detected=True,
        )
        assert events[0].receipt_id == rcpt.receipt_id

    def test_event_carries_law_version_for_replay(self):
        config = EnforcementConfig(mode=EnforcementMode.ENFORCE)
        evaluator = ContinuationEnforcementEvaluator(config=config)
        snap = _make_snapshot(law_version="v0.2.0-enforce")

        events = evaluator.evaluate(
            snapshot=snap,
            receipt=_make_receipt(),
            policy_violation_detected=True,
        )
        assert events[0].law_version == "v0.2.0-enforce"

    def test_enforcement_event_round_trip_preserves_replay_data(self):
        """Serialization round-trip preserves replay-critical fields."""
        event = EnforcementEvent(
            claim_lineage_id="lin-rp-001",
            chain_id="chain-rp-001",
            snapshot_id="snap-rp-001",
            receipt_id="rcpt-rp-001",
            law_version="v0.2.0-enforce",
            mode=EnforcementMode.ENFORCE,
            action=EnforcementAction.HALT_CHAIN,
            is_enforced=True,
            reasoning="replay test",
            reason_codes=["policy_boundary_violation"],
        )
        d = event.to_dict()
        restored = EnforcementEvent.from_dict(d)

        assert restored.snapshot_id == "snap-rp-001"
        assert restored.receipt_id == "rcpt-rp-001"
        assert restored.law_version == "v0.2.0-enforce"
        assert restored.mode == EnforcementMode.ENFORCE
        assert restored.action == EnforcementAction.HALT_CHAIN


# =====================================================================
# TrustLog / audit persistence format
# =====================================================================


class TestTrustLogAuditFormat:
    def test_event_serializable_to_json(self):
        """Events must be JSON-serializable for trustlog persistence."""
        config = EnforcementConfig(mode=EnforcementMode.ENFORCE)
        evaluator = ContinuationEnforcementEvaluator(config=config)

        events = evaluator.evaluate(
            snapshot=_make_snapshot(
                scope=Scope(escalation_required=True),
            ),
            receipt=_make_receipt(),
            chain_id="chain-tl-001",
            has_required_approval=False,
            policy_violation_detected=True,
        )
        for event in events:
            d = event.to_dict()
            # Must not raise
            json_str = json.dumps(d, default=str)
            assert json_str

    def test_conditions_serializable_to_json(self):
        cond = EnforcementCondition(
            condition_type=EnforcementConditionType.REPEATED_DEGRADATION,
            is_met=True,
            confidence=0.85,
            explanation="test",
            evidence={"count": 5, "threshold": 3},
        )
        d = cond.to_dict()
        json_str = json.dumps(d)
        assert json_str

    def test_audit_entry_enforcement_fields(self):
        """Simulate the audit entry enrichment that pipeline_persist does."""
        config = EnforcementConfig(mode=EnforcementMode.ENFORCE)
        evaluator = ContinuationEnforcementEvaluator(config=config)

        events = evaluator.evaluate(
            snapshot=_make_snapshot(),
            receipt=_make_receipt(),
            policy_violation_detected=True,
        )

        # Simulate audit entry enrichment
        event_dicts = [e.to_dict() for e in events]
        audit_entry = {}
        audit_entry["continuation_enforcement_event_count"] = len(event_dicts)
        audit_entry["continuation_enforcement_actions"] = [
            e.get("action") for e in event_dicts
        ]
        audit_entry["continuation_enforcement_halt"] = any(
            e.get("action") == "halt_chain" and e.get("is_enforced")
            for e in event_dicts
        )

        assert audit_entry["continuation_enforcement_event_count"] >= 1
        assert "halt_chain" in audit_entry["continuation_enforcement_actions"]
        assert audit_entry["continuation_enforcement_halt"] is True


# =====================================================================
# Operator visibility (reasoning, severity)
# =====================================================================


class TestOperatorVisibility:
    def test_reasoning_is_explicit(self):
        config = EnforcementConfig(mode=EnforcementMode.ADVISORY)
        evaluator = ContinuationEnforcementEvaluator(config=config)

        events = evaluator.evaluate(
            snapshot=_make_snapshot(
                scope=Scope(escalation_required=True),
            ),
            receipt=_make_receipt(),
            has_required_approval=False,
        )
        assert len(events) >= 1
        reasoning = events[0].reasoning
        # Reasoning must explain:
        # - What action was triggered
        # - What condition caused it
        # - Confidence level
        assert "halt_chain" in reasoning
        assert "approval_required_without_approval" in reasoning
        assert "confidence:" in reasoning

    def test_severity_levels_are_valid(self):
        config = EnforcementConfig(mode=EnforcementMode.ENFORCE)
        evaluator = ContinuationEnforcementEvaluator(config=config)

        events = evaluator.evaluate(
            snapshot=_make_snapshot(
                scope=Scope(escalation_required=True),
            ),
            receipt=_make_receipt(
                revalidation_status=RevalidationStatus.DEGRADED,
            ),
            degradation_count=5,
            has_required_approval=False,
            policy_violation_detected=True,
            replay_divergence_ratio=0.8,
        )
        valid_severities = {"info", "medium", "high", "critical"}
        for event in events:
            assert event.severity in valid_severities

    def test_conditions_met_includes_explanation(self):
        config = EnforcementConfig(mode=EnforcementMode.ADVISORY)
        evaluator = ContinuationEnforcementEvaluator(config=config)

        events = evaluator.evaluate(
            snapshot=_make_snapshot(),
            receipt=_make_receipt(),
            policy_violation_detected=True,
            policy_violation_detail="action_class_restricted",
        )
        assert len(events) >= 1
        conds = events[0].conditions_met
        assert len(conds) == 1
        assert "action_class_restricted" in conds[0].explanation


# =====================================================================
# Event emission logging
# =====================================================================


class TestEventEmissionLogging:
    def test_enforcement_event_logs_info(self, caplog):
        config = EnforcementConfig(mode=EnforcementMode.ENFORCE)
        evaluator = ContinuationEnforcementEvaluator(config=config)

        with caplog.at_level(logging.INFO, logger="veritas_os.core.continuation_runtime.enforcement"):
            evaluator.evaluate(
                snapshot=_make_snapshot(),
                receipt=_make_receipt(),
                chain_id="chain-log-001",
                policy_violation_detected=True,
            )
        assert any(
            "continuation-enforcement" in record.message
            for record in caplog.records
        )

    def test_enforcement_event_log_contains_action(self, caplog):
        config = EnforcementConfig(mode=EnforcementMode.ENFORCE)
        evaluator = ContinuationEnforcementEvaluator(config=config)

        with caplog.at_level(logging.INFO, logger="veritas_os.core.continuation_runtime.enforcement"):
            evaluator.evaluate(
                snapshot=_make_snapshot(),
                receipt=_make_receipt(),
                chain_id="chain-log-002",
                policy_violation_detected=True,
            )
        log_messages = " ".join(r.message for r in caplog.records)
        assert "halt_chain" in log_messages

    def test_advisory_event_logs_advisory(self, caplog):
        config = EnforcementConfig(mode=EnforcementMode.ADVISORY)
        evaluator = ContinuationEnforcementEvaluator(config=config)

        with caplog.at_level(logging.INFO, logger="veritas_os.core.continuation_runtime.enforcement"):
            evaluator.evaluate(
                snapshot=_make_snapshot(),
                receipt=_make_receipt(),
                chain_id="chain-log-003",
                policy_violation_detected=True,
            )
        log_messages = " ".join(r.message for r in caplog.records)
        assert "ADVISORY" in log_messages


# =====================================================================
# Full round-trip: revalidation → enforcement → audit → replay
# =====================================================================


class TestFullRoundTrip:
    def test_revalidation_to_enforcement_to_audit(self):
        """Full flow: revalidation → enforcement → audit entry → replay check."""
        # Step 1: Revalidation
        lineage = ContinuationClaimLineage(chain_id="chain-full-001")
        revalidator = ContinuationRevalidator()
        condition = PresentCondition(
            chain_id="chain-full-001",
            step_index=0,
            query="full round trip test",
            context={"escalation_required": True},
        )
        snapshot, receipt = revalidator.revalidate(
            lineage=lineage,
            condition=condition,
        )

        # Step 2: Enforcement
        config = EnforcementConfig(mode=EnforcementMode.ENFORCE)
        evaluator = ContinuationEnforcementEvaluator(config=config)
        events = evaluator.evaluate(
            snapshot=snapshot,
            receipt=receipt,
            chain_id="chain-full-001",
            has_required_approval=False,
        )

        # Step 3: Build audit entry
        event_dicts = [e.to_dict() for e in events]
        audit_entry = {
            "continuation_snapshot_id": snapshot.snapshot_id,
            "continuation_receipt_id": receipt.receipt_id,
            "continuation_claim_status": snapshot.claim_status.value,
            "continuation_enforcement_event_count": len(event_dicts),
            "continuation_enforcement_actions": [
                e["action"] for e in event_dicts
            ],
            "continuation_enforcement_halt": any(
                e["action"] == "halt_chain" and e["is_enforced"]
                for e in event_dicts
            ),
        }

        # Step 4: Verify audit entry
        assert audit_entry["continuation_enforcement_event_count"] >= 1
        assert audit_entry["continuation_enforcement_halt"] is True
        assert "halt_chain" in audit_entry["continuation_enforcement_actions"]

        # Step 5: Verify replay linkage
        for event in events:
            assert event.snapshot_id == snapshot.snapshot_id
            assert event.receipt_id == receipt.receipt_id
            assert event.claim_lineage_id == lineage.claim_lineage_id

        # Step 6: JSON round-trip for storage
        json_str = json.dumps(audit_entry, default=str)
        restored = json.loads(json_str)
        assert restored["continuation_enforcement_halt"] is True
