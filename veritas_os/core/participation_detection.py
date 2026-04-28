"""Pre-bind structural participation detection evaluator.

This module classifies upstream participation signals into a structural
pre-bind detection state. It is intentionally additive and does not modify
bind-time admissibility or fail-closed bind governance.
"""

from __future__ import annotations

from typing import Any, Mapping

from veritas_os.core.participation_semantics import normalize_participation_signal_payload

PRE_BIND_DETECTION_FAMILY = "pre_bind_structural_detection"
PRE_BIND_DETECTION_VERSION = "v1"
PRE_BIND_PARTICIPATION_STATE_VALUES: tuple[str, ...] = (
    "informative",
    "participatory",
    "decision_shaping",
)

_SIGNAL_SEVERITY_MAP: dict[str, dict[str, int]] = {
    "interpretation_space_narrowing": {
        "open": 0,
        "narrowing": 1,
        "constrained": 2,
        "closed": 3,
    },
    "counterfactual_availability": {
        "high": 0,
        "medium": 1,
        "low": 2,
        "none": 3,
    },
    "intervention_headroom": {
        "high": 0,
        "medium": 1,
        "low": 2,
        "none": 3,
    },
    "structural_openness": {
        "open": 0,
        "partially_open": 1,
        "fragile": 2,
        "closed": 3,
    },
}

_SIGNAL_LABELS: dict[str, str] = {
    "interpretation_space_narrowing": "interpretation_space_narrowing",
    "counterfactual_availability": "counterfactual_availability",
    "intervention_headroom": "intervention_headroom",
    "structural_openness": "structural_openness",
}


def _state_rationale(state: str) -> str:
    """Return concise operator-facing rationale text for the classified state."""
    if state == "decision_shaping":
        return (
            "Structural participation signals indicate interpretation and option "
            "space are materially constrained before bind."
        )
    if state == "participatory":
        return (
            "Structural participation signals indicate decision formation impact "
            "is emerging while alternative space remains available."
        )
    return (
        "Structural participation signals indicate support remains primarily "
        "informative and intervention headroom is preserved."
    )


def _classify_state(severities: Mapping[str, int]) -> tuple[str, float, int, int]:
    """Classify state from structural signal severities.

    Returns
    -------
    tuple
        ``(state, aggregate_index, high_count, moderate_count)`` where
        aggregate_index is a normalized 0.0-1.0 severity index.
    """
    values = [int(v) for v in severities.values()]
    if not values:
        return "informative", 0.0, 0, 0

    high_count = sum(1 for value in values if value >= 2)
    moderate_count = sum(1 for value in values if value >= 1)
    average = sum(values) / float(len(values))
    aggregate_index = round(min(1.0, max(0.0, average / 3.0)), 4)

    # Conservative structural thresholding to avoid over-detection:
    # decision_shaping requires multi-signal severity and high aggregate strain.
    if average >= 2.25 and high_count >= 2 and max(values) >= 3:
        return "decision_shaping", aggregate_index, high_count, moderate_count
    if average >= 1.0 or high_count >= 1 or moderate_count >= 2:
        return "participatory", aggregate_index, high_count, moderate_count
    return "informative", aggregate_index, high_count, moderate_count


def evaluate_pre_bind_structural_detection(
    participation_signal: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate additive pre-bind participation detection from structural signals."""
    normalized = normalize_participation_signal_payload(participation_signal)

    severities: dict[str, int] = {}
    for signal_name in _SIGNAL_SEVERITY_MAP:
        if signal_name not in participation_signal:
            # Low-signal/absent cases are treated conservatively as non-elevating.
            severities[signal_name] = 0
            continue
        severities[signal_name] = _SIGNAL_SEVERITY_MAP[signal_name][normalized[signal_name]]
    state, aggregate_index, high_count, moderate_count = _classify_state(severities)

    sorted_signals = sorted(
        severities.items(),
        key=lambda item: (-item[1], item[0]),
    )
    primary = [
        _SIGNAL_LABELS[name]
        for name, severity in sorted_signals
        if severity > 0
    ][:2]

    summary = {
        "detection_family": PRE_BIND_DETECTION_FAMILY,
        "detection_version": PRE_BIND_DETECTION_VERSION,
        "participation_state": state,
        "primary_contributing_signals": primary,
        "concise_rationale": _state_rationale(state),
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
        "signal_severity": severities,
        "aggregate_index": aggregate_index,
        "high_signal_count": high_count,
        "moderate_signal_count": moderate_count,
    }
    return {
        "pre_bind_detection_summary": summary,
        "pre_bind_detection_detail": detail,
    }
