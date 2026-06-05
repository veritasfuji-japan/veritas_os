import copy
import importlib.util
import json
from pathlib import Path
from typing import Any

SCHEMA_PATH = Path("docs/en/demo/schemas/evaluation-receipt-v1.schema.json")
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
HASH_D = "d" * 64
HASH_E = "e" * 64
HASH_F = "f" * 64


def _load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _jsonschema_module() -> Any | None:
    if importlib.util.find_spec("jsonschema") is None:
        return None
    import jsonschema

    return jsonschema


def _build_minimal_receipt() -> dict[str, Any]:
    return {
        "schema_version": "evaluation-receipt-v1",
        "receipt_id": "evaluation-receipt-demo-v1",
        "issued_at": "2026-01-01T00:00:00Z",
        "evaluation_id": "evaluation-demo-001",
        "evaluation_function_manifest_ref": "evaluation-function-demo-v1",
        "evaluation_function_manifest_hash": HASH_A,
        "root_authority_manifest_ref": "root-authority-demo-v1",
        "evaluator_id": "bind-time-admissibility-evaluator-demo",
        "evaluator_version": "1.0.0",
        "policy_identity": {
            "policy_id": "demo-admissibility-policy",
            "policy_version": "2026.01",
            "policy_source_ref": "policy-source-demo",
        },
        "rule_set_version": "ruleset-2026.01",
        "authority_evidence_refs": [
            "evidence://authority/board-resolution-2026-001"
        ],
        "qualifier_state": [
            {
                "qualifier_name": "authority_validity_status",
                "source_ref": "root-authority-demo-v1",
                "freshness_state": "fresh",
                "required_at_bind": True,
                "qualifier_hash": HASH_B,
            }
        ],
        "authorized_determiners_used": [
            {
                "determiner_id": "authority-evidence-check-demo",
                "determiner_type": "authority_validation",
                "authority_scope": "regulated_action_bind",
                "influenced_outcome": True,
            }
        ],
        "admissibility_inputs": [
            {
                "input_name": "authority_evidence",
                "input_type": "evidence_reference",
                "input_ref": "evidence://authority/board-resolution-2026-001",
                "required": True,
                "input_hash": HASH_C,
            }
        ],
        "consequence_class": {
            "class_id": "demo-low-risk",
            "class_label": "Demo Low Risk",
            "classifier_id": "consequence-classifier-demo",
            "classifier_version": "1.0.0",
        },
        "material_context": {
            "context_ref": "context://demo/evaluation-001",
            "context_hash": HASH_D,
            "context_freshness_state": "fresh",
            "stale_context_allowed": False,
        },
        "outcome": "allow",
        "rationale_codes": ["authority_evidence_fresh"],
        "input_state_hash": HASH_E,
        "evaluation_state_hash": HASH_F,
        "receipt_hash": HASH_A,
    }


def _validate(payload: dict[str, Any], schema: dict[str, Any]) -> None:
    jsonschema = _jsonschema_module()
    if jsonschema is not None:
        validator = jsonschema.Draft202012Validator(schema)
        validator.validate(payload)
        return

    missing = [field for field in schema["required"] if field not in payload]
    assert not missing, f"missing required fields: {missing}"
    assert payload["schema_version"] == "evaluation-receipt-v1"
    assert payload["outcome"] in schema["properties"]["outcome"]["enum"]
    assert len(payload["receipt_hash"]) == 64
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
    _validate(_build_minimal_receipt(), _load_schema())


def test_missing_required_field_fails_validation() -> None:
    payload = _build_minimal_receipt()
    payload.pop("evaluation_id")
    assert _is_rejected(payload, _load_schema())


def test_invalid_outcome_enum_fails_validation() -> None:
    payload = _build_minimal_receipt()
    payload["outcome"] = "approve"
    assert _is_rejected(payload, _load_schema())


def test_invalid_sha256_hash_fails_validation() -> None:
    payload = _build_minimal_receipt()
    payload["receipt_hash"] = "not-a-sha256-hash"
    assert _is_rejected(payload, _load_schema())


def test_unexpected_top_level_property_fails_validation() -> None:
    payload = copy.deepcopy(_build_minimal_receipt())
    payload["unexpected_runtime_enforcement"] = True
    assert _is_rejected(payload, _load_schema())


def test_schema_validation_requires_no_network_or_environment_dependency(
    monkeypatch: Any,
) -> None:
    monkeypatch.delenv("VERITAS_API_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    _validate(_build_minimal_receipt(), _load_schema())
