# veritas_os/core/continuation_runtime/receipt.py
# -*- coding: utf-8 -*-
"""
ContinuationReceipt — audit witness emitted per revalidation pass.

A receipt records *how* the claim's standing was examined, what was
found, and what the runtime would have recommended.  Receipts are
append-only and form a chain-level audit trail.

The receipt is NOT a state store — runtime logic reads the snapshot for
current state; receipts are for audit, replay, and divergence analysis.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .reason_codes import ReasonCode


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class RevalidationStatus(str, Enum):
    """What happened during revalidation (receipt-side, not snapshot-side)."""

    RENEWED = "renewed"
    NARROWED = "narrowed"
    DEGRADED = "degraded"
    ESCALATED = "escalated"
    HALTED = "halted"
    REVOKED = "revoked"
    FAILED = "failed"

    def __str__(self) -> str:
        return self.value


class RevalidationOutcome(str, Enum):
    """High-level outcome of the revalidation pass."""

    RENEWED = "renewed"
    NARROWED = "narrowed"
    DEGRADED = "degraded"
    ESCALATED = "escalated"
    HALTED = "halted"
    REVOKED = "revoked"
    FAILED = "failed"

    def __str__(self) -> str:
        return self.value


@dataclass
class ContinuationReceipt:
    """Audit witness emitted after each revalidation pass.

    Contains everything an auditor, replay engine, or divergence
    analyzer needs to understand what happened during revalidation.
    """

    # identity
    receipt_id: str = field(default_factory=lambda: uuid4().hex)
    claim_lineage_id: str = ""
    snapshot_id: str = ""
    receipt_timestamp: str = field(default_factory=_utcnow)
    law_version_id: str = ""

    # revalidation outcome (receipt-side responsibility)
    revalidation_status: RevalidationStatus = RevalidationStatus.RENEWED
    revalidation_outcome: RevalidationOutcome = RevalidationOutcome.RENEWED
    revalidation_reason_codes: List[ReasonCode] = field(default_factory=list)

    # linkage to preceding decisions and receipts
    prior_decision_continuity_ref: Optional[str] = None
    parent_receipt_ref: Optional[str] = None
    receipt_hash_or_attestation: Optional[str] = None
    replay_linkage_ref: Optional[str] = None

    # step-level observation (receipt holds this, NOT snapshot)
    local_step_result: Optional[str] = None
    divergence_flag: bool = False
    should_refuse_before_effect: bool = False

    # digest summaries for audit (derived from snapshot at emission time)
    support_basis_digest: Optional[str] = None
    scope_digest: Optional[str] = None
    burden_headroom_digest: Optional[str] = None

    # ------------------------------------------------------------------
    # Serialization helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable dict representation."""
        d: Dict[str, Any] = {
            "receipt_id": self.receipt_id,
            "claim_lineage_id": self.claim_lineage_id,
            "snapshot_id": self.snapshot_id,
            "receipt_timestamp": self.receipt_timestamp,
            "law_version_id": self.law_version_id,
            "revalidation_status": self.revalidation_status.value,
            "revalidation_outcome": self.revalidation_outcome.value,
            "revalidation_reason_codes": [rc.value for rc in self.revalidation_reason_codes],
            "prior_decision_continuity_ref": self.prior_decision_continuity_ref,
            "parent_receipt_ref": self.parent_receipt_ref,
            "receipt_hash_or_attestation": self.receipt_hash_or_attestation,
            "replay_linkage_ref": self.replay_linkage_ref,
            "local_step_result": self.local_step_result,
            "divergence_flag": self.divergence_flag,
            "should_refuse_before_effect": self.should_refuse_before_effect,
            "support_basis_digest": self.support_basis_digest,
            "scope_digest": self.scope_digest,
            "burden_headroom_digest": self.burden_headroom_digest,
        }
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContinuationReceipt":
        """Reconstruct from a dict (e.g. deserialized JSON)."""
        data = dict(data)  # shallow copy
        if "revalidation_status" in data and isinstance(data["revalidation_status"], str):
            data["revalidation_status"] = RevalidationStatus(data["revalidation_status"])
        if "revalidation_outcome" in data and isinstance(data["revalidation_outcome"], str):
            data["revalidation_outcome"] = RevalidationOutcome(data["revalidation_outcome"])
        if "revalidation_reason_codes" in data and isinstance(data["revalidation_reason_codes"], list):
            data["revalidation_reason_codes"] = [
                ReasonCode(rc) if isinstance(rc, str) else rc
                for rc in data["revalidation_reason_codes"]
            ]
        return cls(**data)
