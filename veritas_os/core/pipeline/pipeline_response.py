# veritas_os/core/pipeline_response.py
# -*- coding: utf-8 -*-
"""
Pipeline response assembly stage.

Builds the final response dict from :class:`PipelineContext` and
coerces it to DecideResponse.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

try:
    from pydantic import ValidationError as _PydanticValidationError
except ImportError:  # pragma: no cover - pydantic is optional at core layer
    _PydanticValidationError = None  # type: ignore[assignment,misc]

from .pipeline_types import PipelineContext
from .pipeline_evidence import _norm_evidence_item, _dedupe_evidence
from .pipeline_helpers import _warn
from veritas_os.core.decision_semantics import (
    build_required_evidence_profile,
    canonicalize_public_gate_decision,
    derive_gate_decision_from_stop_reasons,
    get_required_evidence_profiles,
    normalize_required_evidence_keys_with_diagnostics,
    normalize_required_evidence_keys,
    unique_preserve_order,
    validate_gate_business_combination,
)
from veritas_os.core.pipeline.governance_layers import (
    assemble_governance_public_fields,
    evaluate_governance_layers,
)
from veritas_os.core.lineage_transition_refusal import (
    evaluate_execution_intent_transition,
)
from veritas_os.observability.metrics import record_required_evidence_telemetry

logger = logging.getLogger(__name__)

# Top-level /v1/decide response groups.
# These constants document the payload layering without changing runtime behavior.
CORE_DECISION_FIELDS = (
    "ok",
    "error",
    "request_id",
    "query",
    "chosen",
    "alternatives",
    "evidence",
    "critique",
    "debate",
    "telos_score",
    "fuji",
    "gate",
    "values",
    "persona",
    "version",
    "decision_status",
    "rejection_reason",
)

AUDIT_DEBUG_INTERNAL_FIELDS = (
    "extras",
    "plan",
    "planner",
    "trust_log",
    "memory_citations",
    "memory_used_count",
    "governance_identity",
)

BACKWARD_COMPAT_FIELDS = (
    "options",
)

ACTION_CANDIDATE_WEIGHTS = {
    "expected_value": 0.35,
    "risk_reduction": 0.30,
    "urgency": 0.20,
    "cost": 0.10,
    "dependency": 0.05,
}

AML_KYC_PROFILE_ENFORCEMENT_KEYS = {
    "kyc_profile",
    "sanctions_screening_trace",
    "pep_screening_result",
    "source_of_funds_record",
}


def _derive_actionability_fields(
    *,
    gate_decision: str,
    business_decision: str,
    human_review_required: bool,
    next_action: str,
    bind_outcome: Any,
    bind_receipt_id: Any,
    execution_intent_id: Any,
) -> Dict[str, Any]:
    """Derive explicit reviewable-vs-actionable boundary fields."""
    normalized_outcome = str(bind_outcome or "").strip().upper()
    normalized_bind_receipt_id = str(bind_receipt_id or "").strip() or None
    normalized_execution_intent_id = str(execution_intent_id or "").strip() or None
    has_bound_lineage = (
        normalized_outcome == "COMMITTED"
        and normalized_bind_receipt_id is not None
        and normalized_execution_intent_id is not None
    )
    implies_execution = next_action in {
        "EXECUTE_WITH_STANDARD_MONITORING",
        "RUN_TARGETED_VALIDATION_CHECKS",
    }

    if gate_decision == "block" or business_decision == "DENY":
        status = "blocked"
        requires_bind = False
    elif human_review_required or gate_decision == "human_review_required":
        status = "human_review_required"
        requires_bind = True
    elif has_bound_lineage:
        status = "actionable_after_bind"
        requires_bind = False
    elif implies_execution or business_decision == "APPROVE":
        status = "bind_required_before_execution"
        requires_bind = True
    else:
        status = "reviewable_only"
        requires_bind = True

    warning = None
    if requires_bind:
        warning = (
            "Decision is reviewable only; bind receipt is required before "
            "execution permission."
        )

    return {
        "actionability_status": status,
        "requires_bind_before_execution": requires_bind,
        "bound_execution_intent_id": normalized_execution_intent_id if has_bound_lineage else None,
        "bind_receipt_id": normalized_bind_receipt_id,
        "execution_intent_id": normalized_execution_intent_id,
        "unbound_execution_warning": warning,
    }




def _apply_structural_transition_refusal_actionability(core: Dict[str, Any]) -> None:
    """Normalize actionability fields for pre-bind formation transition refusal.

    A structurally refused transition indicates the artifact never reached bind
    eligibility. This must not be represented as bind-retry/actionable-after-bind.
    """
    core["actionability_status"] = "formation_transition_refused"
    core["requires_bind_before_execution"] = False
    core["unbound_execution_warning"] = (
        "ExecutionIntent cannot be constructed from a non-promotable "
        "pre-bind formation lineage."
    )
    core["actionability_block_reason"] = "FORMATION_TRANSITION_REFUSED"
    core["actionability_refusal_type"] = "pre_bind_formation_transition_refusal"
    core["business_decision"] = "HOLD"
    core["next_action"] = "RECONSTRUCT_FROM_ELIGIBLE_FORMATION_LINEAGE"
    core["human_review_required"] = True
    core["recovery_action"] = "RECONSTRUCT_FROM_ELIGIBLE_FORMATION_LINEAGE"
    core["recovery_reason"] = (
        "The refused artifact is not bind-retryable; reconstruct the decision "
        "from an eligible formation lineage."
    )
    core["action_selection"] = {
        "evaluation_axes": [
            "formation_eligibility",
            "lineage_reconstruction",
            "operator_review",
        ],
        "selected": {
            "action": "RECONSTRUCT_FROM_ELIGIBLE_FORMATION_LINEAGE",
            "expected_value": 0.0,
            "risk_reduction": 1.0,
            "cost": 0.4,
            "dependency": 0.6,
            "urgency": 0.9,
            "score": 1.0,
            "reason": (
                "Formation transition refusal is not bind-retryable; "
                "reconstruct from an eligible lineage."
            ),
        },
        "candidates_considered": 1,
    }
    core["refusal_reason"] = (
        "FORMATION_TRANSITION_REFUSED: ExecutionIntent cannot be constructed "
        "from a non-promotable pre-bind formation lineage."
    )
    rationale = str(core.get("rationale") or "").strip()
    formation_rationale = (
        "FORMATION_TRANSITION_REFUSED: ExecutionIntent cannot be constructed "
        "from a non-promotable pre-bind formation lineage."
    )
    if rationale:
        if "FORMATION_TRANSITION_REFUSED" not in rationale:
            core["rationale"] = f"{rationale} | {formation_rationale}"
    else:
        core["rationale"] = formation_rationale

def _is_dev_mode_enabled(context: Dict[str, Any]) -> bool:
    """Return whether action-candidate diagnostics should be exposed."""
    explicit_flag = context.get("dev_mode") or context.get("debug")
    if isinstance(explicit_flag, bool):
        return explicit_flag
    env_value = str(os.getenv("VERITAS_DEV_MODE", "")).strip().lower()
    return env_value in {"1", "true", "yes", "on"}


def _calc_action_score(candidate: Dict[str, Any]) -> float:
    """Compute a weighted score for an action candidate."""
    score = (
        ACTION_CANDIDATE_WEIGHTS["expected_value"] * float(candidate["expected_value"])
        + ACTION_CANDIDATE_WEIGHTS["risk_reduction"] * float(candidate["risk_reduction"])
        + ACTION_CANDIDATE_WEIGHTS["urgency"] * float(candidate["urgency"])
        - ACTION_CANDIDATE_WEIGHTS["cost"] * float(candidate["cost"])
        - ACTION_CANDIDATE_WEIGHTS["dependency"] * float(candidate["dependency"])
    )
    return round(score, 4)


def _make_action_candidate(
    *,
    action: str,
    expected_value: float,
    risk_reduction: float,
    cost: float,
    dependency: float,
    urgency: float,
    reason: str,
) -> Dict[str, Any]:
    """Build one ranked action candidate entry."""
    candidate = {
        "action": action,
        "expected_value": round(expected_value, 4),
        "risk_reduction": round(risk_reduction, 4),
        "cost": round(cost, 4),
        "dependency": round(dependency, 4),
        "urgency": round(urgency, 4),
        "reason": reason,
    }
    candidate["score"] = _calc_action_score(candidate)
    return candidate


def _rank_action_candidates(
    *,
    gate_decision: str,
    business_decision: str,
    stop_reasons: List[str],
    missing_evidence: List[str],
    human_review_required: bool,
    context: Dict[str, Any],
    value_total: float,
) -> List[Dict[str, Any]]:
    """Return sorted action candidates aligned to FUJI gate constraints.

    Candidate scoring remains rule-based but adapts to:
    - governance stop reasons (fail-closed conditions),
    - dependency/urgency context hints, and
    - Value Core aggregate score (`value_total`).
    """
    if gate_decision == "block":
        candidates = [
            _make_action_candidate(
                action="DO_NOT_EXECUTE",
                expected_value=0.78,
                risk_reduction=0.98,
                cost=0.05,
                dependency=0.02,
                urgency=0.97,
                reason="FUJI gate is BLOCK; safest high-value action is to halt execution.",
            ),
            _make_action_candidate(
                action="ESCALATE_POLICY_EXCEPTION_REVIEW",
                expected_value=0.52,
                risk_reduction=0.75,
                cost=0.34,
                dependency=0.65,
                urgency=0.84,
                reason="Policy exception path may recover value but needs human/process dependencies.",
            ),
            _make_action_candidate(
                action="COLLECT_REQUIRED_EVIDENCE",
                expected_value=0.40,
                risk_reduction=0.62,
                cost=0.46,
                dependency=0.48,
                urgency=0.70,
                reason="Additional evidence can support later re-assessment without executing now.",
            ),
        ]
    elif business_decision == "REVIEW_REQUIRED":
        candidates = [
            _make_action_candidate(
                action="PREPARE_HUMAN_REVIEW_PACKET",
                expected_value=0.74,
                risk_reduction=0.88,
                cost=0.22,
                dependency=0.44,
                urgency=0.86,
                reason="Boundary ambiguity requires rapid preparation for reviewer adjudication.",
            ),
            _make_action_candidate(
                action="COLLECT_REQUIRED_EVIDENCE",
                expected_value=0.68,
                risk_reduction=0.80,
                cost=0.31,
                dependency=0.36,
                urgency=0.79,
                reason="Evidence strengthens review quality and reduces rework during adjudication.",
            ),
            _make_action_candidate(
                action="ROUTE_TO_HUMAN_REVIEW",
                expected_value=0.66,
                risk_reduction=0.83,
                cost=0.28,
                dependency=0.50,
                urgency=0.82,
                reason="Formal human handoff aligns with gate constraints and governance policy.",
            ),
        ]
    elif business_decision in {"HOLD", "EVIDENCE_REQUIRED", "POLICY_DEFINITION_REQUIRED"}:
        candidates = [
            _make_action_candidate(
                action="COLLECT_REQUIRED_EVIDENCE",
                expected_value=0.76 if missing_evidence else 0.64,
                risk_reduction=0.84,
                cost=0.24,
                dependency=0.30,
                urgency=0.83,
                reason="Missing evidence is the shortest path to unlock the decision safely.",
            ),
            _make_action_candidate(
                action="REVISE_AND_RESUBMIT",
                expected_value=0.62,
                risk_reduction=0.70,
                cost=0.38,
                dependency=0.42,
                urgency=0.72,
                reason="Plan revision may unblock policy-fit gaps but has wider rework cost.",
            ),
            _make_action_candidate(
                action="DEFINE_POLICY_AND_REASSESS",
                expected_value=0.58 if "rule_undefined" in stop_reasons else 0.44,
                risk_reduction=0.64,
                cost=0.52,
                dependency=0.66,
                urgency=0.69,
                reason="Policy work is valuable when rules are undefined but heavier operationally.",
            ),
        ]
    else:
        candidates = [
            _make_action_candidate(
                action="EXECUTE_WITH_STANDARD_MONITORING",
                expected_value=0.83,
                risk_reduction=0.47,
                cost=0.22,
                dependency=0.18,
                urgency=0.75,
                reason="Gate permits proceed; monitored execution captures value with bounded risk.",
            ),
            _make_action_candidate(
                action="RUN_TARGETED_VALIDATION_CHECKS",
                expected_value=0.60,
                risk_reduction=0.71,
                cost=0.33,
                dependency=0.26,
                urgency=0.64,
                reason="Targeted checks reduce tail risk but delay immediate value realization.",
            ),
        ]
    normalized_value_total = min(1.0, max(0.0, float(value_total)))
    dependency_penalty = 0.08 if bool(context.get("critical_dependency_pending")) else 0.0
    urgency_boost = 0.06 if bool(context.get("urgency_high")) else 0.0
    for candidate in candidates:
        if candidate["action"] == "EXECUTE_WITH_STANDARD_MONITORING":
            if human_review_required or "high_risk_ambiguity" in stop_reasons:
                candidate["risk_reduction"] = min(1.0, candidate["risk_reduction"] + 0.22)
                candidate["expected_value"] = max(0.0, candidate["expected_value"] - 0.28)
        if candidate["action"] == "COLLECT_REQUIRED_EVIDENCE" and missing_evidence:
            candidate["expected_value"] = min(1.0, candidate["expected_value"] + 0.10)
            candidate["urgency"] = min(1.0, candidate["urgency"] + 0.08)
        if candidate["action"] in {"PREPARE_HUMAN_REVIEW_PACKET", "ROUTE_TO_HUMAN_REVIEW"}:
            if human_review_required:
                candidate["expected_value"] = min(1.0, candidate["expected_value"] + 0.08)
                candidate["risk_reduction"] = min(1.0, candidate["risk_reduction"] + 0.05)
        if dependency_penalty > 0.0 and candidate["action"] in {
            "ESCALATE_POLICY_EXCEPTION_REVIEW",
            "DEFINE_POLICY_AND_REASSESS",
            "ROUTE_TO_HUMAN_REVIEW",
        }:
            candidate["dependency"] = min(1.0, candidate["dependency"] + dependency_penalty)
        if urgency_boost > 0.0:
            candidate["urgency"] = min(1.0, candidate["urgency"] + urgency_boost)
        if normalized_value_total <= 0.40:
            candidate["expected_value"] = max(0.0, candidate["expected_value"] - 0.04)
            candidate["risk_reduction"] = min(1.0, candidate["risk_reduction"] + 0.03)
        candidate["score"] = _calc_action_score(candidate)
    return sorted(candidates, key=lambda item: item["score"], reverse=True)


def _build_question_first_answer(
    *,
    query: str,
    required_evidence: List[str],
    missing_evidence: List[str],
    stop_reasons: List[str],
) -> Dict[str, Any] | None:
    """Return a structured answer when the user asks condition/evidence questions."""
    query_lower = (query or "").strip().lower()
    if not query_lower:
        return None
    asks_minimum = any(token in query_lower for token in ("最低条件", "minimum", "必須条件"))
    asks_boundary = any(token in query_lower for token in ("境界条件", "boundary"))
    asks_review = any(token in query_lower for token in ("人手審査", "human review", "manual review"))
    asks_evidence = any(
        token in query_lower for token in ("必要証拠", "必要な証拠", "required evidence", "evidence")
    )
    asks_sanctions = any(token in query_lower for token in ("sanctions", "制裁", "一致"))
    asks_sof = any(
        token in query_lower for token in ("source of funds", "source_of_funds", "資金源", "funds")
    )
    if not (asks_minimum or asks_boundary or asks_evidence or asks_review or asks_sanctions or asks_sof):
        return None
    stop_reason_set = sorted(set(stop_reasons))
    return {
        "minimum_conditions": {
            "required_evidence_count": len(required_evidence),
            "missing_evidence_count": len(missing_evidence),
            "all_required_evidence_ready": len(missing_evidence) == 0,
        },
        "boundary_conditions": {
            "stop_reasons": stop_reason_set,
            "has_policy_boundary_risk": any(
                item in {"rule_undefined", "approval_boundary_unknown", "rollback_not_supported"}
                for item in stop_reasons
            ),
        },
        "review_boundary": {
            "human_review_triggered": any(
                item in {"approval_boundary_unknown", "high_risk_ambiguity"}
                for item in stop_reasons
            ),
        },
        "sanctions_controls": {
            "must_hold_or_review": "high_risk_ambiguity" in stop_reasons or bool(missing_evidence),
            "stop_reasons": [
                item for item in stop_reason_set if item in {"high_risk_ambiguity", "required_evidence_missing"}
            ],
        },
        "source_of_funds_controls": {
            "source_of_funds_missing": "source_of_funds_record" in set(missing_evidence),
            "required_before_approval": "source_of_funds_record" in set(required_evidence),
        },
        "required_evidence": required_evidence,
        "missing_evidence": missing_evidence,
        "next_action_hint": "Gather missing evidence first, then route to review if boundary ambiguity remains.",
    }


def _as_string_list(value: Any) -> list[str]:
    """Normalize arbitrary values to a list[str] for public response fields."""
    if isinstance(value, list):
        return [str(item).strip().lower() for item in value if str(item).strip()]
    return []


def _is_falsey_flag(value: Any) -> bool:
    """Return True when a context flag explicitly indicates missing readiness."""
    if isinstance(value, bool):
        return value is False
    if isinstance(value, str):
        normalized = value.strip().lower()
        return normalized in {"0", "false", "no", "off", "missing", "unknown", "undefined"}
    return False


def _extract_stop_reasons(
    *,
    gate_reason: str,
    missing_evidence: List[str],
    context: Dict[str, Any],
) -> List[str]:
    """Collect fail-closed stop reasons used for gate decision classification."""
    reasons: List[str] = []
    reason_lc = gate_reason.lower()
    env_name = str(context.get("environment") or os.getenv("VERITAS_ENV", "")).lower()
    secure_or_prod = env_name in {"secure", "prod", "production"}

    if missing_evidence:
        reasons.append("required_evidence_missing")
    if ("policy_definition_required" in reason_lc) or _is_falsey_flag(context.get("rule_defined")):
        reasons.append("rule_undefined")
    if _is_falsey_flag(context.get("approval_boundary_defined")):
        reasons.append("approval_boundary_unknown")
    if _is_falsey_flag(context.get("audit_trail_complete")):
        reasons.append("audit_trail_incomplete")
    if _is_falsey_flag(context.get("rollback_supported")):
        reasons.append("rollback_not_supported")
    if bool(context.get("irreversible_action")):
        reasons.append("irreversible_action")
    if _is_falsey_flag(context.get("secure_controls_ready")):
        reasons.append("secure_controls_missing")
    if secure_or_prod and _is_falsey_flag(context.get("production_controls_ready")):
        reasons.append("secure_prod_controls_missing")
    try:
        context_risk_score = float(context.get("risk_score", 0.0) or 0.0)
    except (TypeError, ValueError):
        context_risk_score = 0.0
    if bool(context.get("high_risk_ambiguity")) or (
        bool(context.get("ambiguity_detected")) and context_risk_score >= 0.8
    ):
        reasons.append("high_risk_ambiguity")
    if bool(context.get("sanctions_partial_match")):
        reasons.append("sanctions_partial_match")

    return reasons


def _build_required_evidence_telemetry(
    *,
    decision_domain: str,
    template_id: str,
    source: str,
    mode: str,
    required_diagnostics: Dict[str, Any],
    satisfied_diagnostics: Dict[str, Any],
    unknown_keys: List[str],
    profile_missing_keys: List[str],
) -> Dict[str, Any]:
    """Build required-evidence telemetry counters for warning-first rollout."""
    normalization_total = len(unknown_keys) + len(profile_missing_keys)
    alias_hits = int(required_diagnostics.get("alias_normalized_count", 0)) + int(
        satisfied_diagnostics.get("alias_normalized_count", 0)
    )
    denominator = max(1, normalization_total + alias_hits)
    return {
        "domain": decision_domain or "unknown",
        "template_id": template_id or "unknown",
        "source": source or "unknown",
        "mode": mode or "warn",
        "unknown_required_evidence_key_total": len(unknown_keys),
        "required_evidence_alias_normalized_total": alias_hits,
        "required_evidence_profile_miss_total": len(profile_missing_keys),
        "top_unknown_keys": unknown_keys[:5],
        "profile_missing_keys": profile_missing_keys,
        "required_evidence_normalization_hit_rate": round(alias_hits / denominator, 4),
    }


def _should_enforce_aml_kyc_profile(
    decision_domain: str,
    profile_required_keys: List[str],
    required_evidence: List[str],
    template_id: str,
    mode: str,
) -> bool:
    """Return whether AML/KYC full profile strictness should be applied.

    Enforcement is intentionally scoped to avoid unexpected false-fail regressions
    in non-beachhead AML/KYC-adjacent templates:
    - always on for strict mode experiments,
    - always on for beachhead template id,
    - on when the incoming required evidence already includes beachhead anchors.
    """
    if decision_domain != "aml_kyc":
        return False
    if not profile_required_keys:
        return False
    if mode == "strict":
        return True
    if template_id == "aml_kyc_high_risk_country_wire_manual_review":
        return True
    return bool(AML_KYC_PROFILE_ENFORCEMENT_KEYS & set(required_evidence))


def _resolve_required_evidence_mode(context: Dict[str, Any], decision_domain: str) -> str:
    """Resolve required evidence hardening mode for runtime behavior."""
    raw_mode = str(
        context.get("required_evidence_mode")
        or os.getenv("VERITAS_REQUIRED_EVIDENCE_MODE", "warn")
    ).strip().lower()
    mode = "strict" if raw_mode == "strict" else "warn"
    if mode == "strict" and decision_domain != "aml_kyc":
        return "warn"
    return mode


def _derive_business_fields(ctx: PipelineContext) -> Dict[str, Any]:
    """Derive public decision semantics from internal gate outputs.

    This helper separates:
    - gate_decision: safety gate outcome (allow/hold/deny...)
    - business_decision: case lifecycle status (APPROVE/HOLD/...)
    - next_action: operator/system action guidance
    """
    raw_gate_decision = str(
        ctx.fuji_dict.get("decision_status")
        or ctx.fuji_dict.get("status")
        or ctx.decision_status
        or "unknown"
    ).lower()
    gate_reason = str(ctx.rejection_reason or ctx.fuji_dict.get("rejection_reason") or "").strip()
    decision_domain = str(
        ctx.context.get("decision_domain")
        or ctx.context.get("category")
        or ""
    ).strip().lower()
    template_id = str(ctx.context.get("template_id") or "").strip()
    source = str(ctx.context.get("source") or "").strip()
    required_evidence_input = unique_preserve_order(
        _as_string_list(ctx.context.get("required_evidence"))
    )
    satisfied_evidence_input = unique_preserve_order(
        _as_string_list(ctx.context.get("satisfied_evidence"))
    )
    required_normalized, required_diag = normalize_required_evidence_keys_with_diagnostics(
        required_evidence_input
    )
    satisfied_normalized, satisfied_diag = normalize_required_evidence_keys_with_diagnostics(
        satisfied_evidence_input
    )
    required_evidence = unique_preserve_order(required_normalized)
    satisfied_evidence = unique_preserve_order(satisfied_normalized)
    profiles = get_required_evidence_profiles()
    domain_profile = profiles.get(decision_domain, {})
    profile_required_keys = unique_preserve_order(
        normalize_required_evidence_keys(domain_profile.get("required"))
    )
    profile_escalation_sensitive_keys = unique_preserve_order(
        normalize_required_evidence_keys(domain_profile.get("escalation_sensitive"))
    )
    profile_canonical_key_list = unique_preserve_order(
        normalize_required_evidence_keys(domain_profile.get("canonical_key_list"))
    )
    mode = _resolve_required_evidence_mode(ctx.context, decision_domain)
    enforce_profile = _should_enforce_aml_kyc_profile(
        decision_domain,
        profile_required_keys,
        required_evidence,
        template_id,
        mode,
    )
    profile_missing_keys = (
        [key for key in profile_required_keys if key not in set(required_evidence)]
        if enforce_profile
        else []
    )
    if enforce_profile:
        required_evidence = unique_preserve_order(required_evidence + profile_required_keys)
    unknown_keys = unique_preserve_order(
        list(required_diag.get("unknown_keys", []))
        + list(satisfied_diag.get("unknown_keys", []))
    )
    satisfied_canonical = set(satisfied_evidence)
    missing_evidence = [item for item in required_evidence if item not in satisfied_canonical]

    fuji_status = str(ctx.fuji_dict.get("status") or "").lower()
    try:
        risk_score = float(ctx.context.get("risk_score", ctx.fuji_dict.get("risk", 0.0)) or 0.0)
    except (TypeError, ValueError):
        risk_score = 0.0
    human_review_required = bool(
        ctx.context.get("human_review_required")
        or fuji_status == "needs_human_review"
    )
    stop_reasons = _extract_stop_reasons(
        gate_reason=gate_reason,
        missing_evidence=missing_evidence,
        context=ctx.context,
    )
    escalation_sensitive_missing = [
        key for key in profile_escalation_sensitive_keys if key not in satisfied_canonical
    ]
    internal_evidence_reasons: list[str] = []
    if unknown_keys:
        if mode == "strict":
            internal_evidence_reasons.append("unknown_required_evidence_key_strict")
            human_review_required = True
            stop_reasons.append("unknown_required_evidence_key")
        else:
            internal_evidence_reasons.append("unknown_required_evidence_key_warn")
    if profile_missing_keys:
        if mode == "strict":
            internal_evidence_reasons.append("required_evidence_profile_miss_strict")
            human_review_required = True
            stop_reasons.append("required_evidence_profile_miss")
        else:
            internal_evidence_reasons.append("required_evidence_profile_miss_warn")
    if escalation_sensitive_missing:
        human_review_required = True
        stop_reasons.append("escalation_sensitive_evidence_missing")
        internal_evidence_reasons.append("escalation_sensitive_evidence_missing")

    gate_decision, human_review_required = derive_gate_decision_from_stop_reasons(
        stop_reasons=stop_reasons,
        raw_gate_decision=raw_gate_decision,
        decision_status=str(ctx.decision_status).lower(),
        risk_score=risk_score,
        human_review_required=human_review_required,
    )
    gate_decision = canonicalize_public_gate_decision(gate_decision)

    if missing_evidence:
        business_decision = "EVIDENCE_REQUIRED"
    elif gate_decision == "block":
        business_decision = "DENY"
    elif gate_decision == "human_review_required":
        business_decision = "REVIEW_REQUIRED"
    elif gate_decision == "hold":
        business_decision = "HOLD"
    elif "policy_definition_required" in gate_reason.lower():
        business_decision = "POLICY_DEFINITION_REQUIRED"
    else:
        business_decision = "APPROVE"
    validate_gate_business_combination(
        gate_decision=gate_decision,
        business_decision=business_decision,
        human_review_required=human_review_required,
    )

    action_candidates = _rank_action_candidates(
        gate_decision=gate_decision,
        business_decision=business_decision,
        stop_reasons=stop_reasons,
        missing_evidence=missing_evidence,
        human_review_required=human_review_required,
        context=ctx.context,
        value_total=float(ctx.values_payload.get("total", 0.0) or 0.0),
    )
    selected_candidate = action_candidates[0]
    next_action = selected_candidate["action"]
    next_action_reason = selected_candidate["reason"]
    rationale_parts = [gate_reason] if gate_reason else []
    if stop_reasons:
        rationale_parts.append(f"stop_reasons={', '.join(sorted(set(stop_reasons)))}")
    if not rationale_parts:
        rationale_parts.append("Decision derived from FUJI gate outcome and available evidence.")
    rationale_parts.append(f"next_action_reason={next_action_reason}")
    if len(action_candidates) > 1:
        score_gap = round(
            float(selected_candidate["score"]) - float(action_candidates[1]["score"]),
            4,
        )
        rationale_parts.append(f"next_action_score_gap={score_gap}")

    structured_answer = _build_question_first_answer(
        query=ctx.query,
        required_evidence=required_evidence,
        missing_evidence=missing_evidence,
        stop_reasons=stop_reasons,
    )
    refusal_reason = "; ".join(rationale_parts) if gate_decision == "block" else None
    result = {
        "gate_decision": gate_decision,
        "business_decision": business_decision,
        "next_action": next_action,
        "required_evidence": required_evidence,
        "missing_evidence": missing_evidence,
        "satisfied_evidence": satisfied_evidence,
        "required_evidence_profile": build_required_evidence_profile(
            required_evidence,
            decision_domain=decision_domain,
        ),
        "required_evidence_telemetry": _build_required_evidence_telemetry(
            decision_domain=decision_domain,
            template_id=template_id,
            source=source,
            mode=mode,
            required_diagnostics=required_diag,
            satisfied_diagnostics=satisfied_diag,
            unknown_keys=unknown_keys,
            profile_missing_keys=(
                profile_missing_keys + escalation_sensitive_missing
            ),
        ),
        "required_evidence_mode": mode,
        "required_evidence_assessment": {
            "profile_id": str(domain_profile.get("profile_id") or ""),
            "profile_version": str(domain_profile.get("profile_version") or ""),
            "profile_canonical_key_list": profile_canonical_key_list,
            "internal_reasons": unique_preserve_order(internal_evidence_reasons),
            "profile_missing_required_keys": profile_missing_keys,
            "escalation_sensitive_missing_keys": escalation_sensitive_missing,
        },
        "human_review_required": human_review_required,
        "rationale": " | ".join(rationale_parts),
        "refusal_reason": refusal_reason,
        "action_selection": {
            "evaluation_axes": [
                "expected_value",
                "risk_reduction",
                "cost",
                "dependency",
                "urgency",
            ],
            "selected": selected_candidate,
            "candidates_considered": len(action_candidates),
        },
    }
    raw_payload = ctx.raw if isinstance(ctx.raw, dict) else {}
    result.update(
        _derive_actionability_fields(
            gate_decision=gate_decision,
            business_decision=business_decision,
            human_review_required=human_review_required,
            next_action=next_action,
            bind_outcome=raw_payload.get("bind_outcome"),
            bind_receipt_id=raw_payload.get("bind_receipt_id"),
            execution_intent_id=raw_payload.get("execution_intent_id"),
        )
    )
    if structured_answer is not None:
        result["structured_answer"] = structured_answer
    if unknown_keys:
        logger.warning(
            "required-evidence unknown keys observed: domain=%s template_id=%s keys=%s",
            decision_domain or "unknown",
            template_id or "unknown",
            unknown_keys,
        )
        result.setdefault("warnings", []).append(
            "unknown_required_evidence_keys_detected"
        )
    if profile_missing_keys:
        logger.warning(
            "required-evidence profile miss: domain=%s template_id=%s missing=%s",
            decision_domain or "unknown",
            template_id or "unknown",
            profile_missing_keys,
        )
        result.setdefault("warnings", []).append(
            "required_evidence_profile_missing_keys"
        )
    if escalation_sensitive_missing:
        result.setdefault("warnings", []).append(
            "escalation_sensitive_required_evidence_missing"
        )
    telemetry = result["required_evidence_telemetry"]
    record_required_evidence_telemetry(
        domain=telemetry.get("domain"),
        template_id=telemetry.get("template_id"),
        source=telemetry.get("source"),
        mode=telemetry.get("mode"),
        unknown_key_total=int(telemetry.get("unknown_required_evidence_key_total", 0)),
        alias_normalized_total=int(
            telemetry.get("required_evidence_alias_normalized_total", 0)
        ),
        profile_miss_total=int(
            telemetry.get("required_evidence_profile_miss_total", 0)
        ),
    )
    if _is_dev_mode_enabled(ctx.context):
        result["action_candidates"] = action_candidates
        result["action_selection"]["ranking_trace"] = {
            "weights": dict(ACTION_CANDIDATE_WEIGHTS),
            "ordered_actions": [
                {
                    "action": item["action"],
                    "score": item["score"],
                }
                for item in action_candidates
            ],
            "stop_reasons": sorted(set(stop_reasons)),
        }
    else:
        result["action_candidates"] = []
    return result


def _build_response_layers(
    ctx: PipelineContext,
    *,
    load_persona_fn: Any,
    plan: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    """Build grouped payload layers for readability and maintenance.

    Layering is documentation-oriented: callers still receive one flat dict.
    """
    governance_snapshot = evaluate_governance_layers(
        participation_signal=ctx.response_extras.get("participation_signal")
    )

    core = {
        "ok": True,
        "error": None,
        "request_id": ctx.request_id,
        "query": ctx.query,
        "chosen": ctx.chosen,
        "alternatives": ctx.alternatives,
        "evidence": ctx.evidence,
        "critique": ctx.critique,
        "debate": ctx.debate,
        "telos_score": float(ctx.telos),
        "fuji": ctx.fuji_dict,
        "gate": {
            "risk": float(ctx.effective_risk),
            "telos_score": float(ctx.telos),
            "decision_status": ctx.decision_status,
            "reason": ctx.rejection_reason,
            "modifications": ctx.modifications,
        },
        "values": ctx.values_payload,
        "persona": load_persona_fn(),
        "version": os.getenv("VERITAS_API_VERSION", "veritas-api 1.x"),
        "decision_status": ctx.decision_status,
        "rejection_reason": ctx.rejection_reason,
    }
    core.update(assemble_governance_public_fields(governance_snapshot))
    core.update(_derive_business_fields(ctx))
    transition = evaluate_execution_intent_transition(
        lineage_promotability=core.get("lineage_promotability"),
    )
    if transition.get("transition_status") == "structurally_refused":
        core["execution_intent_id"] = None
        core["bound_execution_intent_id"] = None
        core["bind_receipt_id"] = None
        core["bind_receipt"] = None
        _apply_structural_transition_refusal_actionability(core)
        core["transition_refusal"] = transition
    else:
        core["transition_refusal"] = None

    audit_debug_internal = {
        "extras": ctx.response_extras,
        "memory_citations": ctx.response_extras.get("memory_citations", []),
        "memory_used_count": ctx.response_extras.get("memory_used_count", 0),
        "plan": plan,
        "planner": ctx.response_extras.get("planner", {"steps": [], "raw": None, "source": "fallback"}),
        "trust_log": ctx.raw.get("trust_log") if isinstance(ctx.raw, dict) else None,
        "governance_identity": ctx.governance_identity,
    }

    backward_compat = {
        # Legacy alias kept for historical clients; mirrors alternatives.
        "options": list(ctx.alternatives),
    }
    return {
        "core": core,
        "audit_debug_internal": audit_debug_internal,
        "backward_compat": backward_compat,
    }


def assemble_response(
    ctx: PipelineContext,
    *,
    load_persona_fn: Any,
    plan: Dict[str, Any],
) -> Dict[str, Any]:
    """Build the DecideResponse‑compatible dict from pipeline context."""
    layers = _build_response_layers(ctx, load_persona_fn=load_persona_fn, plan=plan)
    # Flattened payload keeps pre-existing top-level contract/shape for clients.
    res: Dict[str, Any] = {}
    res.update(layers["core"])
    res.update(layers["audit_debug_internal"])
    res.update(layers["backward_compat"])

    # Continuation runtime shadow output (flag on only; omitted entirely when off)
    if ctx.continuation_snapshot is not None and ctx.continuation_receipt is not None:
        _cont_data: Dict[str, Any] = {
            "state": ctx.continuation_snapshot,
            "receipt": ctx.continuation_receipt,
        }
        if ctx.continuation_enforcement_events:
            _cont_data["enforcement_events"] = ctx.continuation_enforcement_events
        if ctx.continuation_enforcement_halt:
            _cont_data["enforcement_halt"] = True
        res["continuation"] = _cont_data

    return res


def coerce_to_decide_response(
    res: Dict[str, Any],
    *,
    DecideResponse: Any,
) -> Dict[str, Any]:
    """Coerce dict to DecideResponse model (best‑effort)."""
    _exc_types: tuple = (ValueError, TypeError)
    if _PydanticValidationError is not None:
        _exc_types = (ValueError, TypeError, _PydanticValidationError)
    try:
        payload = DecideResponse.model_validate(res).model_dump()
    except _exc_types as e:
        _warn(f"[model] decide response coerce: {e}")
        payload = res
    return payload


def finalize_evidence(
    payload: Dict[str, Any],
    *,
    web_evidence: Any,
    evidence_max: int,
) -> None:
    """Ensure evidence survives later overwrites, dedupe and cap."""
    try:
        payload_evidence = payload.get("evidence", None)
        if not isinstance(payload_evidence, list):
            try:
                payload_evidence = list(payload_evidence or [])
            except (KeyError, TypeError, AttributeError):
                payload_evidence = []

        if len(payload_evidence) == 0:
            evidence = payload.get("_pipeline_evidence")
            if isinstance(evidence, list) and evidence:
                payload_evidence = list(evidence)
            else:
                payload_evidence = []

        existing = set()
        for ev in payload_evidence:
            if not isinstance(ev, dict):
                continue
            existing.add((ev.get("source"), ev.get("uri"), ev.get("title"), ev.get("snippet")))

        for ev in web_evidence or []:
            if not isinstance(ev, dict):
                continue
            k = (ev.get("source"), ev.get("uri"), ev.get("title"), ev.get("snippet"))
            if k not in existing:
                payload_evidence.append(ev)
                existing.add(k)

        payload["evidence"] = payload_evidence
    except (KeyError, TypeError, AttributeError):
        payload["evidence"] = (
            payload.get("evidence") if isinstance(payload.get("evidence"), list) else []
        )

    # normalize / dedupe / cap
    try:
        payload["evidence"] = _dedupe_evidence(
            [ev for ev in (_norm_evidence_item(x) for x in (payload.get("evidence") or [])) if ev]
        )
    except (KeyError, TypeError, AttributeError):
        payload["evidence"] = []

    if isinstance(payload.get("evidence"), list) and len(payload["evidence"]) > evidence_max:
        payload["evidence"] = payload["evidence"][:evidence_max]
