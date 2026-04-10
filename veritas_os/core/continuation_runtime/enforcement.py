# veritas_os/core/continuation_runtime/enforcement.py
# -*- coding: utf-8 -*-
"""
Continuation-level limited enforcement engine.

Evaluates high-confidence, explainable conditions against continuation
revalidation artifacts and emits narrowly scoped enforcement actions.

Design principles:
  - Only triggers for high-confidence, clearly justified conditions.
  - Every enforcement event is logged, attributable, replay-visible.
  - Conceptually separate from FUJI step-level safety gating.
  - Feature-flagged: default mode is ``observe`` (no enforcement).

Enforcement actions:
  - ``require_human_review``  — pause chain pending operator review
  - ``halt_chain``            — stop chain continuation
  - ``escalate_alert``        — emit alert to operator/governance stream

Trigger conditions (all require high confidence):
  - Repeated high-risk continuation degradation
  - Approval-required transition without approval
  - Replay divergence above threshold for sensitive paths
  - Policy boundary violation in continuation state
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .lineage import ClaimStatus
from .receipt import ContinuationReceipt, RevalidationStatus
from .snapshot import ClaimStateSnapshot
from .reason_codes import ReasonCode

logger = logging.getLogger(__name__)


# =====================================================================
# Enforcement mode (parallels EvaluationMode but specific to enforcement)
# =====================================================================


class EnforcementMode(str, Enum):
    """Continuation enforcement posture.

    - ``observe``  — Phase-1 default; no enforcement, observation only.
    - ``advisory`` — Emit enforcement events as advisories; no blocking.
    - ``enforce``  — Limited enforcement: may block/halt for high-confidence
                     conditions.
    """

    OBSERVE = "observe"
    ADVISORY = "advisory"
    ENFORCE = "enforce"

    def __str__(self) -> str:
        return self.value


# =====================================================================
# Enforcement actions
# =====================================================================


class EnforcementAction(str, Enum):
    """Narrowly scoped enforcement actions.

    These are chain-level governance actions, NOT step-level FUJI actions.
    """

    REQUIRE_HUMAN_REVIEW = "require_human_review"
    HALT_CHAIN = "halt_chain"
    ESCALATE_ALERT = "escalate_alert"

    def __str__(self) -> str:
        return self.value


# =====================================================================
# Enforcement condition
# =====================================================================


class EnforcementConditionType(str, Enum):
    """Types of high-confidence conditions that trigger enforcement."""

    REPEATED_DEGRADATION = "repeated_degradation"
    APPROVAL_REQUIRED_WITHOUT_APPROVAL = "approval_required_without_approval"
    REPLAY_DIVERGENCE_EXCEEDED = "replay_divergence_exceeded"
    POLICY_BOUNDARY_VIOLATION = "policy_boundary_violation"

    def __str__(self) -> str:
        return self.value


@dataclass
class EnforcementCondition:
    """A specific condition that was evaluated for enforcement.

    Each condition carries its own confidence score, explanation,
    and whether it was met.
    """

    condition_type: EnforcementConditionType
    is_met: bool = False
    confidence: float = 0.0
    explanation: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable dict representation."""
        return {
            "condition_type": self.condition_type.value,
            "is_met": self.is_met,
            "confidence": self.confidence,
            "explanation": self.explanation,
            "evidence": dict(self.evidence),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EnforcementCondition":
        """Reconstruct from a dict."""
        data = dict(data)
        if "condition_type" in data and isinstance(data["condition_type"], str):
            data["condition_type"] = EnforcementConditionType(data["condition_type"])
        return cls(**data)


# =====================================================================
# Enforcement event — the primary audit artifact
# =====================================================================

def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class EnforcementEvent:
    """Audit-grade enforcement event emitted when enforcement is triggered.

    Every enforcement event is:
      - Logged (via Python logging + trustlog-ready structure)
      - Attributable (claim_lineage_id, receipt_id, chain_id)
      - Replay-visible (snapshot_id, receipt_id, law_version)
      - Operator-visible (action, reasoning, conditions)
    """

    # identity
    event_id: str = field(default_factory=lambda: uuid4().hex)
    timestamp: str = field(default_factory=_utcnow)

    # linkage to continuation artifacts
    claim_lineage_id: str = ""
    chain_id: str = ""
    snapshot_id: str = ""
    receipt_id: str = ""
    law_version: str = ""

    # enforcement decision
    mode: EnforcementMode = EnforcementMode.OBSERVE
    action: EnforcementAction = EnforcementAction.ESCALATE_ALERT
    is_enforced: bool = False
    is_advisory: bool = False

    # reasoning (explicit, inspectable)
    conditions_evaluated: List[EnforcementCondition] = field(default_factory=list)
    conditions_met: List[EnforcementCondition] = field(default_factory=list)
    reasoning: str = ""
    reason_codes: List[str] = field(default_factory=list)

    # context for operator
    claim_status: str = ""
    boundary_outcome: str = ""
    severity: str = "info"

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable dict representation."""
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "claim_lineage_id": self.claim_lineage_id,
            "chain_id": self.chain_id,
            "snapshot_id": self.snapshot_id,
            "receipt_id": self.receipt_id,
            "law_version": self.law_version,
            "mode": self.mode.value,
            "action": self.action.value,
            "is_enforced": self.is_enforced,
            "is_advisory": self.is_advisory,
            "conditions_evaluated": [c.to_dict() for c in self.conditions_evaluated],
            "conditions_met": [c.to_dict() for c in self.conditions_met],
            "reasoning": self.reasoning,
            "reason_codes": list(self.reason_codes),
            "claim_status": self.claim_status,
            "boundary_outcome": self.boundary_outcome,
            "severity": self.severity,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EnforcementEvent":
        """Reconstruct from a dict."""
        data = dict(data)
        if "mode" in data and isinstance(data["mode"], str):
            data["mode"] = EnforcementMode(data["mode"])
        if "action" in data and isinstance(data["action"], str):
            data["action"] = EnforcementAction(data["action"])
        if "conditions_evaluated" in data:
            data["conditions_evaluated"] = [
                EnforcementCondition.from_dict(c) if isinstance(c, dict) else c
                for c in data["conditions_evaluated"]
            ]
        if "conditions_met" in data:
            data["conditions_met"] = [
                EnforcementCondition.from_dict(c) if isinstance(c, dict) else c
                for c in data["conditions_met"]
            ]
        return cls(**data)


# =====================================================================
# Enforcement configuration (thresholds, toggles)
# =====================================================================


@dataclass
class EnforcementConfig:
    """Configuration for continuation enforcement thresholds.

    All thresholds are testable and documentable.  Defaults are
    conservative (high confidence required, narrow scope).
    """

    mode: EnforcementMode = EnforcementMode.OBSERVE

    # --- Condition thresholds ---

    # Repeated degradation: how many consecutive degraded/escalated
    # receipts before triggering enforcement.
    degradation_repeat_threshold: int = 3

    # Minimum confidence for any enforcement condition to trigger.
    min_confidence: float = 0.8

    # Replay divergence: max allowed divergence ratio (0.0–1.0)
    # for sensitive paths before triggering enforcement.
    replay_divergence_threshold: float = 0.3

    # --- Enabled actions per condition ---
    # Maps condition type to the enforcement action taken.
    # Defaults are narrowly scoped.
    action_map: Dict[str, str] = field(default_factory=lambda: {
        "repeated_degradation": "require_human_review",
        "approval_required_without_approval": "halt_chain",
        "replay_divergence_exceeded": "escalate_alert",
        "policy_boundary_violation": "halt_chain",
    })

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable dict representation."""
        return {
            "mode": self.mode.value,
            "degradation_repeat_threshold": self.degradation_repeat_threshold,
            "min_confidence": self.min_confidence,
            "replay_divergence_threshold": self.replay_divergence_threshold,
            "action_map": dict(self.action_map),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EnforcementConfig":
        """Reconstruct from a dict."""
        data = dict(data)
        if "mode" in data and isinstance(data["mode"], str):
            data["mode"] = EnforcementMode(data["mode"])
        return cls(**data)


# =====================================================================
# Enforcement evaluator
# =====================================================================

_DEFAULT_CONFIG = EnforcementConfig()


class ContinuationEnforcementEvaluator:
    """Evaluates enforcement conditions against continuation artifacts.

    This evaluator is conceptually separate from FUJI step-level gating.
    It operates on chain-level continuation state, not individual step
    merit decisions.

    Args:
        config: Enforcement configuration with thresholds and mode.
    """

    def __init__(self, config: Optional[EnforcementConfig] = None) -> None:
        self._config = config or _DEFAULT_CONFIG

    @property
    def mode(self) -> EnforcementMode:
        """Current enforcement mode."""
        return self._config.mode

    def evaluate(
        self,
        *,
        snapshot: ClaimStateSnapshot,
        receipt: ContinuationReceipt,
        chain_id: str = "",
        degradation_count: int = 0,
        replay_divergence_ratio: float = 0.0,
        has_required_approval: bool = True,
        policy_violation_detected: bool = False,
        policy_violation_detail: str = "",
    ) -> List[EnforcementEvent]:
        """Evaluate all enforcement conditions and emit events.

        In ``observe`` mode, returns an empty list (no events).
        In ``advisory`` mode, returns events with ``is_advisory=True``.
        In ``enforce`` mode, returns events with ``is_enforced=True``.

        Args:
            snapshot: Current claim state snapshot.
            receipt: Current revalidation receipt.
            chain_id: Chain identifier for attribution.
            degradation_count: Count of consecutive degraded/escalated
                receipts in this chain.
            replay_divergence_ratio: Observed replay divergence ratio
                (0.0 = no divergence, 1.0 = full divergence).
            has_required_approval: Whether required approval is present
                for the current transition.
            policy_violation_detected: Whether a policy boundary
                violation was detected in continuation state.
            policy_violation_detail: Human-readable detail of the
                policy violation.

        Returns:
            List of enforcement events (empty in observe mode).
        """
        if self._config.mode == EnforcementMode.OBSERVE:
            return []

        conditions = self._evaluate_conditions(
            snapshot=snapshot,
            receipt=receipt,
            degradation_count=degradation_count,
            replay_divergence_ratio=replay_divergence_ratio,
            has_required_approval=has_required_approval,
            policy_violation_detected=policy_violation_detected,
            policy_violation_detail=policy_violation_detail,
        )

        met_conditions = [c for c in conditions if c.is_met]
        if not met_conditions:
            return []

        events: List[EnforcementEvent] = []
        is_enforce = self._config.mode == EnforcementMode.ENFORCE

        for condition in met_conditions:
            action = self._resolve_action(condition.condition_type)
            severity = self._compute_severity(condition, action)
            reasoning = self._build_reasoning(condition, action)

            event = EnforcementEvent(
                claim_lineage_id=snapshot.claim_lineage_id,
                chain_id=chain_id,
                snapshot_id=snapshot.snapshot_id,
                receipt_id=receipt.receipt_id,
                law_version=snapshot.law_version,
                mode=self._config.mode,
                action=action,
                is_enforced=is_enforce,
                is_advisory=not is_enforce,
                conditions_evaluated=conditions,
                conditions_met=[condition],
                reasoning=reasoning,
                reason_codes=[condition.condition_type.value],
                claim_status=snapshot.claim_status.value,
                boundary_outcome=receipt.boundary_outcome or "",
                severity=severity,
            )
            events.append(event)

            logger.info(
                "[continuation-enforcement] %s event: action=%s condition=%s "
                "chain=%s mode=%s enforced=%s severity=%s",
                "ENFORCEMENT" if is_enforce else "ADVISORY",
                action.value,
                condition.condition_type.value,
                chain_id,
                self._config.mode.value,
                is_enforce,
                severity,
            )

        return events

    # ------------------------------------------------------------------
    # Condition evaluation (high-confidence, explainable)
    # ------------------------------------------------------------------

    def _evaluate_conditions(
        self,
        *,
        snapshot: ClaimStateSnapshot,
        receipt: ContinuationReceipt,
        degradation_count: int,
        replay_divergence_ratio: float,
        has_required_approval: bool,
        policy_violation_detected: bool,
        policy_violation_detail: str,
    ) -> List[EnforcementCondition]:
        """Evaluate all four enforcement conditions.

        Each condition independently computes a confidence score
        and explanation.  Only conditions meeting the minimum
        confidence threshold are marked as met.
        """
        conditions: List[EnforcementCondition] = []

        # 1. Repeated degradation
        conditions.append(self._check_repeated_degradation(
            receipt=receipt,
            degradation_count=degradation_count,
        ))

        # 2. Approval required without approval
        conditions.append(self._check_approval_required(
            snapshot=snapshot,
            receipt=receipt,
            has_required_approval=has_required_approval,
        ))

        # 3. Replay divergence exceeded
        conditions.append(self._check_replay_divergence(
            receipt=receipt,
            replay_divergence_ratio=replay_divergence_ratio,
        ))

        # 4. Policy boundary violation
        conditions.append(self._check_policy_boundary(
            snapshot=snapshot,
            receipt=receipt,
            policy_violation_detected=policy_violation_detected,
            policy_violation_detail=policy_violation_detail,
        ))

        return conditions

    def _check_repeated_degradation(
        self,
        *,
        receipt: ContinuationReceipt,
        degradation_count: int,
    ) -> EnforcementCondition:
        """Check for repeated high-risk continuation degradation.

        Triggers when the chain has experienced consecutive
        degraded/escalated/halted receipts beyond the configured
        threshold.
        """
        threshold = self._config.degradation_repeat_threshold
        is_degraded = receipt.revalidation_status in (
            RevalidationStatus.DEGRADED,
            RevalidationStatus.ESCALATED,
            RevalidationStatus.HALTED,
        )

        if not is_degraded or degradation_count < threshold:
            return EnforcementCondition(
                condition_type=EnforcementConditionType.REPEATED_DEGRADATION,
                is_met=False,
                confidence=0.0,
                explanation=(
                    f"Degradation count {degradation_count} "
                    f"below threshold {threshold}"
                ),
                evidence={
                    "degradation_count": degradation_count,
                    "threshold": threshold,
                    "current_status": receipt.revalidation_status.value,
                },
            )

        # Confidence scales with how far above threshold we are
        confidence = min(
            1.0,
            0.8 + 0.05 * (degradation_count - threshold),
        )

        return EnforcementCondition(
            condition_type=EnforcementConditionType.REPEATED_DEGRADATION,
            is_met=confidence >= self._config.min_confidence,
            confidence=confidence,
            explanation=(
                f"Chain has {degradation_count} consecutive degraded "
                f"receipts (threshold: {threshold}). "
                f"Current status: {receipt.revalidation_status.value}."
            ),
            evidence={
                "degradation_count": degradation_count,
                "threshold": threshold,
                "current_status": receipt.revalidation_status.value,
            },
        )

    def _check_approval_required(
        self,
        *,
        snapshot: ClaimStateSnapshot,
        receipt: ContinuationReceipt,
        has_required_approval: bool,
    ) -> EnforcementCondition:
        """Check for approval-required transition without approval.

        Triggers when the continuation scope requires escalation
        (approval) but no approval has been provided.
        """
        escalation_required = snapshot.scope.escalation_required

        if not escalation_required or has_required_approval:
            return EnforcementCondition(
                condition_type=EnforcementConditionType.APPROVAL_REQUIRED_WITHOUT_APPROVAL,
                is_met=False,
                confidence=0.0,
                explanation=(
                    "No approval gap detected"
                    if has_required_approval
                    else "Escalation not required"
                ),
                evidence={
                    "escalation_required": escalation_required,
                    "has_required_approval": has_required_approval,
                },
            )

        # Approval-required without approval is a deterministic condition
        confidence = 1.0

        return EnforcementCondition(
            condition_type=EnforcementConditionType.APPROVAL_REQUIRED_WITHOUT_APPROVAL,
            is_met=True,
            confidence=confidence,
            explanation=(
                "Continuation scope requires escalation/approval but "
                "no approval has been provided. "
                f"Claim status: {snapshot.claim_status.value}."
            ),
            evidence={
                "escalation_required": True,
                "has_required_approval": False,
                "claim_status": snapshot.claim_status.value,
            },
        )

    def _check_replay_divergence(
        self,
        *,
        receipt: ContinuationReceipt,
        replay_divergence_ratio: float,
    ) -> EnforcementCondition:
        """Check for replay divergence above threshold.

        Triggers when the divergence ratio for a sensitive decision
        path exceeds the configured threshold.
        """
        threshold = self._config.replay_divergence_threshold

        if replay_divergence_ratio <= threshold:
            return EnforcementCondition(
                condition_type=EnforcementConditionType.REPLAY_DIVERGENCE_EXCEEDED,
                is_met=False,
                confidence=0.0,
                explanation=(
                    f"Replay divergence {replay_divergence_ratio:.2f} "
                    f"within threshold {threshold:.2f}"
                ),
                evidence={
                    "replay_divergence_ratio": replay_divergence_ratio,
                    "threshold": threshold,
                    "receipt_divergence_flag": receipt.divergence_flag,
                },
            )

        # Confidence scales linearly with how far above threshold
        excess = replay_divergence_ratio - threshold
        max_excess = 1.0 - threshold
        confidence = min(
            1.0,
            0.8 + 0.2 * (excess / max_excess) if max_excess > 0 else 1.0,
        )

        return EnforcementCondition(
            condition_type=EnforcementConditionType.REPLAY_DIVERGENCE_EXCEEDED,
            is_met=confidence >= self._config.min_confidence,
            confidence=confidence,
            explanation=(
                f"Replay divergence ratio {replay_divergence_ratio:.2f} "
                f"exceeds threshold {threshold:.2f}. "
                f"Receipt divergence flag: {receipt.divergence_flag}."
            ),
            evidence={
                "replay_divergence_ratio": replay_divergence_ratio,
                "threshold": threshold,
                "receipt_divergence_flag": receipt.divergence_flag,
            },
        )

    def _check_policy_boundary(
        self,
        *,
        snapshot: ClaimStateSnapshot,
        receipt: ContinuationReceipt,
        policy_violation_detected: bool,
        policy_violation_detail: str,
    ) -> EnforcementCondition:
        """Check for policy boundary violation in continuation state.

        Triggers when a policy boundary violation has been detected
        in the continuation state (e.g., action class not allowed
        by current scope).
        """
        if not policy_violation_detected:
            return EnforcementCondition(
                condition_type=EnforcementConditionType.POLICY_BOUNDARY_VIOLATION,
                is_met=False,
                confidence=0.0,
                explanation="No policy boundary violation detected",
                evidence={
                    "policy_violation_detected": False,
                    "claim_status": snapshot.claim_status.value,
                },
            )

        # Policy boundary violation is deterministic when detected
        confidence = 1.0

        return EnforcementCondition(
            condition_type=EnforcementConditionType.POLICY_BOUNDARY_VIOLATION,
            is_met=True,
            confidence=confidence,
            explanation=(
                f"Policy boundary violation detected in continuation state. "
                f"Detail: {policy_violation_detail or 'unspecified'}. "
                f"Claim status: {snapshot.claim_status.value}."
            ),
            evidence={
                "policy_violation_detected": True,
                "policy_violation_detail": policy_violation_detail,
                "claim_status": snapshot.claim_status.value,
                "boundary_outcome": receipt.boundary_outcome or "",
            },
        )

    # ------------------------------------------------------------------
    # Action resolution and reasoning
    # ------------------------------------------------------------------

    def _resolve_action(
        self, condition_type: EnforcementConditionType,
    ) -> EnforcementAction:
        """Resolve the enforcement action for a given condition type."""
        action_str = self._config.action_map.get(
            condition_type.value, "escalate_alert"
        )
        try:
            return EnforcementAction(action_str)
        except ValueError:
            return EnforcementAction.ESCALATE_ALERT

    def _compute_severity(
        self,
        condition: EnforcementCondition,
        action: EnforcementAction,
    ) -> str:
        """Compute severity level for operator visibility."""
        if action == EnforcementAction.HALT_CHAIN:
            return "critical"
        if action == EnforcementAction.REQUIRE_HUMAN_REVIEW:
            return "high"
        if condition.confidence >= 0.95:
            return "high"
        return "medium"

    def _build_reasoning(
        self,
        condition: EnforcementCondition,
        action: EnforcementAction,
    ) -> str:
        """Build explicit, inspectable reasoning string."""
        return (
            f"Enforcement action '{action.value}' triggered by "
            f"condition '{condition.condition_type.value}' "
            f"(confidence: {condition.confidence:.2f}). "
            f"{condition.explanation}"
        )
