# veritas_os/core/continuation_runtime/receipt.py
# -*- coding: utf-8 -*-
"""
ContinuationReceipt — proof-bearing audit witness per revalidation pass.

A receipt is the *primary* record of boundary adjudication: what was
evaluated, what outcome was reached, and whether that outcome has durable
state consequences.  Receipts are append-only and form a chain-level
audit trail.

Receipt-first rule:
  Any boundary outcome (halted, narrowed, degraded, escalated) that has
  not yet durably changed the continuation's lawful standing should
  remain receipt-first.  Only outcomes with explicit ``DurableConsequence``
  get promoted into ``ClaimStateSnapshot.claim_status``.

The receipt is NOT a state store — runtime logic reads the snapshot for
current durable standing; receipts are for audit, replay, divergence
analysis, and proof-bearing adjudication witness.
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
    """Proof-bearing audit witness emitted after each revalidation pass.

    The receipt is the *primary* record of boundary adjudication.  It
    contains everything an auditor, replay engine, or divergence
    analyzer needs to understand what happened during revalidation,
    including the explicit promotion assessment (receipt-first vs
    state-promoted).
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
    # Proof-bearing boundary adjudication (receipt-first semantics)
    # ------------------------------------------------------------------

    # Primary boundary outcome — the adjudication vocabulary lives here.
    # This is the receipt's own determination, independent of whether it
    # was promoted into snapshot.claim_status.
    boundary_outcome: Optional[str] = None

    # Whether the boundary outcome was promoted into durable state.
    # True only when a DurableConsequence was recorded in the snapshot.
    is_durable_promotion: bool = False

    # "provisional" (receipt-only, may be re-opened) or
    # "durable_promotable" (has durably altered standing/scope/rights).
    provisional_vs_durable: Optional[str] = None

    # For narrowed: is the prior scope width restorable?
    # Reopening test: if boundary conditions resolve and standing/burden/
    # authority/continuity basis are unchanged, can prior width reopen?
    #   True  → receipt-level narrowing (provisional)
    #   False → durable narrowing (promoted to state)
    reopening_eligible: bool = True

    # ------------------------------------------------------------------
    # Explicit boundary occurrence flags (receipt-first enrichment)
    # ------------------------------------------------------------------

    # Did a halt occur at the boundary (regardless of durability)?
    halt_occurred: bool = False

    # Did narrowing occur at the boundary (regardless of durability)?
    narrowing_occurred: bool = False

    # Halt classification — identifies the nature of the halt so that
    # downstream consumers can distinguish temporary interruptions from
    # durable state transformations without re-parsing the full receipt.
    #   "bounded_interruption"        — headroom breach, not collapsed
    #   "temporary_refusal"           — refusal to proceed, recoverable
    #   "safety_pause"                — pause pending revalidation
    #   "durable_state_transformation" — irreversible headroom collapse
    #   None when no halt occurred.
    halt_classification: Optional[str] = None

    # Granular divergence detail — identifies the specific combination
    # of local-step outcome and boundary outcome so that auditors and
    # replay engines can precisely categorise the divergence.
    #   "local_pass_receipt_halt"           — local ok, receipt-level halt
    #   "local_pass_receipt_narrowing"      — local ok, receipt-level narrowing
    #   "local_pass_durable_narrowing"      — local ok, durable scope reduction
    #   "local_pass_durable_halt"           — local ok, durable halt consequence
    #   "local_pass_revoked"                — local ok, revoked
    #   "local_pass_receipt_degraded"       — local ok, receipt-level degraded
    #   "local_pass_receipt_escalated"      — local ok, receipt-level escalated
    #   "local_fail_continuation_live"      — local fail, continuation still live
    #   None when no divergence.
    divergence_detail: Optional[str] = None

    # The predicates (reason codes as strings) under which the boundary
    # determination was reached — "under what predicates".
    boundary_predicates: List[str] = field(default_factory=list)

    # Reference to the prior snapshot against which adjudication ran.
    prior_state_ref: Optional[str] = None

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
            "boundary_outcome": self.boundary_outcome,
            "is_durable_promotion": self.is_durable_promotion,
            "provisional_vs_durable": self.provisional_vs_durable,
            "reopening_eligible": self.reopening_eligible,
            "halt_occurred": self.halt_occurred,
            "narrowing_occurred": self.narrowing_occurred,
            "halt_classification": self.halt_classification,
            "divergence_detail": self.divergence_detail,
            "boundary_predicates": list(self.boundary_predicates),
            "prior_state_ref": self.prior_state_ref,
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
