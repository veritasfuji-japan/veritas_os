# -*- coding: utf-8 -*-
"""Semantics comparison helpers for governance regression tests."""

from __future__ import annotations

from typing import Any, Mapping

from veritas_os.core.decision_semantics import canonicalize_gate_decision

_NEXT_ACTION_ALIASES = {
    "NEEDS_HUMAN_REVIEW": "PREPARE_HUMAN_REVIEW_PACKET",
    "REJECT_REQUEST": "DO_NOT_EXECUTE",
}


def _normalize_next_action(action: Any) -> str:
    """Normalize legacy next_action labels into current runtime labels."""
    normalized = str(action or "").strip().upper()
    if not normalized:
        return ""
    return _NEXT_ACTION_ALIASES.get(normalized, normalized)


def assert_expected_semantics(
    payload: Mapping[str, Any],
    expected: Mapping[str, Any],
) -> None:
    """Assert payload decision semantics against expected fixture values."""
    assert canonicalize_gate_decision(payload.get("gate_decision")) == (
        canonicalize_gate_decision(expected.get("gate_decision"))
    )
    assert payload.get("business_decision") == expected.get("business_decision")
    assert _normalize_next_action(payload.get("next_action")) == (
        _normalize_next_action(expected.get("next_action"))
    )
    assert payload.get("required_evidence") == expected.get("required_evidence")
    if "missing_evidence" in expected:
        assert payload.get("missing_evidence") == expected.get("missing_evidence")
    assert bool(payload.get("human_review_required")) is bool(
        expected.get("human_review_required")
    )
