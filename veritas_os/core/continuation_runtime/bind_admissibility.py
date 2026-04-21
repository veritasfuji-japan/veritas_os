# -*- coding: utf-8 -*-
"""Deterministic bind-time admissibility evaluator.

This module provides a pure, fail-closed re-check layer for bind-time
admissibility. It does not generate decisions, does not execute side effects,
and does not modify FUJI or continuation runtime semantics.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional


class AdmissibilityOutcome(str, Enum):
    """Recommended bind-time outcome."""

    ELIGIBLE_TO_COMMIT = "eligible_to_commit"
    BLOCK = "block"
    ESCALATE = "escalate"


class CheckStatus(str, Enum):
    """Per-check status for admissibility dimensions."""

    PASS = "pass"
    FAIL = "fail"
    ESCALATE = "escalate"


@dataclass(frozen=True)
class CheckResult:
    """Outcome for a single admissibility dimension."""

    status: CheckStatus
    reason_code: str
    message: str


@dataclass(frozen=True)
class BindAdmissibilityInput:
    """Input contract for bind-time admissibility re-check."""

    execution_intent: str
    current_timestamp: str
    authority_signal: Optional[bool]
    constraint_signals: Optional[Dict[str, bool]]
    live_state_fingerprint: Optional[str]
    expected_state_fingerprint: Optional[str]
    runtime_risk_signal: Optional[bool]
    drift_sensitive: bool = True
    ttl_required: bool = False
    approval_freshness_required: bool = False
    missing_signal_outcome: AdmissibilityOutcome = AdmissibilityOutcome.BLOCK
    ttl_expires_at: Optional[str] = None
    approval_expires_at: Optional[str] = None


@dataclass(frozen=True)
class BindAdmissibilityResult:
    """Deterministic bind-time admissibility evaluation result."""

    authority_check_result: CheckResult
    constraint_check_result: CheckResult
    drift_check_result: CheckResult
    risk_check_result: CheckResult
    freshness_check_result: CheckResult
    admissibility_result: bool
    recommended_outcome: AdmissibilityOutcome
    reason_codes: List[str] = field(default_factory=list)


def evaluate_bind_admissibility(
    evaluation_input: BindAdmissibilityInput,
) -> BindAdmissibilityResult:
    """Evaluate bind-time admissibility with fail-closed defaults."""
    authority = _check_authority(evaluation_input)
    constraints = _check_constraints(evaluation_input)
    drift = _check_drift(evaluation_input)
    risk = _check_runtime_risk(evaluation_input)
    freshness = _check_freshness(evaluation_input)

    checks = [authority, constraints, drift, risk, freshness]
    has_fail = any(c.status is CheckStatus.FAIL for c in checks)
    has_escalate = any(c.status is CheckStatus.ESCALATE for c in checks)

    if has_fail:
        admissible = False
        outcome = AdmissibilityOutcome.BLOCK
    elif has_escalate:
        admissible = False
        outcome = AdmissibilityOutcome.ESCALATE
    else:
        admissible = True
        outcome = AdmissibilityOutcome.ELIGIBLE_TO_COMMIT

    reason_codes = [c.reason_code for c in checks if c.status is not CheckStatus.PASS]

    return BindAdmissibilityResult(
        authority_check_result=authority,
        constraint_check_result=constraints,
        drift_check_result=drift,
        risk_check_result=risk,
        freshness_check_result=freshness,
        admissibility_result=admissible,
        recommended_outcome=outcome,
        reason_codes=reason_codes,
    )


def _check_authority(evaluation_input: BindAdmissibilityInput) -> CheckResult:
    signal = evaluation_input.authority_signal
    if signal is None:
        status = _missing_signal_status(evaluation_input)
        return CheckResult(
            status=status,
            reason_code="BIND_AUTHORITY_MISSING",
            message="Authority signal is missing; policy fallback applied.",
        )
    if signal is False:
        return CheckResult(
            status=CheckStatus.FAIL,
            reason_code="BIND_AUTHORITY_INVALID",
            message="Authority is not currently valid.",
        )
    return CheckResult(
        status=CheckStatus.PASS,
        reason_code="BIND_AUTHORITY_VALID",
        message="Authority remains valid.",
    )


def _check_constraints(evaluation_input: BindAdmissibilityInput) -> CheckResult:
    signals = evaluation_input.constraint_signals
    if not signals:
        status = _missing_signal_status(evaluation_input)
        return CheckResult(
            status=status,
            reason_code="BIND_CONSTRAINTS_MISSING",
            message="Constraint signals are missing; policy fallback applied.",
        )

    violating_constraints = sorted(name for name, passed in signals.items() if not passed)
    if violating_constraints:
        return CheckResult(
            status=CheckStatus.FAIL,
            reason_code="BIND_CONSTRAINTS_VIOLATED",
            message=(
                "Constraints are not satisfied: "
                + ", ".join(violating_constraints)
            ),
        )
    return CheckResult(
        status=CheckStatus.PASS,
        reason_code="BIND_CONSTRAINTS_VALID",
        message="All constraints are currently satisfied.",
    )


def _check_drift(evaluation_input: BindAdmissibilityInput) -> CheckResult:
    if not evaluation_input.drift_sensitive:
        return CheckResult(
            status=CheckStatus.PASS,
            reason_code="BIND_DRIFT_NOT_REQUIRED",
            message="Drift check is not required for this execution intent.",
        )

    live = evaluation_input.live_state_fingerprint
    expected = evaluation_input.expected_state_fingerprint

    if not live or not expected:
        status = _missing_signal_status(evaluation_input)
        return CheckResult(
            status=status,
            reason_code="BIND_DRIFT_SIGNAL_MISSING",
            message="Drift-sensitive path lacks live or expected state fingerprint.",
        )

    if live != expected:
        return CheckResult(
            status=CheckStatus.FAIL,
            reason_code="BIND_DRIFT_DETECTED",
            message="Live state has drifted from decision-time assumptions.",
        )

    return CheckResult(
        status=CheckStatus.PASS,
        reason_code="BIND_DRIFT_NOT_DETECTED",
        message="No live-state drift detected.",
    )


def _check_runtime_risk(evaluation_input: BindAdmissibilityInput) -> CheckResult:
    signal = evaluation_input.runtime_risk_signal
    if signal is None:
        status = _missing_signal_status(evaluation_input)
        return CheckResult(
            status=status,
            reason_code="BIND_RUNTIME_RISK_MISSING",
            message="Runtime risk signal is missing; policy fallback applied.",
        )
    if signal is False:
        return CheckResult(
            status=CheckStatus.FAIL,
            reason_code="BIND_RUNTIME_RISK_UNACCEPTABLE",
            message="Runtime risk is not currently acceptable.",
        )
    return CheckResult(
        status=CheckStatus.PASS,
        reason_code="BIND_RUNTIME_RISK_ACCEPTABLE",
        message="Runtime risk remains acceptable.",
    )


def _check_freshness(evaluation_input: BindAdmissibilityInput) -> CheckResult:
    now = _parse_timestamp(evaluation_input.current_timestamp)

    if evaluation_input.ttl_required and not evaluation_input.ttl_expires_at:
        return CheckResult(
            status=_missing_signal_status(evaluation_input),
            reason_code="BIND_TTL_MISSING",
            message="TTL is required by policy but no TTL signal is available.",
        )

    if evaluation_input.approval_freshness_required and not evaluation_input.approval_expires_at:
        return CheckResult(
            status=_missing_signal_status(evaluation_input),
            reason_code="BIND_APPROVAL_FRESHNESS_MISSING",
            message="Approval freshness is required by policy but signal is missing.",
        )

    expiry_fields = [
        ("ttl", evaluation_input.ttl_expires_at, "BIND_TTL_EXPIRED"),
        ("approval", evaluation_input.approval_expires_at, "BIND_APPROVAL_STALE"),
    ]

    expired = []
    for name, expiry_raw, reason_code in expiry_fields:
        if not expiry_raw:
            continue
        expiry = _parse_timestamp(expiry_raw)
        if now > expiry:
            expired.append((name, reason_code))

    if expired:
        labels = ", ".join(name for name, _ in expired)
        primary_reason = expired[0][1]
        expired_status = _missing_signal_status(evaluation_input)
        return CheckResult(
            status=expired_status,
            reason_code=primary_reason,
            message=f"Freshness window expired ({labels}); policy fallback applied.",
        )

    return CheckResult(
        status=CheckStatus.PASS,
        reason_code="BIND_FRESHNESS_VALID",
        message="TTL and approval freshness checks are valid.",
    )


def _parse_timestamp(raw_timestamp: str) -> datetime:
    normalized = raw_timestamp.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _missing_signal_status(evaluation_input: BindAdmissibilityInput) -> CheckStatus:
    """Return status dictated by policy for missing/invalid runtime signals."""
    if evaluation_input.missing_signal_outcome is AdmissibilityOutcome.ESCALATE:
        return CheckStatus.ESCALATE
    return CheckStatus.FAIL
