"""Test-only Observe Mode decision wrapper for fixture generation.

This module provides a pure helper that converts a would-be governance
enforcement outcome into a semantically validated ``GovernanceObservation``.
It is intentionally scoped to development/test tooling and does not modify
runtime policy behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from veritas_os.api.schemas import GovernanceObservation
from veritas_os.governance.observation_evaluator import evaluate_governance_observation

WouldBeOutcome = Literal["proceed", "block", "human_review"]


@dataclass(frozen=True)
class ObserveModeDecisionInput:
    """Input contract for test-only observation payload generation."""

    policy_mode: str
    environment: str
    would_be_outcome: WouldBeOutcome
    reason: str | None = None


def _normalized_reason(reason: str | None) -> str | None:
    if reason is None:
        return None
    stripped = reason.strip()
    return stripped if stripped else None


def build_governance_observation_for_dry_run(
    decision: ObserveModeDecisionInput,
) -> GovernanceObservation:
    """Build and validate a test-only governance observation payload.

    The function is pure and side-effect free. It performs no runtime mutation,
    no IO, and no policy engine integration.
    """

    if decision.policy_mode == "observe" and decision.environment == "production":
        raise ValueError("observe mode in production is not allowed")

    normalized_reason = _normalized_reason(decision.reason)
    would_have_blocked = decision.would_be_outcome == "block"

    if would_have_blocked and normalized_reason is None:
        raise ValueError("would_be_outcome='block' requires a non-empty reason")

    observed_outcome = (
        "block" if decision.would_be_outcome == "block" else decision.would_be_outcome
    )

    if decision.policy_mode == "observe":
        effective_outcome = "proceed"
        operator_warning = True
    elif decision.policy_mode == "enforce":
        effective_outcome = "block" if would_have_blocked else "proceed"
        operator_warning = would_have_blocked
    else:
        effective_outcome = decision.would_be_outcome
        operator_warning = False

    observation = GovernanceObservation(
        policy_mode=decision.policy_mode,
        environment=decision.environment,
        would_have_blocked=would_have_blocked,
        would_have_blocked_reason=normalized_reason if would_have_blocked else None,
        effective_outcome=effective_outcome,
        observed_outcome=observed_outcome,
        operator_warning=operator_warning,
        audit_required=True,
    )

    evaluation = evaluate_governance_observation(observation)
    if not evaluation.valid:
        issues = ", ".join(f"{issue.code}: {issue.message}" for issue in evaluation.issues)
        raise ValueError(f"generated governance_observation is semantically invalid: {issues}")

    return observation
