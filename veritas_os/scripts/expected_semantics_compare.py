# -*- coding: utf-8 -*-
"""Helpers to compare expected vs actual public decision semantics."""

from __future__ import annotations

from typing import Any, Mapping

from veritas_os.core.decision_semantics import (
    canonicalize_public_gate_decision,
    normalize_required_evidence_keys,
    unique_preserve_order,
)

_NEXT_ACTION_ALIASES = {
    "NEEDS_HUMAN_REVIEW": "PREPARE_HUMAN_REVIEW_PACKET",
    "REJECT_REQUEST": "DO_NOT_EXECUTE",
}

_NEXT_ACTION_FAMILIES = {
    "COLLECT_REQUIRED_EVIDENCE": "collect_evidence",
    "DEFINE_POLICY_AND_REASSESS": "collect_evidence",
    "PREPARE_HUMAN_REVIEW_PACKET": "human_review",
    "ROUTE_TO_HUMAN_REVIEW": "human_review",
    "DO_NOT_EXECUTE": "stop_execution",
    "ESCALATE_POLICY_EXCEPTION_REVIEW": "human_review",
    "EXECUTE_WITH_STANDARD_MONITORING": "execute",
    "RUN_TARGETED_VALIDATION_CHECKS": "execute",
    "REVISE_AND_RESUBMIT": "collect_evidence",
}

_CANONICAL_BUSINESS_DECISIONS = {
    "APPROVE",
    "DENY",
    "HOLD",
    "REVIEW_REQUIRED",
    "EVIDENCE_REQUIRED",
    "POLICY_DEFINITION_REQUIRED",
}

_BUSINESS_ALIASES = {
    "ALLOW": "APPROVE",
    "PROCEED": "APPROVE",
    "REJECTED": "DENY",
    "BLOCK": "DENY",
    "MODIFY": "HOLD",
    "ABSTAIN": "HOLD",
    "AMBIGUOUS_HUMAN_REVIEW": "REVIEW_REQUIRED",
}


def normalize_next_action(value: Any) -> str:
    """Normalize next_action labels into stable canonical labels."""
    normalized = str(value or "").strip().upper()
    if not normalized:
        return ""
    return _NEXT_ACTION_ALIASES.get(normalized, normalized)


def next_action_family(value: Any) -> str:
    """Return coarse action family for tolerant compare in PoC mode."""
    action = normalize_next_action(value)
    return _NEXT_ACTION_FAMILIES.get(action, "other")


def canonicalize_business_decision(value: Any) -> str:
    """Normalize business decision values for stable semantic comparisons."""
    normalized = str(value or "").strip().upper()
    if not normalized:
        return "HOLD"
    if normalized in _CANONICAL_BUSINESS_DECISIONS:
        return normalized
    return _BUSINESS_ALIASES.get(normalized, "HOLD")


def compare_expected_semantics(
    expected: Mapping[str, Any],
    actual: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Return field-level mismatch diff between expected and actual semantics."""
    mismatches: dict[str, dict[str, Any]] = {}

    expected_gate = canonicalize_public_gate_decision(expected.get("gate_decision"))
    actual_gate = canonicalize_public_gate_decision(actual.get("gate_decision"))
    if expected_gate != actual_gate:
        mismatches["gate_decision"] = {"expected": expected_gate, "actual": actual_gate}

    expected_business = canonicalize_business_decision(expected.get("business_decision"))
    actual_business = canonicalize_business_decision(actual.get("business_decision"))
    if expected_business != actual_business:
        mismatches["business_decision"] = {
            "expected": expected_business,
            "actual": actual_business,
        }

    expected_action = normalize_next_action(expected.get("next_action"))
    actual_action = normalize_next_action(actual.get("next_action"))
    if expected_action != actual_action:
        expected_family = next_action_family(expected_action)
        actual_family = next_action_family(actual_action)
        if expected_family != actual_family:
            mismatches["next_action"] = {
                "expected": expected_action,
                "actual": actual_action,
                "expected_family": expected_family,
                "actual_family": actual_family,
            }

    expected_required = unique_preserve_order(
        normalize_required_evidence_keys(
            expected.get("expected_required_evidence", expected.get("required_evidence"))
        )
    )
    actual_required = unique_preserve_order(
        normalize_required_evidence_keys(actual.get("required_evidence"))
    )
    if expected_required != actual_required:
        mismatches["required_evidence"] = {
            "expected": expected_required,
            "actual": actual_required,
            "only_in_expected": [item for item in expected_required if item not in set(actual_required)],
            "only_in_actual": [item for item in actual_required if item not in set(expected_required)],
        }

    expected_missing = unique_preserve_order(
        normalize_required_evidence_keys(
            expected.get("expected_missing_evidence", expected.get("missing_evidence"))
        )
    )
    actual_missing = unique_preserve_order(
        normalize_required_evidence_keys(actual.get("missing_evidence"))
    )
    if "missing_evidence" in expected and expected_missing != actual_missing:
        mismatches["missing_evidence"] = {
            "expected": expected_missing,
            "actual": actual_missing,
            "only_in_expected": [item for item in expected_missing if item not in set(actual_missing)],
            "only_in_actual": [item for item in actual_missing if item not in set(expected_missing)],
        }

    expected_human = bool(expected.get("human_review_required"))
    actual_human = bool(actual.get("human_review_required"))
    if expected_human != actual_human:
        mismatches["human_review_required"] = {
            "expected": expected_human,
            "actual": actual_human,
        }
    telemetry = actual.get("required_evidence_telemetry")
    if isinstance(telemetry, Mapping):
        unknown_keys = telemetry.get("top_unknown_keys") or []
        profile_missing = telemetry.get("profile_missing_keys") or []
        if unknown_keys or profile_missing:
            mismatches["required_evidence_runtime_warnings"] = {
                "expected": {
                    "unknown_keys": [],
                    "profile_missing_keys": [],
                },
                "actual": {
                    "unknown_keys": list(unknown_keys),
                    "profile_missing_keys": list(profile_missing),
                },
            }

    return mismatches


def summarize_semantic_mismatches(mismatches: Mapping[str, Mapping[str, Any]]) -> str:
    """Return a compact human-readable mismatch summary for runner outputs."""
    if not mismatches:
        return "no mismatches"
    mismatch_count = len(mismatches)
    segments: list[str] = []
    for field_name in (
        "gate_decision",
        "business_decision",
        "required_evidence",
        "missing_evidence",
        "required_evidence_runtime_warnings",
        "human_review_required",
        "next_action",
    ):
        item = mismatches.get(field_name)
        if not isinstance(item, Mapping):
            continue
        expected = item.get("expected")
        actual = item.get("actual")
        segments.append(f"{field_name}: expected={expected} actual={actual}")
    if not segments:
        return f"{mismatch_count} mismatch(es): details unavailable"
    return f"{mismatch_count} mismatch(es): " + " | ".join(segments)
