"""Human-readable explanation metadata for compiled policy artifacts."""

from __future__ import annotations

from typing import Any, Dict

from .ir import CanonicalPolicyIR


def build_explanation_metadata(canonical_ir: CanonicalPolicyIR) -> Dict[str, Any]:
    """Build explanation metadata for UI and audit export consumers."""
    outcome = canonical_ir.get("outcome") or {}
    requirements = canonical_ir.get("requirements") or {}
    scope = canonical_ir.get("scope") or {}
    decision = outcome.get("decision", "unknown")
    obligations = canonical_ir.get("obligations") or []
    conditions = canonical_ir.get("conditions") or []
    constraints = canonical_ir.get("constraints") or []

    return {
        "policy_id": canonical_ir.get("policy_id", ""),
        "title": canonical_ir.get("title", ""),
        "purpose": canonical_ir.get("description", ""),
        "application": {
            "scope": scope,
            "condition_count": len(conditions),
            "constraint_count": len(constraints),
            "human_summary": (
                f"Apply to domains={', '.join(scope.get('domains') or [])}; "
                f"routes={', '.join(scope.get('routes') or [])}; "
                f"actors={', '.join(scope.get('actors') or [])}."
            ),
        },
        "outcome": {
            "decision": decision,
            "reason": outcome.get("reason", ""),
            "human_summary": f"If policy matches, outcome is '{decision}'.",
        },
        "obligations": {
            "items": obligations,
            "human_summary": (
                "No obligations are defined."
                if not obligations
                else (
                    "Required obligations: "
                    + ", ".join(obligations)
                    + "."
                )
            ),
        },
        "requirements": {
            "required_evidence": requirements.get("required_evidence", []),
            "required_reviewers": requirements.get("required_reviewers", []),
            "minimum_approval_count": requirements.get("minimum_approval_count", 0),
        },
    }
