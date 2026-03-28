# veritas_os/core/continuation_runtime/reason_codes.py
# -*- coding: utf-8 -*-
"""
Reason codes for continuation revalidation outcomes.

Each code identifies a specific condition that caused standing to change.
Codes are carried in ContinuationReceipt.revalidation_reason_codes.
"""
from __future__ import annotations

from enum import Enum


class ReasonCode(str, Enum):
    """Machine-readable reason codes for revalidation outcomes."""

    SUPPORT_LOST_POLICY_SCOPE = "SUPPORT_LOST_POLICY_SCOPE"
    SUPPORT_LOST_WORLD_STATE = "SUPPORT_LOST_WORLD_STATE"
    SUPPORT_LOST_APPROVAL = "SUPPORT_LOST_APPROVAL"
    BURDEN_THRESHOLD_EXCEEDED = "BURDEN_THRESHOLD_EXCEEDED"
    HEADROOM_COLLAPSED = "HEADROOM_COLLAPSED"
    REVALIDATION_FAILED = "REVALIDATION_FAILED"
    ACTION_CLASS_NOT_ALLOWED = "ACTION_CLASS_NOT_ALLOWED"
    CLAIM_HALTED = "CLAIM_HALTED"
    CLAIM_REVOKED = "CLAIM_REVOKED"

    def __str__(self) -> str:
        return self.value
