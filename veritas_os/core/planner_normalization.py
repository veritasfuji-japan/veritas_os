"""Normalization helpers for Planner payloads.

This module centralizes value normalization and error policies used in
``veritas_os.core.planner`` so future schema extensions can reuse the same
conversion rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Literal, Mapping

FailurePolicy = Literal["use_default", "reject"]


@dataclass(frozen=True)
class NumericNormalizationRule:
    """Rule set for normalizing numeric planner fields.

    Attributes:
        default: Fallback value used when conversion fails and policy is
            ``"use_default"``.
        minimum: Optional lower clamp bound.
        maximum: Optional upper clamp bound.
        on_failure: Conversion failure policy. ``"use_default"`` keeps planner
            resilient, while ``"reject"`` re-raises conversion errors.
    """

    default: float
    minimum: float | None = None
    maximum: float | None = None
    on_failure: FailurePolicy = "use_default"


NORMALIZATION_POLICY_TABLE: Dict[str, NumericNormalizationRule] = {
    "eta_hours": NumericNormalizationRule(
        default=1.0,
        minimum=0.0,
        on_failure="use_default",
    ),
    "risk": NumericNormalizationRule(
        default=0.1,
        minimum=0.0,
        maximum=1.0,
        on_failure="use_default",
    ),
    "progress": NumericNormalizationRule(
        default=0.0,
        minimum=0.0,
        maximum=1.0,
        on_failure="use_default",
    ),
    "decision_count": NumericNormalizationRule(
        default=0.0,
        minimum=0.0,
        on_failure="use_default",
    ),
}


def normalize_float(
    value: Any,
    *,
    field_name: str,
    rule_overrides: Mapping[str, NumericNormalizationRule] | None = None,
    default_override: Any | None = None,
) -> float:
    """Normalize a value into float using planner normalization policies."""
    rules = rule_overrides or NORMALIZATION_POLICY_TABLE
    rule = rules[field_name]

    default_candidate = rule.default if default_override is None else default_override
    fallback = _coerce_default(default_candidate, field_name=field_name, rule=rule)

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        if rule.on_failure == "reject":
            raise
        numeric = fallback

    if rule.minimum is not None:
        numeric = max(rule.minimum, numeric)
    if rule.maximum is not None:
        numeric = min(rule.maximum, numeric)

    return numeric


def normalize_int(
    value: Any,
    *,
    field_name: str,
    rule_overrides: Mapping[str, NumericNormalizationRule] | None = None,
    default_override: Any | None = None,
) -> int:
    """Normalize a value into int using planner normalization policies."""
    normalized = normalize_float(
        value,
        field_name=field_name,
        rule_overrides=rule_overrides,
        default_override=default_override,
    )
    return int(normalized)


def _coerce_default(
    default_value: Any,
    *,
    field_name: str,
    rule: NumericNormalizationRule,
) -> float:
    """Coerce and clamp default values according to rule and failure policy."""
    try:
        numeric_default = float(default_value)
    except (TypeError, ValueError):
        if rule.on_failure == "reject":
            raise
        numeric_default = float(rule.default)

    if rule.minimum is not None:
        numeric_default = max(rule.minimum, numeric_default)
    if rule.maximum is not None:
        numeric_default = min(rule.maximum, numeric_default)
    return numeric_default
