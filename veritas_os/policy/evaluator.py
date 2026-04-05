"""Policy runtime evaluator for compiled Policy-as-Code artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import logging
import math
from typing import Any, Dict, Iterable, List
import re

from .runtime_adapter import RuntimePolicy, RuntimePolicyBundle

logger = logging.getLogger(__name__)

OUTCOME_PRECEDENCE = {
    "allow": 0,
    "require_human_review": 1,
    "escalate": 2,
    "halt": 3,
    "deny": 4,
}

_REGEX_MAX_PATTERN_LENGTH = 256
_REGEX_MAX_TARGET_LENGTH = 1024
_REGEX_NESTED_QUANTIFIER_GUARD = re.compile(
    r"\((?:[^()\\]|\\.)*[+*](?:[^()\\]|\\.)*\)[+*]"
)


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


def _safe_numeric_compare(operator: str, actual: Any, expected: Any) -> bool:
    """Evaluate numeric comparisons with float coercion and error handling."""
    if actual is None:
        return False
    try:
        a = float(actual)
        b = float(expected)
    except (ValueError, TypeError):
        return False
    if not math.isfinite(a) or not math.isfinite(b):
        return False
    if operator == "gt":
        return a > b
    if operator == "gte":
        return a >= b
    if operator == "lt":
        return a < b
    # lte
    return a <= b


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
    if operator in ("gt", "gte", "lt", "lte"):
        return _safe_numeric_compare(operator, actual, expected)
    if operator == "contains":
        if isinstance(actual, str):
            return isinstance(expected, str) and expected in actual
        if isinstance(actual, (list, tuple, set)):
            return expected in actual
        return False
    if operator == "regex":
        return _safe_regex_search(expected, actual)
    logger.warning("unknown operator %r in policy expression (field=%r)", operator, field)
    return False


def _safe_regex_search(expected: Any, actual: Any) -> bool:
    """Evaluate regex expressions with lightweight guardrails for runtime safety."""
    if not isinstance(expected, str) or not isinstance(actual, str):
        return False
    if len(expected) > _REGEX_MAX_PATTERN_LENGTH:
        logger.warning(
            "regex pattern rejected: length %d exceeds limit %d",
            len(expected),
            _REGEX_MAX_PATTERN_LENGTH,
        )
        return False
    if len(actual) > _REGEX_MAX_TARGET_LENGTH:
        logger.warning(
            "regex target rejected: length %d exceeds limit %d",
            len(actual),
            _REGEX_MAX_TARGET_LENGTH,
        )
        return False
    if _REGEX_NESTED_QUANTIFIER_GUARD.search(expected):
        logger.warning(
            "regex pattern rejected: nested quantifier detected in %.50r",
            expected,
        )
        return False

    try:
        compiled = re.compile(expected)
    except re.error as exc:
        logger.warning("regex compilation failed for pattern %.50r: %s", expected, exc)
        return False
    return compiled.search(actual) is not None


def _scope_matches(policy: RuntimePolicy, context: Dict[str, Any]) -> bool:
    domain = context.get("domain")
    route = context.get("route")
    actor = context.get("actor")

    if domain is None or route is None or actor is None:
        missing = [k for k, v in (("domain", domain), ("route", route), ("actor", actor)) if v is None]
        logger.debug(
            "policy %s: scope fields %s absent in context, defaulting to match",
            policy.policy_id,
            missing,
        )

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


def _is_effective(policy: RuntimePolicy, today: date) -> bool:
    """Return True when the policy's effective_date is today or in the past."""
    effective = getattr(policy, "effective_date", None)
    if not effective:
        return True
    try:
        return date.fromisoformat(effective) <= today
    except (ValueError, TypeError):
        return True


def evaluate_runtime_policies(
    runtime_bundle: RuntimePolicyBundle,
    context: Dict[str, Any],
) -> PolicyEvaluationResult:
    """Evaluate adapted runtime policies for a request context."""
    if context is None:
        context = {}
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

    today = date.today()

    for policy in runtime_bundle.runtime_policies:
        if not _is_effective(policy, today):
            logger.debug(
                "policy %s skipped: not yet effective (effective_date=%s)",
                policy.policy_id,
                policy.effective_date,
            )
            continue
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
            outcome = policy.outcome.get("decision", "allow")
            outcome_reason = policy.outcome.get("reason", "")
            explanation = (
                f"{policy.title}: {outcome_reason}"
                if outcome_reason
                else policy.title
            )
            outcomes.append(outcome)
            reasons.append(outcome_reason or policy.title)
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

    logger.info(
        "policy evaluation complete: outcome=%s applicable=%s triggered=%s",
        final_outcome,
        sorted(set(applicable)),
        sorted(set(triggered)),
    )

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
