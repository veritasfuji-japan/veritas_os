"""Runtime contract helpers for public decision semantics.

This module centralizes:
- gate decision canonicalization (legacy aliases -> canonical public values),
- stop-reason gate priority classification,
- required evidence taxonomy normalization.

The goal is to keep runtime behavior stable while making the semantics explicit
and reusable across pipeline stages, schema validation, and adapters.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping

CANONICAL_GATE_DECISIONS = {
    "proceed",
    "hold",
    "block",
    "human_review_required",
}

GATE_DECISION_ALIAS_TO_CANONICAL = {
    "allow": "proceed",
    "deny": "block",
    "rejected": "block",
    "modify": "hold",
    "abstain": "hold",
    # Keep unknown as-is for schema default/backward compatibility.
    # Runtime derivation later resolves fallback to proceed when needed.
    "unknown": "unknown",
    "proceed": "proceed",
    "hold": "hold",
    "block": "block",
    "human_review_required": "human_review_required",
}

# Decision-semantics.md section D: single source-of-truth ordering.
STOP_REASON_GATE_PRIORITY: tuple[tuple[tuple[str, ...], str], ...] = (
    (("rollback_not_supported",), "block"),
    (("irreversible_action", "audit_trail_incomplete"), "block"),
    (("secure_prod_controls_missing",), "block"),
    (("required_evidence_missing",), "hold"),
    (("high_risk_ambiguity",), "human_review_required"),
    (("approval_boundary_unknown",), "human_review_required"),
    (("rule_undefined",), "hold"),
    (("audit_trail_incomplete",), "hold"),
    (("secure_controls_missing",), "hold"),
)

STOP_REASONS_REQUIRING_HUMAN_REVIEW = {
    "approval_boundary_unknown",
    "high_risk_ambiguity",
}

TAXONOMY_PATH = (
    Path(__file__).resolve().parents[1]
    / "sample_data"
    / "governance"
    / "required_evidence_taxonomy_v0.json"
)


@lru_cache(maxsize=1)
def _load_required_evidence_taxonomy() -> dict[str, object]:
    """Load required evidence taxonomy JSON once per process."""
    with TAXONOMY_PATH.open("r", encoding="utf-8") as fp:
        payload = json.load(fp)
    if not isinstance(payload, dict):
        return {"allow_free_string": True, "items": []}
    return payload


@lru_cache(maxsize=1)
def get_required_evidence_alias_map() -> dict[str, str]:
    """Return lower-cased alias->canonical map from taxonomy v0."""
    payload = _load_required_evidence_taxonomy()
    items = payload.get("items")
    alias_to_canonical: dict[str, str] = {}
    if not isinstance(items, list):
        return alias_to_canonical

    for item in items:
        if not isinstance(item, Mapping):
            continue
        canonical = str(item.get("canonical_key", "")).strip()
        if not canonical:
            continue
        canonical_lc = canonical.lower()
        alias_to_canonical[canonical_lc] = canonical_lc
        aliases = item.get("aliases")
        if not isinstance(aliases, list):
            continue
        for alias in aliases:
            alias_lc = str(alias).strip().lower()
            if alias_lc:
                alias_to_canonical.setdefault(alias_lc, canonical_lc)
    return alias_to_canonical


def canonicalize_gate_decision(value: object) -> str:
    """Canonicalize gate_decision-compatible values.

    Unknown values are preserved in lower-case for backward compatibility.
    """
    normalized = str(value or "unknown").strip().lower()
    if not normalized:
        normalized = "unknown"
    return GATE_DECISION_ALIAS_TO_CANONICAL.get(normalized, normalized)


def normalize_required_evidence_keys(values: Iterable[object] | None) -> list[str]:
    """Normalize evidence keys via taxonomy aliases while keeping free strings."""
    if values is None:
        return []
    alias_map = get_required_evidence_alias_map()
    out: list[str] = []
    for value in values:
        key = str(value).strip().lower()
        if not key:
            continue
        out.append(alias_map.get(key, key))
    return out


@lru_cache(maxsize=1)
def get_required_evidence_category_map() -> dict[str, str]:
    """Return canonical_key -> category map from taxonomy v0."""
    payload = _load_required_evidence_taxonomy()
    items = payload.get("items")
    out: dict[str, str] = {}
    if not isinstance(items, list):
        return out
    for item in items:
        if not isinstance(item, Mapping):
            continue
        canonical_key = str(item.get("canonical_key", "")).strip().lower()
        category = str(item.get("category", "")).strip().lower()
        if canonical_key and category:
            out[canonical_key] = category
    return out


def build_required_evidence_profile(values: Iterable[object] | None) -> list[dict[str, Any]]:
    """Build machine-readable evidence profile entries with taxonomy categories."""
    canonical_values = unique_preserve_order(normalize_required_evidence_keys(values))
    categories = get_required_evidence_category_map()
    profile: list[dict[str, Any]] = []
    for key in canonical_values:
        profile.append(
            {
                "key": key,
                "category": categories.get(key, "free_string"),
                "taxonomy_matched": key in categories,
            }
        )
    return profile


def unique_preserve_order(values: Iterable[str]) -> list[str]:
    """Return unique items preserving first-seen order."""
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def derive_gate_decision_from_stop_reasons(
    *,
    stop_reasons: Iterable[str],
    raw_gate_decision: str,
    decision_status: str,
    risk_score: float,
    human_review_required: bool,
) -> tuple[str, bool]:
    """Classify canonical gate decision using a single priority definition."""
    reasons = set(stop_reasons)
    deny_family = {"deny", "rejected", "block"}
    hold_family = {"hold", "modify", "abstain"}
    # Decision-semantics.md section D priority order.
    if "rollback_not_supported" in reasons:
        return "block", human_review_required
    if {"irreversible_action", "audit_trail_incomplete"} <= reasons:
        return "block", human_review_required
    if "secure_prod_controls_missing" in reasons:
        return "block", human_review_required
    if raw_gate_decision in deny_family or decision_status in deny_family:
        return "block", human_review_required
    if "required_evidence_missing" in reasons:
        return "hold", human_review_required
    if "high_risk_ambiguity" in reasons and risk_score >= 0.8:
        return "human_review_required", True
    if "approval_boundary_unknown" in reasons or human_review_required:
        return "human_review_required", True
    if (
        {"rule_undefined", "audit_trail_incomplete", "secure_controls_missing"} & reasons
        or raw_gate_decision in hold_family
    ):
        return "hold", human_review_required
    return "proceed", human_review_required


def validate_gate_business_combination(
    *, gate_decision: str, business_decision: str, human_review_required: bool
) -> None:
    """Raise ValueError when gate/business combination is forbidden."""
    forbidden = {
        ("block", "APPROVE"),
        ("hold", "APPROVE"),
        ("proceed", "DENY"),
    }
    if (gate_decision, business_decision) in forbidden:
        raise ValueError(
            "forbidden gate/business combination: "
            f"gate_decision={gate_decision}, business_decision={business_decision}"
        )
    if gate_decision == "human_review_required" and not human_review_required:
        raise ValueError(
            "forbidden combination: gate_decision=human_review_required "
            "requires human_review_required=true"
        )
    if gate_decision == "proceed" and human_review_required:
        raise ValueError(
            "forbidden combination: gate_decision=proceed "
            "requires human_review_required=false"
        )
    if business_decision == "REVIEW_REQUIRED" and not human_review_required:
        raise ValueError(
            "forbidden combination: business_decision=REVIEW_REQUIRED "
            "requires human_review_required=true"
        )
    if business_decision == "APPROVE" and human_review_required:
        raise ValueError(
            "forbidden combination: business_decision=APPROVE "
            "requires human_review_required=false"
        )
