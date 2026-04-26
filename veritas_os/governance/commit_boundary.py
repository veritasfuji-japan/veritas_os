"""Deterministic irreversible commit-boundary evaluator.

This module evaluates whether an execution intent may cross a regulated commit
boundary using Action Class Contract + Authority Evidence artifacts. The design
is fail-closed and inspectable, and reuses RuntimeAuthorityValidator predicate
results for compatibility with existing bind-boundary architecture.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from veritas_os.governance.action_contracts import ActionClassContract
from veritas_os.governance.authority_evidence import AuthorityEvidence
from veritas_os.governance.predicates import PredicateResult
from veritas_os.governance.runtime_authority import RuntimeAuthorityValidator

CommitBoundaryOutcome = Literal["commit", "block", "escalate", "refuse"]


@dataclass(frozen=True)
class CommitBoundaryResult:
    """Inspectable commit-boundary decision record."""

    commit_boundary_result: CommitBoundaryOutcome
    action_contract_id: str
    action_contract_version: str
    authority_evidence_id: str
    authority_evidence_hash: str
    authority_validation_status: str
    admissibility_predicates: list[PredicateResult] = field(default_factory=list)
    failed_predicates: list[PredicateResult] = field(default_factory=list)
    stale_predicates: list[PredicateResult] = field(default_factory=list)
    missing_predicates: list[PredicateResult] = field(default_factory=list)
    refusal_basis: list[str] = field(default_factory=list)
    escalation_basis: list[str] = field(default_factory=list)
    irreversibility_boundary_id: str = ""
    evaluated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    reason_summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class CommitBoundaryEvaluator:
    """Evaluate commit-boundary admissibility with deterministic fail-closed rules."""

    def __init__(self, validator: RuntimeAuthorityValidator | None = None) -> None:
        self._validator = validator or RuntimeAuthorityValidator()

    def evaluate(
        self,
        *,
        execution_intent: str | dict[str, Any],
        action_contract: ActionClassContract | None,
        authority_evidence: AuthorityEvidence | None,
        requested_scope: list[str],
        required_evidence_metadata: dict[str, Any],
        evidence_freshness_metadata: dict[str, Any],
        policy_snapshot_id: str | None,
        actor_identity: str | None,
        human_approval_state: dict[str, Any],
        bind_context_metadata: dict[str, Any],
        now: datetime | None = None,
    ) -> CommitBoundaryResult:
        """Return commit/block/escalate/refuse for irreversible commit boundary."""
        evaluated_at = (now or datetime.now(UTC)).isoformat()
        merged_evidence = self._merge_evidence_metadata(
            required_evidence_metadata=required_evidence_metadata,
            evidence_freshness_metadata=evidence_freshness_metadata,
        )

        authority_result = self._validator.validate(
            action_contract=action_contract,
            authority_evidence=authority_evidence,
            requested_scope=requested_scope,
            required_evidence_metadata=merged_evidence,
            policy_snapshot_id=policy_snapshot_id,
            actor_identity=actor_identity,
            human_approval_state=human_approval_state,
            bind_context_metadata=bind_context_metadata,
            now=now,
        )

        predicates = self._sorted_predicates(
            authority_result.passed_predicates
            + authority_result.failed_predicates
            + authority_result.stale_predicates
            + authority_result.missing_predicates
            + authority_result.indeterminate_predicates
        )
        failed = self._sorted_predicates(authority_result.failed_predicates)
        stale = self._sorted_predicates(authority_result.stale_predicates)
        missing = self._sorted_predicates(authority_result.missing_predicates)

        refusal_basis = sorted(set(authority_result.refusal_basis))
        escalation_basis = sorted(set(authority_result.escalation_basis))
        outcome = self._resolve_outcome(
            execution_intent=execution_intent,
            action_contract=action_contract,
            authority_result=authority_result,
        )

        return CommitBoundaryResult(
            commit_boundary_result=outcome,
            action_contract_id=action_contract.id if action_contract else "",
            action_contract_version=action_contract.version if action_contract else "",
            authority_evidence_id=(
                authority_evidence.authority_evidence_id if authority_evidence else ""
            ),
            authority_evidence_hash=(
                authority_evidence.evidence_hash if authority_evidence else ""
            ),
            authority_validation_status=authority_result.status,
            admissibility_predicates=predicates,
            failed_predicates=failed,
            stale_predicates=stale,
            missing_predicates=missing,
            refusal_basis=refusal_basis,
            escalation_basis=escalation_basis,
            irreversibility_boundary_id=(
                str(action_contract.irreversibility.get("boundary", ""))
                if action_contract
                else ""
            ),
            evaluated_at=evaluated_at,
            reason_summary=authority_result.reason_summary,
            metadata={"validator_metadata": authority_result.metadata},
        )

    def _resolve_outcome(
        self,
        *,
        execution_intent: str | dict[str, Any],
        action_contract: ActionClassContract | None,
        authority_result: Any,
    ) -> CommitBoundaryOutcome:
        if authority_result.recommended_outcome == "escalate":
            return "escalate"
        if authority_result.recommended_outcome == "refuse":
            return "refuse"
        if authority_result.recommended_outcome == "block":
            return "block"

        if not self._is_action_admissible(execution_intent, action_contract):
            return "refuse"
        return "commit"

    def _is_action_admissible(
        self,
        execution_intent: str | dict[str, Any],
        action_contract: ActionClassContract | None,
    ) -> bool:
        if not action_contract:
            return False

        if isinstance(execution_intent, str):
            return bool(execution_intent.strip())

        intent_action_class = str(execution_intent.get("action_class", "")).strip()
        if intent_action_class and intent_action_class != action_contract.action_class:
            return False

        admissible_flag = execution_intent.get("admissible")
        if admissible_flag is False:
            return False

        return True

    def _merge_evidence_metadata(
        self,
        *,
        required_evidence_metadata: dict[str, Any],
        evidence_freshness_metadata: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        keys = sorted(set(required_evidence_metadata) | set(evidence_freshness_metadata))
        for key in keys:
            required = dict(required_evidence_metadata.get(key, {}))
            freshness = dict(evidence_freshness_metadata.get(key, {}))
            present = bool(required.get("present", False))
            fresh_value = freshness.get("fresh", required.get("fresh", False))
            merged[key] = {"present": present, "fresh": fresh_value}
        return merged

    def _sorted_predicates(
        self,
        predicates: list[PredicateResult],
    ) -> list[PredicateResult]:
        return sorted(predicates, key=lambda item: item.predicate_id)


def evaluate_commit_boundary(**kwargs: Any) -> CommitBoundaryResult:
    """Helper for one-shot commit-boundary evaluation."""
    return CommitBoundaryEvaluator().evaluate(**kwargs)
