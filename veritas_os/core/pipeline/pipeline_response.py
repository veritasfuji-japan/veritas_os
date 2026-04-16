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
    canonicalize_gate_decision,
    derive_gate_decision_from_stop_reasons,
    normalize_required_evidence_keys,
    unique_preserve_order,
)

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
    asks_evidence = any(
        token in query_lower for token in ("必要証拠", "必要な証拠", "required evidence", "evidence")
    )
    if not (asks_minimum or asks_boundary or asks_evidence):
        return None
    return {
        "minimum_conditions": {
            "required_evidence_count": len(required_evidence),
            "missing_evidence_count": len(missing_evidence),
            "all_required_evidence_ready": len(missing_evidence) == 0,
        },
        "boundary_conditions": {
            "stop_reasons": sorted(set(stop_reasons)),
            "has_policy_boundary_risk": any(
                item in {"rule_undefined", "approval_boundary_unknown", "rollback_not_supported"}
                for item in stop_reasons
            ),
        },
        "required_evidence": required_evidence,
        "missing_evidence": missing_evidence,
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

    return reasons


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
    required_evidence = unique_preserve_order(_as_string_list(ctx.context.get("required_evidence")))
    satisfied_evidence = unique_preserve_order(_as_string_list(ctx.context.get("satisfied_evidence")))
    satisfied_canonical = set(normalize_required_evidence_keys(satisfied_evidence))
    missing_evidence = []
    for item in required_evidence:
        canonical_item = normalize_required_evidence_keys([item])[0]
        if canonical_item not in satisfied_canonical:
            missing_evidence.append(item)

    fuji_status = str(ctx.fuji_dict.get("status") or "").lower()
    try:
        risk_score = float(ctx.context.get("risk_score", ctx.fuji_dict.get("risk", 0.0)) or 0.0)
    except (TypeError, ValueError):
        risk_score = 0.0
    human_review_required = bool(
        ctx.context.get("human_review_required")
        or fuji_status == "needs_human_review"
        or raw_gate_decision == "hold"
    )
    stop_reasons = _extract_stop_reasons(
        gate_reason=gate_reason,
        missing_evidence=missing_evidence,
        context=ctx.context,
    )

    gate_decision, human_review_required = derive_gate_decision_from_stop_reasons(
        stop_reasons=stop_reasons,
        raw_gate_decision=raw_gate_decision,
        decision_status=str(ctx.decision_status).lower(),
        risk_score=risk_score,
        human_review_required=human_review_required,
    )
    gate_decision = canonicalize_gate_decision(gate_decision)

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
    if structured_answer is not None:
        result["structured_answer"] = structured_answer
    if _is_dev_mode_enabled(ctx.context):
        result["action_candidates"] = action_candidates
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
    core.update(_derive_business_fields(ctx))

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
