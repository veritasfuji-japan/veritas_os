# veritas_os/core/continuation_runtime/__init__.py
# -*- coding: utf-8 -*-
"""
Continuation Runtime — Core Data Model (Phase-1: observe/shadow only)

Chain-level continuation observation substrate that runs *beside* the
existing step-level decision infrastructure.  This module defines the
four core structures:

- ContinuationClaimLineage : live object representing a chain's standing
- ClaimStateSnapshot       : minimal governable state at a point in time
- ContinuationReceipt      : audit witness emitted per revalidation
- ContinuationLawPack      : versioned rule set governing revalidation

Phase-1 contract:
  - Feature flag off → zero side effects, zero imports beyond this module
  - No enforcement; snapshots and receipts are observation artifacts only
  - FUJI is unmodified; gate.decision_status is unmodified
"""
from __future__ import annotations

from .reason_codes import ReasonCode
from .lineage import ContinuationClaimLineage, ClaimStatus
from .snapshot import (
    ClaimStateSnapshot,
    SupportBasis,
    Scope,
    BurdenState,
    HeadroomState,
    RevocationCondition,
)
from .receipt import ContinuationReceipt, RevalidationStatus, RevalidationOutcome
from .lawpack import ContinuationLawPack, EvaluationMode
from .revalidator import (
    ContinuationRevalidator,
    PresentCondition,
    run_continuation_revalidation_shadow,
)

__all__ = [
    # lineage
    "ContinuationClaimLineage",
    "ClaimStatus",
    # snapshot
    "ClaimStateSnapshot",
    "SupportBasis",
    "Scope",
    "BurdenState",
    "HeadroomState",
    "RevocationCondition",
    # receipt
    "ContinuationReceipt",
    "RevalidationStatus",
    "RevalidationOutcome",
    # lawpack
    "ContinuationLawPack",
    "EvaluationMode",
    # reason codes
    "ReasonCode",
    # revalidator
    "ContinuationRevalidator",
    "PresentCondition",
    "run_continuation_revalidation_shadow",
]
