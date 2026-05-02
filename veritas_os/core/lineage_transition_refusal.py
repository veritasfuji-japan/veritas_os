"""Transition eligibility helpers for execution-intent construction."""

from __future__ import annotations

from typing import Any, Mapping


_INVARIANT_ID = "BIND_ELIGIBLE_ARTIFACT_CANNOT_EMERGE_FROM_NON_PROMOTABLE_LINEAGE"
_NON_PROMOTABLE_REASON = "NON_PROMOTABLE_LINEAGE"


def evaluate_execution_intent_transition(
    *,
    lineage_promotability: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Evaluate whether execution-intent formation is structurally allowed."""
    promotability_status = str(
        (lineage_promotability or {}).get("promotability_status") or ""
    ).strip() or None

    if promotability_status == "non_promotable":
        return {
            "transition_status": "structurally_refused",
            "reason_code": _NON_PROMOTABLE_REASON,
            "invariant_id": str(
                (lineage_promotability or {}).get("invariant_id") or _INVARIANT_ID
            ),
            "source_promotability_status": "non_promotable",
            "execution_intent_created": False,
            "bind_receipt_created": False,
            "concise_rationale": (
                "ExecutionIntent cannot be constructed from a non-promotable "
                "pre-bind formation lineage."
            ),
        }

    return {
        "transition_status": "allowed",
        "reason_code": None,
        "invariant_id": str((lineage_promotability or {}).get("invariant_id") or _INVARIANT_ID),
        "source_promotability_status": promotability_status,
        "execution_intent_created": False,
        "bind_receipt_created": False,
        "concise_rationale": None,
    }
