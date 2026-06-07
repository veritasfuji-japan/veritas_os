import copy
import importlib.util
import json
import re
from pathlib import Path
from typing import Any

SCHEMA_PATH = Path(
    "docs/en/demo/schemas/legitimacy-impact-review-v1.schema.json"
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


def _impact(
    explanation: str,
    **flags: bool,
) -> dict[str, Any]:
    return {
        **flags,
        "evidence_refs": ["evidence://legitimacy-impact/demo"],
        "explanation": explanation,
    }


def _build_minimal_review() -> dict[str, Any]:
    return {
        "schema_version": "legitimacy-impact-review-v1",
        "review_id": "legitimacy-impact-review-demo-v1",
        "issued_at": "2026-01-01T00:00:00Z",
        "reviewed_artifact_type": "trajectory_admissibility_monitor",
        "reviewed_artifact_ref": "trajectory-admissibility-monitor-demo-v1",
        "reviewed_artifact_hash": HASH_A,
        "triggering_change_ref": "manifest-change-receipt-demo-v1",
        "triggering_change_hash": HASH_B,
        "legitimacy_impact_detected": True,
        "impact_categories": [
            "authority_scope_expansion",
            "high_risk_admissibility_expanded",
        ],
        "authority_impact": _impact(
            "The reviewed change expands the asserted authority scope.",
            authority_scope_expanded=True,
            trusted_authority_source_changed=False,
            root_authority_changed=False,
        ),
        "oversight_impact": _impact(
            "Human oversight requirements are unchanged.",
            human_oversight_weakened=False,
            approval_requirement_reduced=False,
            reviewer_authority_changed=False,
        ),
        "refusal_boundary_impact": _impact(
            "Refusal boundaries are unchanged.",
            refusal_boundary_relaxed=False,
            refusal_condition_removed=False,
            refusal_condition_changed=False,
        ),
        "escalation_impact": _impact(
            "Escalation requirements are unchanged.",
            escalation_requirement_reduced=False,
            escalation_path_changed=False,
            escalation_authority_changed=False,
        ),
        "auditability_impact": _impact(
            "Auditability and replayability requirements are unchanged.",
            auditability_reduced=False,
            replayability_reduced=False,
            evidence_chain_weakened=False,
            receipt_requirements_reduced=False,
        ),
        "high_risk_admissibility_impact": _impact(
            "The high-risk admissibility posture may expand.",
            high_risk_scope_expanded=True,
            high_risk_controls_weakened=False,
            high_risk_review_requirement_reduced=False,
        ),
        "review_status": "required",
        "recommended_governance_action": "multi_party_review",
        "review_summary": "The change requires legitimacy impact review.",
        "review_hash": HASH_C,
    }


def _validate(payload: dict[str, Any], schema: dict[str, Any]) -> None:
    jsonschema = _jsonschema_module()
    if jsonschema is not None:
        validator = jsonschema.Draft202012Validator(schema)
        validator.validate(payload)
        return

    missing = [field for field in schema["required"] if field not in payload]
    assert not missing, f"missing required fields: {missing}"
    assert payload["schema_version"] == "legitimacy-impact-review-v1"
    assert payload["reviewed_artifact_type"] in (
        schema["$defs"]["artifact_type"]["enum"]
    )
    assert all(
        category in schema["$defs"]["impact_category"]["enum"]
        for category in payload["impact_categories"]
    )
    assert payload["review_status"] in (
        schema["$defs"]["review_status"]["enum"]
    )
    assert payload["recommended_governance_action"] in (
        schema["$defs"]["governance_action"]["enum"]
    )
    sha256_pattern = re.compile(r"^[0-9a-f]{64}$")
    assert sha256_pattern.match(payload["reviewed_artifact_hash"])
    assert sha256_pattern.match(payload["triggering_change_hash"])
    assert sha256_pattern.match(payload["review_hash"])
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
    _validate(_build_minimal_review(), _load_schema())


def test_missing_required_field_fails_validation() -> None:
    payload = _build_minimal_review()
    payload.pop("reviewed_artifact_hash")
    assert _is_rejected(payload, _load_schema())


def test_invalid_reviewed_artifact_type_enum_fails_validation() -> None:
    payload = _build_minimal_review()
    payload["reviewed_artifact_type"] = "runtime_decision"
    assert _is_rejected(payload, _load_schema())


def test_invalid_impact_categories_enum_fails_validation() -> None:
    payload = copy.deepcopy(_build_minimal_review())
    payload["impact_categories"][0] = "automatic_legitimacy_created"
    assert _is_rejected(payload, _load_schema())


def test_invalid_review_status_enum_fails_validation() -> None:
    payload = _build_minimal_review()
    payload["review_status"] = "auto_approved"
    assert _is_rejected(payload, _load_schema())


def test_invalid_recommended_governance_action_enum_fails_validation() -> None:
    payload = _build_minimal_review()
    payload["recommended_governance_action"] = "auto_enforce"
    assert _is_rejected(payload, _load_schema())


def test_invalid_sha256_hash_fails_validation() -> None:
    payload = copy.deepcopy(_build_minimal_review())
    payload["triggering_change_hash"] = "not-a-sha256-hash"
    assert _is_rejected(payload, _load_schema())


def test_unexpected_top_level_property_fails_validation() -> None:
    payload = copy.deepcopy(_build_minimal_review())
    payload["unexpected_runtime_enforcement"] = True
    assert _is_rejected(payload, _load_schema())


def test_schema_validation_requires_no_network_or_environment_dependency(
    monkeypatch: Any,
) -> None:
    monkeypatch.delenv("VERITAS_API_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    _validate(_build_minimal_review(), _load_schema())
