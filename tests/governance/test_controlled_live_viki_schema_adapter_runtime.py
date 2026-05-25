"""Runtime tests for the local controlled live V.I.K.I. schema adapter."""

from __future__ import annotations

import ast
import json
from datetime import datetime
from pathlib import Path

from veritas_os.governance.controlled_live_viki_schema_adapter import (
    ACCEPTED_RSA_STATUSES,
    ADAPTER_FORBIDDEN_FIELD_PRESENT,
    ADAPTER_INVALID_JSON_OBJECT,
    ADAPTER_INVALID_TIMESTAMP,
    ADAPTER_MISSING_REQUIRED_FIELD,
    ADAPTER_REGULATED_DATA_PRESENT,
    ADAPTER_REPLAY_DUPLICATE_REQUEST_ID,
    ADAPTER_SECRET_LIKE_VALUE_PRESENT,
    ADAPTER_UNKNOWN_RSA_STATUS,
    ADAPTER_UNSUPPORTED_SCHEMA_VERSION,
    ADAPTER_VALID,
    CLASS_TO_REASON_CODE,
    CONTROLLED_LIVE_VIKI_SCHEMA_VERSION,
    FORBIDDEN_REASONING_FIELDS,
    RAW_BODY_FIELDS,
    REGULATED_DATA_FIELDS,
    REQUIRED_FIELDS,
    SECRET_LIKE_FIELDS,
    build_controlled_live_viki_schema_fail_closed_decision,
    classify_controlled_live_viki_schema_input,
    contains_any_key,
    controlled_live_viki_reason_code_for_classification,
    has_future_payload_issued_at_skew,
    is_timezone_aware_timestamp,
)


def _load_payload_fixture(name: str) -> dict:
    fixture_dir = Path(__file__).resolve().parent.parent / "fixtures" / "controlled_live_viki_payload_schema"
    return json.loads((fixture_dir / name).read_text(encoding="utf-8"))


def test_schema_adapter_runtime_valid_fixtures_classify_as_valid() -> None:
    fixtures = [
        "valid_safe_proceed_v1alpha1.json",
        "valid_density_throttled_v1alpha1.json",
        "valid_algorithmic_humility_engaged_v1alpha1.json",
        "valid_deferral_engaged_v1alpha1.json",
    ]
    for fixture_name in fixtures:
        payload = _load_payload_fixture(fixture_name)
        assert classify_controlled_live_viki_schema_input(payload) == ADAPTER_VALID
        assert payload["schema_version"] == CONTROLLED_LIVE_VIKI_SCHEMA_VERSION
        assert payload["rsa_status"] in ACCEPTED_RSA_STATUSES
        assert all(field in payload for field in REQUIRED_FIELDS)
        assert is_timezone_aware_timestamp(payload["timestamp"])
        assert is_timezone_aware_timestamp(payload["payload_issued_at"])
        assert not contains_any_key(payload, FORBIDDEN_REASONING_FIELDS)
        assert not contains_any_key(payload, SECRET_LIKE_FIELDS)
        assert not contains_any_key(payload, REGULATED_DATA_FIELDS)
        assert not contains_any_key(payload, RAW_BODY_FIELDS)
        assert payload.get("final_commit_approved") is not True


def test_schema_adapter_runtime_invalid_fixtures_classify_deterministically() -> None:
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
    for fixture_name, classification in expected.items():
        payload = _load_payload_fixture(fixture_name)
        assert classify_controlled_live_viki_schema_input(payload) == classification


def test_schema_adapter_runtime_invalid_classes_map_to_fail_closed_decisions() -> None:
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
    for classification in invalid_classes:
        reason_code = controlled_live_viki_reason_code_for_classification(classification)
        assert reason_code == CLASS_TO_REASON_CODE[classification]
        decision = build_controlled_live_viki_schema_fail_closed_decision(reason_code)
        assert decision["veritas_continuation_decision"] == "PAUSE_FOR_HUMAN_REVIEW"
        assert decision["veritas_sandbox_commit_state"] == "SUSPENDED_NOT_COMMITTED"
        assert decision["final_commit_approved"] is False
        assert decision["upstream_signal_source"] == "RSA"
        assert decision["reason_code"] != "SAFE_PROCEED"
        assert decision["veritas_continuation_decision"] != "CONTINUE_TO_BIND_BOUNDARY"


def test_schema_adapter_runtime_duplicate_request_id_scenario_fails_closed() -> None:
    scenario_a = _load_payload_fixture("invalid_duplicate_request_id_scenario_a_v1alpha1.json")
    scenario_b = _load_payload_fixture("invalid_duplicate_request_id_scenario_b_v1alpha1.json")
    assert scenario_a["request_id"] == scenario_b["request_id"]
    assert scenario_a["correlation_id"] != scenario_b["correlation_id"]

    seen_request_ids: dict[str, str] = {}
    assert classify_controlled_live_viki_schema_input(scenario_a, seen_request_ids=seen_request_ids) == ADAPTER_VALID
    assert (
        classify_controlled_live_viki_schema_input(scenario_b, seen_request_ids=seen_request_ids)
        == ADAPTER_REPLAY_DUPLICATE_REQUEST_ID
    )
    reason = controlled_live_viki_reason_code_for_classification(ADAPTER_REPLAY_DUPLICATE_REQUEST_ID)
    assert reason == "CONTROLLED_LIVE_REPLAY_DUPLICATE_REQUEST_ID"
    decision = build_controlled_live_viki_schema_fail_closed_decision(reason)
    assert decision["final_commit_approved"] is False


def test_schema_adapter_runtime_safe_proceed_does_not_grant_final_commit() -> None:
    payload = _load_payload_fixture("valid_safe_proceed_v1alpha1.json")
    assert payload["rsa_status"] == "SAFE_PROCEED"
    assert classify_controlled_live_viki_schema_input(payload) == ADAPTER_VALID

    decision = build_controlled_live_viki_schema_fail_closed_decision("UPSTREAM_SAFE_PROCEED_SIGNAL")
    assert decision["final_commit_approved"] is False


def test_schema_adapter_runtime_rejects_forbidden_secret_and_regulated_fields() -> None:
    fixtures = {
        "invalid_forbidden_chain_of_thought_v1alpha1.json": ADAPTER_FORBIDDEN_FIELD_PRESENT,
        "invalid_secret_access_token_v1alpha1.json": ADAPTER_SECRET_LIKE_VALUE_PRESENT,
        "invalid_raw_kyc_record_v1alpha1.json": ADAPTER_REGULATED_DATA_PRESENT,
    }

    for fixture_name, expected_class in fixtures.items():
        payload = _load_payload_fixture(fixture_name)
        classification = classify_controlled_live_viki_schema_input(payload)
        assert classification == expected_class
        reason = controlled_live_viki_reason_code_for_classification(classification)
        decision = build_controlled_live_viki_schema_fail_closed_decision(reason)
        dumped = json.dumps(decision)
        assert "chain_of_thought" not in dumped
        assert "raw_kyc_record" not in dumped
        assert "access_token" not in dumped
        assert "raw_payload_body" not in dumped


def test_schema_adapter_runtime_rejects_non_object_payloads() -> None:
    for payload in (None, [], "not-json-object", 123):
        classification = classify_controlled_live_viki_schema_input(payload)
        assert classification == ADAPTER_INVALID_JSON_OBJECT
        reason = controlled_live_viki_reason_code_for_classification(classification)
        decision = build_controlled_live_viki_schema_fail_closed_decision(reason)
        assert decision["reason_code"] == "CONTROLLED_LIVE_INVALID_JSON_OBJECT"
        assert decision["final_commit_approved"] is False


def test_schema_adapter_runtime_future_skew_is_fixture_relative_not_current_time_dependent() -> None:
    payload = _load_payload_fixture("invalid_payload_issued_at_future_skew_v1alpha1.json")
    assert is_timezone_aware_timestamp(payload["timestamp"])
    assert is_timezone_aware_timestamp(payload["payload_issued_at"])

    timestamp = datetime.fromisoformat(payload["timestamp"].replace("Z", "+00:00"))
    payload_issued_at = datetime.fromisoformat(payload["payload_issued_at"].replace("Z", "+00:00"))
    assert payload_issued_at > timestamp
    assert (payload_issued_at - timestamp).total_seconds() > 300
    assert has_future_payload_issued_at_skew(payload["timestamp"], payload["payload_issued_at"])
    assert classify_controlled_live_viki_schema_input(payload) == ADAPTER_INVALID_TIMESTAMP


def test_schema_adapter_runtime_module_is_no_network_no_endpoint_no_telemetry() -> None:
    source_path = Path("veritas_os/governance/controlled_live_viki_schema_adapter.py")
    source = source_path.read_text(encoding="utf-8")
    module = ast.parse(source)

    disallowed_import_roots = {"requests", "httpx", "urllib", "socket"}
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in disallowed_import_roots
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] not in disallowed_import_roots

    lowered = source.lower()
    forbidden_literals = [
        "http" + "://",
        "https" + "://",
        "bear" + "er" + " ",
        "api" + "_" + "key=",
        "telemetrysdk",
        "fastapi",
        "flask",
        "live_viki_client",
    ]
    for token in forbidden_literals:
        assert token not in lowered


def test_schema_adapter_runtime_does_not_touch_downstream_contract() -> None:
    source = Path("veritas_os/governance/controlled_live_viki_schema_adapter.py").read_text(encoding="utf-8")
    assert "viki_status" not in source
    assert "VIKIPayload" not in source
    assert "rsa_status" in source

    decision = build_controlled_live_viki_schema_fail_closed_decision("CONTROLLED_LIVE_INVALID_JSON_OBJECT")
    assert decision["upstream_signal_source"] == "RSA"
