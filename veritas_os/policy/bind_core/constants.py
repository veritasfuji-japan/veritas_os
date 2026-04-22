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
    IDEMPOTENT_REPLAY = "BIND_IDEMPOTENT_REPLAY"


class BindRetrySafety(str, Enum):
    """Minimal retry safety classes for bind-boundary failures."""

    SAFE = "SAFE"
    UNSAFE = "UNSAFE"
    REQUIRES_ESCALATION = "REQUIRES_ESCALATION"


class BindFailureCategory(str, Enum):
    """Minimal failure taxonomy for bind receipts and adapter operators."""

    NONE = "NONE"
    PRECONDITION = "PRECONDITION"
    SNAPSHOT = "SNAPSHOT"
    ADMISSIBILITY = "ADMISSIBILITY"
    APPLY = "APPLY"
    POSTCONDITION = "POSTCONDITION"
    ROLLBACK = "ROLLBACK"


BIND_OUTCOME_VALUES: tuple[str, ...] = tuple(item.value for item in BindOutcome)
