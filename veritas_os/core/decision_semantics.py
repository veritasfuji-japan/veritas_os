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

CANONICAL_GATE_DECISION_VALUES: tuple[str, ...] = (
    "proceed",
    "hold",
    "block",
    "human_review_required",
)

CANONICAL_GATE_DECISIONS = set(CANONICAL_GATE_DECISION_VALUES)

LEGACY_GATE_DECISION_ALIASES: tuple[str, ...] = (
    "allow",
    "deny",
    "modify",
    "rejected",
    "abstain",
)

COMPATIBLE_GATE_DECISION_VALUES: tuple[str, ...] = (
    *CANONICAL_GATE_DECISION_VALUES,
    *LEGACY_GATE_DECISION_ALIASES,
    "unknown",
)

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

FORBIDDEN_GATE_BUSINESS_COMBINATIONS: frozenset[tuple[str, str]] = frozenset(
    {
        ("block", "APPROVE"),
        ("hold", "APPROVE"),
        ("proceed", "DENY"),
    }
)

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


def canonicalize_public_gate_decision(
    value: object,
    *,
    fallback: str = "unknown",
) -> str:
    """Canonicalize gate_decision for public response surfaces.

    Legacy aliases are normalized to canonical values.
    Non-canonical / unrecognized values are collapsed to ``fallback``.
    """
    canonical_value = canonicalize_gate_decision(value)
    if canonical_value in CANONICAL_GATE_DECISIONS:
        return canonical_value
    return fallback


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


def normalize_required_evidence_keys_with_diagnostics(
    values: Iterable[object] | None,
) -> tuple[list[str], dict[str, Any]]:
    """Normalize evidence keys and return diagnostics for telemetry.

    Diagnostics include:
    - ``alias_normalized_count``: values changed from alias to canonical.
    - ``unknown_keys``: normalized keys not in taxonomy categories.
    """
    if values is None:
        return [], {"alias_normalized_count": 0, "unknown_keys": []}
    alias_map = get_required_evidence_alias_map()
    category_map = get_required_evidence_category_map()
    normalized: list[str] = []
    alias_normalized_count = 0
    for value in values:
        raw_key = str(value).strip().lower()
        if not raw_key:
            continue
        canonical_key = alias_map.get(raw_key, raw_key)
        if canonical_key != raw_key:
            alias_normalized_count += 1
        normalized.append(canonical_key)
    unknown_keys = unique_preserve_order(
        [key for key in normalized if key not in category_map]
    )
    diagnostics = {
        "alias_normalized_count": alias_normalized_count,
        "unknown_keys": unknown_keys,
    }
    return normalized, diagnostics


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


@lru_cache(maxsize=1)
def get_required_evidence_profiles() -> dict[str, dict[str, Any]]:
    """Return per-domain evidence profiles keyed by normalized domain name."""
    payload = _load_required_evidence_taxonomy()
    raw_profiles = payload.get("profiles")
    canonical_keys = set(get_required_evidence_category_map())
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(raw_profiles, Mapping):
        return out
    for domain_name, profile in raw_profiles.items():
        domain_key = str(domain_name).strip().lower()
        if not domain_key or not isinstance(profile, Mapping):
            continue
        validated_profile = validate_required_evidence_profile_shape(
            profile,
            canonical_keys=canonical_keys,
        )
        if validated_profile is None:
            continue
        out[domain_key] = validated_profile
    return out


def validate_required_evidence_profile_shape(
    profile: Mapping[str, Any],
    *,
    canonical_keys: set[str],
) -> dict[str, Any] | None:
    """Validate and normalize one required-evidence profile.

    The profile must include:
    - ``profile_id`` (non-empty string),
    - ``profile_version`` (non-empty string),
    - ``required`` / ``optional`` / ``escalation_sensitive`` lists,
    - ``canonical_key_list`` list.

    Validation is fail-soft: malformed profiles return ``None`` so runtime can
    continue with declared context evidence instead of crashing.
    """
    required_keys = unique_preserve_order(
        normalize_required_evidence_keys(profile.get("required"))
    )
    optional_keys = unique_preserve_order(
        normalize_required_evidence_keys(profile.get("optional"))
    )
    escalation_sensitive_keys = unique_preserve_order(
        normalize_required_evidence_keys(profile.get("escalation_sensitive"))
    )
    canonical_key_list = unique_preserve_order(
        normalize_required_evidence_keys(profile.get("canonical_key_list"))
    )
    profile_id = str(profile.get("profile_id") or "").strip()
    profile_version = str(profile.get("profile_version") or "").strip()

    if not profile_id or not profile_version:
        return None
    if not required_keys:
        return None
    if not canonical_key_list:
        return None
    if any(key not in canonical_keys for key in canonical_key_list):
        return None

    key_union = set(required_keys) | set(optional_keys) | set(escalation_sensitive_keys)
    if set(canonical_key_list) != key_union:
        return None
    if not set(escalation_sensitive_keys) <= set(required_keys):
        return None

    return {
        "required": required_keys,
        "optional": optional_keys,
        "escalation_sensitive": escalation_sensitive_keys,
        "canonical_key_list": canonical_key_list,
        "profile_id": profile_id,
        "profile_version": profile_version,
    }


def build_required_evidence_profile(
    values: Iterable[object] | None,
    *,
    decision_domain: str = "",
) -> list[dict[str, Any]]:
    """Build machine-readable evidence profile entries with taxonomy categories."""
    canonical_values = unique_preserve_order(normalize_required_evidence_keys(values))
    categories = get_required_evidence_category_map()
    profiles = get_required_evidence_profiles()
    domain_key = str(decision_domain or "").strip().lower()
    domain_profile = profiles.get(domain_key, {})
    required_keys = set(domain_profile.get("required", []))
    optional_keys = set(domain_profile.get("optional", []))
    escalation_sensitive_keys = set(domain_profile.get("escalation_sensitive", []))
    entries: list[dict[str, Any]] = []
    for key in canonical_values:
        requirement_level = "unclassified"
        if key in required_keys:
            requirement_level = "required"
        elif key in optional_keys:
            requirement_level = "optional"
        elif key in escalation_sensitive_keys:
            requirement_level = "escalation_sensitive"
        entries.append(
            {
                "key": key,
                "category": categories.get(key, "free_string"),
                "taxonomy_matched": key in categories,
                "requirement_level": requirement_level,
                "domain_profile_matched": key in (
                    required_keys | optional_keys | escalation_sensitive_keys
                ),
            }
        )
    return entries


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
    normalized_raw_gate = canonicalize_gate_decision(raw_gate_decision)
    normalized_decision_status = canonicalize_gate_decision(decision_status)
    # Decision-semantics.md section D priority order.
    if "rollback_not_supported" in reasons:
        return "block", human_review_required
    if {"irreversible_action", "audit_trail_incomplete"} <= reasons:
        return "block", human_review_required
    if "secure_prod_controls_missing" in reasons:
        return "block", human_review_required
    if normalized_raw_gate == "block" or normalized_decision_status == "block":
        return "block", human_review_required
    if "required_evidence_missing" in reasons:
        return "hold", human_review_required
    if "sanctions_partial_match" in reasons:
        return "hold", human_review_required
    if "high_risk_ambiguity" in reasons and risk_score >= 0.8:
        return "human_review_required", True
    if "approval_boundary_unknown" in reasons or human_review_required:
        return "human_review_required", True
    if (
        {"rule_undefined", "audit_trail_incomplete", "secure_controls_missing"} & reasons
        or normalized_raw_gate == "hold"
    ):
        return "hold", human_review_required
    return "proceed", human_review_required


def validate_gate_business_combination(
    *, gate_decision: str, business_decision: str, human_review_required: bool
) -> None:
    """Raise ValueError when gate/business combination is forbidden."""
    gate_decision = canonicalize_public_gate_decision(gate_decision)
    if (gate_decision, business_decision) in FORBIDDEN_GATE_BUSINESS_COMBINATIONS:
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
