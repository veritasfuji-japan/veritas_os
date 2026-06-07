#!/usr/bin/env python3
"""Generate a draft Legitimacy Impact Review from governance artifacts.

This offline demo helper is intentionally schema-shaped and non-enforcing. It
reads a local Manifest Change Receipt v1 JSON object and, optionally, a local
Trajectory-Level Admissibility Monitor v1 JSON object, then surfaces
deterministic legitimacy-impacting signals as reviewable evidence. VERITAS does
not automatically create or guarantee legitimacy; this helper does not prove
legitimacy, certify compliance, dereference artifact references, access the
network, or connect to runtime admissibility paths.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO_ROOT / "docs/en/demo/schemas"
MANIFEST_CHANGE_RECEIPT_SCHEMA_PATH = (
    SCHEMA_DIR / "manifest-change-receipt-v1.schema.json"
)
TRAJECTORY_ADMISSIBILITY_MONITOR_SCHEMA_PATH = (
    SCHEMA_DIR / "trajectory-admissibility-monitor-v1.schema.json"
)
LEGITIMACY_IMPACT_REVIEW_SCHEMA_PATH = (
    SCHEMA_DIR / "legitimacy-impact-review-v1.schema.json"
)

REVIEW_ID = "legitimacy-impact-review-example-001"
ISSUED_AT = "2026-01-01T00:00:00Z"
UNKNOWN_REF = "unknown-governance-artifact"
UNKNOWN_HASH = "0" * 64

MANIFEST_TYPE_TO_ARTIFACT_TYPE = {
    "root_authority_manifest": "root_authority_manifest",
    "evaluation_function_manifest": "evaluation_function_manifest",
    "manifest_change_receipt": "manifest_change_receipt",
    "other_governance_manifest": "other_governance_artifact",
}
FLAG_TO_CATEGORY = {
    "authority_scope_expanded": "authority_scope_expansion",
    "human_oversight_weakened": "human_oversight_weakened",
    "refusal_boundary_relaxed": "refusal_boundary_relaxed",
    "escalation_requirement_reduced": "escalation_requirement_reduced",
    "policy_source_changed": "policy_source_changed",
    "evaluator_behavior_changed": "evaluation_behavior_changed",
    "trusted_authority_source_changed": "trusted_authority_source_changed",
    "auditability_reduced": "auditability_reduced",
    "replayability_reduced": "replayability_reduced",
}
CATEGORY_ORDER = [
    "authority_scope_expansion",
    "trusted_authority_source_changed",
    "policy_source_changed",
    "human_oversight_weakened",
    "refusal_boundary_relaxed",
    "escalation_requirement_reduced",
    "auditability_reduced",
    "replayability_reduced",
    "high_risk_admissibility_expanded",
    "evaluation_behavior_changed",
    "root_authority_changed",
    "constitutional_trust_anchor_changed",
    "unknown_legitimacy_impact",
]
SUSPICIOUS_TRAJECTORY_STATUSES = {
    "suspicious",
    "drift_detected",
    "strategically_shaped",
    "non_deterministically_governed",
}
REVIEWER_POWER_ROLES = {
    "reviewer",
    "admin",
    "governance_owner",
    "governance-owner",
    "governance owner",
}
HIGH_SEVERITY_CATEGORIES = {
    "authority_scope_expansion",
    "human_oversight_weakened",
    "refusal_boundary_relaxed",
    "escalation_requirement_reduced",
    "high_risk_admissibility_expanded",
    "root_authority_changed",
    "constitutional_trust_anchor_changed",
}


def _jsonschema_module() -> Any | None:
    """Return the optional jsonschema module when available locally."""
    if importlib.util.find_spec("jsonschema") is None:
        return None

    import jsonschema

    return jsonschema


def _load_json_object(path: Path) -> dict[str, Any]:
    """Load a JSON object from a local file with reviewer-friendly errors."""
    if not path.is_file():
        raise FileNotFoundError(f"missing file: {path}")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise TypeError(f"expected JSON object in {path}")
    return payload


def _validate_against_schema(payload: dict[str, Any], schema_path: Path) -> None:
    """Validate a JSON object when jsonschema is installed locally."""
    jsonschema = _jsonschema_module()
    if jsonschema is None:
        return

    schema = _load_json_object(schema_path)
    validator = jsonschema.Draft202012Validator(schema)
    validator.validate(payload)


def _canonical_json_bytes(payload: Any) -> bytes:
    """Return deterministic UTF-8 JSON bytes for hashing."""
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_json_hash(payload: Any) -> str:
    """Return the SHA-256 hex digest of canonical JSON."""
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _string_list(value: Any) -> list[str]:
    """Return non-empty strings from a JSON array value."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _string_value(value: Any, default: str = "") -> str:
    """Return a string value or a default."""
    if isinstance(value, str) and value:
        return value
    return default


def _contains_any(text: str, needles: set[str]) -> bool:
    """Return whether normalized text contains any requested phrase."""
    normalized = text.lower().replace("_", "-")
    spaced = normalized.replace("-", " ")
    return any(needle in normalized or needle in spaced for needle in needles)


def _has_high_risk_evidence(
    manifest_change: dict[str, Any],
    trajectory_monitor: dict[str, Any] | None,
) -> bool:
    """Return whether local artifact fields mention high-risk or regulated scope."""
    values: list[str] = []
    values.extend(_string_list(manifest_change.get("impact_scope")))
    if trajectory_monitor is not None:
        values.extend(_string_list(trajectory_monitor.get("evaluation_receipt_refs")))
        values.extend(_string_list(trajectory_monitor.get("outcome_delta_attribution_refs")))
        values.extend(_string_list(trajectory_monitor.get("evaluation_drift_detection_refs")))
        for signal in _trajectory_risk_signals(trajectory_monitor):
            values.extend(_string_list(signal.get("evidence_refs")))
            values.append(_string_value(signal.get("explanation")))

    return any(
        _contains_any(value, {"high-risk", "high risk", "regulated"})
        or "high_risk" in value.lower()
        for value in values
    )


def _trajectory_risk_signals(
    trajectory_monitor: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Return well-shaped trajectory risk signal dictionaries."""
    if trajectory_monitor is None:
        return []
    signals = trajectory_monitor.get("trajectory_risk_signals", [])
    if not isinstance(signals, list):
        return []
    return [signal for signal in signals if isinstance(signal, dict)]


def _trajectory_monitor_ref(trajectory_monitor: dict[str, Any] | None) -> str | None:
    """Return the monitor ID, if present, without dereferencing it."""
    if trajectory_monitor is None:
        return None
    monitor_id = trajectory_monitor.get("monitor_id")
    if isinstance(monitor_id, str) and monitor_id:
        return monitor_id
    return "unknown-trajectory-admissibility-monitor"


def _unique_refs(refs: list[str | None]) -> list[str]:
    """Return ordered, non-empty, unique evidence references."""
    unique: list[str] = []
    for ref in refs:
        if ref and ref not in unique:
            unique.append(ref)
    return unique


def _legitimacy_impact_detected(
    manifest_change: dict[str, Any],
    trajectory_monitor: dict[str, Any] | None,
) -> bool:
    """Classify whether any deterministic v1 legitimacy-impact signal exists."""
    changed_type = manifest_change.get("changed_manifest_type")
    if _string_list(manifest_change.get("legitimacy_impact_flags")):
        return True
    if changed_type in {"root_authority_manifest", "evaluation_function_manifest"}:
        return True

    if trajectory_monitor is None:
        return False

    scope_change = trajectory_monitor.get("admissibility_scope_change")
    if isinstance(scope_change, dict) and scope_change.get("scope_expanded") is True:
        return True

    trajectory_status = trajectory_monitor.get("trajectory_status")
    if trajectory_status in SUSPICIOUS_TRAJECTORY_STATUSES:
        return True

    action = trajectory_monitor.get("recommended_governance_action")
    return isinstance(action, str) and action != "none"


def classify_impact_categories(
    manifest_change: dict[str, Any],
    trajectory_monitor: dict[str, Any] | None = None,
) -> list[str]:
    """Return deterministic Legitimacy Impact Review v1 categories.

    The helper only classifies review signals from local JSON fields. It does
    not determine legitimacy, enforce admissibility, or resolve artifact refs.
    """
    categories: set[str] = set()
    changed_type = manifest_change.get("changed_manifest_type")
    high_risk_evidence = _has_high_risk_evidence(
        manifest_change,
        trajectory_monitor,
    )

    for flag in _string_list(manifest_change.get("legitimacy_impact_flags")):
        category = FLAG_TO_CATEGORY.get(flag)
        if category is not None:
            categories.add(category)

    if changed_type == "root_authority_manifest":
        categories.add("root_authority_changed")
        categories.add("constitutional_trust_anchor_changed")
    if changed_type == "evaluation_function_manifest":
        categories.add("evaluation_behavior_changed")
    if high_risk_evidence:
        categories.add("high_risk_admissibility_expanded")

    if trajectory_monitor is not None:
        scope_change = trajectory_monitor.get("admissibility_scope_change")
        if isinstance(scope_change, dict):
            expansion_type = scope_change.get("expansion_type")
            if scope_change.get("scope_expanded") is True:
                categories.add("authority_scope_expansion")
            if expansion_type == "delegated_authority_expansion":
                categories.add("authority_scope_expansion")
            if expansion_type == "refusal_boundary_relaxation":
                categories.add("refusal_boundary_relaxed")
            if expansion_type == "escalation_requirement_reduction":
                categories.add("escalation_requirement_reduced")

        for signal in _trajectory_risk_signals(trajectory_monitor):
            signal_type = signal.get("signal_type")
            if signal_type == "admissibility_envelope_expansion":
                if high_risk_evidence:
                    categories.add("high_risk_admissibility_expanded")
                else:
                    categories.add("authority_scope_expansion")
            elif signal_type == "delegated_scope_widening":
                categories.add("authority_scope_expansion")
            elif signal_type == "strategic_admissibility_drift":
                if high_risk_evidence:
                    categories.add("high_risk_admissibility_expanded")
                else:
                    categories.add("unknown_legitimacy_impact")

    if not categories:
        categories.add("unknown_legitimacy_impact")
    elif _legitimacy_impact_detected(manifest_change, trajectory_monitor):
        categories.discard("unknown_legitimacy_impact")

    return [category for category in CATEGORY_ORDER if category in categories]


def build_impact_objects(
    manifest_change: dict[str, Any],
    trajectory_monitor: dict[str, Any] | None,
    impact_categories: list[str],
) -> dict[str, dict[str, Any]]:
    """Build schema-shaped impact objects from deterministic categories."""
    category_set = set(impact_categories)
    flags = set(_string_list(manifest_change.get("legitimacy_impact_flags")))
    triggering_ref = _string_value(
        manifest_change.get("receipt_id"),
        "unknown-manifest-change-receipt",
    )
    monitor_ref = _trajectory_monitor_ref(trajectory_monitor)
    approval_refs = _string_list(manifest_change.get("approval_evidence_refs"))
    authority_ref = _string_value(manifest_change.get("authority_evidence_ref"))
    changed_type = manifest_change.get("changed_manifest_type")
    change_reason = _string_value(manifest_change.get("change_reason"))
    changed_by = manifest_change.get("changed_by", {})
    changed_role = ""
    if isinstance(changed_by, dict):
        changed_role = _string_value(changed_by.get("role")).lower()

    authority_scope_expanded = "authority_scope_expansion" in category_set
    trusted_authority_source_changed = (
        "trusted_authority_source_changed" in category_set
        or changed_type == "root_authority_manifest"
    )
    root_authority_changed = (
        "root_authority_changed" in category_set
        or changed_type == "root_authority_manifest"
    )
    human_oversight_weakened = "human_oversight_weakened" in category_set
    escalation_requirement_reduced = (
        "escalation_requirement_reduced" in category_set
    )
    refusal_boundary_relaxed = "refusal_boundary_relaxed" in category_set
    high_risk_scope_expanded = "high_risk_admissibility_expanded" in category_set

    reviewer_authority_changed = root_authority_changed or any(
        role in changed_role for role in REVIEWER_POWER_ROLES
    )
    auditability_reduced = "auditability_reduced" in category_set or _contains_any(
        change_reason,
        {"auditability reduced"},
    )
    replayability_reduced = "replayability_reduced" in category_set or _contains_any(
        change_reason,
        {"replayability reduced"},
    )
    evidence_chain_weakened = _contains_any(
        change_reason,
        {"evidence chain weakened", "receipt requirements reduced"},
    )
    receipt_requirements_reduced = _contains_any(
        change_reason,
        {"receipt requirements reduced"},
    )

    return {
        "authority_impact": {
            "authority_scope_expanded": authority_scope_expanded,
            "trusted_authority_source_changed": trusted_authority_source_changed,
            "root_authority_changed": root_authority_changed,
            "evidence_refs": _unique_refs([authority_ref, triggering_ref, monitor_ref]),
            "explanation": (
                "Authority-impacting signals were detected for reviewer assessment."
                if authority_scope_expanded or trusted_authority_source_changed
                else "No authority scope expansion was detected by the offline helper."
            ),
        },
        "oversight_impact": {
            "human_oversight_weakened": human_oversight_weakened,
            "approval_requirement_reduced": (
                human_oversight_weakened or escalation_requirement_reduced
            ),
            "reviewer_authority_changed": reviewer_authority_changed,
            "evidence_refs": _unique_refs([*approval_refs, triggering_ref]),
            "explanation": (
                "Human oversight or approval requirements may be weakened."
                if human_oversight_weakened or escalation_requirement_reduced
                else "No human oversight weakening was detected by the offline helper."
            ),
        },
        "refusal_boundary_impact": {
            "refusal_boundary_relaxed": refusal_boundary_relaxed,
            "refusal_condition_removed": "refusal_condition_removed" in flags,
            "refusal_condition_changed": refusal_boundary_relaxed
            or "refusal" in change_reason.lower(),
            "evidence_refs": _unique_refs([triggering_ref, monitor_ref]),
            "explanation": (
                "Refusal boundary changes require reviewer assessment."
                if refusal_boundary_relaxed or "refusal" in change_reason.lower()
                else "No refusal boundary relaxation was detected."
            ),
        },
        "escalation_impact": {
            "escalation_requirement_reduced": escalation_requirement_reduced,
            "escalation_path_changed": escalation_requirement_reduced
            or "escalation" in change_reason.lower(),
            "escalation_authority_changed": root_authority_changed
            or authority_scope_expanded,
            "evidence_refs": _unique_refs([triggering_ref, *approval_refs]),
            "explanation": (
                "Escalation requirements or authority may have changed."
                if escalation_requirement_reduced or authority_scope_expanded
                else "No escalation requirement reduction was detected."
            ),
        },
        "auditability_impact": {
            "auditability_reduced": auditability_reduced,
            "replayability_reduced": replayability_reduced,
            "evidence_chain_weakened": evidence_chain_weakened,
            "receipt_requirements_reduced": receipt_requirements_reduced,
            "evidence_refs": [triggering_ref],
            "explanation": (
                "Auditability, replayability, or evidence-chain signals require review."
                if auditability_reduced
                or replayability_reduced
                or evidence_chain_weakened
                else "No auditability reduction was detected."
            ),
        },
        "high_risk_admissibility_impact": {
            "high_risk_scope_expanded": high_risk_scope_expanded,
            "high_risk_controls_weakened": high_risk_scope_expanded
            and (
                human_oversight_weakened
                or refusal_boundary_relaxed
                or escalation_requirement_reduced
            ),
            "high_risk_review_requirement_reduced": high_risk_scope_expanded
            and (human_oversight_weakened or escalation_requirement_reduced),
            "evidence_refs": _unique_refs([triggering_ref, monitor_ref]),
            "explanation": (
                "High-risk admissibility scope expansion signals require review."
                if high_risk_scope_expanded
                else "No high-risk admissibility expansion was detected."
            ),
        },
    }


def classify_review_status(
    legitimacy_impact_detected: bool,
    impact_categories: list[str],
    approval_evidence_refs: list[str],
) -> str:
    """Classify deterministic review status for the draft review."""
    category_set = set(impact_categories)
    if not legitimacy_impact_detected:
        return "not_required"
    if category_set == {"unknown_legitimacy_impact"}:
        return "unresolved"
    if {
        "constitutional_trust_anchor_changed",
        "root_authority_changed",
    } & category_set:
        return "requires_external_review"
    if not approval_evidence_refs:
        return "required"
    if approval_evidence_refs:
        return "pending"
    return "not_required"


def classify_recommended_governance_action(
    legitimacy_impact_detected: bool,
    impact_categories: list[str],
    rollback_conditions: list[str],
) -> str:
    """Classify deterministic recommended governance action by priority."""
    category_set = set(impact_categories)
    if {
        "constitutional_trust_anchor_changed",
        "root_authority_changed",
    } & category_set:
        return "external_audit_flag"
    if {
        "authority_scope_expansion",
        "high_risk_admissibility_expanded",
    } <= category_set:
        return "multi_party_review"
    if rollback_conditions and category_set & HIGH_SEVERITY_CATEGORIES:
        return "rollback"
    if {
        "authority_scope_expansion",
        "trusted_authority_source_changed",
    } & category_set:
        return "requalify_authority"
    if "evaluation_behavior_changed" in category_set:
        return "requalify_evaluator"
    if {
        "human_oversight_weakened",
        "refusal_boundary_relaxed",
        "escalation_requirement_reduced",
    } & category_set:
        return "escalate"
    if legitimacy_impact_detected:
        return "review"
    return "none"


def _reviewed_artifact_type(manifest_change: dict[str, Any]) -> str:
    """Map a changed manifest type to a review artifact type."""
    changed_type = manifest_change.get("changed_manifest_type")
    if not isinstance(changed_type, str):
        return "other_governance_artifact"
    return MANIFEST_TYPE_TO_ARTIFACT_TYPE.get(
        changed_type,
        "other_governance_artifact",
    )


def _review_summary(
    legitimacy_impact_detected: bool,
    impact_categories: list[str],
    review_status: str,
    action: str,
) -> str:
    """Build a concise non-certifying review summary."""
    if not legitimacy_impact_detected:
        return (
            "No deterministic v1 legitimacy-impact signal was detected; this "
            "offline helper does not prove legitimacy or certify compliance."
        )
    categories = ", ".join(impact_categories)
    return (
        "Draft offline review surfaced legitimacy-impacting signals "
        f"({categories}); status={review_status}, recommended_action={action}. "
        "This is reviewable evidence only, not an automatic legitimacy or "
        "compliance determination."
    )


def generate_legitimacy_impact_review(
    manifest_change: dict[str, Any],
    trajectory_monitor: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate a schema-shaped draft Legitimacy Impact Review v1 object."""
    impact_categories = classify_impact_categories(
        manifest_change,
        trajectory_monitor,
    )
    legitimacy_impact_detected = _legitimacy_impact_detected(
        manifest_change,
        trajectory_monitor,
    )
    if not legitimacy_impact_detected and not impact_categories:
        impact_categories = ["unknown_legitimacy_impact"]

    approval_refs = _string_list(manifest_change.get("approval_evidence_refs"))
    rollback_conditions = _string_list(manifest_change.get("rollback_conditions"))
    review_status = classify_review_status(
        legitimacy_impact_detected,
        impact_categories,
        approval_refs,
    )
    action = classify_recommended_governance_action(
        legitimacy_impact_detected,
        impact_categories,
        rollback_conditions,
    )
    review = {
        "schema_version": "legitimacy-impact-review-v1",
        "review_id": REVIEW_ID,
        "issued_at": ISSUED_AT,
        "reviewed_artifact_type": _reviewed_artifact_type(manifest_change),
        "reviewed_artifact_ref": _string_value(
            manifest_change.get("changed_manifest_id"),
            UNKNOWN_REF,
        ),
        "reviewed_artifact_hash": _string_value(
            manifest_change.get("new_manifest_hash"),
            UNKNOWN_HASH,
        ),
        "triggering_change_ref": _string_value(
            manifest_change.get("receipt_id"),
            "unknown-manifest-change-receipt",
        ),
        "triggering_change_hash": canonical_json_hash(manifest_change),
        "legitimacy_impact_detected": legitimacy_impact_detected,
        "impact_categories": impact_categories,
        **build_impact_objects(
            manifest_change,
            trajectory_monitor,
            impact_categories,
        ),
        "review_status": review_status,
        "recommended_governance_action": action,
        "review_summary": _review_summary(
            legitimacy_impact_detected,
            impact_categories,
            review_status,
            action,
        ),
    }
    review["review_hash"] = canonical_json_hash(review)
    return review


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Generate a non-enforcing draft Legitimacy Impact Review v1 from "
            "local governance artifacts."
        )
    )
    parser.add_argument(
        "--manifest-change",
        required=True,
        type=Path,
        help="Path to a Manifest Change Receipt v1 JSON file.",
    )
    parser.add_argument(
        "--trajectory-monitor",
        type=Path,
        help="Optional Trajectory-Level Admissibility Monitor v1 JSON file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional output path. Prints JSON to stdout when omitted.",
    )
    return parser.parse_args()


def main() -> int:
    """CLI entry point for the offline Legitimacy Impact Review helper."""
    args = _parse_args()

    try:
        manifest_change = _load_json_object(args.manifest_change)
        _validate_against_schema(
            manifest_change,
            MANIFEST_CHANGE_RECEIPT_SCHEMA_PATH,
        )
        trajectory_monitor = None
        if args.trajectory_monitor is not None:
            trajectory_monitor = _load_json_object(args.trajectory_monitor)
            _validate_against_schema(
                trajectory_monitor,
                TRAJECTORY_ADMISSIBILITY_MONITOR_SCHEMA_PATH,
            )

        review = generate_legitimacy_impact_review(
            manifest_change,
            trajectory_monitor,
        )
        _validate_against_schema(review, LEGITIMACY_IMPACT_REVIEW_SCHEMA_PATH)
    except Exception as exc:  # noqa: BLE001 - CLI should present concise errors.
        print(f"error: {exc}", file=sys.stderr)
        return 1

    output = json.dumps(review, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(output, end="")
    else:
        args.output.write_text(output, encoding="utf-8")
        print(
            "Generated Legitimacy Impact Review v1: "
            f"{review['review_id']} -> {args.output}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
