#!/usr/bin/env python3
"""Generate a draft Trajectory-Level Admissibility Monitor.

This offline demo helper is intentionally schema-shaped and non-enforcing. It
reads local Evaluation Receipt v1, Outcome Delta Attribution v1, and Evaluation
Drift Detection v1 JSON objects, summarizes deterministic trajectory-level
signals, and optionally validates inputs and output with ``jsonschema`` when
that package is available locally. It never dereferences artifact references,
accesses the network, or connects to runtime admissibility paths.
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
EVALUATION_RECEIPT_SCHEMA_PATH = SCHEMA_DIR / "evaluation-receipt-v1.schema.json"
OUTCOME_DELTA_ATTRIBUTION_SCHEMA_PATH = (
    SCHEMA_DIR / "outcome-delta-attribution-v1.schema.json"
)
EVALUATION_DRIFT_DETECTION_SCHEMA_PATH = (
    SCHEMA_DIR / "evaluation-drift-detection-v1.schema.json"
)
TRAJECTORY_ADMISSIBILITY_MONITOR_SCHEMA_PATH = (
    SCHEMA_DIR / "trajectory-admissibility-monitor-v1.schema.json"
)

ISSUED_AT = "2026-01-01T00:00:00Z"
MONITOR_ID = "trajectory-admissibility-monitor-example-001"
TRAJECTORY_ID = "trajectory-admissibility-monitor-example-001"
UNKNOWN_AUTHORITY_EVIDENCE = "unknown-authority-evidence"

SCOPE_EXPANDING_CAUSE_TYPES = {
    "authority_state_changed",
    "threshold_state_changed",
    "refusal_boundary_changed",
    "escalation_resolver_changed",
}
DRIFT_SCOPE_EXPANDING_STATUSES = {
    "suspected",
    "confirmed",
    "unexplained",
    "non_deterministically_governed",
}
MORE_PERMISSIVE_RANK = {
    "refuse": 0,
    "escalate": 1,
    "allow": 2,
}
RISK_SIGNAL_SEVERITY = {
    "admissibility_envelope_expansion": "high",
    "delegated_scope_widening": "high",
    "permissive_requalification_trend": "medium",
    "low_risk_event_accumulation": "medium",
    "continuity_as_authorization_risk": "medium",
    "strategic_admissibility_drift": "high",
    "governance_exhaustion_signal": "medium",
    "unexplained_trajectory_shift": "high",
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
    """Return non-empty strings from a JSON value when it is a list."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _receipt_id(receipt: dict[str, Any]) -> str:
    """Return a stable receipt reference without dereferencing artifacts."""
    receipt_id = receipt.get("receipt_id")
    if isinstance(receipt_id, str) and receipt_id:
        return receipt_id
    return "unknown-evaluation-receipt"


def _attribution_id(attribution: dict[str, Any]) -> str:
    """Return a stable attribution reference without dereferencing artifacts."""
    attribution_id = attribution.get("attribution_id")
    if isinstance(attribution_id, str) and attribution_id:
        return attribution_id
    return "unknown-outcome-delta-attribution"


def _detection_id(detection: dict[str, Any]) -> str:
    """Return a stable detection reference without dereferencing artifacts."""
    detection_id = detection.get("detection_id")
    if isinstance(detection_id, str) and detection_id:
        return detection_id
    return "unknown-evaluation-drift-detection"


def _authority_evidence_refs(receipt: dict[str, Any]) -> list[str]:
    """Return local authority evidence refs from a receipt."""
    return _string_list(receipt.get("authority_evidence_refs"))


def _authority_scope(receipt: dict[str, Any], scope_id: str) -> dict[str, str]:
    """Build a schema-shaped authority scope from receipt evidence refs."""
    evidence_refs = _authority_evidence_refs(receipt)
    authority_evidence_ref = (
        evidence_refs[0] if evidence_refs else UNKNOWN_AUTHORITY_EVIDENCE
    )
    return {
        "scope_id": scope_id,
        "scope_hash": canonical_json_hash(evidence_refs),
        "authority_evidence_ref": authority_evidence_ref,
    }


def _delta_causes(attribution: dict[str, Any]) -> list[dict[str, Any]]:
    """Return well-shaped delta cause dictionaries from an attribution."""
    causes = attribution.get("delta_causes", [])
    if not isinstance(causes, list):
        return []
    return [cause for cause in causes if isinstance(cause, dict)]


def _cause_types(attributions: list[dict[str, Any]]) -> set[str]:
    """Return all delta cause types observed across attribution artifacts."""
    cause_types = set()
    for attribution in attributions:
        for cause in _delta_causes(attribution):
            cause_type = cause.get("cause_type")
            if isinstance(cause_type, str):
                cause_types.add(cause_type)
    return cause_types


def _drift_statuses(drift_detections: list[dict[str, Any]]) -> set[str]:
    """Return all drift statuses observed across detection artifacts."""
    statuses = set()
    for detection in drift_detections:
        drift_status = detection.get("drift_status")
        if isinstance(drift_status, str):
            statuses.add(drift_status)
    return statuses


def _more_permissive_outcome_trend(receipts: list[dict[str, Any]]) -> bool:
    """Return true when receipt outcomes become more permissive over time."""
    ranks = []
    for receipt in receipts:
        outcome = receipt.get("outcome")
        if isinstance(outcome, str) and outcome in MORE_PERMISSIVE_RANK:
            ranks.append(MORE_PERMISSIVE_RANK[outcome])
    return any(
        current > prior
        for prior, current in zip(ranks, ranks[1:], strict=False)
    )


def _reauthorization_evidence_refs(
    attributions: list[dict[str, Any]],
) -> list[str]:
    """Return attribution evidence refs that mention reauthorization."""
    refs = []
    seen = set()
    for attribution in attributions:
        for cause in _delta_causes(attribution):
            for evidence_ref in _string_list(cause.get("evidence_refs")):
                if "reauthorization" not in evidence_ref.lower():
                    continue
                if evidence_ref in seen:
                    continue
                seen.add(evidence_ref)
                refs.append(evidence_ref)
    return refs


def _expansion_type(
    evidence_changed: bool,
    cause_types: set[str],
    scope_expanded: bool,
    increasingly_permissive: bool,
) -> str:
    """Classify the first applicable v1 expansion type."""
    if not scope_expanded:
        return "none"
    if evidence_changed or "authority_state_changed" in cause_types:
        return "delegated_authority_expansion"
    if "threshold_state_changed" in cause_types:
        return "threshold_expansion"
    if "refusal_boundary_changed" in cause_types:
        return "refusal_boundary_relaxation"
    if "escalation_resolver_changed" in cause_types:
        return "escalation_requirement_reduction"
    if "material_context_changed" in cause_types and increasingly_permissive:
        return "contextual_scope_expansion"
    return "unknown"


def detect_scope_change(
    receipts: list[dict[str, Any]],
    attributions: list[dict[str, Any]] | None = None,
    drift_detections: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Detect deterministic v1 admissibility scope change signals.

    Args:
        receipts: Evaluation Receipt v1 JSON objects in trajectory order.
        attributions: Outcome Delta Attribution v1 JSON objects.
        drift_detections: Evaluation Drift Detection v1 JSON objects.

    Returns:
        Schema-shaped admissibility scope change summary.
    """
    attributions = attributions or []
    drift_detections = drift_detections or []
    first_refs = _authority_evidence_refs(receipts[0])
    last_refs = _authority_evidence_refs(receipts[-1])
    evidence_changed = first_refs != last_refs
    cause_types = _cause_types(attributions)
    drift_statuses = _drift_statuses(drift_detections)
    increasingly_permissive = _more_permissive_outcome_trend(receipts)
    scope_expanded = any(
        (
            evidence_changed,
            bool(cause_types & SCOPE_EXPANDING_CAUSE_TYPES),
            bool(drift_statuses & DRIFT_SCOPE_EXPANDING_STATUSES),
            increasingly_permissive,
        )
    )
    reauthorization_refs = _reauthorization_evidence_refs(attributions)

    return {
        "scope_expanded": scope_expanded,
        "expansion_type": _expansion_type(
            evidence_changed,
            cause_types,
            scope_expanded,
            increasingly_permissive,
        ),
        "explicit_reauthorization_present": bool(reauthorization_refs),
        "reauthorization_evidence_refs": reauthorization_refs,
    }


def summarize_continuity_events(
    receipts: list[dict[str, Any]],
    attributions: list[dict[str, Any]] | None = None,
    drift_detections: list[dict[str, Any]] | None = None,
) -> dict[str, int]:
    """Summarize deterministic v1 continuity event counts."""
    attributions = attributions or []
    drift_detections = drift_detections or []
    cause_type_sets = [_cause_types([attribution]) for attribution in attributions]

    low_risk_events_count = 0
    escalation_events_count = 0
    for receipt in receipts:
        consequence_class = receipt.get("consequence_class", {})
        class_label = ""
        if isinstance(consequence_class, dict):
            label = consequence_class.get("class_label")
            if isinstance(label, str):
                class_label = label.lower()
        if class_label in {"low", "medium"}:
            low_risk_events_count += 1
        if receipt.get("outcome") == "escalate":
            escalation_events_count += 1

    material_change_events_count = sum(
        1
        for cause_types in cause_type_sets
        if cause_types & {"material_context_changed", "consequence_class_changed"}
    )
    requalification_events_count = sum(
        1
        for detection in drift_detections
        if detection.get("recommended_governance_action")
        in {"requalify_evaluator", "reconcile_qualifiers"}
    )
    escalation_events_count += sum(
        1
        for detection in drift_detections
        if detection.get("recommended_governance_action") == "escalate"
    )

    return {
        "continuity_events_observed": len(receipts),
        "low_risk_events_count": low_risk_events_count,
        "material_change_events_count": material_change_events_count,
        "requalification_events_count": requalification_events_count,
        "escalation_events_count": escalation_events_count,
    }


def _signal(
    signal_type: str,
    evidence_refs: list[str],
    explanation: str,
) -> dict[str, Any]:
    """Build a schema-shaped trajectory risk signal."""
    return {
        "signal_type": signal_type,
        "severity": RISK_SIGNAL_SEVERITY[signal_type],
        "evidence_refs": evidence_refs,
        "explanation": explanation,
    }


def generate_risk_signals(
    receipts: list[dict[str, Any]],
    attributions: list[dict[str, Any]] | None = None,
    drift_detections: list[dict[str, Any]] | None = None,
    scope_change: dict[str, Any] | None = None,
    continuity_summary: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    """Generate deterministic v1 trajectory risk signals."""
    attributions = attributions or []
    drift_detections = drift_detections or []
    scope_change = scope_change or detect_scope_change(
        receipts, attributions, drift_detections
    )
    continuity_summary = continuity_summary or summarize_continuity_events(
        receipts, attributions, drift_detections
    )
    receipt_refs = [_receipt_id(receipt) for receipt in receipts]
    attribution_refs = [_attribution_id(attribution) for attribution in attributions]
    detection_refs = [_detection_id(detection) for detection in drift_detections]
    cause_types = _cause_types(attributions)
    drift_statuses = _drift_statuses(drift_detections)
    first_refs = _authority_evidence_refs(receipts[0])
    last_refs = _authority_evidence_refs(receipts[-1])
    signals = []

    if scope_change["scope_expanded"] is True:
        signals.append(
            _signal(
                "admissibility_envelope_expansion",
                receipt_refs + attribution_refs + detection_refs,
                "The v1 helper observed trajectory-level scope expansion.",
            )
        )
    if "authority_state_changed" in cause_types or first_refs != last_refs:
        signals.append(
            _signal(
                "delegated_scope_widening",
                receipt_refs + attribution_refs,
                "Authority evidence or authority state changed over time.",
            )
        )
    if _more_permissive_outcome_trend(receipts):
        signals.append(
            _signal(
                "permissive_requalification_trend",
                receipt_refs,
                "Evaluation outcomes became more permissive over time.",
            )
        )
    if (
        continuity_summary["low_risk_events_count"] >= 2
        and continuity_summary["continuity_events_observed"] >= 3
    ):
        signals.append(
            _signal(
                "low_risk_event_accumulation",
                receipt_refs,
                "Multiple low or medium risk events accumulated in one trajectory.",
            )
        )
    if (
        continuity_summary["continuity_events_observed"] >= 3
        and scope_change["explicit_reauthorization_present"] is False
    ):
        signals.append(
            _signal(
                "continuity_as_authorization_risk",
                receipt_refs,
                "Repeated continuity events lacked explicit reauthorization evidence.",
            )
        )
    if scope_change["scope_expanded"] is True and (
        len(attributions) >= 2 or len(drift_detections) >= 2
    ):
        signals.append(
            _signal(
                "strategic_admissibility_drift",
                attribution_refs + detection_refs,
                "Scope expansion appeared across repeated attribution or drift artifacts.",
            )
        )
    if (
        continuity_summary["escalation_events_count"] >= 2
        or continuity_summary["requalification_events_count"] >= 2
    ):
        signals.append(
            _signal(
                "governance_exhaustion_signal",
                receipt_refs + detection_refs,
                "Repeated escalation or requalification events were observed.",
            )
        )
    if drift_statuses & {"unexplained", "non_deterministically_governed"}:
        signals.append(
            _signal(
                "unexplained_trajectory_shift",
                detection_refs,
                "A drift detection reported unexplained or non-deterministic governance.",
            )
        )

    return signals


def classify_trajectory_status(
    risk_signals: list[dict[str, Any]],
    drift_detections: list[dict[str, Any]] | None = None,
    scope_change: dict[str, Any] | None = None,
) -> str:
    """Classify trajectory status using the v1 priority order."""
    drift_detections = drift_detections or []
    drift_statuses = _drift_statuses(drift_detections)
    signal_types = {
        signal.get("signal_type")
        for signal in risk_signals
        if isinstance(signal, dict)
    }
    severities = {
        signal.get("severity") for signal in risk_signals if isinstance(signal, dict)
    }
    scope_expanded = bool(scope_change and scope_change.get("scope_expanded"))

    if "non_deterministically_governed" in drift_statuses:
        return "non_deterministically_governed"
    if drift_statuses & {"confirmed", "unexplained"}:
        return "drift_detected"
    if "strategic_admissibility_drift" in signal_types:
        return "strategically_shaped"
    if scope_expanded or "high" in severities:
        return "suspicious"
    if "medium" in severities:
        return "watch"
    return "stable"


def _recommended_governance_action(
    trajectory_status: str,
    risk_signals: list[dict[str, Any]],
) -> str:
    """Map trajectory status and risk signals to a draft governance action."""
    signal_types = {
        signal.get("signal_type")
        for signal in risk_signals
        if isinstance(signal, dict)
    }
    if trajectory_status == "non_deterministically_governed":
        return "mark_non_deterministically_governed"
    if trajectory_status == "strategically_shaped":
        return "mark_strategic_admissibility_drift"
    if trajectory_status == "drift_detected":
        return "requalify_trajectory"
    if "delegated_scope_widening" in signal_types:
        return "reconcile_authority_scope"
    if trajectory_status in {"suspicious", "watch"}:
        return "review"
    return "none"


def _monitor_summary(
    receipt_count: int,
    attribution_count: int,
    drift_detection_count: int,
    scope_change: dict[str, Any],
) -> str:
    """Build a concise human-readable monitor summary."""
    summary = (
        f"Trajectory monitor observed {receipt_count} evaluation receipts, "
        f"{attribution_count} outcome delta attributions, and "
        f"{drift_detection_count} drift detections."
    )
    if scope_change["scope_expanded"] is True:
        return (
            f"{summary} Authority scope changed across the trajectory and "
            "repeated continuity events may indicate admissibility envelope "
            "expansion."
        )
    return f"{summary} No v1 admissibility scope expansion was detected."


def _trajectory_window(receipts: list[dict[str, Any]]) -> dict[str, Any]:
    """Build trajectory window from receipt issued_at values."""
    issued_at_values = []
    for receipt in receipts:
        issued_at = receipt.get("issued_at")
        if isinstance(issued_at, str) and issued_at:
            issued_at_values.append(issued_at)
    if not issued_at_values:
        raise ValueError("evaluation receipts must include issued_at values")
    return {
        "started_at": min(issued_at_values),
        "ended_at": max(issued_at_values),
        "evaluation_count": len(receipts),
    }


def generate_trajectory_admissibility_monitor(
    evaluation_receipts: list[dict[str, Any]],
    attributions: list[dict[str, Any]] | None = None,
    drift_detections: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Generate a Trajectory-Level Admissibility Monitor v1 object.

    Args:
        evaluation_receipts: One or more Evaluation Receipt v1 JSON objects.
        attributions: Zero or more Outcome Delta Attribution v1 JSON objects.
        drift_detections: Zero or more Evaluation Drift Detection v1 JSON objects.

    Returns:
        Deterministic Trajectory-Level Admissibility Monitor v1 JSON object.

    Raises:
        ValueError: If no evaluation receipts are provided.
        jsonschema.ValidationError: If ``jsonschema`` is available and an input
            artifact or generated monitor does not validate locally.
    """
    if not evaluation_receipts:
        raise ValueError("at least one evaluation receipt is required")

    attributions = attributions or []
    drift_detections = drift_detections or []
    for receipt in evaluation_receipts:
        _validate_against_schema(receipt, EVALUATION_RECEIPT_SCHEMA_PATH)
    for attribution in attributions:
        _validate_against_schema(
            attribution, OUTCOME_DELTA_ATTRIBUTION_SCHEMA_PATH
        )
    for detection in drift_detections:
        _validate_against_schema(
            detection, EVALUATION_DRIFT_DETECTION_SCHEMA_PATH
        )

    scope_change = detect_scope_change(
        evaluation_receipts, attributions, drift_detections
    )
    continuity_summary = summarize_continuity_events(
        evaluation_receipts, attributions, drift_detections
    )
    risk_signals = generate_risk_signals(
        evaluation_receipts,
        attributions,
        drift_detections,
        scope_change,
        continuity_summary,
    )
    trajectory_status = classify_trajectory_status(
        risk_signals, drift_detections, scope_change
    )
    monitor: dict[str, Any] = {
        "schema_version": "trajectory-admissibility-monitor-v1",
        "monitor_id": MONITOR_ID,
        "issued_at": ISSUED_AT,
        "trajectory_id": TRAJECTORY_ID,
        "evaluation_receipt_refs": [
            _receipt_id(receipt) for receipt in evaluation_receipts
        ],
        "outcome_delta_attribution_refs": [
            _attribution_id(attribution) for attribution in attributions
        ],
        "evaluation_drift_detection_refs": [
            _detection_id(detection) for detection in drift_detections
        ],
        "trajectory_window": _trajectory_window(evaluation_receipts),
        "baseline_authority_scope": _authority_scope(
            evaluation_receipts[0], "baseline-authority-scope"
        ),
        "current_authority_scope": _authority_scope(
            evaluation_receipts[-1], "current-authority-scope"
        ),
        "admissibility_scope_change": scope_change,
        "continuity_event_summary": continuity_summary,
        "trajectory_risk_signals": risk_signals,
        "trajectory_status": trajectory_status,
        "recommended_governance_action": _recommended_governance_action(
            trajectory_status, risk_signals
        ),
        "monitor_summary": _monitor_summary(
            len(evaluation_receipts),
            len(attributions),
            len(drift_detections),
            scope_change,
        ),
        "monitor_hash": "0" * 64,
    }
    monitor_without_hash = dict(monitor)
    monitor_without_hash.pop("monitor_hash")
    monitor["monitor_hash"] = canonical_json_hash(monitor_without_hash)

    _validate_against_schema(monitor, TRAJECTORY_ADMISSIBILITY_MONITOR_SCHEMA_PATH)
    return monitor


def _parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Generate a draft Trajectory-Level Admissibility Monitor v1 JSON "
            "object from local Evaluation Governance artifacts."
        )
    )
    parser.add_argument(
        "--evaluation-receipts",
        required=True,
        nargs="+",
        type=Path,
        help="One or more local Evaluation Receipt v1 JSON files.",
    )
    parser.add_argument(
        "--attributions",
        nargs="*",
        type=Path,
        default=[],
        help="Zero or more local Outcome Delta Attribution v1 JSON files.",
    )
    parser.add_argument(
        "--drift-detections",
        nargs="*",
        type=Path,
        default=[],
        help="Zero or more local Evaluation Drift Detection v1 JSON files.",
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    """Run the CLI and return a process exit code."""
    args = _parse_args()
    try:
        receipts = [_load_json_object(path) for path in args.evaluation_receipts]
        attributions = [_load_json_object(path) for path in args.attributions]
        drift_detections = [
            _load_json_object(path) for path in args.drift_detections
        ]
        monitor = generate_trajectory_admissibility_monitor(
            receipts, attributions, drift_detections
        )
        output = json.dumps(monitor, indent=2, ensure_ascii=False)
        if args.output is None:
            print(output)
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(f"{output}\n", encoding="utf-8")
            print(
                "Generated Trajectory-Level Admissibility Monitor v1: "
                f"{args.output} "
                f"(status={monitor['trajectory_status']}, "
                f"signals={len(monitor['trajectory_risk_signals'])})"
            )
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
