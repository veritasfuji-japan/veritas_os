# veritas_os/core/continuation_runtime/__init__.py
# -*- coding: utf-8 -*-
"""
Continuation Runtime — Core Data Model

Chain-level continuation observation and limited enforcement substrate
that runs *beside* (not inside) the existing step-level decision
infrastructure.  This module defines the core structures:

- ContinuationClaimLineage : live object representing a chain's standing
- ClaimStateSnapshot       : minimal governable state at a point in time
- ContinuationReceipt      : audit witness emitted per revalidation
- ContinuationLawPack      : versioned rule set governing revalidation
- ContinuationEnforcementEvaluator : limited enforcement engine (Phase-2)

Default behavior (Phase-1):
  - Feature flag off → zero side effects, zero imports beyond this module
  - Observe mode: snapshots and receipts are observation artifacts only
  - FUJI is unmodified; gate.decision_status is unmodified

Phase-2 enforcement modes (feature-flagged):
  - Advisory mode: emit enforcement events as advisories (no blocking)
  - Enforce mode: limited blocking for high-confidence conditions
"""
from __future__ import annotations

from .reason_codes import ReasonCode
from .lineage import ContinuationClaimLineage, ClaimStatus
from .snapshot import (
    ClaimStateSnapshot,
    DurableConsequence,
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
from .bind_admissibility import (
    AdmissibilityOutcome,
    CheckStatus,
    CheckResult,
    BindAdmissibilityInput,
    BindAdmissibilityResult,
    evaluate_bind_admissibility,
)
from .enforcement import (
    EnforcementMode,
    EnforcementAction,
    EnforcementConditionType,
    EnforcementCondition,
    EnforcementEvent,
    EnforcementConfig,
    ContinuationEnforcementEvaluator,
)

__all__ = [
    # lineage
    "ContinuationClaimLineage",
    "ClaimStatus",
    # snapshot
    "ClaimStateSnapshot",
    "DurableConsequence",
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
    # bind-time admissibility
    "AdmissibilityOutcome",
    "CheckStatus",
    "CheckResult",
    "BindAdmissibilityInput",
    "BindAdmissibilityResult",
    "evaluate_bind_admissibility",
    # enforcement (Phase-2)
    "EnforcementMode",
    "EnforcementAction",
    "EnforcementConditionType",
    "EnforcementCondition",
    "EnforcementEvent",
    "EnforcementConfig",
    "ContinuationEnforcementEvaluator",
]
