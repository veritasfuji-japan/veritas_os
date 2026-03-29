"""Policy runtime evaluator for compiled Policy-as-Code artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

from .runtime_adapter import RuntimePolicy, RuntimePolicyBundle

OUTCOME_PRECEDENCE = {
    "allow": 0,
    "require_human_review": 1,
    "escalate": 2,
    "halt": 3,
    "deny": 4,
}


@dataclass(frozen=True)
class PolicyEvaluationResult:
    """Structured decision payload for audit/export and pipeline adapters."""

    applicable_policies: List[str]
    triggered_policies: List[str]
    final_outcome: str
    reasons: List[str]
    required_actions: List[str]
    obligations: List[str]
    approval_requirements: List[Dict[str, Any]]
    evidence_gaps: List[Dict[str, Any]]
    explanations: List[Dict[str, Any]]
    policy_results: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        """Convert dataclass result to serializable mapping."""
        return {
            "applicable_policies": self.applicable_policies,
            "triggered_policies": self.triggered_policies,
            "final_outcome": self.final_outcome,
            "reasons": self.reasons,
            "required_actions": self.required_actions,
            "obligations": self.obligations,
            "approval_requirements": self.approval_requirements,
            "evidence_gaps": self.evidence_gaps,
            "explanations": self.explanations,
            "policy_results": self.policy_results,
        }


def _read_path(context: Dict[str, Any], field_path: str) -> Any:
    current: Any = context
    for part in field_path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _evaluate_expression(expression: Dict[str, Any], context: Dict[str, Any]) -> bool:
    field = str(expression.get("field", ""))
    operator = str(expression.get("operator", "eq"))
    expected = expression.get("value")
    actual = _read_path(context, field)

    if operator == "eq":
        return actual == expected
    if operator == "neq":
        return actual != expected
    if operator == "in":
        return actual in expected if isinstance(expected, list) else False
    if operator == "not_in":
        return actual not in expected if isinstance(expected, list) else True
    if operator == "gt":
        return actual is not None and actual > expected
    if operator == "gte":
        return actual is not None and actual >= expected
    if operator == "lt":
        return actual is not None and actual < expected
    if operator == "lte":
        return actual is not None and actual <= expected
    if operator == "contains":
        if isinstance(actual, (list, tuple, set, str)):
            return expected in actual
        return False
    if operator == "regex":
        import re

        return bool(
            isinstance(actual, str)
            and isinstance(expected, str)
            and re.search(expected, actual)
        )
    return False


def _scope_matches(policy: RuntimePolicy, context: Dict[str, Any]) -> bool:
    domain = context.get("domain")
    route = context.get("route")
    actor = context.get("actor")

    domain_match = domain in policy.scope["domains"] if domain is not None else True
    route_match = route in policy.scope["routes"] if route is not None else True
    actor_match = actor in policy.scope["actors"] if actor is not None else True
    return bool(domain_match and route_match and actor_match)


def _listify(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    return []


def _evaluate_requirements(policy: RuntimePolicy, context: Dict[str, Any]) -> Dict[str, Any]:
    requirements = policy.requirements
    required_evidence = _listify(requirements.get("required_evidence"))
    required_reviewers = _listify(requirements.get("required_reviewers"))
    minimum_approval_count = int(requirements.get("minimum_approval_count", 0))

    evidence_context = context.get("evidence")
    approvals_context = context.get("approvals")

    evidence_available = []
    if isinstance(evidence_context, dict):
        evidence_available = _listify(evidence_context.get("available"))

    approved_by = []
    if isinstance(approvals_context, dict):
        approved_by = _listify(approvals_context.get("approved_by"))

    missing_evidence = sorted(
        item for item in required_evidence if item not in evidence_available
    )
    missing_reviewers = sorted(
        reviewer for reviewer in required_reviewers if reviewer not in approved_by
    )

    return {
        "required_reviewers": sorted(required_reviewers),
        "approved_by": sorted(approved_by),
        "minimum_approval_count": minimum_approval_count,
        "approved_count": len(approved_by),
        "missing_reviewers": missing_reviewers,
        "minimum_approval_met": len(approved_by) >= minimum_approval_count,
        "required_evidence": sorted(required_evidence),
        "missing_evidence": missing_evidence,
    }


def _choose_final_outcome(outcomes: Iterable[str]) -> str:
    selected = "allow"
    best_score = -1
    for outcome in outcomes:
        score = OUTCOME_PRECEDENCE.get(outcome, -1)
        if score > best_score:
            selected = outcome
            best_score = score
    return selected


def evaluate_runtime_policies(
    runtime_bundle: RuntimePolicyBundle,
    context: Dict[str, Any],
) -> PolicyEvaluationResult:
    """Evaluate adapted runtime policies for a request context."""
    applicable: List[str] = []
    triggered: List[str] = []
    reasons: List[str] = []
    required_actions: List[str] = []
    obligations: List[str] = []
    approval_requirements: List[Dict[str, Any]] = []
    evidence_gaps: List[Dict[str, Any]] = []
    explanations: List[Dict[str, Any]] = []
    outcomes: List[str] = []
    policy_results: List[Dict[str, Any]] = []

    for policy in runtime_bundle.runtime_policies:
        applies = _scope_matches(policy, context)
        matched_conditions = [
            cond for cond in policy.conditions if _evaluate_expression(cond, context)
        ]
        matched_constraints = [
            cond for cond in policy.constraints if _evaluate_expression(cond, context)
        ]
        triggered_policy = applies
        if policy.conditions:
            triggered_policy = triggered_policy and (
                len(matched_conditions) == len(policy.conditions)
            )
        if policy.constraints:
            triggered_policy = triggered_policy and (
                len(matched_constraints) == len(policy.constraints)
            )

        req_eval = _evaluate_requirements(policy, context)
        unmet_requirements = []
        if req_eval["missing_evidence"]:
            unmet_requirements.append("required_evidence")
        if req_eval["missing_reviewers"] or not req_eval["minimum_approval_met"]:
            unmet_requirements.append("required_approvals")

        outcome = "allow"
        explanation = "Policy did not apply."
        if applies:
            applicable.append(policy.policy_id)
            explanation = "Policy applied but did not trigger conditions/constraints."
        if triggered_policy:
            triggered.append(policy.policy_id)
            outcome = policy.outcome["decision"]
            explanation = (
                f"{policy.title}: {policy.outcome['reason']}"
                if policy.outcome["reason"]
                else policy.title
            )
            outcomes.append(outcome)
            reasons.append(policy.outcome["reason"] or policy.title)
            obligations.extend(policy.obligations)
            required_actions.extend(policy.obligations)

        if triggered_policy and req_eval["missing_evidence"] and outcome == "allow":
            outcome = "halt"
            outcomes.append(outcome)
            reasons.append("missing required evidence")
        if (
            triggered_policy
            and (req_eval["missing_reviewers"] or not req_eval["minimum_approval_met"])
            and outcome == "allow"
        ):
            outcome = "require_human_review"
            outcomes.append(outcome)
            reasons.append("required approvals are not satisfied")

        approval_requirements.append(
            {
                "policy_id": policy.policy_id,
                "required_reviewers": req_eval["required_reviewers"],
                "minimum_approval_count": req_eval["minimum_approval_count"],
                "approved_by": req_eval["approved_by"],
                "missing_reviewers": req_eval["missing_reviewers"],
                "minimum_approval_met": req_eval["minimum_approval_met"],
            }
        )
        evidence_gaps.append(
            {
                "policy_id": policy.policy_id,
                "required_evidence": req_eval["required_evidence"],
                "missing_evidence": req_eval["missing_evidence"],
            }
        )
        explanations.append(
            {
                "policy_id": policy.policy_id,
                "summary": explanation,
                "matched_conditions": matched_conditions,
                "matched_constraints": matched_constraints,
                "unmet_requirements": unmet_requirements,
            }
        )
        policy_results.append(
            {
                "policy_id": policy.policy_id,
                "applicable": applies,
                "triggered": triggered_policy,
                "outcome": outcome,
                "matched_conditions": matched_conditions,
                "matched_constraints": matched_constraints,
                "unmet_requirements": unmet_requirements,
                "missing_evidence": req_eval["missing_evidence"],
                "approval_requirements": {
                    "required_reviewers": req_eval["required_reviewers"],
                    "minimum_approval_count": req_eval["minimum_approval_count"],
                    "missing_reviewers": req_eval["missing_reviewers"],
                    "minimum_approval_met": req_eval["minimum_approval_met"],
                },
                "obligations": list(policy.obligations),
                "explanation": explanation,
            }
        )

    final_outcome = _choose_final_outcome(outcomes)
    return PolicyEvaluationResult(
        applicable_policies=sorted(set(applicable)),
        triggered_policies=sorted(set(triggered)),
        final_outcome=final_outcome,
        reasons=sorted(set(item for item in reasons if item)),
        required_actions=sorted(set(item for item in required_actions if item)),
        obligations=sorted(set(item for item in obligations if item)),
        approval_requirements=approval_requirements,
        evidence_gaps=evidence_gaps,
        explanations=explanations,
        policy_results=policy_results,
    )
