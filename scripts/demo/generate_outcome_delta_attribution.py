#!/usr/bin/env python3
"""Generate a draft Outcome Delta Attribution from two receipts.

This offline demo helper is intentionally schema-shaped and non-enforcing. It
compares two local Evaluation Receipt v1 JSON objects, records deterministic
candidate delta causes, and optionally validates the inputs and output with
``jsonschema`` when that package is available locally. It never dereferences
artifact references, accesses the network, or connects to runtime admissibility
paths.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO_ROOT / "docs/en/demo/schemas"
EVALUATION_RECEIPT_SCHEMA_PATH = (
    SCHEMA_DIR / "evaluation-receipt-v1.schema.json"
)
OUTCOME_DELTA_ATTRIBUTION_SCHEMA_PATH = (
    SCHEMA_DIR / "outcome-delta-attribution-v1.schema.json"
)
ISSUED_AT = "2026-01-01T00:00:00Z"
ATTRIBUTION_ID = "outcome-delta-attribution-example-001"
NO_DELTA_CAUSE_TYPE = "governed_state_changed"

SEVERITY_BY_CAUSE_TYPE = {
    "evaluator_version_changed": "medium",
    "policy_identity_changed": "medium",
    "rule_version_changed": "medium",
    "authority_state_changed": "high",
    "qualifier_freshness_changed": "medium",
    "consequence_class_changed": "high",
    "material_context_changed": "medium",
    "authorized_determiner_changed": "medium",
    "unauthorized_determiner_influence": "high",
    "unexplained_evaluation_drift": "high",
    NO_DELTA_CAUSE_TYPE: "info",
}
UNAUTHORIZED_AUTHORITY_SCOPE_MARKERS = {
    "",
    "unknown",
    "unauthorized",
    "unauthorised",
    "explicitly_unauthorized",
    "explicitly_unauthorised",
}


def _jsonschema_module() -> Any | None:
    """Return the optional jsonschema module when available locally."""
    try:
        import jsonschema
    except ImportError:
        return None
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


def _receipt_ref(receipt: dict[str, Any]) -> str:
    """Return a stable receipt reference without dereferencing artifacts."""
    receipt_id = receipt.get("receipt_id")
    if isinstance(receipt_id, str) and receipt_id:
        return receipt_id
    evaluation_id = receipt.get("evaluation_id")
    if isinstance(evaluation_id, str) and evaluation_id:
        return evaluation_id
    return "unknown-evaluation-receipt"


def _json_value_ref(value: Any) -> str:
    """Serialize a compared value into a compact deterministic reference."""
    if isinstance(value, str) and value:
        return value
    if value is None:
        return "missing"
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _cause(
    cause_type: str,
    prior_value: Any,
    current_value: Any,
    evidence_refs: list[str],
    explanation: str,
) -> dict[str, Any]:
    """Build a schema-shaped delta cause object."""
    return {
        "cause_type": cause_type,
        "severity": SEVERITY_BY_CAUSE_TYPE[cause_type],
        "prior_value_ref": _json_value_ref(prior_value),
        "current_value_ref": _json_value_ref(current_value),
        "evidence_refs": evidence_refs,
        "explanation": explanation,
    }


def _compare_field(
    causes: list[dict[str, Any]],
    prior: Any,
    current: Any,
    cause_type: str,
    evidence_refs: list[str],
    explanation: str,
) -> None:
    """Append a cause when two comparable values differ."""
    if prior != current:
        causes.append(
            _cause(cause_type, prior, current, evidence_refs, explanation)
        )


def _qualifier_map(receipt: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index qualifier state by qualifier_name."""
    qualifiers = receipt.get("qualifier_state", [])
    if not isinstance(qualifiers, list):
        return {}

    result = {}
    for qualifier in qualifiers:
        if not isinstance(qualifier, dict):
            continue
        name = qualifier.get("qualifier_name")
        if isinstance(name, str) and name:
            result[name] = qualifier
    return result


def _determiner_identity_set(receipt: dict[str, Any]) -> list[tuple[str, str]]:
    """Return sorted determiner_id/determiner_type pairs."""
    determiners = receipt.get("authorized_determiners_used", [])
    if not isinstance(determiners, list):
        return []

    identities = set()
    for determiner in determiners:
        if not isinstance(determiner, dict):
            continue
        determiner_id = determiner.get("determiner_id")
        determiner_type = determiner.get("determiner_type")
        if isinstance(determiner_id, str) and isinstance(determiner_type, str):
            identities.add((determiner_id, determiner_type))
    return sorted(identities)


def _has_unauthorized_determiner(receipt: dict[str, Any]) -> bool:
    """Detect current determiners represented as unauthorized in example data."""
    determiners = receipt.get("authorized_determiners_used", [])
    if not isinstance(determiners, list):
        return False

    for determiner in determiners:
        if not isinstance(determiner, dict):
            continue
        authority_scope = str(determiner.get("authority_scope", ""))
        normalized_scope = authority_scope.strip().lower()
        if normalized_scope in UNAUTHORIZED_AUTHORITY_SCOPE_MARKERS:
            return True
        if "unauthorized" in normalized_scope or "unauthorised" in normalized_scope:
            return True
    return False


def compare_receipts(
    prior: dict[str, Any], current: dict[str, Any]
) -> list[dict[str, Any]]:
    """Compare two Evaluation Receipts and return deterministic delta causes.

    The comparison is limited to local JSON fields and does not dereference any
    artifact reference fields. Causes are emitted in a stable order so repeated
    runs over the same input objects produce identical attribution JSON.
    """
    current_ref = _receipt_ref(current)
    evidence_refs = [current_ref]
    causes: list[dict[str, Any]] = []

    _compare_field(
        causes,
        prior.get("evaluator_version"),
        current.get("evaluator_version"),
        "evaluator_version_changed",
        evidence_refs,
        "The evaluator version changed between receipts.",
    )
    policy_identity_fields = (
        "policy_id",
        "policy_version",
        "policy_source_ref",
    )
    prior_policy = prior.get("policy_identity", {})
    current_policy = current.get("policy_identity", {})
    _compare_field(
        causes,
        {field: prior_policy.get(field) for field in policy_identity_fields},
        {field: current_policy.get(field) for field in policy_identity_fields},
        "policy_identity_changed",
        evidence_refs,
        "The policy identity fields changed between receipts.",
    )
    _compare_field(
        causes,
        prior.get("rule_set_version"),
        current.get("rule_set_version"),
        "rule_version_changed",
        evidence_refs,
        "The rule set version changed between receipts.",
    )
    _compare_field(
        causes,
        prior.get("authority_evidence_refs", []),
        current.get("authority_evidence_refs", []),
        "authority_state_changed",
        evidence_refs,
        "The authority evidence references changed between receipts.",
    )

    prior_qualifiers = _qualifier_map(prior)
    current_qualifiers = _qualifier_map(current)
    for qualifier_name in sorted(set(prior_qualifiers) | set(current_qualifiers)):
        prior_qualifier = prior_qualifiers.get(qualifier_name, {})
        current_qualifier = current_qualifiers.get(qualifier_name, {})
        prior_value = {
            "freshness_state": prior_qualifier.get("freshness_state"),
            "qualifier_hash": prior_qualifier.get("qualifier_hash"),
        }
        current_value = {
            "freshness_state": current_qualifier.get("freshness_state"),
            "qualifier_hash": current_qualifier.get("qualifier_hash"),
        }
        if prior_value != current_value:
            causes.append(
                _cause(
                    "qualifier_freshness_changed",
                    {"qualifier_name": qualifier_name, **prior_value},
                    {"qualifier_name": qualifier_name, **current_value},
                    evidence_refs,
                    f"Qualifier {qualifier_name!r} freshness or hash changed.",
                )
            )

    consequence_fields = (
        "class_id",
        "class_label",
        "classifier_id",
        "classifier_version",
    )
    prior_consequence = prior.get("consequence_class", {})
    current_consequence = current.get("consequence_class", {})
    _compare_field(
        causes,
        {field: prior_consequence.get(field) for field in consequence_fields},
        {field: current_consequence.get(field) for field in consequence_fields},
        "consequence_class_changed",
        evidence_refs,
        "The consequence classification changed between receipts.",
    )

    material_context_fields = (
        "context_hash",
        "context_freshness_state",
        "stale_context_allowed",
    )
    prior_context = prior.get("material_context", {})
    current_context = current.get("material_context", {})
    _compare_field(
        causes,
        {field: prior_context.get(field) for field in material_context_fields},
        {field: current_context.get(field) for field in material_context_fields},
        "material_context_changed",
        evidence_refs,
        "The material context state changed between receipts.",
    )

    _compare_field(
        causes,
        _determiner_identity_set(prior),
        _determiner_identity_set(current),
        "authorized_determiner_changed",
        evidence_refs,
        "The authorized determiner identity set changed between receipts.",
    )

    if _has_unauthorized_determiner(current):
        causes.append(
            _cause(
                "unauthorized_determiner_influence",
                "not_detected_in_prior_receipt",
                "unauthorized_or_unknown_authority_scope_in_current_receipt",
                evidence_refs,
                (
                    "The current receipt contains a determiner with an "
                    "unknown or unauthorized authority scope marker."
                ),
            )
        )

    outcome_changed = prior.get("outcome") != current.get("outcome")
    if outcome_changed and not causes:
        causes.append(
            _cause(
                "unexplained_evaluation_drift",
                prior.get("outcome"),
                current.get("outcome"),
                evidence_refs,
                "The outcome changed, but no configured comparison field explained the delta.",
            )
        )

    if not outcome_changed and not causes:
        causes.append(
            _cause(
                NO_DELTA_CAUSE_TYPE,
                "no_compared_delta_detected",
                "no_compared_delta_detected",
                evidence_refs,
                (
                    "No compared receipt fields changed; this neutral cause "
                    "satisfies the v1 schema shape."
                ),
            )
        )

    return causes


def _recommended_action(
    outcome_changed: bool, causes: list[dict[str, Any]]
) -> str:
    """Map generated causes to a governance action recommendation."""
    cause_types = {cause["cause_type"] for cause in causes}
    if "unauthorized_determiner_influence" in cause_types:
        return "escalate"
    if "unexplained_evaluation_drift" in cause_types:
        return "mark_evaluation_drift"
    if not outcome_changed and cause_types == {NO_DELTA_CAUSE_TYPE}:
        return "none"
    if outcome_changed:
        return "review"
    return "review"


def _attribution_confidence(
    outcome_changed: bool, causes: list[dict[str, Any]]
) -> str:
    """Return deterministic attribution confidence for the draft output."""
    cause_types = {cause["cause_type"] for cause in causes}
    if "unexplained_evaluation_drift" in cause_types:
        return "low"
    if outcome_changed and cause_types:
        return "high"
    return "medium"


def _summary(
    prior_outcome: str,
    current_outcome: str,
    causes: list[dict[str, Any]],
) -> str:
    """Build a concise human-readable attribution summary."""
    cause_types = [cause["cause_type"] for cause in causes]
    if cause_types == [NO_DELTA_CAUSE_TYPE]:
        return "No outcome change or compared receipt-field delta was detected."
    joined_causes = ", ".join(cause_types)
    return (
        f"Outcome changed from {prior_outcome} to {current_outcome}; "
        f"detected causes: {joined_causes}."
    )


def generate_outcome_delta_attribution(
    prior: dict[str, Any], current: dict[str, Any]
) -> dict[str, Any]:
    """Generate a schema-shaped Outcome Delta Attribution v1 object.

    Args:
        prior: Prior Evaluation Receipt v1 JSON object.
        current: Current Evaluation Receipt v1 JSON object.

    Returns:
        Deterministic Outcome Delta Attribution v1 JSON object.

    Raises:
        jsonschema.ValidationError: If ``jsonschema`` is available and either
            receipt or the generated attribution does not validate locally.
    """
    _validate_against_schema(prior, EVALUATION_RECEIPT_SCHEMA_PATH)
    _validate_against_schema(current, EVALUATION_RECEIPT_SCHEMA_PATH)

    prior_outcome = str(prior.get("outcome", "undetermined"))
    current_outcome = str(current.get("outcome", "undetermined"))
    outcome_changed = prior_outcome != current_outcome
    causes = compare_receipts(prior, current)
    cause_types = {cause["cause_type"] for cause in causes}
    unresolved_present = "unexplained_evaluation_drift" in cause_types

    attribution: dict[str, Any] = {
        "schema_version": "outcome-delta-attribution-v1",
        "attribution_id": ATTRIBUTION_ID,
        "issued_at": ISSUED_AT,
        "prior_evaluation_receipt_ref": _receipt_ref(prior),
        "current_evaluation_receipt_ref": _receipt_ref(current),
        "prior_evaluation_receipt_hash": _sha256_json(prior),
        "current_evaluation_receipt_hash": _sha256_json(current),
        "prior_outcome": prior_outcome,
        "current_outcome": current_outcome,
        "outcome_changed": outcome_changed,
        "delta_causes": causes,
        "attribution_summary": _summary(prior_outcome, current_outcome, causes),
        "attribution_confidence": _attribution_confidence(outcome_changed, causes),
        "unresolved_delta": {
            "present": unresolved_present,
            "reason": (
                "Outcome changed without a configured comparison-field cause."
                if unresolved_present
                else "No unexplained evaluation drift was detected."
            ),
            "requires_review": unresolved_present,
        },
        "recommended_governance_action": _recommended_action(
            outcome_changed, causes
        ),
        "attribution_hash": "0" * 64,
    }
    attribution_without_hash = dict(attribution)
    attribution_without_hash.pop("attribution_hash")
    attribution["attribution_hash"] = _sha256_json(attribution_without_hash)

    _validate_against_schema(attribution, OUTCOME_DELTA_ATTRIBUTION_SCHEMA_PATH)
    return attribution


def _parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Generate a draft Outcome Delta Attribution v1 JSON object from "
            "two local Evaluation Receipt v1 JSON files."
        )
    )
    parser.add_argument("--prior", required=True, type=Path)
    parser.add_argument("--current", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    """Run the CLI and return a process exit code."""
    args = _parse_args()
    try:
        prior = _load_json_object(args.prior)
        current = _load_json_object(args.current)
        attribution = generate_outcome_delta_attribution(prior, current)
        output = json.dumps(attribution, indent=2, ensure_ascii=False)
        if args.output is None:
            print(output)
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(f"{output}\n", encoding="utf-8")
            print(
                "Generated Outcome Delta Attribution v1: "
                f"{args.output} "
                f"({attribution['prior_outcome']} -> "
                f"{attribution['current_outcome']}, "
                f"{len(attribution['delta_causes'])} causes)"
            )
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
