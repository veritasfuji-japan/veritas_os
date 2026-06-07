#!/usr/bin/env python3
"""Generate a draft Evaluation Drift Detection from attribution JSON.

This offline demo helper is intentionally schema-shaped and non-enforcing. It
reads one local Outcome Delta Attribution v1 JSON object, classifies drift
signals deterministically, and optionally validates input and output with
``jsonschema`` when that package is available locally. It never dereferences
artifact references, accesses the network, or connects to runtime admissibility
paths.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO_ROOT / "docs/en/demo/schemas"
OUTCOME_DELTA_ATTRIBUTION_SCHEMA_PATH = (
    SCHEMA_DIR / "outcome-delta-attribution-v1.schema.json"
)
EVALUATION_DRIFT_DETECTION_SCHEMA_PATH = (
    SCHEMA_DIR / "evaluation-drift-detection-v1.schema.json"
)
DETECTION_ID = "evaluation-drift-detection-example-001"
ISSUED_AT = "2026-01-01T00:00:00Z"

DRIFT_CAUSE_TYPE_BY_ATTRIBUTION_CAUSE = {
    "unexplained_evaluation_drift": "unexplained_evaluation_drift",
    "unauthorized_determiner_influence": "unauthorized_determiner_influence",
    "evaluator_version_changed": "evaluator_version_changed",
    "rule_version_changed": "rule_version_changed",
    "policy_identity_changed": "policy_identity_changed",
    "threshold_state_changed": "threshold_state_changed",
    "refusal_boundary_changed": "refusal_boundary_changed",
    "escalation_resolver_changed": "escalation_resolver_changed",
    "material_context_changed": "material_context_ambiguous",
    "qualifier_freshness_changed": "qualifier_state_ambiguous",
}
DRIFT_LIKE_CAUSE_TYPES = {
    "unexplained_evaluation_drift",
    "unauthorized_determiner_influence",
    "evaluator_version_changed",
    "rule_version_changed",
    "policy_identity_changed",
    "threshold_state_changed",
    "refusal_boundary_changed",
    "escalation_resolver_changed",
}
CONTEXT_OR_QUALIFIER_CAUSE_TYPES = {
    "material_context_changed",
    "qualifier_freshness_changed",
}
DEFAULT_SEVERITY_BY_DRIFT_CAUSE_TYPE = {
    "unexplained_evaluation_drift": "high",
    "unauthorized_determiner_influence": "high",
    "evaluator_version_changed": "medium",
    "rule_version_changed": "medium",
    "policy_identity_changed": "medium",
    "threshold_state_changed": "medium",
    "refusal_boundary_changed": "high",
    "escalation_resolver_changed": "medium",
    "material_context_ambiguous": "medium",
    "qualifier_state_ambiguous": "medium",
    "attribution_inconclusive": "medium",
}
ACTION_BY_ATTRIBUTION_ACTION = {
    "none": "none",
    "review": "review",
    "requalify": "requalify_evaluator",
    "escalate": "escalate",
    "refuse": "refuse",
    "mark_evaluation_drift": "mark_evaluation_drift",
    "mark_non_deterministically_governed": (
        "mark_non_deterministically_governed"
    ),
}


@dataclass(frozen=True)
class DriftClassification:
    """Computed drift classification fields for a detection artifact."""

    drift_detected: bool
    drift_status: str
    evaluator_consistency_status: str
    explanation_status: str
    recommended_governance_action: str


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


def _canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    """Return deterministic UTF-8 JSON bytes for hashing."""
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256_json(payload: dict[str, Any]) -> str:
    """Return the SHA-256 hex digest of canonical JSON."""
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _delta_causes(attribution: dict[str, Any]) -> list[dict[str, Any]]:
    """Return well-shaped delta cause dictionaries from an attribution."""
    causes = attribution.get("delta_causes", [])
    if not isinstance(causes, list):
        return []
    return [cause for cause in causes if isinstance(cause, dict)]


def _cause_types(attribution: dict[str, Any]) -> set[str]:
    """Return the set of string cause types in an attribution."""
    cause_types = set()
    for cause in _delta_causes(attribution):
        cause_type = cause.get("cause_type")
        if isinstance(cause_type, str):
            cause_types.add(cause_type)
    return cause_types


def _attribution_action(attribution: dict[str, Any]) -> str:
    """Map attribution governance action into detection governance action."""
    action = attribution.get("recommended_governance_action")
    if isinstance(action, str):
        return ACTION_BY_ATTRIBUTION_ACTION.get(action, "review")
    return "review"


def _has_unresolved_delta(attribution: dict[str, Any]) -> bool:
    """Return whether the attribution reports an unresolved delta."""
    unresolved_delta = attribution.get("unresolved_delta", {})
    if not isinstance(unresolved_delta, dict):
        return False
    return unresolved_delta.get("present") is True


def classify_drift(attribution: dict[str, Any]) -> DriftClassification:
    """Classify attribution causes into Evaluation Drift Detection fields.

    Args:
        attribution: Outcome Delta Attribution v1 JSON object.

    Returns:
        Deterministic drift classification for the generated detection object.
    """
    cause_types = _cause_types(attribution)
    outcome_changed = attribution.get("outcome_changed") is True
    has_drift_like_causes = bool(cause_types & DRIFT_LIKE_CAUSE_TYPES)

    if "unexplained_evaluation_drift" in cause_types:
        return DriftClassification(
            drift_detected=True,
            drift_status="unexplained",
            evaluator_consistency_status="inconsistent",
            explanation_status="unexplained",
            recommended_governance_action="mark_evaluation_drift",
        )
    if "unauthorized_determiner_influence" in cause_types:
        return DriftClassification(
            drift_detected=True,
            drift_status="confirmed",
            evaluator_consistency_status="inconsistent",
            explanation_status="requires_review",
            recommended_governance_action="escalate",
        )
    if _has_unresolved_delta(attribution):
        return DriftClassification(
            drift_detected=True,
            drift_status="non_deterministically_governed",
            evaluator_consistency_status="unknown",
            explanation_status="requires_review",
            recommended_governance_action="mark_non_deterministically_governed",
        )
    if "evaluator_version_changed" in cause_types:
        return DriftClassification(
            drift_detected=True,
            drift_status="suspected",
            evaluator_consistency_status="unknown",
            explanation_status="partially_explained",
            recommended_governance_action="requalify_evaluator",
        )
    if cause_types & {
        "rule_version_changed",
        "policy_identity_changed",
        "threshold_state_changed",
    }:
        return DriftClassification(
            drift_detected=True,
            drift_status="suspected",
            evaluator_consistency_status="unknown",
            explanation_status="partially_explained",
            recommended_governance_action=_attribution_action(attribution),
        )
    if cause_types & {
        "refusal_boundary_changed",
        "escalation_resolver_changed",
    }:
        return DriftClassification(
            drift_detected=True,
            drift_status="suspected",
            evaluator_consistency_status="unknown",
            explanation_status="requires_review",
            recommended_governance_action=_attribution_action(attribution),
        )
    if cause_types and cause_types <= CONTEXT_OR_QUALIFIER_CAUSE_TYPES:
        return DriftClassification(
            drift_detected=False,
            drift_status="not_detected",
            evaluator_consistency_status="not_comparable",
            explanation_status="fully_explained",
            recommended_governance_action="review" if outcome_changed else "none",
        )
    if not outcome_changed and not has_drift_like_causes:
        return DriftClassification(
            drift_detected=False,
            drift_status="not_detected",
            evaluator_consistency_status="consistent",
            explanation_status="fully_explained",
            recommended_governance_action="none",
        )
    return DriftClassification(
        drift_detected=False,
        drift_status="not_detected",
        evaluator_consistency_status="not_comparable",
        explanation_status="fully_explained",
        recommended_governance_action=_attribution_action(attribution),
    )


def _drift_cause_from_delta_cause(cause: dict[str, Any]) -> dict[str, Any] | None:
    """Map one attribution delta cause into one drift detection cause."""
    attribution_cause_type = cause.get("cause_type")
    if not isinstance(attribution_cause_type, str):
        return None

    drift_cause_type = DRIFT_CAUSE_TYPE_BY_ATTRIBUTION_CAUSE.get(
        attribution_cause_type
    )
    if drift_cause_type is None:
        return None

    severity = cause.get("severity")
    if not isinstance(severity, str):
        severity = DEFAULT_SEVERITY_BY_DRIFT_CAUSE_TYPE[drift_cause_type]

    evidence_refs = cause.get("evidence_refs")
    if not isinstance(evidence_refs, list):
        evidence_refs = []
    evidence_refs = [ref for ref in evidence_refs if isinstance(ref, str) and ref]

    explanation = cause.get("explanation")
    if not isinstance(explanation, str) or not explanation:
        explanation = f"Attribution reported {attribution_cause_type}."

    return {
        "cause_type": drift_cause_type,
        "severity": severity,
        "evidence_refs": evidence_refs,
        "explanation": explanation,
    }


def _drift_causes(attribution: dict[str, Any]) -> list[dict[str, Any]]:
    """Build a non-empty, schema-shaped drift cause list."""
    drift_causes = []
    seen = set()
    for cause in _delta_causes(attribution):
        drift_cause = _drift_cause_from_delta_cause(cause)
        if drift_cause is None:
            continue
        cause_type = drift_cause["cause_type"]
        if cause_type in seen:
            continue
        seen.add(cause_type)
        drift_causes.append(drift_cause)

    if drift_causes:
        return drift_causes

    attribution_id = attribution.get("attribution_id", "unknown-attribution")
    evidence_refs = [attribution_id] if isinstance(attribution_id, str) else []
    return [
        {
            "cause_type": "attribution_inconclusive",
            "severity": DEFAULT_SEVERITY_BY_DRIFT_CAUSE_TYPE[
                "attribution_inconclusive"
            ],
            "evidence_refs": evidence_refs,
            "explanation": (
                "No v1 drift-specific attribution cause was present; the "
                "draft detection records a neutral inconclusive cause to "
                "satisfy the schema shape."
            ),
        }
    ]


def _summary(
    attribution: dict[str, Any], classification: DriftClassification
) -> str:
    """Build a concise human-readable drift detection summary."""
    prior_outcome = attribution.get("prior_outcome", "unknown")
    current_outcome = attribution.get("current_outcome", "unknown")
    if classification.drift_detected:
        return (
            f"Draft detection marked {classification.drift_status} drift "
            f"from {prior_outcome} to {current_outcome}."
        )
    return (
        "Draft detection did not detect evaluator drift from "
        f"{prior_outcome} to {current_outcome}."
    )


def generate_evaluation_drift_detection(
    attribution: dict[str, Any]
) -> dict[str, Any]:
    """Generate a schema-shaped Evaluation Drift Detection v1 object.

    Args:
        attribution: Outcome Delta Attribution v1 JSON object.

    Returns:
        Deterministic Evaluation Drift Detection v1 JSON object.

    Raises:
        jsonschema.ValidationError: If ``jsonschema`` is available and the
            attribution or generated detection does not validate locally.
    """
    _validate_against_schema(attribution, OUTCOME_DELTA_ATTRIBUTION_SCHEMA_PATH)

    classification = classify_drift(attribution)
    attribution_id = attribution.get("attribution_id", "unknown-attribution")
    prior_ref = attribution.get(
        "prior_evaluation_receipt_ref", "unknown-prior-evaluation-receipt"
    )
    current_ref = attribution.get(
        "current_evaluation_receipt_ref", "unknown-current-evaluation-receipt"
    )
    detection: dict[str, Any] = {
        "schema_version": "evaluation-drift-detection-v1",
        "detection_id": DETECTION_ID,
        "issued_at": ISSUED_AT,
        "outcome_delta_attribution_ref": str(attribution_id),
        "outcome_delta_attribution_hash": _sha256_json(attribution),
        "prior_evaluation_receipt_ref": str(prior_ref),
        "current_evaluation_receipt_ref": str(current_ref),
        "drift_detected": classification.drift_detected,
        "drift_status": classification.drift_status,
        "drift_causes": _drift_causes(attribution),
        "evaluator_consistency_status": (
            classification.evaluator_consistency_status
        ),
        "explanation_status": classification.explanation_status,
        "recommended_governance_action": (
            classification.recommended_governance_action
        ),
        "detection_summary": _summary(attribution, classification),
        "detection_hash": "0" * 64,
    }
    detection_without_hash = dict(detection)
    detection_without_hash.pop("detection_hash")
    detection["detection_hash"] = _sha256_json(detection_without_hash)

    _validate_against_schema(detection, EVALUATION_DRIFT_DETECTION_SCHEMA_PATH)
    return detection


def _parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Generate a draft Evaluation Drift Detection v1 JSON object from "
            "one local Outcome Delta Attribution v1 JSON file."
        )
    )
    parser.add_argument("--attribution", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    """Run the CLI and return a process exit code."""
    args = _parse_args()
    try:
        attribution = _load_json_object(args.attribution)
        detection = generate_evaluation_drift_detection(attribution)
        output = json.dumps(detection, indent=2, ensure_ascii=False)
        if args.output is None:
            print(output)
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(f"{output}\n", encoding="utf-8")
            print(
                "Generated Evaluation Drift Detection v1: "
                f"{args.output} "
                f"(status={detection['drift_status']}, "
                f"causes={len(detection['drift_causes'])})"
            )
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
