import copy
import importlib.util
import json
import re
from pathlib import Path
from typing import Any

SCHEMA_PATH = Path(
    "docs/en/demo/schemas/trajectory-admissibility-monitor-v1.schema.json"
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


def _build_minimal_monitor() -> dict[str, Any]:
    return {
        "schema_version": "trajectory-admissibility-monitor-v1",
        "monitor_id": "trajectory-admissibility-monitor-demo-v1",
        "issued_at": "2026-01-01T00:00:00Z",
        "trajectory_id": "trajectory-demo-v1",
        "evaluation_receipt_refs": [
            "evaluation-receipt-demo-prior-v1",
            "evaluation-receipt-demo-current-v1",
        ],
        "outcome_delta_attribution_refs": ["outcome-delta-demo-v1"],
        "evaluation_drift_detection_refs": ["evaluation-drift-demo-v1"],
        "trajectory_window": {
            "started_at": "2026-01-01T00:00:00Z",
            "ended_at": "2026-01-02T00:00:00Z",
            "evaluation_count": 2,
        },
        "baseline_authority_scope": {
            "scope_id": "authority-scope-baseline-v1",
            "scope_hash": HASH_A,
            "authority_evidence_ref": "evidence://authority/baseline",
        },
        "current_authority_scope": {
            "scope_id": "authority-scope-current-v1",
            "scope_hash": HASH_B,
            "authority_evidence_ref": "evidence://authority/current",
        },
        "admissibility_scope_change": {
            "scope_expanded": True,
            "expansion_type": "delegated_authority_expansion",
            "explicit_reauthorization_present": False,
            "reauthorization_evidence_refs": [],
        },
        "continuity_event_summary": {
            "continuity_events_observed": 2,
            "low_risk_events_count": 1,
            "material_change_events_count": 1,
            "requalification_events_count": 1,
            "escalation_events_count": 0,
        },
        "trajectory_risk_signals": [
            {
                "signal_type": "admissibility_envelope_expansion",
                "severity": "medium",
                "evidence_refs": ["evidence://trajectory/scope-expansion"],
                "explanation": "The current scope is broader than baseline.",
            }
        ],
        "trajectory_status": "watch",
        "recommended_governance_action": "review",
        "monitor_summary": "Trajectory requires reviewer assessment.",
        "monitor_hash": HASH_C,
    }


def _validate(payload: dict[str, Any], schema: dict[str, Any]) -> None:
    jsonschema = _jsonschema_module()
    if jsonschema is not None:
        validator = jsonschema.Draft202012Validator(schema)
        validator.validate(payload)
        return

    missing = [field for field in schema["required"] if field not in payload]
    assert not missing, f"missing required fields: {missing}"
    assert payload["schema_version"] == "trajectory-admissibility-monitor-v1"
    assert payload["admissibility_scope_change"]["expansion_type"] in (
        schema["$defs"]["admissibility_scope_change"]["properties"][
            "expansion_type"
        ]["enum"]
    )
    assert payload["trajectory_risk_signals"][0]["signal_type"] in (
        schema["$defs"]["trajectory_risk_signal"]["properties"][
            "signal_type"
        ]["enum"]
    )
    assert payload["trajectory_status"] in (
        schema["$defs"]["trajectory_status"]["enum"]
    )
    assert payload["recommended_governance_action"] in (
        schema["$defs"]["governance_action"]["enum"]
    )
    sha256_pattern = re.compile(r"^[0-9a-f]{64}$")
    assert sha256_pattern.match(
        payload["baseline_authority_scope"]["scope_hash"]
    )
    assert sha256_pattern.match(payload["current_authority_scope"]["scope_hash"])
    assert sha256_pattern.match(payload["monitor_hash"])
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
    _validate(_build_minimal_monitor(), _load_schema())


def test_missing_required_field_fails_validation() -> None:
    payload = _build_minimal_monitor()
    payload.pop("current_authority_scope")
    assert _is_rejected(payload, _load_schema())


def test_invalid_expansion_type_enum_fails_validation() -> None:
    payload = copy.deepcopy(_build_minimal_monitor())
    payload["admissibility_scope_change"]["expansion_type"] = "auto_expand"
    assert _is_rejected(payload, _load_schema())


def test_invalid_signal_type_enum_fails_validation() -> None:
    payload = copy.deepcopy(_build_minimal_monitor())
    payload["trajectory_risk_signals"][0]["signal_type"] = "runtime_refusal"
    assert _is_rejected(payload, _load_schema())


def test_invalid_trajectory_status_enum_fails_validation() -> None:
    payload = _build_minimal_monitor()
    payload["trajectory_status"] = "auto_enforced"
    assert _is_rejected(payload, _load_schema())


def test_invalid_recommended_governance_action_enum_fails_validation() -> None:
    payload = _build_minimal_monitor()
    payload["recommended_governance_action"] = "auto_enforce"
    assert _is_rejected(payload, _load_schema())


def test_invalid_sha256_hash_fails_validation() -> None:
    payload = copy.deepcopy(_build_minimal_monitor())
    payload["baseline_authority_scope"]["scope_hash"] = "not-a-sha256-hash"
    assert _is_rejected(payload, _load_schema())


def test_unexpected_top_level_property_fails_validation() -> None:
    payload = copy.deepcopy(_build_minimal_monitor())
    payload["unexpected_runtime_enforcement"] = True
    assert _is_rejected(payload, _load_schema())


def test_schema_validation_requires_no_network_or_environment_dependency(
    monkeypatch: Any,
) -> None:
    monkeypatch.delenv("VERITAS_API_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    _validate(_build_minimal_monitor(), _load_schema())
