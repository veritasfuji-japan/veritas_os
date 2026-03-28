# veritas_os/core/continuation_runtime/lineage.py
# -*- coding: utf-8 -*-
"""
ContinuationClaimLineage — the live chain-level continuation object.

A lineage is created at chain entry and updated at each revalidation.
It is not a permit — it is the structured record of an ongoing claim
that must be continuously justified.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from uuid import uuid4


class ClaimStatus(str, Enum):
    """Current standing of a continuation claim."""

    LIVE = "live"
    NARROWED = "narrowed"
    DEGRADED = "degraded"
    ESCALATED = "escalated"
    HALTED = "halted"
    REVOKED = "revoked"

    def __str__(self) -> str:
        return self.value


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ContinuationClaimLineage:
    """Live object representing a chain's continuation standing.

    Created once at chain entry.  ``latest_snapshot_id`` and
    ``current_claim_status`` are updated after each revalidation pass.
    """

    # identity
    claim_lineage_id: str = field(default_factory=lambda: uuid4().hex)
    chain_id: str = ""
    origin_ref: str = ""

    # provenance
    created_at: str = field(default_factory=_utcnow)
    initial_law_version: str = ""
    initial_support_basis_ref: str = ""

    # mutable pointers (updated by revalidation)
    latest_snapshot_id: Optional[str] = None
    current_claim_status: ClaimStatus = ClaimStatus.LIVE

    # revocation
    is_revoked: bool = False
    revoked_at: Optional[str] = None

    # ------------------------------------------------------------------
    # Serialization helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable dict representation."""
        d = asdict(self)
        d["current_claim_status"] = self.current_claim_status.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContinuationClaimLineage":
        """Reconstruct from a dict (e.g. deserialized JSON)."""
        data = dict(data)  # shallow copy
        if "current_claim_status" in data:
            data["current_claim_status"] = ClaimStatus(data["current_claim_status"])
        return cls(**data)
