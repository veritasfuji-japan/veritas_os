"""Pre-bind preservation evaluator.

This module introduces an additive preservation layer that is independent from
bind-time commitment admissibility and distinct from pre-bind detection.
"""

from __future__ import annotations

from typing import Any, Mapping

from veritas_os.core.preservation_semantics import (
    OPENNESS_FLOOR_STATUS_VALUES,
    PRESERVATION_FAMILY,
    PRESERVATION_STATE_VALUES,
    PRESERVATION_VERSION,
    normalize_preservation_input,
)


def _derive_openness_floor_status(structural_openness: str) -> str:
    if structural_openness == "closed":
        return "breached"
    if structural_openness == "fragile":
        return "at_risk"
    return "met"


def _derive_intervention_viability(
    intervention_headroom: str,
    *,
    counterfactual_availability: str,
    openness_floor_status: str,
) -> dict[str, Any]:
    if intervention_headroom == "none":
        level = "none"
    elif intervention_headroom == "low":
        level = "minimal"
    elif intervention_headroom == "medium":
        level = "partial"
    else:
        level = "high"

    meaningful = level != "none"
    if openness_floor_status == "breached" and counterfactual_availability == "none":
        meaningful = False
    return {
        "level": level,
        "meaningful_intervention_possible": meaningful,
    }


def _derive_counterfactual_recovery_possible(
    *,
    counterfactual_availability: str,
    interpretation_space_narrowing: str,
) -> bool:
    if counterfactual_availability == "none":
        return False
    if (
        counterfactual_availability == "low"
        and interpretation_space_narrowing in {"constrained", "closed"}
    ):
        return False
    return True


def _state_rationale(state: str) -> str:
    if state == "collapsed":
        return (
            "Decision-space openness is materially lost and meaningful "
            "intervention is no longer realistically available."
        )
    if state == "degrading":
        return (
            "Intervention and recovery remain possible, but structural "
            "openness is degrading and reversal difficulty is increasing."
        )
    return (
        "Intervention, correction, and counterfactual exploration remain "
        "meaningfully available before bind."
    )


def _classify_preservation_state(
    *,
    normalized: Mapping[str, str],
    detection_state: str | None,
    intervention_viability: Mapping[str, Any],
    openness_floor_status: str,
    counterfactual_recovery_possible: bool,
) -> str:
    if (
        intervention_viability["meaningful_intervention_possible"] is False
        or openness_floor_status == "breached"
        or (
            normalized["intervention_headroom"] == "none"
            and normalized["counterfactual_availability"] in {"low", "none"}
        )
        or (
            detection_state == "decision_shaping"
            and normalized["intervention_headroom"] in {"low", "none"}
            and not counterfactual_recovery_possible
        )
    ):
        return "collapsed"

    if (
        openness_floor_status == "at_risk"
        or normalized["intervention_headroom"] == "low"
        or normalized["counterfactual_availability"] == "low"
        or normalized["interpretation_space_narrowing"] in {"narrowing", "constrained"}
        or detection_state == "decision_shaping"
    ):
        return "degrading"
    return "open"


def evaluate_pre_bind_preservation(
    participation_signal: Mapping[str, Any],
    *,
    pre_bind_detection_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate additive pre-bind preservation state and rationale surfaces."""
    normalized = normalize_preservation_input(participation_signal)
    detection_state = None
    if isinstance(pre_bind_detection_summary, Mapping):
        detection_state = str(pre_bind_detection_summary.get("participation_state") or "")

    openness_floor_status = _derive_openness_floor_status(
        normalized["structural_openness"]
    )
    intervention_viability = _derive_intervention_viability(
        normalized["intervention_headroom"],
        counterfactual_availability=normalized["counterfactual_availability"],
        openness_floor_status=openness_floor_status,
    )
    counterfactual_recovery_possible = _derive_counterfactual_recovery_possible(
        counterfactual_availability=normalized["counterfactual_availability"],
        interpretation_space_narrowing=normalized["interpretation_space_narrowing"],
    )
    preservation_state = _classify_preservation_state(
        normalized=normalized,
        detection_state=detection_state or None,
        intervention_viability=intervention_viability,
        openness_floor_status=openness_floor_status,
        counterfactual_recovery_possible=counterfactual_recovery_possible,
    )
    if preservation_state not in PRESERVATION_STATE_VALUES:
        preservation_state = "open"
    if openness_floor_status not in OPENNESS_FLOOR_STATUS_VALUES:
        openness_floor_status = "met"

    contributing_conditions: list[str] = []
    if normalized["intervention_headroom"] in {"low", "none"}:
        contributing_conditions.append("intervention_headroom")
    if normalized["counterfactual_availability"] in {"low", "none"}:
        contributing_conditions.append("counterfactual_availability")
    if normalized["structural_openness"] in {"fragile", "closed"}:
        contributing_conditions.append("structural_openness")
    if normalized["interpretation_space_narrowing"] in {"constrained", "closed"}:
        contributing_conditions.append("interpretation_space_narrowing")
    if detection_state:
        contributing_conditions.append("pre_bind_detection_state")

    summary = {
        "preservation_family": PRESERVATION_FAMILY,
        "preservation_version": PRESERVATION_VERSION,
        "preservation_state": preservation_state,
        "preservation_outcome": preservation_state,
        "intervention_viability": intervention_viability["level"],
        "counterfactual_recovery_possible": counterfactual_recovery_possible,
        "openness_floor": openness_floor_status,
        "concise_rationale": _state_rationale(preservation_state),
        "main_contributing_conditions": contributing_conditions[:3],
    }
    detail = {
        "normalized_signal_levels": {
            "interpretation_space_narrowing": normalized[
                "interpretation_space_narrowing"
            ],
            "counterfactual_availability": normalized[
                "counterfactual_availability"
            ],
            "intervention_headroom": normalized["intervention_headroom"],
            "structural_openness": normalized["structural_openness"],
        },
        "intervention_viability": intervention_viability,
        "openness_floor": {
            "status": openness_floor_status,
            "structural_openness_level": normalized["structural_openness"],
        },
        "counterfactual_recovery_possible": counterfactual_recovery_possible,
        "detection_context": {
            "participation_state": detection_state or "informative",
        },
        "main_contributing_conditions": contributing_conditions,
    }
    return {
        "pre_bind_preservation_summary": summary,
        "pre_bind_preservation_detail": detail,
    }
