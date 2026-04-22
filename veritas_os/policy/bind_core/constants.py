"""Canonical bind outcome and reason code constants."""

from __future__ import annotations

from enum import Enum

from veritas_os.policy.bind_artifacts import FinalOutcome


class BindOutcome(str, Enum):
    """Canonical bind outcome values exposed by governance API surfaces."""

    COMMITTED = FinalOutcome.COMMITTED.value
    BLOCKED = FinalOutcome.BLOCKED.value
    ESCALATED = FinalOutcome.ESCALATED.value
    ROLLED_BACK = FinalOutcome.ROLLED_BACK.value
    APPLY_FAILED = FinalOutcome.APPLY_FAILED.value
    SNAPSHOT_FAILED = FinalOutcome.SNAPSHOT_FAILED.value
    PRECONDITION_FAILED = FinalOutcome.PRECONDITION_FAILED.value


class BindReasonCode(str, Enum):
    """Canonical bind reason-code vocabulary for adapters and API mapping."""

    PRECONDITION_INVALID = "BIND_PRECONDITION_INVALID"
    SNAPSHOT_FAILED = "BIND_SNAPSHOT_FAILED"
    APPLY_FAILED = "BIND_APPLY_FAILED"
    POSTCONDITION_FAILED = "BIND_POSTCONDITION_FAILED"
    POST_SIGNAL_MISSING = "BIND_POST_SIGNAL_MISSING"
    ADMISSIBILITY_ESCALATION_REQUIRED = "BIND_ADMISSIBILITY_ESCALATION_REQUIRED"


BIND_OUTCOME_VALUES: tuple[str, ...] = tuple(item.value for item in BindOutcome)
