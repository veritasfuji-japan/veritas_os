import copy
import importlib.util
import json
import re
from pathlib import Path
from typing import Any

SCHEMA_PATH = Path(
    "docs/en/demo/schemas/outcome-delta-attribution-v1.schema.json"
)
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


def _load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _jsonschema_module() -> Any | None:
    if importlib.util.find_spec("jsonschema") is None:
        return None
    import jsonschema

    return jsonschema


def _build_minimal_attribution() -> dict[str, Any]:
    return {
        "schema_version": "outcome-delta-attribution-v1",
        "attribution_id": "outcome-delta-demo-v1",
        "issued_at": "2026-01-01T00:00:00Z",
        "prior_evaluation_receipt_ref": "evaluation-receipt-demo-prior-v1",
        "current_evaluation_receipt_ref": "evaluation-receipt-demo-current-v1",
        "prior_evaluation_receipt_hash": HASH_A,
        "current_evaluation_receipt_hash": HASH_B,
        "prior_outcome": "allow",
        "current_outcome": "escalate",
        "outcome_changed": True,
        "delta_causes": [
            {
                "cause_type": "qualifier_freshness_changed",
                "severity": "medium",
                "prior_value_ref": "qualifier://authority_validity_status/fresh",
                "current_value_ref": "qualifier://authority_validity_status/stale",
                "evidence_refs": [
                    "evidence://receipt-comparison/qualifier-freshness"
                ],
                "explanation": "Authority qualifier freshness changed.",
            }
        ],
        "attribution_summary": "Outcome changed after qualifier freshness changed.",
        "attribution_confidence": "high",
        "unresolved_delta": {
            "present": False,
            "reason": "All material deltas are attributed.",
            "requires_review": False,
        },
        "recommended_governance_action": "review",
        "attribution_hash": HASH_C,
    }


def _validate(payload: dict[str, Any], schema: dict[str, Any]) -> None:
    jsonschema = _jsonschema_module()
    if jsonschema is not None:
        validator = jsonschema.Draft202012Validator(schema)
        validator.validate(payload)
        return

    missing = [field for field in schema["required"] if field not in payload]
    assert not missing, f"missing required fields: {missing}"
    assert payload["schema_version"] == "outcome-delta-attribution-v1"
    outcome_enum = schema["$defs"]["admissibility_outcome"]["enum"]
    assert payload["prior_outcome"] in outcome_enum
    assert payload["current_outcome"] in outcome_enum
    assert payload["delta_causes"][0]["cause_type"] in (
        schema["$defs"]["delta_cause"]["properties"]["cause_type"]["enum"]
    )
    assert payload["recommended_governance_action"] in (
        schema["$defs"]["governance_action"]["enum"]
    )
    sha256_pattern = re.compile(r"^[0-9a-f]{64}$")
    assert sha256_pattern.match(payload["prior_evaluation_receipt_hash"])
    assert sha256_pattern.match(payload["current_evaluation_receipt_hash"])
    assert sha256_pattern.match(payload["attribution_hash"])
    assert set(payload) <= set(schema["properties"])


def _is_rejected(payload: dict[str, Any], schema: dict[str, Any]) -> bool:
    try:
        _validate(payload, schema)
    except (AssertionError, Exception):
        return True
    return False


def test_schema_file_exists() -> None:
    assert SCHEMA_PATH.is_file()


def test_schema_file_parses_as_valid_json_schema() -> None:
    schema = _load_schema()
    assert isinstance(schema, dict)
    jsonschema = _jsonschema_module()
    if jsonschema is not None:
        jsonschema.Draft202012Validator.check_schema(schema)


def test_minimal_valid_example_validates() -> None:
    _validate(_build_minimal_attribution(), _load_schema())


def test_missing_required_field_fails_validation() -> None:
    payload = _build_minimal_attribution()
    payload.pop("current_evaluation_receipt_ref")
    assert _is_rejected(payload, _load_schema())


def test_invalid_prior_outcome_enum_fails_validation() -> None:
    payload = _build_minimal_attribution()
    payload["prior_outcome"] = "approve"
    assert _is_rejected(payload, _load_schema())


def test_invalid_current_outcome_enum_fails_validation() -> None:
    payload = _build_minimal_attribution()
    payload["current_outcome"] = "approve"
    assert _is_rejected(payload, _load_schema())


def test_invalid_cause_type_enum_fails_validation() -> None:
    payload = copy.deepcopy(_build_minimal_attribution())
    payload["delta_causes"][0]["cause_type"] = "runtime_enforcement_changed"
    assert _is_rejected(payload, _load_schema())


def test_invalid_recommended_governance_action_enum_fails_validation() -> None:
    payload = _build_minimal_attribution()
    payload["recommended_governance_action"] = "auto_enforce"
    assert _is_rejected(payload, _load_schema())


def test_invalid_sha256_hash_fails_validation() -> None:
    payload = _build_minimal_attribution()
    payload["current_evaluation_receipt_hash"] = "not-a-sha256-hash"
    assert _is_rejected(payload, _load_schema())


def test_unexpected_top_level_property_fails_validation() -> None:
    payload = copy.deepcopy(_build_minimal_attribution())
    payload["unexpected_runtime_enforcement"] = True
    assert _is_rejected(payload, _load_schema())


def test_schema_validation_requires_no_network_or_environment_dependency(
    monkeypatch: Any,
) -> None:
    monkeypatch.delenv("VERITAS_API_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    _validate(_build_minimal_attribution(), _load_schema())
