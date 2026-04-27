"""Pre-bind participation admissibility vocabulary and normalization helpers.

This module defines the first-class schema vocabulary for upstream
``participation_signal`` artifacts. It is intentionally additive and does not
modify bind-time commitment admissibility semantics.
"""

from __future__ import annotations

from typing import Any, Mapping

PARTICIPATION_SIGNAL_FAMILY = "participation_signal"

INTERPRETATION_SPACE_NARROWING_VALUES: tuple[str, ...] = (
    "open",
    "narrowing",
    "constrained",
    "closed",
)
COUNTERFACTUAL_AVAILABILITY_VALUES: tuple[str, ...] = (
    "high",
    "medium",
    "low",
    "none",
)
INTERVENTION_HEADROOM_VALUES: tuple[str, ...] = (
    "high",
    "medium",
    "low",
    "none",
)
STRUCTURAL_OPENNESS_VALUES: tuple[str, ...] = (
    "open",
    "partially_open",
    "fragile",
    "closed",
)
PARTICIPATION_ADMISSIBILITY_VALUES: tuple[str, ...] = (
    "admissible",
    "review_required",
    "inadmissible",
    "unknown",
)


def _canonicalize_level(value: Any, *, allowed: tuple[str, ...], fallback: str) -> str:
    """Normalize level-like values to lowercase and clamp to known vocabulary."""
    normalized = str(value or "").strip().lower()
    if normalized in allowed:
        return normalized
    return fallback


def normalize_participation_signal_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return normalized payload using fixed participation vocabulary.

    Unknown values are normalized to conservative compatibility defaults so this
    additive surface remains fail-soft for partial upstream producers.
    """
    normalized = dict(payload)
    normalized["signal_family"] = PARTICIPATION_SIGNAL_FAMILY
    normalized["interpretation_space_narrowing"] = _canonicalize_level(
        payload.get("interpretation_space_narrowing"),
        allowed=INTERPRETATION_SPACE_NARROWING_VALUES,
        fallback="open",
    )
    normalized["counterfactual_availability"] = _canonicalize_level(
        payload.get("counterfactual_availability"),
        allowed=COUNTERFACTUAL_AVAILABILITY_VALUES,
        fallback="medium",
    )
    normalized["intervention_headroom"] = _canonicalize_level(
        payload.get("intervention_headroom"),
        allowed=INTERVENTION_HEADROOM_VALUES,
        fallback="medium",
    )
    normalized["structural_openness"] = _canonicalize_level(
        payload.get("structural_openness"),
        allowed=STRUCTURAL_OPENNESS_VALUES,
        fallback="open",
    )
    normalized["participation_admissibility"] = _canonicalize_level(
        payload.get("participation_admissibility"),
        allowed=PARTICIPATION_ADMISSIBILITY_VALUES,
        fallback="unknown",
    )
    return normalized
