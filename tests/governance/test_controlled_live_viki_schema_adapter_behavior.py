"""Offline test-only schema adapter behavior skeleton for controlled live V.I.K.I."""

from __future__ import annotations

import ast
import json
from datetime import datetime, timedelta
from pathlib import Path

ADAPTER_VALID = "ADAPTER_VALID"
ADAPTER_UNSUPPORTED_SCHEMA_VERSION = "ADAPTER_UNSUPPORTED_SCHEMA_VERSION"
ADAPTER_UNKNOWN_RSA_STATUS = "ADAPTER_UNKNOWN_RSA_STATUS"
ADAPTER_MISSING_REQUIRED_FIELD = "ADAPTER_MISSING_REQUIRED_FIELD"
ADAPTER_INVALID_TIMESTAMP = "ADAPTER_INVALID_TIMESTAMP"
ADAPTER_FORBIDDEN_FIELD_PRESENT = "ADAPTER_FORBIDDEN_FIELD_PRESENT"
ADAPTER_SECRET_LIKE_VALUE_PRESENT = "ADAPTER_SECRET_LIKE_VALUE_PRESENT"
ADAPTER_REGULATED_DATA_PRESENT = "ADAPTER_REGULATED_DATA_PRESENT"
ADAPTER_REPLAY_DUPLICATE_REQUEST_ID = "ADAPTER_REPLAY_DUPLICATE_REQUEST_ID"
ADAPTER_INVALID_JSON_OBJECT = "ADAPTER_INVALID_JSON_OBJECT"

ACCEPTED_RSA_STATUSES = {
    "SAFE_PROCEED",
    "DENSITY_THROTTLED",
    "ALGORITHMIC_HUMILITY_ENGAGED",
    "DEFERRAL_ENGAGED",
}
REQUIRED_FIELDS = {
    "schema_version",
    "rsa_status",
    "trigger_source",
    "timestamp",
    "request_id",
    "correlation_id",
    "payload_issued_at",
}
FORBIDDEN_REASONING_FIELDS = {
    "chain_of_thought",
    "hidden_model_state",
    "raw_llm_reasoning",
    "raw_viki_reasoning",
    "raw_llm_text",
}
SECRET_LIKE_FIELDS = {
    "secrets",
    "credentials",
    "api_key",
    "access_token",
    "refresh_token",
    "private_key",
    "webhook_secret",
    "raw_authorization_header",
    "authorization",
    "bearer_token",
}
REGULATED_DATA_FIELDS = {
    "raw_kyc_record",
    "customer_pii",
    "unredacted_regulated_data",
}
RAW_BODY_FIELDS = {
    "raw_payload_body",
    "raw_request_body",
    "raw_response_body",
    "raw_stack_trace_with_secrets",
}

CLASS_TO_REASON_CODE = {
    ADAPTER_UNSUPPORTED_SCHEMA_VERSION: "CONTROLLED_LIVE_UNSUPPORTED_SCHEMA_VERSION",
    ADAPTER_UNKNOWN_RSA_STATUS: "CONTROLLED_LIVE_UNKNOWN_RSA_STATUS",
    ADAPTER_MISSING_REQUIRED_FIELD: "CONTROLLED_LIVE_MISSING_REQUIRED_FIELD",
    ADAPTER_INVALID_TIMESTAMP: "CONTROLLED_LIVE_INVALID_TIMESTAMP",
    ADAPTER_FORBIDDEN_FIELD_PRESENT: "CONTROLLED_LIVE_FORBIDDEN_FIELD_PRESENT",
    ADAPTER_SECRET_LIKE_VALUE_PRESENT: "CONTROLLED_LIVE_SECRET_LIKE_VALUE_PRESENT",
    ADAPTER_REGULATED_DATA_PRESENT: "CONTROLLED_LIVE_REGULATED_DATA_PRESENT",
    ADAPTER_REPLAY_DUPLICATE_REQUEST_ID: "CONTROLLED_LIVE_REPLAY_DUPLICATE_REQUEST_ID",
    ADAPTER_INVALID_JSON_OBJECT: "CONTROLLED_LIVE_INVALID_JSON_OBJECT",
}



def _load_payload_fixture(name: str) -> dict:
    fixture_dir = Path(__file__).resolve().parent.parent / "fixtures" / "controlled_live_viki_payload_schema"
    return json.loads((fixture_dir / name).read_text(encoding="utf-8"))



def _is_timezone_aware_timestamp(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None



def _contains_any_key(payload: dict, keys: set[str]) -> bool:
    return any(key in payload for key in keys)


def _has_future_payload_issued_at_skew(
    timestamp_value: str,
    payload_issued_at_value: str,
) -> bool:
    """Return True when payload_issued_at is more than 300s after timestamp."""
    timestamp = datetime.fromisoformat(timestamp_value.replace("Z", "+00:00"))
    payload_issued_at = datetime.fromisoformat(
        payload_issued_at_value.replace("Z", "+00:00")
    )
    return payload_issued_at - timestamp > timedelta(seconds=300)



def _classify_schema_adapter_input(
    payload: object,
    *,
    seen_request_ids: dict[str, str] | None = None,
) -> str:
    if not isinstance(payload, dict):
        return ADAPTER_INVALID_JSON_OBJECT

    if payload.get("schema_version") != "v1alpha1":
        return ADAPTER_UNSUPPORTED_SCHEMA_VERSION

    if any(field not in payload for field in REQUIRED_FIELDS):
        return ADAPTER_MISSING_REQUIRED_FIELD

    if payload["rsa_status"] not in ACCEPTED_RSA_STATUSES:
        return ADAPTER_UNKNOWN_RSA_STATUS

    if not _is_timezone_aware_timestamp(payload["timestamp"]):
        return ADAPTER_INVALID_TIMESTAMP
    if not _is_timezone_aware_timestamp(payload["payload_issued_at"]):
        return ADAPTER_INVALID_TIMESTAMP

    if _has_future_payload_issued_at_skew(
        payload["timestamp"],
        payload["payload_issued_at"],
    ):
        return ADAPTER_INVALID_TIMESTAMP

    if _contains_any_key(payload, REGULATED_DATA_FIELDS):
        return ADAPTER_REGULATED_DATA_PRESENT

    if _contains_any_key(payload, SECRET_LIKE_FIELDS):
        return ADAPTER_SECRET_LIKE_VALUE_PRESENT

    if _contains_any_key(payload, FORBIDDEN_REASONING_FIELDS):
        return ADAPTER_FORBIDDEN_FIELD_PRESENT

    if seen_request_ids is not None:
        request_id = payload["request_id"]
        if request_id in seen_request_ids:
            return ADAPTER_REPLAY_DUPLICATE_REQUEST_ID
        seen_request_ids[request_id] = payload["correlation_id"]

    return ADAPTER_VALID



def _expected_fail_closed_adapter_decision(
    reason_code: str,
    *,
    request_id: str = "req_viki_schema_adapter_001",
    correlation_id: str = "corr_viki_veritas_schema_adapter_001",
    schema_version: str = "v1alpha1",
) -> dict:
    return {
        "veritas_continuation_decision": "PAUSE_FOR_HUMAN_REVIEW",
        "veritas_sandbox_commit_state": "SUSPENDED_NOT_COMMITTED",
        "final_commit_approved": False,
        "required_next_action": "REQUEST_HUMAN_REVIEW_OR_RETRY_WITH_VALID_UPSTREAM_STATE",
        "upstream_signal_source": "RSA",
        "decision_source": "controlled_live_viki_schema_adapter_behavior_skeleton",
        "reason_code": reason_code,
        "request_id": request_id,
        "correlation_id": correlation_id,
        "schema_version": schema_version,
    }



def _assert_adapter_fail_closed(decision: dict) -> None:
    assert decision["veritas_continuation_decision"] == "PAUSE_FOR_HUMAN_REVIEW"
    assert decision["veritas_sandbox_commit_state"] == "SUSPENDED_NOT_COMMITTED"
    assert decision["required_next_action"] == "REQUEST_HUMAN_REVIEW_OR_RETRY_WITH_VALID_UPSTREAM_STATE"



def _assert_no_final_commit(decision: dict) -> None:
    assert decision["final_commit_approved"] is False



def test_schema_adapter_valid_fixtures_classify_as_valid() -> None:
    valid_fixtures = [
        "valid_safe_proceed_v1alpha1.json",
        "valid_density_throttled_v1alpha1.json",
        "valid_algorithmic_humility_engaged_v1alpha1.json",
        "valid_deferral_engaged_v1alpha1.json",
    ]

    for fixture_name in valid_fixtures:
        payload = _load_payload_fixture(fixture_name)
        classification = _classify_schema_adapter_input(payload)
        assert classification == ADAPTER_VALID
        assert payload["schema_version"] == "v1alpha1"
        assert payload["rsa_status"] in ACCEPTED_RSA_STATUSES
        assert all(field in payload for field in REQUIRED_FIELDS)
        assert _is_timezone_aware_timestamp(payload["timestamp"])
        assert _is_timezone_aware_timestamp(payload["payload_issued_at"])
        assert not _contains_any_key(payload, FORBIDDEN_REASONING_FIELDS)
        assert not _contains_any_key(payload, SECRET_LIKE_FIELDS)
        assert not _contains_any_key(payload, REGULATED_DATA_FIELDS)
        assert not _contains_any_key(payload, RAW_BODY_FIELDS)
        assert payload.get("final_commit_approved") is not True



def test_schema_adapter_invalid_fixtures_classify_deterministically() -> None:
    expected = {
        "invalid_unknown_rsa_status_v1alpha1.json": ADAPTER_UNKNOWN_RSA_STATUS,
        "invalid_missing_request_id_v1alpha1.json": ADAPTER_MISSING_REQUIRED_FIELD,
        "invalid_missing_correlation_id_v1alpha1.json": ADAPTER_MISSING_REQUIRED_FIELD,
        "invalid_forbidden_chain_of_thought_v1alpha1.json": ADAPTER_FORBIDDEN_FIELD_PRESENT,
        "invalid_secret_access_token_v1alpha1.json": ADAPTER_SECRET_LIKE_VALUE_PRESENT,
        "invalid_raw_kyc_record_v1alpha1.json": ADAPTER_REGULATED_DATA_PRESENT,
        "invalid_naive_timestamp_v1alpha1.json": ADAPTER_INVALID_TIMESTAMP,
        "invalid_payload_issued_at_future_skew_v1alpha1.json": ADAPTER_INVALID_TIMESTAMP,
        "invalid_unsupported_schema_version.json": ADAPTER_UNSUPPORTED_SCHEMA_VERSION,
    }

    for fixture_name, expected_classification in expected.items():
        payload = _load_payload_fixture(fixture_name)
        assert _classify_schema_adapter_input(payload) == expected_classification



def test_schema_adapter_invalid_classes_map_to_fail_closed_decisions() -> None:
    invalid_classes = [
        ADAPTER_UNSUPPORTED_SCHEMA_VERSION,
        ADAPTER_UNKNOWN_RSA_STATUS,
        ADAPTER_MISSING_REQUIRED_FIELD,
        ADAPTER_INVALID_TIMESTAMP,
        ADAPTER_FORBIDDEN_FIELD_PRESENT,
        ADAPTER_SECRET_LIKE_VALUE_PRESENT,
        ADAPTER_REGULATED_DATA_PRESENT,
        ADAPTER_REPLAY_DUPLICATE_REQUEST_ID,
        ADAPTER_INVALID_JSON_OBJECT,
    ]

    for class_name in invalid_classes:
        decision = _expected_fail_closed_adapter_decision(CLASS_TO_REASON_CODE[class_name])
        _assert_adapter_fail_closed(decision)
        _assert_no_final_commit(decision)
        assert decision["upstream_signal_source"] == "RSA"
        assert decision["veritas_continuation_decision"] != "CONTINUE_TO_BIND_BOUNDARY"
        assert decision["reason_code"] != "SAFE_PROCEED"



def test_schema_adapter_duplicate_request_id_scenario_fails_closed() -> None:
    scenario_a = _load_payload_fixture("invalid_duplicate_request_id_scenario_a_v1alpha1.json")
    scenario_b = _load_payload_fixture("invalid_duplicate_request_id_scenario_b_v1alpha1.json")
    assert scenario_a["request_id"] == scenario_b["request_id"]
    assert scenario_a["correlation_id"] != scenario_b["correlation_id"]

    seen_request_ids: dict[str, str] = {}
    assert _classify_schema_adapter_input(scenario_a, seen_request_ids=seen_request_ids) == ADAPTER_VALID
    assert _classify_schema_adapter_input(scenario_b, seen_request_ids=seen_request_ids) == ADAPTER_REPLAY_DUPLICATE_REQUEST_ID

    decision = _expected_fail_closed_adapter_decision("CONTROLLED_LIVE_REPLAY_DUPLICATE_REQUEST_ID")
    _assert_no_final_commit(decision)



def test_schema_adapter_safe_proceed_does_not_grant_final_commit() -> None:
    payload = _load_payload_fixture("valid_safe_proceed_v1alpha1.json")
    assert payload["rsa_status"] == "SAFE_PROCEED"
    assert _classify_schema_adapter_input(payload) == ADAPTER_VALID

    decision = _expected_fail_closed_adapter_decision("UPSTREAM_SAFE_PROCEED_SIGNAL")
    _assert_no_final_commit(decision)
    assert decision["final_commit_approved"] is False



def test_schema_adapter_rejects_forbidden_secret_and_regulated_fields() -> None:
    fixtures = {
        "invalid_forbidden_chain_of_thought_v1alpha1.json": ADAPTER_FORBIDDEN_FIELD_PRESENT,
        "invalid_secret_access_token_v1alpha1.json": ADAPTER_SECRET_LIKE_VALUE_PRESENT,
        "invalid_raw_kyc_record_v1alpha1.json": ADAPTER_REGULATED_DATA_PRESENT,
    }

    for fixture_name, expected_class in fixtures.items():
        payload = _load_payload_fixture(fixture_name)
        classification = _classify_schema_adapter_input(payload)
        assert classification == expected_class
        decision = _expected_fail_closed_adapter_decision(CLASS_TO_REASON_CODE[classification])
        _assert_adapter_fail_closed(decision)
        dumped = json.dumps(decision)
        assert "chain_of_thought" not in dumped
        assert "raw_kyc_record" not in dumped
        assert "access_token" not in dumped
        assert "raw_payload_body" not in dumped



def test_schema_adapter_rejects_non_object_payloads() -> None:
    for payload in (None, [], "not-json-object", 123):
        classification = _classify_schema_adapter_input(payload)
        assert classification == ADAPTER_INVALID_JSON_OBJECT
        decision = _expected_fail_closed_adapter_decision(CLASS_TO_REASON_CODE[classification])
        assert decision["reason_code"] == "CONTROLLED_LIVE_INVALID_JSON_OBJECT"
        _assert_no_final_commit(decision)



def test_schema_adapter_behavior_skeleton_is_offline_static_and_no_network() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    module = ast.parse(source)

    disallowed_import_roots = {"requests", "httpx", "urllib", "socket"}
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in disallowed_import_roots
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] not in disallowed_import_roots

    precheck_source = source.split(
        "def test_schema_adapter_behavior_skeleton_is_offline_static_and_no_network",
        maxsplit=1,
    )[0].lower()
    forbidden_literals = [
        "https://",
        "http://",
        "telemetrysdk",
        "live_viki_client",
        "prod.viki",
        "bear" + "er" + " ",
        "api" + "_key=",
    ]
    for token in forbidden_literals:
        assert token not in precheck_source



def test_schema_adapter_behavior_skeleton_does_not_touch_runtime_modules() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    module = ast.parse(source)

    disallowed_modules = {
        "veritas_os.governance.controlled_live_viki_schema_adapter",
        "veritas_os.goovernance.controlled_live_viki_schema_adapter",
        "live_viki_client",
    }
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in disallowed_modules
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module not in disallowed_modules
