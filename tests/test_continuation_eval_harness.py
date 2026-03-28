# tests/test_continuation_eval_harness.py
# -*- coding: utf-8 -*-
"""
Minimal evaluation harness for Continuation Runtime phase-1.

Runs a battery of scenarios and computes key metrics:
  - divergence_detection_rate
  - false_alarm_rate
  - support_loss_capture_rate
  - burden_headroom_drift_usefulness
  - replay_explanatory_usefulness
  - state_receipt_separation_clarity

This is not a pytest-only file — the harness can also be run standalone
for reporting.  But it is structured as pytest tests so CI picks it up.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple

import pytest

from veritas_os.core.continuation_runtime.revalidator import (
    run_continuation_revalidation_shadow,
    ContinuationRevalidator,
    PresentCondition,
)
from veritas_os.core.continuation_runtime.lineage import (
    ContinuationClaimLineage,
    ClaimStatus,
)
from veritas_os.core.continuation_runtime.receipt import ContinuationReceipt
from veritas_os.core.continuation_runtime.snapshot import ClaimStateSnapshot


# =====================================================================
# Scenario definitions
# =====================================================================


@dataclass
class EvalScenario:
    """A single evaluation scenario."""

    name: str
    chain_id: str = "eval-chain"
    context: Dict[str, Any] = field(default_factory=dict)
    prior_decision_status: str = "allow"
    expected_divergence: bool = False
    expected_status: str = "live"
    is_support_loss: bool = False
    has_burden_drift: bool = False


_SCENARIOS: List[EvalScenario] = [
    # Normal — no divergence
    EvalScenario(
        name="normal_live",
        context={},
        expected_divergence=False,
        expected_status="live",
    ),
    # True positive: support lost
    EvalScenario(
        name="support_lost_revoked",
        chain_id="",
        context={"authorization": "", "policy_ref": ""},
        expected_divergence=True,
        expected_status="revoked",
        is_support_loss=True,
    ),
    # True positive: burden degraded
    EvalScenario(
        name="burden_degraded",
        context={
            "required_evidence": ["e1", "e2", "e3"],
            "satisfied_evidence": ["e1"],
        },
        expected_divergence=True,
        expected_status="degraded",
        has_burden_drift=True,
    ),
    # True positive: headroom halted
    EvalScenario(
        name="headroom_halted",
        context={
            "required_evidence": ["e1", "e2"],
            "satisfied_evidence": [],
            "burden_current_level": 0.0,
        },
        expected_divergence=True,
        expected_status="halted",
        has_burden_drift=True,
    ),
    # True positive: scope narrowed
    EvalScenario(
        name="scope_narrowed",
        context={"restricted_actions": ["execute"]},
        expected_divergence=True,
        expected_status="narrowed",
    ),
    # True positive: escalation required
    EvalScenario(
        name="escalation_required",
        context={"escalation_required": True},
        expected_divergence=True,
        expected_status="escalated",
    ),
    # Normal — explicit good conditions
    EvalScenario(
        name="explicit_good_conditions",
        context={
            "authorization": "admin",
            "policy_ref": "default",
            "environment_status": "nominal",
        },
        expected_divergence=False,
        expected_status="live",
    ),
    # Burden partial but not breached
    EvalScenario(
        name="burden_partial_not_breached",
        context={
            "required_evidence": ["e1", "e2"],
            "satisfied_evidence": ["e1", "e2"],
        },
        expected_divergence=False,
        expected_status="live",
    ),
]


def _run_scenario(scenario: EvalScenario) -> Tuple[ClaimStateSnapshot, ContinuationReceipt]:
    """Run a single scenario and return (snapshot, receipt)."""
    _, snap, rcpt = run_continuation_revalidation_shadow(
        chain_id=scenario.chain_id,
        step_index=1,
        query=f"eval: {scenario.name}",
        context=scenario.context,
        prior_decision_status=scenario.prior_decision_status,
    )
    return snap, rcpt


# =====================================================================
# Metric computation
# =====================================================================


@dataclass
class EvalMetrics:
    """Evaluation metrics for the continuation runtime."""

    total_scenarios: int = 0
    divergence_true_positive: int = 0
    divergence_false_positive: int = 0
    divergence_true_negative: int = 0
    divergence_false_negative: int = 0
    support_loss_detected: int = 0
    support_loss_total: int = 0
    burden_drift_detected: int = 0
    burden_drift_total: int = 0
    state_receipt_separated: int = 0
    replay_explainable: int = 0

    @property
    def divergence_detection_rate(self) -> float:
        tp = self.divergence_true_positive
        fn = self.divergence_false_negative
        return tp / (tp + fn) if (tp + fn) > 0 else 0.0

    @property
    def false_alarm_rate(self) -> float:
        fp = self.divergence_false_positive
        tn = self.divergence_true_negative
        return fp / (fp + tn) if (fp + tn) > 0 else 0.0

    @property
    def support_loss_capture_rate(self) -> float:
        return (
            self.support_loss_detected / self.support_loss_total
            if self.support_loss_total > 0
            else 0.0
        )

    @property
    def burden_headroom_drift_usefulness(self) -> float:
        return (
            self.burden_drift_detected / self.burden_drift_total
            if self.burden_drift_total > 0
            else 0.0
        )

    @property
    def replay_explanatory_usefulness(self) -> float:
        return (
            self.replay_explainable / self.total_scenarios
            if self.total_scenarios > 0
            else 0.0
        )

    @property
    def state_receipt_separation_clarity(self) -> float:
        return (
            self.state_receipt_separated / self.total_scenarios
            if self.total_scenarios > 0
            else 0.0
        )


def _compute_metrics() -> EvalMetrics:
    """Run all scenarios and compute metrics."""
    metrics = EvalMetrics()

    for scenario in _SCENARIOS:
        snap, rcpt = _run_scenario(scenario)
        metrics.total_scenarios += 1

        actual_divergence = rcpt.divergence_flag
        expected_divergence = scenario.expected_divergence

        if expected_divergence and actual_divergence:
            metrics.divergence_true_positive += 1
        elif not expected_divergence and not actual_divergence:
            metrics.divergence_true_negative += 1
        elif not expected_divergence and actual_divergence:
            metrics.divergence_false_positive += 1
        elif expected_divergence and not actual_divergence:
            metrics.divergence_false_negative += 1

        # Support loss detection
        if scenario.is_support_loss:
            metrics.support_loss_total += 1
            if snap.claim_status == ClaimStatus.REVOKED:
                metrics.support_loss_detected += 1

        # Burden/headroom drift
        if scenario.has_burden_drift:
            metrics.burden_drift_total += 1
            if snap.claim_status in (ClaimStatus.DEGRADED, ClaimStatus.HALTED):
                metrics.burden_drift_detected += 1

        # State/receipt separation check
        snap_d = snap.to_dict()
        rcpt_d = rcpt.to_dict()
        receipt_only_fields = {"revalidation_status", "divergence_flag", "should_refuse_before_effect"}
        state_only_fields = {"support_basis", "burden_state", "headroom_state"}
        if (
            not receipt_only_fields.intersection(snap_d.keys())
            and not state_only_fields.intersection(rcpt_d.keys())
        ):
            metrics.state_receipt_separated += 1

        # Replay explainability: receipt has digests and reason codes
        if (
            rcpt.support_basis_digest is not None
            and rcpt.scope_digest is not None
            and rcpt.burden_headroom_digest is not None
            and rcpt.law_version_id
        ):
            metrics.replay_explainable += 1

    return metrics


# =====================================================================
# Pytest tests wrapping the harness
# =====================================================================


class TestEvalHarness:
    """Evaluation harness as pytest tests."""

    def test_divergence_detection_rate_is_perfect(self):
        """All known divergence scenarios must be detected."""
        metrics = _compute_metrics()
        assert metrics.divergence_detection_rate == 1.0

    def test_false_alarm_rate_is_zero(self):
        """No false alarms on non-divergent scenarios."""
        metrics = _compute_metrics()
        assert metrics.false_alarm_rate == 0.0

    def test_support_loss_capture_rate_is_perfect(self):
        """All support-loss scenarios captured."""
        metrics = _compute_metrics()
        assert metrics.support_loss_capture_rate == 1.0

    def test_burden_headroom_drift_usefulness_is_perfect(self):
        """All burden/headroom drift scenarios detected."""
        metrics = _compute_metrics()
        assert metrics.burden_headroom_drift_usefulness == 1.0

    def test_replay_explanatory_usefulness_is_perfect(self):
        """All receipts have sufficient data for replay explanation."""
        metrics = _compute_metrics()
        assert metrics.replay_explanatory_usefulness == 1.0

    def test_state_receipt_separation_clarity_is_perfect(self):
        """State and receipt never contaminate each other."""
        metrics = _compute_metrics()
        assert metrics.state_receipt_separation_clarity == 1.0

    def test_scenario_count_minimum(self):
        """Harness has at least 8 scenarios."""
        metrics = _compute_metrics()
        assert metrics.total_scenarios >= 8

    def test_metrics_printable_report(self):
        """Metrics can be rendered as a human-readable report."""
        metrics = _compute_metrics()
        report = {
            "total_scenarios": metrics.total_scenarios,
            "divergence_detection_rate": metrics.divergence_detection_rate,
            "false_alarm_rate": metrics.false_alarm_rate,
            "support_loss_capture_rate": metrics.support_loss_capture_rate,
            "burden_headroom_drift_usefulness": metrics.burden_headroom_drift_usefulness,
            "replay_explanatory_usefulness": metrics.replay_explanatory_usefulness,
            "state_receipt_separation_clarity": metrics.state_receipt_separation_clarity,
        }
        # All values must be numeric and within [0, 1]
        for key, val in report.items():
            if key == "total_scenarios":
                assert isinstance(val, int) and val > 0
            else:
                assert 0.0 <= val <= 1.0, f"{key} out of range: {val}"
