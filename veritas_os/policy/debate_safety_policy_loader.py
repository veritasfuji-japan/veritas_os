"""Shadow loader and parity helpers for Debate safety policy YAML.

Phase 2 constraints:
- This module MUST NOT alter runtime enforcement decisions.
- Hardcoded logic in ``veritas_os/core/debate.py`` remains authoritative.
- YAML is loaded from an explicit local path only.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pydantic
import yaml

from veritas_os.core import debate
from veritas_os.policy.debate_safety_policy_schema import DebateSafetyPolicy


class DebateSafetyPolicyLoadError(ValueError):
    """Base error for debate safety policy shadow-loading failures."""


class DebateSafetyPolicyYamlSyntaxError(DebateSafetyPolicyLoadError):
    """Raised when debate safety policy YAML cannot be parsed."""


class DebateSafetyPolicySchemaError(DebateSafetyPolicyLoadError):
    """Raised when parsed YAML fails DebateSafetyPolicy schema validation."""


@dataclass(frozen=True)
class DebateSafetyPolicyParityReport:
    """Conservative parity report between YAML categories and hardcoded inventory."""

    status: str
    hardcoded_categories: list[str]
    yaml_categories: list[str]
    missing_hardcoded_categories: list[str]
    extra_yaml_categories: list[str]
    hardcoded_pattern_count: int | None
    yaml_pattern_count: int
    notes: list[str]


_HARDCODED_CATEGORY_MAP: dict[str, Any] = {
    "danger_terms_ja": debate._DANGER_TERMS_JA,
    "danger_patterns_en": debate._DANGER_PATTERNS_EN,
    "benign_context_strong_terms": debate._BENIGN_CONTEXT_STRONG_TERMS,
    "benign_context_weak_terms": debate._BENIGN_CONTEXT_WEAK_TERMS,
    "dangerous_intent_patterns": debate._DANGEROUS_INTENT_PATTERNS,
    "actionable_intent_patterns": debate._ACTIONABLE_INTENT_PATTERNS,
    "instructional_cue_patterns": debate._INSTRUCTIONAL_CUE_PATTERNS,
    "risk_negation_terms": debate._RISK_NEGATION_TERMS,
    "ascii_risk_negation_by_keyword": debate._ASCII_RISK_NEGATION_BY_KEYWORD,
    "ja_risk_negation_by_keyword": debate._JA_RISK_NEGATION_BY_KEYWORD,
    "refusal_context_patterns": debate._REFUSAL_CONTEXT_PATTERNS,
    "risk_keywords_weighted": debate._RISK_KEYWORDS_WEIGHTED,
    "regulatory_ambiguity_patterns": debate._REGULATORY_AMBIGUITY_PATTERNS,
    "regulatory_ambiguity_negation_terms": debate._REGULATORY_AMBIGUITY_NEGATION_TERMS,
}


def load_debate_safety_policy_from_yaml(path: str | Path) -> DebateSafetyPolicy:
    """Load and validate Debate safety policy YAML from an explicit path.

    Args:
        path: Local file path to YAML policy.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        DebateSafetyPolicyYamlSyntaxError: If YAML cannot be parsed.
        DebateSafetyPolicySchemaError: If YAML shape fails schema validation.

    Returns:
        Validated ``DebateSafetyPolicy`` instance.
    """
    policy_path = Path(path)
    raw_text = policy_path.read_text(encoding="utf-8")

    try:
        payload = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise DebateSafetyPolicyYamlSyntaxError(
            f"Failed to parse YAML at '{policy_path}': {exc}"
        ) from exc

    try:
        return DebateSafetyPolicy.model_validate(payload)
    except pydantic.ValidationError as exc:
        raise DebateSafetyPolicySchemaError(
            f"YAML at '{policy_path}' failed DebateSafetyPolicy validation: {exc}"
        ) from exc


def compare_policy_to_hardcoded_inventory(
    policy: DebateSafetyPolicy,
) -> DebateSafetyPolicyParityReport:
    """Create a conservative Phase 2 parity report.

    This helper only compares category inventory and pattern counts and does not
    evaluate semantic regex parity. It intentionally avoids over-claiming parity.
    """
    hardcoded_categories = sorted(_HARDCODED_CATEGORY_MAP.keys())
    yaml_categories = sorted(policy.categories.keys())
    missing_hardcoded = sorted(set(hardcoded_categories) - set(yaml_categories))
    extra_yaml = sorted(set(yaml_categories) - set(hardcoded_categories))

    hardcoded_pattern_count = _count_hardcoded_patterns()
    yaml_pattern_count = sum(len(category.patterns) for category in policy.categories.values())

    notes: list[str] = [
        "Phase 2 shadow-only comparison. Runtime enforcement remains hardcoded.",
        "Semantic regex equivalence is not validated in this report.",
    ]

    if missing_hardcoded or extra_yaml:
        status = "parity_unknown"
        notes.append(
            "TODO: align YAML categories to full hardcoded inventory before considering enforcement parity."
        )
    else:
        status = "partial_parity"
        notes.append(
            "Category names align with hardcoded inventory, but semantic parity remains unproven."
        )

    return DebateSafetyPolicyParityReport(
        status=status,
        hardcoded_categories=hardcoded_categories,
        yaml_categories=yaml_categories,
        missing_hardcoded_categories=missing_hardcoded,
        extra_yaml_categories=extra_yaml,
        hardcoded_pattern_count=hardcoded_pattern_count,
        yaml_pattern_count=yaml_pattern_count,
        notes=notes,
    )


def _count_hardcoded_patterns() -> int:
    total = 0
    for value in _HARDCODED_CATEGORY_MAP.values():
        if isinstance(value, dict):
            total += sum(len(items) for items in value.values())
        else:
            total += len(value)
    return total
