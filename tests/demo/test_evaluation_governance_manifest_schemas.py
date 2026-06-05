import copy
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

SCHEMA_DIR = Path("docs/en/demo/schemas")
ROOT_AUTHORITY_SCHEMA_PATH = SCHEMA_DIR / "root-authority-manifest-v1.schema.json"
EVALUATION_FUNCTION_SCHEMA_PATH = (
    SCHEMA_DIR / "evaluation-function-manifest-v1.schema.json"
)
MANIFEST_CHANGE_RECEIPT_SCHEMA_PATH = (
    SCHEMA_DIR / "manifest-change-receipt-v1.schema.json"
)

SCHEMA_CASES = [
    (
        ROOT_AUTHORITY_SCHEMA_PATH,
        "root_authority_manifest",
        "root_authority_id",
    ),
    (
        EVALUATION_FUNCTION_SCHEMA_PATH,
        "evaluation_function_manifest",
        "evaluator_id",
    ),
    (
        MANIFEST_CHANGE_RECEIPT_SCHEMA_PATH,
        "manifest_change_receipt",
        "change_reason",
    ),
]

HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
HASH_D = "d" * 64


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonschema_module() -> Any | None:
    if importlib.util.find_spec("jsonschema") is None:
        return None
    import jsonschema

    return jsonschema


def _build_root_authority_manifest() -> dict[str, Any]:
    return {
        "schema_version": "root-authority-manifest-v1",
        "manifest_id": "root-authority-demo-v1",
        "issued_at": "2026-01-01T00:00:00Z",
        "root_authority_id": "constitutional-trust-anchor-demo",
        "trusted_authority_sources": [
            {
                "source_id": "board-resolution-2026-001",
                "source_type": "board_resolution",
                "validity_status": "active",
                "evidence_ref": "evidence://authority/board-resolution-2026-001",
            }
        ],
        "authorized_manifest_modifiers": [
            {
                "actor_id": "governance-maintainer-demo",
                "role": "governance_maintainer",
                "scope": "demo_governance_manifests",
                "approval_required": True,
            }
        ],
        "authoritative_policy_sources": [
            {
                "policy_source_id": "policy-source-demo",
                "policy_domain": "demo_admissibility",
                "version": "2026.01",
                "evidence_ref": "evidence://policy/source-demo",
            }
        ],
        "approval_requirements": [
            {
                "change_type": "evaluation_function_manifest_update",
                "required_approvals": 2,
                "human_review_required": True,
            }
        ],
        "fail_closed_conditions": [
            "root authority evidence is missing or revoked"
        ],
        "challenge_process": {
            "challenge_allowed": True,
            "review_authority": "governance-review-board-demo",
            "evidence_required": ["authority_evidence", "approval_receipts"],
        },
        "manifest_hash": HASH_A,
    }


def _build_evaluation_function_manifest() -> dict[str, Any]:
    return {
        "schema_version": "evaluation-function-manifest-v1",
        "manifest_id": "evaluation-function-demo-v1",
        "issued_at": "2026-01-01T00:00:00Z",
        "evaluator_id": "bind-time-admissibility-evaluator-demo",
        "evaluator_version": "1.0.0",
        "policy_identity": {
            "policy_id": "demo-admissibility-policy",
            "policy_version": "2026.01",
            "policy_source_ref": "policy-source-demo",
        },
        "rule_set_version": "ruleset-2026.01",
        "authorized_determiners": [
            {
                "determiner_id": "authority-evidence-check-demo",
                "determiner_type": "authority_validation",
                "authority_scope": "regulated_action_bind",
                "may_influence_outcome": True,
            }
        ],
        "admissibility_inputs": [
            {
                "input_name": "authority_evidence",
                "input_type": "evidence_reference",
                "required": True,
                "freshness_required": True,
            }
        ],
        "qualifier_sources": [
            {
                "qualifier_name": "authority_validity_status",
                "source_ref": "root-authority-demo-v1",
                "freshness_ttl_seconds": 3600,
                "required_at_bind": True,
            }
        ],
        "consequence_classifier": {
            "classifier_id": "consequence-classifier-demo",
            "classifier_version": "1.0.0",
        },
        "threshold_resolver": {
            "resolver_id": "threshold-resolver-demo",
            "resolver_version": "1.0.0",
        },
        "refusal_boundaries": [
            {
                "boundary_id": "missing-authority-evidence",
                "condition": "required authority evidence is unavailable",
                "action": "refuse_or_escalate",
            }
        ],
        "escalation_resolver": {
            "resolver_id": "escalation-resolver-demo",
            "resolver_version": "1.0.0",
            "authority_validation_required": True,
        },
        "baseline_hash": HASH_B,
        "root_authority_manifest_ref": "root-authority-demo-v1",
        "manifest_hash": HASH_C,
    }


def _build_manifest_change_receipt() -> dict[str, Any]:
    return {
        "schema_version": "manifest-change-receipt-v1",
        "receipt_id": "manifest-change-demo-v1",
        "issued_at": "2026-01-01T00:00:00Z",
        "changed_manifest_type": "evaluation_function_manifest",
        "changed_manifest_id": "evaluation-function-demo-v1",
        "previous_manifest_hash": HASH_C,
        "new_manifest_hash": HASH_D,
        "change_reason": "Add explicit evaluator governance metadata.",
        "changed_by": {
            "actor_id": "governance-maintainer-demo",
            "role": "governance_maintainer",
        },
        "authority_evidence_ref": "evidence://authority/board-resolution-2026-001",
        "approval_evidence_refs": ["evidence://approval/demo-001"],
        "impact_scope": ["demo_schema_foundation"],
        "legitimacy_impact_flags": ["evaluator_behavior_changed"],
        "rollback_conditions": ["approval evidence is invalidated"],
    }


def _example_for_schema(name: str) -> dict[str, Any]:
    if name == "root_authority_manifest":
        return _build_root_authority_manifest()
    if name == "evaluation_function_manifest":
        return _build_evaluation_function_manifest()
    if name == "manifest_change_receipt":
        return _build_manifest_change_receipt()
    raise AssertionError(f"unknown schema example: {name}")


def _validate_or_fallback(payload: dict[str, Any], schema: dict[str, Any]) -> None:
    jsonschema = _jsonschema_module()
    if jsonschema is not None:
        validator = jsonschema.Draft202012Validator(schema)
        validator.validate(payload)
        return

    missing = [field for field in schema["required"] if field not in payload]
    assert not missing, f"missing required fields: {missing}"
    for field, field_schema in schema["properties"].items():
        if field not in payload or "const" not in field_schema:
            continue
        assert payload[field] == field_schema["const"]


def _is_rejected_or_fallback_detected(
    payload: dict[str, Any], schema: dict[str, Any]
) -> bool:
    try:
        _validate_or_fallback(payload, schema)
    except (AssertionError, Exception):
        return True
    return False


@pytest.mark.parametrize(("schema_path", "_name", "_field"), SCHEMA_CASES)
def test_schema_files_exist(schema_path: Path, _name: str, _field: str) -> None:
    assert schema_path.is_file()


@pytest.mark.parametrize(("schema_path", "_name", "_field"), SCHEMA_CASES)
def test_schema_files_parse_as_valid_json(
    schema_path: Path, _name: str, _field: str
) -> None:
    schema = _load_json(schema_path)
    assert isinstance(schema, dict)
    jsonschema = _jsonschema_module()
    if jsonschema is not None:
        jsonschema.Draft202012Validator.check_schema(schema)


@pytest.mark.parametrize(("schema_path", "name", "_field"), SCHEMA_CASES)
def test_minimal_valid_examples_validate(
    schema_path: Path, name: str, _field: str
) -> None:
    _validate_or_fallback(_example_for_schema(name), _load_json(schema_path))


@pytest.mark.parametrize(("schema_path", "name", "missing_field"), SCHEMA_CASES)
def test_missing_required_fields_fail_validation(
    schema_path: Path, name: str, missing_field: str
) -> None:
    payload = copy.deepcopy(_example_for_schema(name))
    payload.pop(missing_field)
    assert _is_rejected_or_fallback_detected(payload, _load_json(schema_path))


@pytest.mark.parametrize(("schema_path", "name", "_field"), SCHEMA_CASES)
def test_schema_validation_requires_no_network_or_environment_dependency(
    monkeypatch: pytest.MonkeyPatch, schema_path: Path, name: str, _field: str
) -> None:
    monkeypatch.delenv("VERITAS_API_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    _validate_or_fallback(_example_for_schema(name), _load_json(schema_path))
