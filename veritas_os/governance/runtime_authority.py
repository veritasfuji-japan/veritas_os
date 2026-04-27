"""Runtime authority validator for regulated action governance."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from veritas_os.governance.action_contracts import ActionClassContract
from veritas_os.governance.authority_evidence import (
    AuthorityEvidence,
    VerificationResult,
    is_expired,
)
from veritas_os.governance.predicates import PredicateResult

RuntimeValidationStatus = Literal["pass", "fail"]
RecommendedOutcome = Literal["commit", "block", "escalate", "refuse"]
KNOWN_PREDICATE_TYPES = {
    "action_contract_present",
    "action_contract_valid",
    "authority_present",
    "authority_valid",
    "authority_not_expired",
    "scope_allowed",
    "prohibited_scope_absent",
    "evidence_present",
    "evidence_fresh",
    "policy_snapshot_resolved",
    "human_approval_present",
    "irreversibility_boundary_defined",
    "actor_identity_resolved",
    "bind_context_valid",
}


@dataclass(frozen=True)
class RuntimeAuthorityValidationResult:
    """Aggregate result for runtime authority validation."""

    status: RuntimeValidationStatus
    recommended_outcome: RecommendedOutcome
    passed_predicates: list[PredicateResult] = field(default_factory=list)
    failed_predicates: list[PredicateResult] = field(default_factory=list)
    stale_predicates: list[PredicateResult] = field(default_factory=list)
    missing_predicates: list[PredicateResult] = field(default_factory=list)
    indeterminate_predicates: list[PredicateResult] = field(default_factory=list)
    refusal_basis: list[str] = field(default_factory=list)
    escalation_basis: list[str] = field(default_factory=list)
    evaluated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    reason_summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class RuntimeAuthorityValidator:
    """Deterministic predicate-based runtime validator with fail-closed defaults."""

    def validate(
        self,
        *,
        action_contract: ActionClassContract | None,
        authority_evidence: AuthorityEvidence | None,
        requested_scope: list[str],
        required_evidence_metadata: dict[str, Any],
        policy_snapshot_id: str | None,
        actor_identity: str | None,
        human_approval_state: dict[str, Any],
        bind_context_metadata: dict[str, Any],
        now: datetime | None = None,
    ) -> RuntimeAuthorityValidationResult:
        """Validate runtime authority with explicit deterministic predicates."""
        evaluated_at = (now or datetime.now(UTC)).isoformat()
        predicates: list[PredicateResult] = []

        try:
            contract_present = action_contract is not None
            predicates.append(
                self._predicate(
                    predicate_id="p-action-contract-present",
                    predicate_type="action_contract_present",
                    status="pass" if contract_present else "missing",
                    reason="action_contract_present" if contract_present else "action_contract_missing",
                    evaluated_at=evaluated_at,
                )
            )

            contract_valid = bool(action_contract and action_contract.id and action_contract.version)
            predicates.append(
                self._predicate(
                    predicate_id="p-action-contract-valid",
                    predicate_type="action_contract_valid",
                    status="pass" if contract_valid else "fail",
                    reason="action_contract_valid" if contract_valid else "action_contract_invalid",
                    evaluated_at=evaluated_at,
                )
            )

            authority_present = authority_evidence is not None
            predicates.append(
                self._predicate(
                    predicate_id="p-authority-present",
                    predicate_type="authority_present",
                    status="pass" if authority_present else "missing",
                    reason="authority_present" if authority_present else "authority_missing",
                    evaluated_at=evaluated_at,
                )
            )

            authority_valid = False
            if authority_evidence and action_contract:
                authority_valid = (
                    authority_evidence.verification_result == VerificationResult.VALID
                    and authority_evidence.action_contract_version == action_contract.version
                    and bool(authority_evidence.actor_role.strip())
                    and bool(authority_evidence.authority_source_refs)
                )
            predicates.append(
                self._predicate(
                    predicate_id="p-authority-valid",
                    predicate_type="authority_valid",
                    status="pass" if authority_valid else "fail",
                    reason="authority_valid" if authority_valid else "authority_invalid",
                    evaluated_at=evaluated_at,
                )
            )

            not_expired = False
            expiration_reason = "authority_expired_or_missing"
            if authority_evidence:
                not_expired = not is_expired(authority_evidence, now=now)
                expiration_reason = "authority_not_expired" if not_expired else "authority_expired"
            predicates.append(
                self._predicate(
                    predicate_id="p-authority-not-expired",
                    predicate_type="authority_not_expired",
                    status="pass" if not_expired else "fail",
                    reason=expiration_reason,
                    evaluated_at=evaluated_at,
                )
            )

            actor_resolved = bool((actor_identity or "").strip())
            predicates.append(
                self._predicate(
                    predicate_id="p-actor-identity-resolved",
                    predicate_type="actor_identity_resolved",
                    status="pass" if actor_resolved else "missing",
                    reason="actor_identity_resolved" if actor_resolved else "actor_identity_missing",
                    evaluated_at=evaluated_at,
                )
            )

            scope_allowed = bool(action_contract) and all(
                scope in action_contract.allowed_scope for scope in requested_scope
            )
            predicates.append(
                self._predicate(
                    predicate_id="p-scope-allowed",
                    predicate_type="scope_allowed",
                    status="pass" if scope_allowed else "fail",
                    reason="scope_allowed" if scope_allowed else "scope_expansion_detected",
                    evaluated_at=evaluated_at,
                )
            )

            prohibited_absent = bool(action_contract) and all(
                scope not in action_contract.prohibited_scope for scope in requested_scope
            )
            predicates.append(
                self._predicate(
                    predicate_id="p-prohibited-scope-absent",
                    predicate_type="prohibited_scope_absent",
                    status="pass" if prohibited_absent else "fail",
                    reason=(
                        "prohibited_scope_absent"
                        if prohibited_absent
                        else "prohibited_scope_detected"
                    ),
                    evaluated_at=evaluated_at,
                )
            )

            required_evidence = action_contract.required_evidence if action_contract else []
            evidence_present = all(
                bool(required_evidence_metadata.get(key, {}).get("present"))
                for key in required_evidence
            )
            predicates.append(
                self._predicate(
                    predicate_id="p-evidence-present",
                    predicate_type="evidence_present",
                    status="pass" if evidence_present else "missing",
                    reason="evidence_present" if evidence_present else "required_evidence_missing",
                    evaluated_at=evaluated_at,
                )
            )

            freshness_states = [
                required_evidence_metadata.get(key, {}).get("fresh", False)
                for key in required_evidence
            ]
            if all(state is True for state in freshness_states):
                evidence_fresh_status = "pass"
                evidence_fresh_reason = "evidence_fresh"
            elif any(state == "indeterminate" for state in freshness_states):
                evidence_fresh_status = "indeterminate"
                evidence_fresh_reason = "evidence_freshness_indeterminate"
            else:
                evidence_fresh_status = "stale"
                evidence_fresh_reason = "evidence_stale"
            predicates.append(
                self._predicate(
                    predicate_id="p-evidence-fresh",
                    predicate_type="evidence_fresh",
                    status=evidence_fresh_status,
                    reason=evidence_fresh_reason,
                    evaluated_at=evaluated_at,
                )
            )

            snapshot_resolved = bool((policy_snapshot_id or "").strip())
            if authority_evidence and authority_evidence.policy_snapshot_id:
                snapshot_resolved = (
                    snapshot_resolved
                    and authority_evidence.policy_snapshot_id == policy_snapshot_id
                )
            predicates.append(
                self._predicate(
                    predicate_id="p-policy-snapshot-resolved",
                    predicate_type="policy_snapshot_resolved",
                    status="pass" if snapshot_resolved else "fail",
                    reason=(
                        "policy_snapshot_resolved"
                        if snapshot_resolved
                        else "policy_snapshot_unresolved"
                    ),
                    evaluated_at=evaluated_at,
                )
            )

            boundary_defined = bool(
                action_contract
                and str(action_contract.irreversibility.get("boundary", "")).strip()
            )
            predicates.append(
                self._predicate(
                    predicate_id="p-irreversibility-boundary-defined",
                    predicate_type="irreversibility_boundary_defined",
                    status="pass" if boundary_defined else "fail",
                    reason=(
                        "irreversibility_boundary_defined"
                        if boundary_defined
                        else "irreversibility_boundary_missing"
                    ),
                    evaluated_at=evaluated_at,
                )
            )

            needs_approval = self._requires_human_approval(action_contract)
            approved = bool(human_approval_state.get("approved"))
            human_approval_ok = (not needs_approval) or approved
            predicates.append(
                self._predicate(
                    predicate_id="p-human-approval-present",
                    predicate_type="human_approval_present",
                    status="pass" if human_approval_ok else "missing",
                    reason=(
                        "human_approval_present"
                        if human_approval_ok
                        else "human_approval_missing"
                    ),
                    evaluated_at=evaluated_at,
                )
            )

            bind_context_valid = bool(bind_context_metadata) and not bool(
                bind_context_metadata.get("invalid", False)
            )
            predicates.append(
                self._predicate(
                    predicate_id="p-bind-context-valid",
                    predicate_type="bind_context_valid",
                    status="pass" if bind_context_valid else "fail",
                    reason="bind_context_valid" if bind_context_valid else "bind_context_invalid",
                    evaluated_at=evaluated_at,
                )
            )
        except Exception as exc:  # fail closed by design
            return RuntimeAuthorityValidationResult(
                status="fail",
                recommended_outcome="block",
                reason_summary="validator_exception_fail_closed",
                refusal_basis=["validator_exception"],
                metadata={"exception": str(exc)},
                evaluated_at=evaluated_at,
            )

        return self._build_result(predicates=predicates, action_contract=action_contract)

    def _build_result(
        self,
        *,
        predicates: list[PredicateResult],
        action_contract: ActionClassContract | None,
    ) -> RuntimeAuthorityValidationResult:
        unknown_critical_predicates = [
            item
            for item in predicates
            if str(item.predicate_type) not in KNOWN_PREDICATE_TYPES
            and str(item.severity) == "critical"
        ]
        passed = [item for item in predicates if item.status == "pass"]
        failed = [item for item in predicates if item.status == "fail"]
        stale = [item for item in predicates if item.status == "stale"]
        missing = [item for item in predicates if item.status == "missing"]
        indeterminate = [item for item in predicates if item.status == "indeterminate"]

        has_critical = bool(
            failed or stale or missing or indeterminate or unknown_critical_predicates
        )
        status: RuntimeValidationStatus = "fail" if has_critical else "pass"
        recommended: RecommendedOutcome = "commit"
        refusal_basis: list[str] = []
        escalation_basis: list[str] = []

        if indeterminate:
            recommended = "refuse"
            refusal_basis = sorted({item.reason for item in indeterminate})
        elif stale:
            if self._stale_should_escalate(action_contract):
                recommended = "escalate"
                escalation_basis = sorted({item.reason for item in stale})
            else:
                recommended = "block"
        elif failed or missing or unknown_critical_predicates:
            recommended = "block"

        reason_tokens = [item.reason for item in failed + stale + missing + indeterminate]
        if unknown_critical_predicates:
            reason_tokens.append("unknown_critical_predicate")
        summary = ", ".join(reason_tokens) if reason_tokens else "all_predicates_passed"

        return RuntimeAuthorityValidationResult(
            status=status,
            recommended_outcome=recommended,
            passed_predicates=passed,
            failed_predicates=failed,
            stale_predicates=stale,
            missing_predicates=missing,
            indeterminate_predicates=indeterminate,
            refusal_basis=refusal_basis,
            escalation_basis=escalation_basis,
            reason_summary=summary,
        )

    def _stale_should_escalate(self, action_contract: ActionClassContract | None) -> bool:
        if not action_contract:
            return False
        conditions = {item.lower() for item in action_contract.escalation_conditions}
        return "evidence_stale" in conditions or "stale_evidence" in conditions

    def _requires_human_approval(self, action_contract: ActionClassContract | None) -> bool:
        if not action_contract:
            return False
        rules = action_contract.human_approval_rules
        minimum_approvals = int(rules.get("minimum_approvals", 0) or 0)
        if bool(rules.get("required", False)):
            return True
        return (
            action_contract.irreversibility.get("level") == "high"
            and minimum_approvals > 0
        )

    def _predicate(
        self,
        *,
        predicate_id: str,
        predicate_type: Literal["action_contract_present", "action_contract_valid", "authority_present", "authority_valid", "authority_not_expired", "scope_allowed", "prohibited_scope_absent", "evidence_present", "evidence_fresh", "policy_snapshot_resolved", "human_approval_present", "irreversibility_boundary_defined", "actor_identity_resolved", "bind_context_valid"],
        status: Literal["pass", "fail", "stale", "missing", "indeterminate"],
        reason: str,
        evaluated_at: str,
    ) -> PredicateResult:
        return PredicateResult(
            predicate_id=predicate_id,
            predicate_type=predicate_type,
            status=status,
            reason=reason,
            evaluated_at=evaluated_at,
        )


def validate_runtime_authority(**kwargs: Any) -> RuntimeAuthorityValidationResult:
    """Helper for one-shot runtime authority validation."""
    return RuntimeAuthorityValidator().validate(**kwargs)
