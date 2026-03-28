# veritas_os/core/continuation_runtime/revalidator.py
# -*- coding: utf-8 -*-
"""
ContinuationRevalidator — pre-merit chain-level revalidation engine.

Phase-1 contract:
  - Shadow / observe only; no enforcement, no refusal gating.
  - Runs *before* step-level merit evaluation (FUJI / gate).
  - Emits a (snapshot, receipt) pair per revalidation pass.
  - ``should_refuse_before_effect`` is advisory only.
  - snapshot and receipt are tightly coupled (emitted together,
    share snapshot_id) but remain separate objects.

The revalidator is NOT part of FUJI.  It lives beside FUJI as an
independent chain-level observation substrate.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

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
from .reason_codes import ReasonCode

logger = logging.getLogger(__name__)


# =====================================================================
# Present-condition input (collected from pipeline context)
# =====================================================================


@dataclass
class PresentCondition:
    """Observable conditions at the point of revalidation.

    Collected from the pipeline context *before* step-level evaluation.
    This is the revalidator's input — not a snapshot (output).
    """

    chain_id: str = ""
    step_index: int = 0
    query: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    prior_decision_status: Optional[str] = None
    prior_receipt_id: Optional[str] = None


# =====================================================================
# Default law pack (phase-1: shadow, conservative)
# =====================================================================

_DEFAULT_LAW_PACK = ContinuationLawPack(
    law_version_id="v0.1.0-shadow",
    policy_family="continuation_baseline",
    invariant_family="structural_v1",
    corridor_family="default",
    rule_refs=[
        "support_basis_present",
        "scope_within_bounds",
        "burden_below_threshold",
        "headroom_positive",
    ],
    evaluation_mode=EvaluationMode.SHADOW,
)


def _default_law_pack() -> ContinuationLawPack:
    """Return the default phase-1 law pack (shadow mode)."""
    return _DEFAULT_LAW_PACK


# =====================================================================
# ContinuationRevalidator
# =====================================================================


class ContinuationRevalidator:
    """Pre-merit chain-level revalidation engine.

    Usage::

        revalidator = ContinuationRevalidator()
        snapshot, receipt = revalidator.revalidate(
            lineage=lineage,
            condition=present_condition,
        )

    The revalidator:
      1. Loads / initialises the lineage (or accepts one).
      2. Collects present conditions.
      3. Resolves the applicable law pack.
      4. Evaluates continuation standing (conservative).
      5. Builds a new snapshot (state) and receipt (audit witness).
      6. Updates the lineage's mutable pointers.

    It does NOT enforce; it observes and records.
    """

    def __init__(
        self,
        law_pack: Optional[ContinuationLawPack] = None,
    ) -> None:
        self._law_pack = law_pack or _default_law_pack()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def revalidate(
        self,
        lineage: ContinuationClaimLineage,
        condition: PresentCondition,
        *,
        prior_snapshot: Optional[ClaimStateSnapshot] = None,
        prior_receipt: Optional[ContinuationReceipt] = None,
    ) -> Tuple[ClaimStateSnapshot, ContinuationReceipt]:
        """Run a single revalidation pass.

        Returns ``(snapshot, receipt)`` — always both, always consistent.
        """
        # 1. Collect present conditions into a candidate support basis
        support_basis = self._collect_support_basis(condition)

        # 2. Build candidate scope
        scope = self._collect_scope(condition)

        # 3. Evaluate burden / headroom from context
        burden_state = self._evaluate_burden(condition, prior_snapshot)
        headroom_state = self._evaluate_headroom(burden_state)

        # 4. Check revocation conditions
        revocation_conditions = self._check_revocation_conditions(
            condition, support_basis, prior_snapshot
        )

        # 5. Determine boundary outcome and reason codes (receipt-first)
        boundary_status, reason_codes = self._determine_status(
            support_basis=support_basis,
            scope=scope,
            burden_state=burden_state,
            headroom_state=headroom_state,
            revocation_conditions=revocation_conditions,
            prior_status=lineage.current_claim_status,
        )

        # 5b. Assess durability — determine whether the boundary outcome
        #     has durably changed standing, scope, or continuation rights.
        durable_consequence, claim_status = self._assess_durability(
            boundary_status=boundary_status,
            scope=scope,
            headroom_state=headroom_state,
            revocation_conditions=revocation_conditions,
        )

        # 6. Build snapshot (durable standing only)
        snapshot = ClaimStateSnapshot(
            claim_lineage_id=lineage.claim_lineage_id,
            prior_snapshot_id=(
                prior_snapshot.snapshot_id if prior_snapshot else lineage.latest_snapshot_id
            ),
            support_basis=support_basis,
            scope=scope,
            burden_state=burden_state,
            headroom_state=headroom_state,
            law_version=self._law_pack.law_version_id,
            revocation_conditions=revocation_conditions,
            claim_status=claim_status,
            durable_consequence=durable_consequence,
        )

        # 7. Map boundary outcome to revalidation status/outcome
        reval_status = self._map_revalidation_status(boundary_status)
        reval_outcome = self._map_revalidation_outcome(boundary_status)

        # 8. Determine divergence and advisory refusal
        should_refuse = boundary_status in (
            ClaimStatus.HALTED,
            ClaimStatus.REVOKED,
        )
        divergence = boundary_status != ClaimStatus.LIVE

        # 8b. Provisional vs durable assessment
        is_durable = durable_consequence is not None
        if boundary_status == ClaimStatus.LIVE:
            prov_vs_dur = None
        elif is_durable:
            prov_vs_dur = "durable_promotable"
        else:
            prov_vs_dur = "provisional"

        # 8c. Reopening eligibility (narrowed-specific)
        reopening = self._assess_reopening_eligible(
            boundary_status, scope, is_durable
        )

        # 9. Build receipt (proof-bearing boundary adjudication witness)
        receipt = ContinuationReceipt(
            claim_lineage_id=lineage.claim_lineage_id,
            snapshot_id=snapshot.snapshot_id,
            law_version_id=self._law_pack.law_version_id,
            revalidation_status=reval_status,
            revalidation_outcome=reval_outcome,
            revalidation_reason_codes=reason_codes,
            prior_decision_continuity_ref=condition.prior_decision_status,
            parent_receipt_ref=(
                prior_receipt.receipt_id if prior_receipt else condition.prior_receipt_id
            ),
            divergence_flag=divergence,
            should_refuse_before_effect=should_refuse,
            support_basis_digest=self._digest_support_basis(support_basis),
            scope_digest=self._digest_scope(scope),
            burden_headroom_digest=self._digest_burden_headroom(
                burden_state, headroom_state
            ),
            boundary_outcome=boundary_status.value,
            is_durable_promotion=is_durable,
            provisional_vs_durable=prov_vs_dur,
            reopening_eligible=reopening,
        )

        # 10. Coherence guard: snapshot and receipt must agree on status
        #     (prevents runtime claiming standing while receipt shows loss)
        self._assert_coherence(snapshot, receipt)

        # 11. Update lineage mutable pointers
        lineage.latest_snapshot_id = snapshot.snapshot_id
        lineage.current_claim_status = claim_status
        if claim_status == ClaimStatus.REVOKED:
            lineage.is_revoked = True
            from .lineage import _utcnow
            lineage.revoked_at = _utcnow()

        return snapshot, receipt

    # ------------------------------------------------------------------
    # Condition collectors
    # ------------------------------------------------------------------

    def _collect_support_basis(self, condition: PresentCondition) -> SupportBasis:
        """Build support basis from present conditions.

        Phase-1 uses simple heuristics; production will integrate with
        actual authority/policy/evidence stores.
        """
        ctx = condition.context or {}

        # Authority: check if there's an explicit authorization
        authority = ctx.get("authorization", "")
        if not authority and condition.chain_id:
            authority = f"chain:{condition.chain_id}"

        # Policy: check for policy reference
        policy = ctx.get("policy_ref", "default")

        # Evidence: summarize available evidence
        evidence_count = len(ctx.get("evidence", []))
        evidence = f"evidence_count:{evidence_count}" if evidence_count else ""

        # Dependency: external dependencies still available
        dependency = ctx.get("dependency_status", "")

        # Environment: runtime conditions
        environment = ctx.get("environment_status", "nominal")

        return SupportBasis(
            authority=authority,
            policy=policy,
            evidence=evidence,
            dependency=dependency,
            environment=environment,
        )

    def _collect_scope(self, condition: PresentCondition) -> Scope:
        """Build scope from present conditions."""
        ctx = condition.context or {}
        return Scope(
            allowed_action_classes=ctx.get("allowed_actions", ["query", "decide"]),
            restricted_action_classes=ctx.get("restricted_actions", []),
            escalation_required=ctx.get("escalation_required", False),
        )

    def _evaluate_burden(
        self,
        condition: PresentCondition,
        prior_snapshot: Optional[ClaimStateSnapshot],
    ) -> BurdenState:
        """Evaluate current burden state.

        Burden accumulates across steps; each step may satisfy or
        increase evidentiary requirements.
        """
        ctx = condition.context or {}

        # Carry forward from prior snapshot if available
        if prior_snapshot is not None:
            prior_burden = prior_snapshot.burden_state
            required = list(prior_burden.required_evidence)
            satisfied = list(prior_burden.satisfied_evidence)
            threshold = prior_burden.threshold
            current_level = prior_burden.current_level
        else:
            required = ctx.get("required_evidence", [])
            satisfied = ctx.get("satisfied_evidence", [])
            threshold = ctx.get("burden_threshold", 1.0)
            current_level = ctx.get("burden_current_level", 1.0)

        # Check for newly satisfied evidence
        new_evidence = ctx.get("new_evidence", [])
        for ev in new_evidence:
            if ev in required and ev not in satisfied:
                satisfied.append(ev)

        # Recalculate current level
        if required:
            current_level = len(satisfied) / len(required)
        else:
            current_level = 1.0

        return BurdenState(
            required_evidence=required,
            satisfied_evidence=satisfied,
            threshold=threshold,
            current_level=current_level,
        )

    def _evaluate_headroom(self, burden_state: BurdenState) -> HeadroomState:
        """Derive headroom from burden state.

        Headroom = how much margin remains before burden thresholds
        are breached.
        """
        remaining = burden_state.current_level
        return HeadroomState(
            remaining=remaining,
            threshold_escalation=0.3,
            threshold_suspension=0.0,
        )

    def _check_revocation_conditions(
        self,
        condition: PresentCondition,
        support_basis: SupportBasis,
        prior_snapshot: Optional[ClaimStateSnapshot],
    ) -> List[RevocationCondition]:
        """Check pre-declared revocation conditions."""
        conditions: List[RevocationCondition] = []

        # Condition: support basis must have authority
        conditions.append(
            RevocationCondition(
                condition_id="authority_present",
                description="Chain must have an authority reference",
                is_met=not bool(support_basis.authority),
            )
        )

        # Condition: policy must be present
        conditions.append(
            RevocationCondition(
                condition_id="policy_present",
                description="Policy reference must exist",
                is_met=not bool(support_basis.policy),
            )
        )

        return conditions

    # ------------------------------------------------------------------
    # Status determination (conservative)
    # ------------------------------------------------------------------

    def _determine_status(
        self,
        *,
        support_basis: SupportBasis,
        scope: Scope,
        burden_state: BurdenState,
        headroom_state: HeadroomState,
        revocation_conditions: List[RevocationCondition],
        prior_status: ClaimStatus,
    ) -> Tuple[ClaimStatus, List[ReasonCode]]:
        """Determine claim status from evaluated conditions.

        Phase-1 is conservative: only degrades, never upgrades.
        Once revoked, stays revoked.
        """
        reason_codes: List[ReasonCode] = []

        # Revoked is terminal
        if prior_status == ClaimStatus.REVOKED:
            return ClaimStatus.REVOKED, [ReasonCode.CLAIM_REVOKED]

        # Halted is terminal within a session
        if prior_status == ClaimStatus.HALTED:
            return ClaimStatus.HALTED, [ReasonCode.CLAIM_HALTED]

        # Check revocation conditions
        met_revocations = [rc for rc in revocation_conditions if rc.is_met]
        if met_revocations:
            # Both authority AND policy lost → revoked
            authority_lost = any(
                rc.condition_id == "authority_present" for rc in met_revocations
            )
            policy_lost = any(
                rc.condition_id == "policy_present" for rc in met_revocations
            )
            if authority_lost and policy_lost:
                reason_codes.append(ReasonCode.SUPPORT_LOST_APPROVAL)
                reason_codes.append(ReasonCode.SUPPORT_LOST_POLICY_SCOPE)
                return ClaimStatus.REVOKED, reason_codes

        # Support basis lost (no authority and no policy)
        if not support_basis.authority and not support_basis.policy:
            reason_codes.append(ReasonCode.SUPPORT_LOST_APPROVAL)
            return ClaimStatus.REVOKED, reason_codes

        # Headroom collapsed
        if headroom_state.remaining <= headroom_state.threshold_suspension:
            reason_codes.append(ReasonCode.HEADROOM_COLLAPSED)
            return ClaimStatus.HALTED, reason_codes

        # Headroom near escalation
        if headroom_state.remaining <= headroom_state.threshold_escalation:
            reason_codes.append(ReasonCode.HEADROOM_COLLAPSED)
            return ClaimStatus.ESCALATED, reason_codes

        # Scope mismatch: escalation required
        if scope.escalation_required:
            reason_codes.append(ReasonCode.ACTION_CLASS_NOT_ALLOWED)
            return ClaimStatus.ESCALATED, reason_codes

        # Burden threshold exceeded
        if burden_state.current_level < burden_state.threshold:
            reason_codes.append(ReasonCode.BURDEN_THRESHOLD_EXCEEDED)
            return ClaimStatus.DEGRADED, reason_codes

        # Scope narrowing: restricted actions present
        if scope.restricted_action_classes:
            reason_codes.append(ReasonCode.ACTION_CLASS_NOT_ALLOWED)
            return ClaimStatus.NARROWED, reason_codes

        # All clear — maintain or renew
        return ClaimStatus.LIVE, reason_codes

    # ------------------------------------------------------------------
    # Durability assessment (receipt-first boundary rule)
    # ------------------------------------------------------------------

    @staticmethod
    def _assess_durability(
        *,
        boundary_status: ClaimStatus,
        scope: Scope,
        headroom_state: HeadroomState,
        revocation_conditions: List[RevocationCondition],
    ) -> Tuple[Optional[DurableConsequence], ClaimStatus]:
        """Decide whether a boundary outcome has durable state consequence.

        Receipt-first rule: any boundary outcome that has not yet durably
        changed lawful standing, available scope, continuation rights,
        onward carryability, or continuation class remains receipt-only.

        Returns ``(durable_consequence, state_claim_status)``.
        When the outcome is receipt-only, ``durable_consequence`` is None
        and ``state_claim_status`` falls back to LIVE (standing preserved).
        """
        # LIVE and REVOKED are inherently state-level.
        if boundary_status == ClaimStatus.LIVE:
            return None, ClaimStatus.LIVE

        if boundary_status == ClaimStatus.REVOKED:
            return DurableConsequence(
                has_irreversible_revocation=True,
                promotion_reason="irreversible support loss",
            ), ClaimStatus.REVOKED

        # HALTED: durable when headroom has irreversibly collapsed.
        if boundary_status == ClaimStatus.HALTED:
            if headroom_state.remaining <= headroom_state.threshold_suspension:
                return DurableConsequence(
                    has_durable_halt=True,
                    promotion_reason="headroom irreversibly collapsed",
                ), ClaimStatus.HALTED
            # Runtime interruption without irreversible collapse → receipt-only.
            return None, ClaimStatus.LIVE

        # NARROWED: durable when scope reduction is not re-openable.
        if boundary_status == ClaimStatus.NARROWED:
            if scope.restricted_action_classes:
                return DurableConsequence(
                    has_durable_scope_reduction=True,
                    promotion_reason="durable scope restriction present",
                ), ClaimStatus.NARROWED
            return None, ClaimStatus.LIVE

        # DEGRADED: receipt-first by default in Phase-1.
        # Burden pressure is recoverable; not a durable standing change.
        if boundary_status == ClaimStatus.DEGRADED:
            return None, ClaimStatus.DEGRADED

        # ESCALATED: receipt-first by default in Phase-1.
        # Escalation requirement is a boundary condition, not a durable
        # standing transformation — unless it has already locked scope.
        if boundary_status == ClaimStatus.ESCALATED:
            return None, ClaimStatus.ESCALATED

        # Unrecognised status — conservative: treat as state-level.
        return None, boundary_status

    @staticmethod
    def _assess_reopening_eligible(
        boundary_status: ClaimStatus,
        scope: Scope,
        is_durable: bool,
    ) -> bool:
        """Reopening test for narrowed outcomes.

        "If the immediate boundary condition resolves, and standing /
        burden / authority / continuity basis have no deeper change,
        should the prior scope width reopen?"

        - Yes → receipt-level narrowing (provisional, reopening eligible)
        - No  → durable narrowing (promoted to state, not reopenable)
        """
        if boundary_status != ClaimStatus.NARROWED:
            return True  # default: non-narrowed outcomes are not scope-locked
        # If the narrowing is durable, prior width cannot reopen.
        return not is_durable

    # ------------------------------------------------------------------
    # Status mapping (ClaimStatus → RevalidationStatus / Outcome)
    # ------------------------------------------------------------------

    _STATUS_MAP: Dict[ClaimStatus, RevalidationStatus] = {
        ClaimStatus.LIVE: RevalidationStatus.RENEWED,
        ClaimStatus.NARROWED: RevalidationStatus.NARROWED,
        ClaimStatus.DEGRADED: RevalidationStatus.DEGRADED,
        ClaimStatus.ESCALATED: RevalidationStatus.ESCALATED,
        ClaimStatus.HALTED: RevalidationStatus.HALTED,
        ClaimStatus.REVOKED: RevalidationStatus.REVOKED,
    }

    _OUTCOME_MAP: Dict[ClaimStatus, RevalidationOutcome] = {
        ClaimStatus.LIVE: RevalidationOutcome.RENEWED,
        ClaimStatus.NARROWED: RevalidationOutcome.NARROWED,
        ClaimStatus.DEGRADED: RevalidationOutcome.DEGRADED,
        ClaimStatus.ESCALATED: RevalidationOutcome.ESCALATED,
        ClaimStatus.HALTED: RevalidationOutcome.HALTED,
        ClaimStatus.REVOKED: RevalidationOutcome.REVOKED,
    }

    def _map_revalidation_status(self, status: ClaimStatus) -> RevalidationStatus:
        return self._STATUS_MAP.get(status, RevalidationStatus.FAILED)

    def _map_revalidation_outcome(self, status: ClaimStatus) -> RevalidationOutcome:
        return self._OUTCOME_MAP.get(status, RevalidationOutcome.FAILED)

    # ------------------------------------------------------------------
    # Digest helpers (for receipt audit fields)
    # ------------------------------------------------------------------

    @staticmethod
    def _digest_support_basis(sb: SupportBasis) -> str:
        raw = json.dumps(sb.to_dict(), sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    @staticmethod
    def _digest_scope(scope: Scope) -> str:
        raw = json.dumps(scope.to_dict(), sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    @staticmethod
    def _digest_burden_headroom(
        burden: BurdenState, headroom: HeadroomState
    ) -> str:
        raw = json.dumps(
            {"burden": burden.to_dict(), "headroom": headroom.to_dict()},
            sort_keys=True,
        )
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    # ------------------------------------------------------------------
    # Coherence guard
    # ------------------------------------------------------------------

    @staticmethod
    def _assert_coherence(
        snapshot: ClaimStateSnapshot,
        receipt: ContinuationReceipt,
    ) -> None:
        """Ensure snapshot and receipt do not contradict each other.

        Receipt-first coherence rules:
          - REVOKED is always durable: bi-directional agreement required.
          - HALTED in snapshot → receipt must also show HALTED (state
            cannot claim durable halt without receipt evidence).
          - HALTED in receipt → snapshot may be LIVE (receipt-first:
            halt can be receipt-only when not durable).  When the halt IS
            promoted to state, ``is_durable_promotion`` must be True.
          - snapshot_id must match.
        """
        # snapshot.claim_status == REVOKED ↔ receipt shows REVOKED
        if snapshot.claim_status == ClaimStatus.REVOKED:
            if receipt.revalidation_status != RevalidationStatus.REVOKED:
                raise ValueError(
                    "Coherence violation: snapshot is REVOKED but "
                    f"receipt status is {receipt.revalidation_status}"
                )
        if receipt.revalidation_status == RevalidationStatus.REVOKED:
            if snapshot.claim_status != ClaimStatus.REVOKED:
                raise ValueError(
                    "Coherence violation: receipt is REVOKED but "
                    f"snapshot status is {snapshot.claim_status}"
                )

        # snapshot.claim_status == HALTED → receipt must also show HALTED
        # (state cannot claim halt without receipt evidence)
        if snapshot.claim_status == ClaimStatus.HALTED:
            if receipt.revalidation_status != RevalidationStatus.HALTED:
                raise ValueError(
                    "Coherence violation: snapshot is HALTED but "
                    f"receipt status is {receipt.revalidation_status}"
                )

        # receipt shows HALTED but snapshot is not HALTED: this is valid
        # under receipt-first semantics (halt is receipt-only, not durable).
        # However, if receipt claims durable promotion, snapshot must agree.
        if receipt.revalidation_status == RevalidationStatus.HALTED:
            if receipt.is_durable_promotion and snapshot.claim_status != ClaimStatus.HALTED:
                raise ValueError(
                    "Coherence violation: receipt claims durable HALTED "
                    f"promotion but snapshot status is {snapshot.claim_status}"
                )

        # Shared snapshot_id
        if receipt.snapshot_id != snapshot.snapshot_id:
            raise ValueError(
                "Coherence violation: receipt.snapshot_id != snapshot.snapshot_id"
            )


# =====================================================================
# Pipeline integration helper
# =====================================================================


def run_continuation_revalidation_shadow(
    *,
    chain_id: str,
    step_index: int,
    query: str,
    context: Dict[str, Any],
    prior_decision_status: Optional[str] = None,
    prior_receipt_id: Optional[str] = None,
    lineage: Optional[ContinuationClaimLineage] = None,
    prior_snapshot: Optional[ClaimStateSnapshot] = None,
    prior_receipt: Optional[ContinuationReceipt] = None,
) -> Tuple[
    ContinuationClaimLineage,
    ClaimStateSnapshot,
    ContinuationReceipt,
]:
    """Convenience function for pipeline integration.

    Creates a lineage if none exists, runs revalidation, returns all
    three objects.  This is the single entry-point used by the pipeline
    sidecar stage.
    """
    if lineage is None:
        lineage = ContinuationClaimLineage(
            chain_id=chain_id,
            origin_ref=f"step:{step_index}",
            initial_law_version=_DEFAULT_LAW_PACK.law_version_id,
        )

    condition = PresentCondition(
        chain_id=chain_id,
        step_index=step_index,
        query=query,
        context=context,
        prior_decision_status=prior_decision_status,
        prior_receipt_id=prior_receipt_id,
    )

    revalidator = ContinuationRevalidator()
    snapshot, receipt = revalidator.revalidate(
        lineage=lineage,
        condition=condition,
        prior_snapshot=prior_snapshot,
        prior_receipt=prior_receipt,
    )

    return lineage, snapshot, receipt
