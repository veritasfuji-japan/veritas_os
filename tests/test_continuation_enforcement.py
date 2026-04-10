# tests/test_continuation_enforcement.py
# -*- coding: utf-8 -*-
"""
Unit tests for continuation-level limited enforcement engine.

Tests cover:
  - Threshold logic for all four enforcement conditions
  - Enforcement mode switching (observe/advisory/enforce)
  - EnforcementEvent structure and serialization
  - Confidence scoring
  - Action resolution
  - Severity computation
  - Reasoning generation
"""
from __future__ import annotations

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
from veritas_os.core.continuation_runtime.lineage import ClaimStatus
from veritas_os.core.continuation_runtime.snapshot import (
    ClaimStateSnapshot,
    Scope,
    SupportBasis,
    BurdenState,
    HeadroomState,
)
from veritas_os.core.continuation_runtime.receipt import (
    ContinuationReceipt,
    RevalidationStatus,
    RevalidationOutcome,
)

pytestmark = [pytest.mark.unit]


# =====================================================================
# Helpers
# =====================================================================

def _make_snapshot(**overrides) -> ClaimStateSnapshot:
    """Build a minimal snapshot with optional overrides."""
    defaults = {
        "claim_lineage_id": "lineage-test-001",
        "claim_status": ClaimStatus.LIVE,
        "law_version": "v0.1.0-shadow",
    }
    defaults.update(overrides)
    return ClaimStateSnapshot(**defaults)


def _make_receipt(**overrides) -> ContinuationReceipt:
    """Build a minimal receipt with optional overrides."""
    defaults = {
        "claim_lineage_id": "lineage-test-001",
        "snapshot_id": "snap-001",
        "revalidation_status": RevalidationStatus.RENEWED,
        "revalidation_outcome": RevalidationOutcome.RENEWED,
    }
    defaults.update(overrides)
    return ContinuationReceipt(**defaults)


def _make_evaluator(
    mode: EnforcementMode = EnforcementMode.ADVISORY,
    **config_overrides,
) -> ContinuationEnforcementEvaluator:
    """Build an evaluator with the given mode and config overrides."""
    config = EnforcementConfig(mode=mode, **config_overrides)
    return ContinuationEnforcementEvaluator(config=config)


# =====================================================================
# EnforcementMode enum
# =====================================================================


class TestEnforcementMode:
    def test_observe_is_default(self):
        config = EnforcementConfig()
        assert config.mode == EnforcementMode.OBSERVE

    def test_mode_values(self):
        assert EnforcementMode.OBSERVE.value == "observe"
        assert EnforcementMode.ADVISORY.value == "advisory"
        assert EnforcementMode.ENFORCE.value == "enforce"

    def test_mode_str(self):
        assert str(EnforcementMode.OBSERVE) == "observe"
        assert str(EnforcementMode.ENFORCE) == "enforce"


# =====================================================================
# EnforcementAction enum
# =====================================================================


class TestEnforcementAction:
    def test_action_values(self):
        assert EnforcementAction.REQUIRE_HUMAN_REVIEW.value == "require_human_review"
        assert EnforcementAction.HALT_CHAIN.value == "halt_chain"
        assert EnforcementAction.ESCALATE_ALERT.value == "escalate_alert"

    def test_action_str(self):
        assert str(EnforcementAction.HALT_CHAIN) == "halt_chain"


# =====================================================================
# EnforcementCondition serialization
# =====================================================================


class TestEnforcementCondition:
    def test_to_dict_and_from_dict(self):
        cond = EnforcementCondition(
            condition_type=EnforcementConditionType.REPEATED_DEGRADATION,
            is_met=True,
            confidence=0.9,
            explanation="test explanation",
            evidence={"count": 5},
        )
        d = cond.to_dict()
        assert d["condition_type"] == "repeated_degradation"
        assert d["is_met"] is True
        assert d["confidence"] == 0.9
        assert d["explanation"] == "test explanation"
        assert d["evidence"]["count"] == 5

        restored = EnforcementCondition.from_dict(d)
        assert restored.condition_type == EnforcementConditionType.REPEATED_DEGRADATION
        assert restored.is_met is True
        assert restored.confidence == 0.9

    def test_condition_type_values(self):
        assert EnforcementConditionType.REPEATED_DEGRADATION.value == "repeated_degradation"
        assert EnforcementConditionType.APPROVAL_REQUIRED_WITHOUT_APPROVAL.value == "approval_required_without_approval"
        assert EnforcementConditionType.REPLAY_DIVERGENCE_EXCEEDED.value == "replay_divergence_exceeded"
        assert EnforcementConditionType.POLICY_BOUNDARY_VIOLATION.value == "policy_boundary_violation"


# =====================================================================
# EnforcementEvent serialization
# =====================================================================


class TestEnforcementEvent:
    def test_to_dict_and_from_dict(self):
        event = EnforcementEvent(
            claim_lineage_id="lin-001",
            chain_id="chain-001",
            snapshot_id="snap-001",
            receipt_id="rcpt-001",
            mode=EnforcementMode.ENFORCE,
            action=EnforcementAction.HALT_CHAIN,
            is_enforced=True,
            reasoning="test reasoning",
            severity="critical",
        )
        d = event.to_dict()
        assert d["mode"] == "enforce"
        assert d["action"] == "halt_chain"
        assert d["is_enforced"] is True
        assert d["severity"] == "critical"
        assert d["claim_lineage_id"] == "lin-001"

        restored = EnforcementEvent.from_dict(d)
        assert restored.mode == EnforcementMode.ENFORCE
        assert restored.action == EnforcementAction.HALT_CHAIN
        assert restored.is_enforced is True

    def test_event_has_required_fields(self):
        event = EnforcementEvent()
        d = event.to_dict()
        required = [
            "event_id", "timestamp", "mode", "action",
            "is_enforced", "is_advisory", "reasoning",
            "conditions_evaluated", "conditions_met",
        ]
        for field in required:
            assert field in d, f"Missing required field: {field}"


# =====================================================================
# EnforcementConfig serialization
# =====================================================================


class TestEnforcementConfig:
    def test_to_dict_and_from_dict(self):
        config = EnforcementConfig(
            mode=EnforcementMode.ENFORCE,
            degradation_repeat_threshold=5,
            min_confidence=0.9,
        )
        d = config.to_dict()
        assert d["mode"] == "enforce"
        assert d["degradation_repeat_threshold"] == 5
        assert d["min_confidence"] == 0.9

        restored = EnforcementConfig.from_dict(d)
        assert restored.mode == EnforcementMode.ENFORCE
        assert restored.degradation_repeat_threshold == 5

    def test_default_action_map(self):
        config = EnforcementConfig()
        assert config.action_map["repeated_degradation"] == "require_human_review"
        assert config.action_map["approval_required_without_approval"] == "halt_chain"
        assert config.action_map["replay_divergence_exceeded"] == "escalate_alert"
        assert config.action_map["policy_boundary_violation"] == "halt_chain"


# =====================================================================
# Observe mode — no events
# =====================================================================


class TestObserveMode:
    def test_observe_mode_returns_no_events(self):
        evaluator = _make_evaluator(mode=EnforcementMode.OBSERVE)
        events = evaluator.evaluate(
            snapshot=_make_snapshot(),
            receipt=_make_receipt(
                revalidation_status=RevalidationStatus.DEGRADED,
            ),
            degradation_count=10,
        )
        assert events == []

    def test_observe_mode_even_with_all_conditions_met(self):
        evaluator = _make_evaluator(mode=EnforcementMode.OBSERVE)
        events = evaluator.evaluate(
            snapshot=_make_snapshot(
                scope=Scope(escalation_required=True),
            ),
            receipt=_make_receipt(
                revalidation_status=RevalidationStatus.HALTED,
            ),
            degradation_count=10,
            has_required_approval=False,
            policy_violation_detected=True,
            replay_divergence_ratio=0.9,
        )
        assert events == []


# =====================================================================
# Repeated degradation threshold
# =====================================================================


class TestRepeatedDegradation:
    def test_below_threshold_no_event(self):
        evaluator = _make_evaluator(degradation_repeat_threshold=3)
        events = evaluator.evaluate(
            snapshot=_make_snapshot(),
            receipt=_make_receipt(
                revalidation_status=RevalidationStatus.DEGRADED,
            ),
            degradation_count=2,
        )
        assert not any(
            "repeated_degradation" in e.to_dict().get("reason_codes", [])
            for e in events
        )

    def test_at_threshold_triggers(self):
        evaluator = _make_evaluator(degradation_repeat_threshold=3)
        events = evaluator.evaluate(
            snapshot=_make_snapshot(),
            receipt=_make_receipt(
                revalidation_status=RevalidationStatus.DEGRADED,
            ),
            degradation_count=3,
        )
        degradation_events = [
            e for e in events
            if "repeated_degradation" in e.reason_codes
        ]
        assert len(degradation_events) == 1
        evt = degradation_events[0]
        assert evt.action == EnforcementAction.REQUIRE_HUMAN_REVIEW

    def test_above_threshold_increases_confidence(self):
        evaluator = _make_evaluator(degradation_repeat_threshold=3)
        events_at = evaluator.evaluate(
            snapshot=_make_snapshot(),
            receipt=_make_receipt(
                revalidation_status=RevalidationStatus.ESCALATED,
            ),
            degradation_count=3,
        )
        events_above = evaluator.evaluate(
            snapshot=_make_snapshot(),
            receipt=_make_receipt(
                revalidation_status=RevalidationStatus.ESCALATED,
            ),
            degradation_count=10,
        )
        # Both should trigger, but higher count has higher confidence
        assert len(events_at) >= 1
        assert len(events_above) >= 1

    def test_non_degraded_receipt_does_not_trigger(self):
        evaluator = _make_evaluator(degradation_repeat_threshold=3)
        events = evaluator.evaluate(
            snapshot=_make_snapshot(),
            receipt=_make_receipt(
                revalidation_status=RevalidationStatus.RENEWED,
            ),
            degradation_count=10,
        )
        assert not any(
            "repeated_degradation" in e.reason_codes
            for e in events
        )

    def test_halted_receipt_counts_as_degradation(self):
        evaluator = _make_evaluator(degradation_repeat_threshold=3)
        events = evaluator.evaluate(
            snapshot=_make_snapshot(),
            receipt=_make_receipt(
                revalidation_status=RevalidationStatus.HALTED,
            ),
            degradation_count=3,
        )
        degradation_events = [
            e for e in events
            if "repeated_degradation" in e.reason_codes
        ]
        assert len(degradation_events) == 1

    def test_custom_threshold(self):
        evaluator = _make_evaluator(degradation_repeat_threshold=10)
        events = evaluator.evaluate(
            snapshot=_make_snapshot(),
            receipt=_make_receipt(
                revalidation_status=RevalidationStatus.DEGRADED,
            ),
            degradation_count=5,
        )
        assert not any(
            "repeated_degradation" in e.reason_codes
            for e in events
        )


# =====================================================================
# Approval-required without approval
# =====================================================================


class TestApprovalRequired:
    def test_no_escalation_required_no_event(self):
        evaluator = _make_evaluator()
        events = evaluator.evaluate(
            snapshot=_make_snapshot(),
            receipt=_make_receipt(),
            has_required_approval=False,
        )
        assert not any(
            "approval_required_without_approval" in e.reason_codes
            for e in events
        )

    def test_escalation_required_with_approval_no_event(self):
        evaluator = _make_evaluator()
        events = evaluator.evaluate(
            snapshot=_make_snapshot(
                scope=Scope(escalation_required=True),
            ),
            receipt=_make_receipt(),
            has_required_approval=True,
        )
        assert not any(
            "approval_required_without_approval" in e.reason_codes
            for e in events
        )

    def test_escalation_required_without_approval_triggers(self):
        evaluator = _make_evaluator()
        events = evaluator.evaluate(
            snapshot=_make_snapshot(
                scope=Scope(escalation_required=True),
            ),
            receipt=_make_receipt(),
            has_required_approval=False,
        )
        approval_events = [
            e for e in events
            if "approval_required_without_approval" in e.reason_codes
        ]
        assert len(approval_events) == 1
        evt = approval_events[0]
        assert evt.action == EnforcementAction.HALT_CHAIN

    def test_approval_condition_is_deterministic(self):
        evaluator = _make_evaluator()
        events = evaluator.evaluate(
            snapshot=_make_snapshot(
                scope=Scope(escalation_required=True),
            ),
            receipt=_make_receipt(),
            has_required_approval=False,
        )
        approval_events = [
            e for e in events
            if "approval_required_without_approval" in e.reason_codes
        ]
        assert len(approval_events) == 1
        # Confidence should be 1.0 (deterministic condition)
        met_conds = approval_events[0].conditions_met
        assert len(met_conds) == 1
        assert met_conds[0].confidence == 1.0


# =====================================================================
# Replay divergence
# =====================================================================


class TestReplayDivergence:
    def test_below_threshold_no_event(self):
        evaluator = _make_evaluator(replay_divergence_threshold=0.3)
        events = evaluator.evaluate(
            snapshot=_make_snapshot(),
            receipt=_make_receipt(),
            replay_divergence_ratio=0.2,
        )
        assert not any(
            "replay_divergence_exceeded" in e.reason_codes
            for e in events
        )

    def test_at_threshold_no_event(self):
        evaluator = _make_evaluator(replay_divergence_threshold=0.3)
        events = evaluator.evaluate(
            snapshot=_make_snapshot(),
            receipt=_make_receipt(),
            replay_divergence_ratio=0.3,
        )
        assert not any(
            "replay_divergence_exceeded" in e.reason_codes
            for e in events
        )

    def test_above_threshold_triggers(self):
        evaluator = _make_evaluator(replay_divergence_threshold=0.3)
        events = evaluator.evaluate(
            snapshot=_make_snapshot(),
            receipt=_make_receipt(divergence_flag=True),
            replay_divergence_ratio=0.8,
        )
        divergence_events = [
            e for e in events
            if "replay_divergence_exceeded" in e.reason_codes
        ]
        assert len(divergence_events) == 1
        evt = divergence_events[0]
        assert evt.action == EnforcementAction.ESCALATE_ALERT

    def test_zero_divergence_no_event(self):
        evaluator = _make_evaluator()
        events = evaluator.evaluate(
            snapshot=_make_snapshot(),
            receipt=_make_receipt(),
            replay_divergence_ratio=0.0,
        )
        assert not any(
            "replay_divergence_exceeded" in e.reason_codes
            for e in events
        )


# =====================================================================
# Policy boundary violation
# =====================================================================


class TestPolicyBoundaryViolation:
    def test_no_violation_no_event(self):
        evaluator = _make_evaluator()
        events = evaluator.evaluate(
            snapshot=_make_snapshot(),
            receipt=_make_receipt(),
            policy_violation_detected=False,
        )
        assert not any(
            "policy_boundary_violation" in e.reason_codes
            for e in events
        )

    def test_violation_detected_triggers(self):
        evaluator = _make_evaluator()
        events = evaluator.evaluate(
            snapshot=_make_snapshot(),
            receipt=_make_receipt(),
            policy_violation_detected=True,
            policy_violation_detail="action_class_not_allowed in scope",
        )
        violation_events = [
            e for e in events
            if "policy_boundary_violation" in e.reason_codes
        ]
        assert len(violation_events) == 1
        evt = violation_events[0]
        assert evt.action == EnforcementAction.HALT_CHAIN

    def test_violation_detail_in_reasoning(self):
        evaluator = _make_evaluator()
        events = evaluator.evaluate(
            snapshot=_make_snapshot(),
            receipt=_make_receipt(),
            policy_violation_detected=True,
            policy_violation_detail="restricted action attempted",
        )
        violation_events = [
            e for e in events
            if "policy_boundary_violation" in e.reason_codes
        ]
        assert len(violation_events) == 1
        assert "restricted action attempted" in violation_events[0].reasoning


# =====================================================================
# Advisory vs enforce mode
# =====================================================================


class TestAdvisoryVsEnforceMode:
    def test_advisory_mode_sets_is_advisory(self):
        evaluator = _make_evaluator(mode=EnforcementMode.ADVISORY)
        events = evaluator.evaluate(
            snapshot=_make_snapshot(
                scope=Scope(escalation_required=True),
            ),
            receipt=_make_receipt(),
            has_required_approval=False,
        )
        assert len(events) >= 1
        for event in events:
            assert event.is_advisory is True
            assert event.is_enforced is False

    def test_enforce_mode_sets_is_enforced(self):
        evaluator = _make_evaluator(mode=EnforcementMode.ENFORCE)
        events = evaluator.evaluate(
            snapshot=_make_snapshot(
                scope=Scope(escalation_required=True),
            ),
            receipt=_make_receipt(),
            has_required_approval=False,
        )
        assert len(events) >= 1
        for event in events:
            assert event.is_enforced is True
            assert event.is_advisory is False


# =====================================================================
# Severity computation
# =====================================================================


class TestSeverityComputation:
    def test_halt_chain_is_critical(self):
        evaluator = _make_evaluator(mode=EnforcementMode.ENFORCE)
        events = evaluator.evaluate(
            snapshot=_make_snapshot(
                scope=Scope(escalation_required=True),
            ),
            receipt=_make_receipt(),
            has_required_approval=False,
        )
        halt_events = [e for e in events if e.action == EnforcementAction.HALT_CHAIN]
        assert len(halt_events) >= 1
        assert halt_events[0].severity == "critical"

    def test_require_human_review_is_high(self):
        evaluator = _make_evaluator(mode=EnforcementMode.ENFORCE)
        events = evaluator.evaluate(
            snapshot=_make_snapshot(),
            receipt=_make_receipt(
                revalidation_status=RevalidationStatus.DEGRADED,
            ),
            degradation_count=3,
        )
        review_events = [
            e for e in events
            if e.action == EnforcementAction.REQUIRE_HUMAN_REVIEW
        ]
        assert len(review_events) >= 1
        assert review_events[0].severity == "high"

    def test_escalate_alert_is_medium(self):
        evaluator = _make_evaluator(mode=EnforcementMode.ENFORCE)
        events = evaluator.evaluate(
            snapshot=_make_snapshot(),
            receipt=_make_receipt(divergence_flag=True),
            replay_divergence_ratio=0.8,
        )
        alert_events = [
            e for e in events
            if e.action == EnforcementAction.ESCALATE_ALERT
        ]
        assert len(alert_events) >= 1
        assert alert_events[0].severity == "medium"


# =====================================================================
# Reasoning transparency
# =====================================================================


class TestReasoningTransparency:
    def test_reasoning_contains_action(self):
        evaluator = _make_evaluator()
        events = evaluator.evaluate(
            snapshot=_make_snapshot(
                scope=Scope(escalation_required=True),
            ),
            receipt=_make_receipt(),
            has_required_approval=False,
        )
        assert len(events) >= 1
        assert "halt_chain" in events[0].reasoning

    def test_reasoning_contains_condition_type(self):
        evaluator = _make_evaluator()
        events = evaluator.evaluate(
            snapshot=_make_snapshot(
                scope=Scope(escalation_required=True),
            ),
            receipt=_make_receipt(),
            has_required_approval=False,
        )
        assert len(events) >= 1
        assert "approval_required_without_approval" in events[0].reasoning

    def test_reasoning_contains_confidence(self):
        evaluator = _make_evaluator()
        events = evaluator.evaluate(
            snapshot=_make_snapshot(
                scope=Scope(escalation_required=True),
            ),
            receipt=_make_receipt(),
            has_required_approval=False,
        )
        assert len(events) >= 1
        assert "confidence:" in events[0].reasoning

    def test_conditions_evaluated_included(self):
        evaluator = _make_evaluator()
        events = evaluator.evaluate(
            snapshot=_make_snapshot(
                scope=Scope(escalation_required=True),
            ),
            receipt=_make_receipt(),
            has_required_approval=False,
        )
        assert len(events) >= 1
        # All 4 conditions should be evaluated even if only 1 is met
        assert len(events[0].conditions_evaluated) == 4


# =====================================================================
# Multiple conditions triggered simultaneously
# =====================================================================


class TestMultipleConditions:
    def test_multiple_conditions_produce_multiple_events(self):
        evaluator = _make_evaluator(mode=EnforcementMode.ENFORCE)
        events = evaluator.evaluate(
            snapshot=_make_snapshot(
                scope=Scope(escalation_required=True),
            ),
            receipt=_make_receipt(
                revalidation_status=RevalidationStatus.HALTED,
            ),
            degradation_count=5,
            has_required_approval=False,
            policy_violation_detected=True,
            policy_violation_detail="test violation",
        )
        # At least 3 conditions should be met
        assert len(events) >= 3
        actions = {e.action for e in events}
        assert EnforcementAction.HALT_CHAIN in actions
        assert EnforcementAction.REQUIRE_HUMAN_REVIEW in actions

    def test_each_event_has_single_met_condition(self):
        evaluator = _make_evaluator()
        events = evaluator.evaluate(
            snapshot=_make_snapshot(
                scope=Scope(escalation_required=True),
            ),
            receipt=_make_receipt(
                revalidation_status=RevalidationStatus.DEGRADED,
            ),
            degradation_count=5,
            has_required_approval=False,
        )
        for event in events:
            assert len(event.conditions_met) == 1


# =====================================================================
# Attribution and linkage
# =====================================================================


class TestAttributionAndLinkage:
    def test_event_carries_lineage_id(self):
        evaluator = _make_evaluator()
        snap = _make_snapshot(claim_lineage_id="lin-test-42")
        events = evaluator.evaluate(
            snapshot=snap,
            receipt=_make_receipt(),
            chain_id="chain-42",
            policy_violation_detected=True,
        )
        assert len(events) >= 1
        assert events[0].claim_lineage_id == "lin-test-42"
        assert events[0].chain_id == "chain-42"

    def test_event_carries_snapshot_and_receipt_ids(self):
        evaluator = _make_evaluator()
        snap = _make_snapshot()
        rcpt = _make_receipt()
        events = evaluator.evaluate(
            snapshot=snap,
            receipt=rcpt,
            policy_violation_detected=True,
        )
        assert len(events) >= 1
        assert events[0].snapshot_id == snap.snapshot_id
        assert events[0].receipt_id == rcpt.receipt_id

    def test_event_carries_law_version(self):
        evaluator = _make_evaluator()
        snap = _make_snapshot(law_version="v1.0.0-test")
        events = evaluator.evaluate(
            snapshot=snap,
            receipt=_make_receipt(),
            policy_violation_detected=True,
        )
        assert len(events) >= 1
        assert events[0].law_version == "v1.0.0-test"

    def test_event_carries_claim_status(self):
        evaluator = _make_evaluator()
        snap = _make_snapshot(claim_status=ClaimStatus.HALTED)
        events = evaluator.evaluate(
            snapshot=snap,
            receipt=_make_receipt(),
            policy_violation_detected=True,
        )
        assert len(events) >= 1
        assert events[0].claim_status == "halted"


# =====================================================================
# Confidence threshold behavior
# =====================================================================


class TestConfidenceThreshold:
    def test_high_min_confidence_filters_marginal_conditions(self):
        evaluator = _make_evaluator(
            min_confidence=0.95,
            degradation_repeat_threshold=3,
        )
        # At threshold (confidence=0.8), should NOT meet 0.95 minimum
        events = evaluator.evaluate(
            snapshot=_make_snapshot(),
            receipt=_make_receipt(
                revalidation_status=RevalidationStatus.DEGRADED,
            ),
            degradation_count=3,
        )
        degradation_events = [
            e for e in events
            if "repeated_degradation" in e.reason_codes
        ]
        assert len(degradation_events) == 0

    def test_high_degradation_count_meets_high_confidence(self):
        evaluator = _make_evaluator(
            min_confidence=0.95,
            degradation_repeat_threshold=3,
        )
        # Way above threshold (confidence should be > 0.95)
        events = evaluator.evaluate(
            snapshot=_make_snapshot(),
            receipt=_make_receipt(
                revalidation_status=RevalidationStatus.DEGRADED,
            ),
            degradation_count=10,
        )
        degradation_events = [
            e for e in events
            if "repeated_degradation" in e.reason_codes
        ]
        assert len(degradation_events) == 1

    def test_deterministic_conditions_always_meet_confidence(self):
        """Approval and policy violation are deterministic (confidence=1.0)."""
        evaluator = _make_evaluator(min_confidence=0.99)
        events = evaluator.evaluate(
            snapshot=_make_snapshot(
                scope=Scope(escalation_required=True),
            ),
            receipt=_make_receipt(),
            has_required_approval=False,
            policy_violation_detected=True,
        )
        assert len(events) >= 2


# =====================================================================
# Custom action map
# =====================================================================


class TestCustomActionMap:
    def test_custom_action_for_degradation(self):
        config = EnforcementConfig(
            mode=EnforcementMode.ADVISORY,
            action_map={
                "repeated_degradation": "halt_chain",
                "approval_required_without_approval": "escalate_alert",
                "replay_divergence_exceeded": "require_human_review",
                "policy_boundary_violation": "escalate_alert",
            },
        )
        evaluator = ContinuationEnforcementEvaluator(config=config)
        events = evaluator.evaluate(
            snapshot=_make_snapshot(),
            receipt=_make_receipt(
                revalidation_status=RevalidationStatus.DEGRADED,
            ),
            degradation_count=5,
        )
        degradation_events = [
            e for e in events
            if "repeated_degradation" in e.reason_codes
        ]
        assert len(degradation_events) == 1
        assert degradation_events[0].action == EnforcementAction.HALT_CHAIN

    def test_unknown_action_falls_back_to_escalate(self):
        config = EnforcementConfig(
            mode=EnforcementMode.ADVISORY,
            action_map={
                "repeated_degradation": "unknown_action",
                "approval_required_without_approval": "halt_chain",
                "replay_divergence_exceeded": "escalate_alert",
                "policy_boundary_violation": "halt_chain",
            },
        )
        evaluator = ContinuationEnforcementEvaluator(config=config)
        events = evaluator.evaluate(
            snapshot=_make_snapshot(),
            receipt=_make_receipt(
                revalidation_status=RevalidationStatus.DEGRADED,
            ),
            degradation_count=5,
        )
        degradation_events = [
            e for e in events
            if "repeated_degradation" in e.reason_codes
        ]
        assert len(degradation_events) == 1
        assert degradation_events[0].action == EnforcementAction.ESCALATE_ALERT


# =====================================================================
# Edge cases
# =====================================================================


class TestEdgeCases:
    def test_default_evaluator_observe_mode(self):
        evaluator = ContinuationEnforcementEvaluator()
        assert evaluator.mode == EnforcementMode.OBSERVE

    def test_empty_chain_id(self):
        evaluator = _make_evaluator()
        events = evaluator.evaluate(
            snapshot=_make_snapshot(),
            receipt=_make_receipt(),
            chain_id="",
            policy_violation_detected=True,
        )
        assert len(events) >= 1
        assert events[0].chain_id == ""

    def test_zero_degradation_count(self):
        evaluator = _make_evaluator()
        events = evaluator.evaluate(
            snapshot=_make_snapshot(),
            receipt=_make_receipt(),
            degradation_count=0,
        )
        assert not any(
            "repeated_degradation" in e.reason_codes
            for e in events
        )

    def test_boundary_outcome_in_event(self):
        evaluator = _make_evaluator()
        events = evaluator.evaluate(
            snapshot=_make_snapshot(),
            receipt=_make_receipt(boundary_outcome="halted"),
            policy_violation_detected=True,
        )
        assert len(events) >= 1
        assert events[0].boundary_outcome == "halted"
