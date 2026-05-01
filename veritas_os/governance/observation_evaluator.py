"""Dry-run evaluator for governance observation semantic consistency.

This module validates ``GovernanceObservation`` fixture/test payload semantics
without changing runtime governance behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from veritas_os.api.schemas import GovernanceObservation


ObservationIssueSeverity = Literal["error", "warning"]


@dataclass(frozen=True)
class ObservationEvaluationIssue:
    """Single semantic issue produced by observation evaluation."""

    code: str
    message: str
    severity: ObservationIssueSeverity


@dataclass(frozen=True)
class ObservationEvaluationResult:
    """Result object for dry-run governance observation evaluation."""

    valid: bool
    issues: tuple[ObservationEvaluationIssue, ...]


def _is_blank(value: str | None) -> bool:
    return value is None or value.strip() == ""


def evaluate_governance_observation(
    observation: "GovernanceObservation",
) -> ObservationEvaluationResult:
    """Validate semantic consistency for ``GovernanceObservation``.

    This is a pure function intended for fixture/tests and dry-run checks only.
    It has no side effects and does not alter runtime enforcement behavior.
    """

    issues: list[ObservationEvaluationIssue] = []

    if observation.environment == "production" and observation.policy_mode == "observe":
        issues.append(
            ObservationEvaluationIssue(
                code="OBSERVE_MODE_NOT_ALLOWED_IN_PRODUCTION",
                message="Observe mode is not allowed in production environment.",
                severity="error",
            )
        )

    if observation.policy_mode == "observe" and observation.audit_required is not True:
        issues.append(
            ObservationEvaluationIssue(
                code="OBSERVE_MODE_REQUIRES_AUDIT",
                message="Observe mode requires audit_required to be true.",
                severity="error",
            )
        )

    if observation.policy_mode == "observe" and observation.operator_warning is not True:
        issues.append(
            ObservationEvaluationIssue(
                code="OBSERVE_MODE_REQUIRES_OPERATOR_WARNING",
                message="Observe mode requires operator_warning to be true.",
                severity="error",
            )
        )

    if observation.would_have_blocked is True and _is_blank(observation.would_have_blocked_reason):
        issues.append(
            ObservationEvaluationIssue(
                code="WOULD_HAVE_BLOCKED_REQUIRES_REASON",
                message="would_have_blocked=true requires would_have_blocked_reason.",
                severity="error",
            )
        )

    if observation.would_have_blocked is True and _is_blank(observation.observed_outcome):
        issues.append(
            ObservationEvaluationIssue(
                code="WOULD_HAVE_BLOCKED_REQUIRES_OBSERVED_OUTCOME",
                message="would_have_blocked=true requires observed_outcome.",
                severity="error",
            )
        )

    if (
        observation.policy_mode == "observe"
        and observation.would_have_blocked is True
        and observation.observed_outcome != "block"
    ):
        issues.append(
            ObservationEvaluationIssue(
                code="OBSERVED_OUTCOME_SHOULD_PRESERVE_BLOCK",
                message="Observe mode should preserve blocked observed_outcome when would_have_blocked=true.",
                severity="warning",
            )
        )

    if (
        observation.policy_mode == "enforce"
        and observation.would_have_blocked is True
        and observation.effective_outcome == "proceed"
    ):
        issues.append(
            ObservationEvaluationIssue(
                code="ENFORCE_MODE_CANNOT_PROCEED_WHEN_BLOCKED",
                message="Enforce mode cannot proceed when would_have_blocked=true.",
                severity="error",
            )
        )

    if observation.policy_mode == "off" and observation.audit_required is not True:
        issues.append(
            ObservationEvaluationIssue(
                code="OFF_MODE_REQUIRES_AUDIT",
                message="Off mode requires audit_required to be true.",
                severity="error",
            )
        )

    has_errors = any(issue.severity == "error" for issue in issues)
    return ObservationEvaluationResult(valid=not has_errors, issues=tuple(issues))
