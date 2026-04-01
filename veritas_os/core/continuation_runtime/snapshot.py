# veritas_os/core/continuation_runtime/snapshot.py
# -*- coding: utf-8 -*-
"""
ClaimStateSnapshot — minimal governable state of a continuation claim.

A snapshot is the *input* to the next revalidation.  It contains exactly
the durable standing facts — what remains true after adjudication.

Separation rule (receipt-first by default):
  Any boundary outcome that has not yet durably changed the
  continuation's lawful standing remains receipt-first.

  - revalidation_status           → receipt, NOT snapshot
  - boundary adjudication outcome → receipt-first; state only when durable
  - preceding_decision_continuity → receipt, NOT snapshot
  - replay linkage                → receipt, NOT snapshot
  - local_step_result             → receipt, NOT snapshot
  - receipt hash / attestation    → receipt, NOT snapshot
  - provisional vs durable assess → receipt, NOT snapshot
  - halted / narrowed / degraded / escalated → receipt-first;
    promoted to state only when ``DurableConsequence`` is present
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .lineage import ClaimStatus


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# =====================================================================
# Sub-structures carried in the snapshot
# =====================================================================


@dataclass
class SupportBasis:
    """Structured justification sustaining a continuation claim.

    Not a flat bool or prose — a structured collection of grounds.
    Burden lives here as a component of the support basis.
    """

    authority: str = ""
    policy: str = ""
    evidence: str = ""
    dependency: str = ""
    environment: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SupportBasis":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Scope:
    """Explicit boundary of what a chain is permitted to continue doing.

    Never implicit — always declares allowed/restricted action classes.
    """

    allowed_action_classes: List[str] = field(default_factory=list)
    restricted_action_classes: List[str] = field(default_factory=list)
    escalation_required: bool = False
    restrictions_durable: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Scope":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class BurdenState:
    """Current evidentiary obligation the claim must sustain.

    Not an optional note — a structured runtime object.
    """

    required_evidence: List[str] = field(default_factory=list)
    satisfied_evidence: List[str] = field(default_factory=list)
    threshold: float = 1.0
    current_level: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BurdenState":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class HeadroomState:
    """Remaining capacity before automatic escalation/suspension.

    Headroom is the runtime interpretation of burden — how much margin
    remains before thresholds are breached.
    """

    remaining: float = 1.0
    threshold_escalation: float = 0.3
    threshold_suspension: float = 0.0
    collapse_irreversible: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HeadroomState":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class RevocationCondition:
    """Pre-declared condition under which standing is revoked.

    Declarative, not implicit — conditions are stated up front so that
    revocation is traceable to a specific, pre-announced trigger.
    """

    condition_id: str = ""
    description: str = ""
    is_met: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RevocationCondition":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# =====================================================================
# DurableConsequence — explicit record of why a boundary outcome
# was promoted from receipt to state
# =====================================================================


@dataclass
class DurableConsequence:
    """Tracks which durable state consequences caused a boundary outcome
    to be promoted into ``claim_status``.

    A boundary outcome (halted, narrowed, degraded, escalated) defaults
    to receipt-first.  It becomes state-relevant **only** when it has
    durably changed lawful standing, available scope, continuation rights,
    onward carryability, or continuation class.

    When ``claim_status`` is LIVE or REVOKED, ``durable_consequence`` may
    be ``None`` (those are inherently state-level).
    """

    has_durable_halt: bool = False
    has_durable_scope_reduction: bool = False
    has_durable_class_change: bool = False
    has_irreversible_revocation: bool = False
    promotion_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DurableConsequence":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# =====================================================================
# ClaimStateSnapshot
# =====================================================================


@dataclass
class ClaimStateSnapshot:
    """Minimal governable state of a continuation claim at a point in time.

    Contains only *durable* standing facts — what remains true after
    adjudication.  Boundary adjudication vocabulary (the *process* of
    arriving at an outcome) belongs in ``ContinuationReceipt``.

    ``claim_status`` reflects durable standing:
      - LIVE / REVOKED are inherently state-level.
      - HALTED, NARROWED, DEGRADED, ESCALATED appear here **only** when
        the revalidator has determined a durable consequence exists.
        In that case ``durable_consequence`` records the promotion reason.

    Replaced at each revalidation; only the current snapshot is
    authoritative for runtime logic.
    """

    # identity & linkage
    snapshot_id: str = field(default_factory=lambda: uuid4().hex)
    claim_lineage_id: str = ""
    prior_snapshot_id: Optional[str] = None
    timestamp: str = field(default_factory=_utcnow)

    # governable facts (core)
    support_basis: SupportBasis = field(default_factory=SupportBasis)
    scope: Scope = field(default_factory=Scope)
    burden_state: BurdenState = field(default_factory=BurdenState)
    headroom_state: HeadroomState = field(default_factory=HeadroomState)
    law_version: str = ""
    revocation_conditions: List[RevocationCondition] = field(default_factory=list)
    claim_status: ClaimStatus = ClaimStatus.LIVE

    # durable consequence — present when a boundary outcome was promoted
    # from receipt into state (None when claim_status is LIVE or REVOKED
    # without a non-obvious promotion path).
    durable_consequence: Optional[DurableConsequence] = None

    # optional lightweight metadata (permitted but minimal)
    state_digest: Optional[str] = None
    effective_from: Optional[str] = None
    effective_until: Optional[str] = None

    # ------------------------------------------------------------------
    # Serialization helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable dict representation."""
        d: Dict[str, Any] = {
            "snapshot_id": self.snapshot_id,
            "claim_lineage_id": self.claim_lineage_id,
            "prior_snapshot_id": self.prior_snapshot_id,
            "timestamp": self.timestamp,
            "support_basis": self.support_basis.to_dict(),
            "scope": self.scope.to_dict(),
            "burden_state": self.burden_state.to_dict(),
            "headroom_state": self.headroom_state.to_dict(),
            "law_version": self.law_version,
            "revocation_conditions": [rc.to_dict() for rc in self.revocation_conditions],
            "claim_status": self.claim_status.value,
            "durable_consequence": (
                self.durable_consequence.to_dict()
                if self.durable_consequence is not None
                else None
            ),
            "state_digest": self.state_digest,
            "effective_from": self.effective_from,
            "effective_until": self.effective_until,
        }
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClaimStateSnapshot":
        """Reconstruct from a dict (e.g. deserialized JSON)."""
        data = dict(data)  # shallow copy
        if "support_basis" in data and isinstance(data["support_basis"], dict):
            data["support_basis"] = SupportBasis.from_dict(data["support_basis"])
        if "scope" in data and isinstance(data["scope"], dict):
            data["scope"] = Scope.from_dict(data["scope"])
        if "burden_state" in data and isinstance(data["burden_state"], dict):
            data["burden_state"] = BurdenState.from_dict(data["burden_state"])
        if "headroom_state" in data and isinstance(data["headroom_state"], dict):
            data["headroom_state"] = HeadroomState.from_dict(data["headroom_state"])
        if "revocation_conditions" in data and isinstance(data["revocation_conditions"], list):
            data["revocation_conditions"] = [
                RevocationCondition.from_dict(rc) if isinstance(rc, dict) else rc
                for rc in data["revocation_conditions"]
            ]
        if "claim_status" in data and isinstance(data["claim_status"], str):
            data["claim_status"] = ClaimStatus(data["claim_status"])
        if "durable_consequence" in data and isinstance(data["durable_consequence"], dict):
            data["durable_consequence"] = DurableConsequence.from_dict(
                data["durable_consequence"]
            )
        return cls(**data)
