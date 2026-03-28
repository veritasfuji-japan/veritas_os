"""Human-readable explanation metadata for compiled policy artifacts."""

from __future__ import annotations

from typing import Any, Dict

from .ir import CanonicalPolicyIR


def build_explanation_metadata(canonical_ir: CanonicalPolicyIR) -> Dict[str, Any]:
    """Build explanation metadata for UI and audit export consumers."""
    outcome = canonical_ir["outcome"]
    requirements = canonical_ir["requirements"]
    decision = outcome["decision"]

    return {
        "policy_id": canonical_ir["policy_id"],
        "title": canonical_ir["title"],
        "purpose": canonical_ir["description"],
        "application": {
            "scope": canonical_ir["scope"],
            "condition_count": len(canonical_ir["conditions"]),
            "constraint_count": len(canonical_ir["constraints"]),
            "human_summary": (
                f"Apply to domains={', '.join(canonical_ir['scope']['domains'])}; "
                f"routes={', '.join(canonical_ir['scope']['routes'])}; "
                f"actors={', '.join(canonical_ir['scope']['actors'])}."
            ),
        },
        "outcome": {
            "decision": decision,
            "reason": outcome["reason"],
            "human_summary": f"If policy matches, outcome is '{decision}'.",
        },
        "obligations": {
            "items": canonical_ir["obligations"],
            "human_summary": (
                "No obligations are defined."
                if not canonical_ir["obligations"]
                else (
                    "Required obligations: "
                    + ", ".join(canonical_ir["obligations"])
                    + "."
                )
            ),
        },
        "requirements": {
            "required_evidence": requirements["required_evidence"],
            "required_reviewers": requirements["required_reviewers"],
            "minimum_approval_count": requirements["minimum_approval_count"],
        },
    }
