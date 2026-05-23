"""Offline validation skeleton for controlled live V.I.K.I. observability event fixtures."""

from __future__ import annotations

import ast
import json
from datetime import datetime
from pathlib import Path

FIXTURE_DIR = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "controlled_live_viki_observability_events"
)

EXPECTED_FIXTURES = {
    "valid_safe_proceed_decision_event_v1alpha1.json",
    "valid_density_throttled_decision_event_v1alpha1.json",
    "valid_algorithmic_humility_decision_event_v1alpha1.json",
    "valid_deferral_decision_event_v1alpha1.json",
    "fail_closed_unknown_rsa_status_event_v1alpha1.json",
    "fail_closed_missing_request_id_event_v1alpha1.json",
    "fail_closed_forbidden_chain_of_thought_event_v1alpha1.json",
    "fail_closed_secret_access_token_event_v1alpha1.json",
    "fail_closed_raw_kyc_record_event_v1alpha1.json",
    "fail_closed_duplicate_request_id_event_v1alpha1.json",
    "upstream_timeout_fail_closed_event_v1alpha1.json",
    "transport_auth_failed_event_v1alpha1.json",
    "message_integrity_failed_event_v1alpha1.json",
    "replay_cache_unavailable_event_v1alpha1.json",
}

REQUIRED_FIELDS = {
    "event_type",
    "event_version",
    "schema_version",
    "upstream_signal_source",
    "request_id",
    "correlation_id",
    "timestamp",
    "payload_issued_at",
    "veritas_continuation_decision",
    "veritas_reason_code",
    "veritas_sandbox_commit_state",
    "required_next_action",
    "final_commit_approved",
}

ALLOWED_EVENT_TYPES = {
    "veritas_decision_emitted",
    "human_review_required",
    "fail_closed_emitted",
    "forbidden_field_detected",
    "secret_like_value_detected",
    "regulated_data_detected",
    "upstream_timeout",
    "transport_authentication_checked",
    "message_integrity_checked",
    "replay_cache_checked",
}

ALLOWED_AUTH_RESULT = {
    "AUTHENTICATED",
    "AUTHENTICATION_FAILED",
    "AUTHENTICATION_NOT_EVALUATED",
}
ALLOWED_INTEGRITY_RESULT = {
    "INTEGRITY_VALID",
    "INTEGRITY_FAILED",
    "BODY_HASH_MISMATCH",
    "INTEGRITY_NOT_EVALUATED",
}
ALLOWED_REPLAY_RESULT = {
    "NO_REPLAY_DETECTED",
    "REPLAY_DUPLICATE_REQUEST_ID",
    "REPLAY_CACHE_UNAVAILABLE",
    "REPLAY_NOT_EVALUATED",
}
ALLOWED_SCHEMA_RESULT = {
    "SCHEMA_VALID",
    "SCHEMA_INVALID",
    "SCHEMA_UNSUPPORTED_VERSION",
    "SCHEMA_UNKNOWN_RSA_STATUS",
    "SCHEMA_MISSING_REQUIRED_FIELD",
    "SCHEMA_INVALID_TIMESTAMP",
    "SCHEMA_NOT_EVALUATED",
}
ALLOWED_REDACTION_RESULT = {
    "REDACTION_VALID",
    "FORBIDDEN_FIELD_DETECTED",
    "SECRET_LIKE_VALUE_DETECTED",
    "REGULATED_DATA_DETECTED",
    "REDACTION_NOT_EVALUATED",
}
ALLOWED_CONTINUATION = {
    "CONTINUE_TO_BIND_BOUNDARY",
    "CONTINUE_WITH_UPSTREAM_INTERVENTION_LOGGED",
    "PAUSE_FOR_HUMAN_REVIEW",
}
ALLOWED_NEXT_ACTIONS = {
    "CONTINUE_BOUNDARY_EVALUATION",
    "CONTINUE_BOUNDARY_EVALUATION_WITH_INTERVENTION_AUDIT",
    "REQUEST_HUMAN_REVIEW_OR_RETRY_WITH_VALID_UPSTREAM_STATE",
    "REQUEST_VALID_SYNTHETIC_PAYLOAD_OR_HUMAN_REVIEW",
}
FORBIDDEN_FIELDS = {
    "chain_of_thought",
    "hidden_model_state",
    "raw_llm_reasoning",
    "raw_viki_reasoning",
    "raw_llm_text",
    "raw_kyc_record",
    "customer_pii",
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
    "unredacted_regulated_data",
    "raw_payload_body",
    "raw_request_body",
    "raw_response_body",
    "raw_stack_trace_with_secrets",
}

POSITIVE_FIXTURES = {
    "valid_safe_proceed_decision_event_v1alpha1.json",
    "valid_density_throttled_decision_event_v1alpha1.json",
    "valid_algorithmic_humility_decision_event_v1alpha1.json",
    "valid_deferral_decision_event_v1alpha1.json",
}

FAIL_CLOSED_FIXTURES = {
    "fail_closed_unknown_rsa_status_event_v1alpha1.json",
    "fail_closed_missing_request_id_event_v1alpha1.json",
    "fail_closed_forbidden_chain_of_thought_event_v1alpha1.json",
    "fail_closed_secret_access_token_event_v1alpha1.json",
    "fail_closed_raw_kyc_record_event_v1alpha1.json",
    "fail_closed_duplicate_request_id_event_v1alpha1.json",
    "upstream_timeout_fail_closed_event_v1alpha1.json",
    "transport_auth_failed_event_v1alpha1.json",
    "message_integrity_failed_event_v1alpha1.json",
    "replay_cache_unavailable_event_v1alpha1.json",
}


def _load_event_fixture(name: str) -> dict:
    with (FIXTURE_DIR / name).open("r", encoding="utf-8") as fixture_file:
        payload = json.load(fixture_file)
    assert isinstance(payload, dict)
    return payload


def _load_all_event_fixtures() -> dict[str, dict]:
    return {name: _load_event_fixture(name) for name in sorted(EXPECTED_FIXTURES)}


def _is_timezone_aware_timestamp(value: str) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _contains_forbidden_field(payload: dict) -> bool:
    return any(field in payload for field in FORBIDDEN_FIELDS)


def _assert_required_event_fields(payload: dict, fixture_name: str) -> None:
    for field in REQUIRED_FIELDS:
        assert field in payload, f"missing required field {field} in {fixture_name}"
    for field in REQUIRED_FIELDS - {"final_commit_approved"}:
        assert isinstance(payload[field], str), f"{field} must be str in {fixture_name}"
        assert payload[field].strip(), f"{field} must be non-empty in {fixture_name}"


def _assert_no_final_commit(payload: dict) -> None:
    assert payload["final_commit_approved"] is False
    assert payload["veritas_sandbox_commit_state"] == "SUSPENDED_NOT_COMMITTED"


def _assert_fail_closed_event(payload: dict) -> None:
    assert payload["veritas_continuation_decision"] == "PAUSE_FOR_HUMAN_REVIEW"
    assert payload["veritas_sandbox_commit_state"] == "SUSPENDED_NOT_COMMITTED"
    assert payload["final_commit_approved"] is False


def test_observability_event_fixture_inventory_is_exact() -> None:
    assert FIXTURE_DIR.exists()
    json_files = {path.name for path in FIXTURE_DIR.glob("*.json")}
    assert EXPECTED_FIXTURES.issubset(json_files)
    assert not (EXPECTED_FIXTURES - json_files)
    assert json_files == EXPECTED_FIXTURES


def test_observability_event_fixtures_are_valid_json_objects() -> None:
    fixtures = _load_all_event_fixtures()
    assert fixtures
    for name, payload in fixtures.items():
        assert isinstance(payload, dict), name
        assert not isinstance(payload, list), name
        assert payload, name


def test_observability_event_required_fields_and_versions() -> None:
    for name, payload in _load_all_event_fixtures().items():
        _assert_required_event_fields(payload, name)
        assert payload["event_version"] == "v1alpha1"
        assert payload["schema_version"] == "v1alpha1"
        assert payload["upstream_signal_source"] == "RSA"
        assert _is_timezone_aware_timestamp(payload["timestamp"])
        assert _is_timezone_aware_timestamp(payload["payload_issued_at"])
        _assert_no_final_commit(payload)


def test_observability_event_taxonomy_values_are_allowed() -> None:
    for payload in _load_all_event_fixtures().values():
        assert payload["event_type"] in ALLOWED_EVENT_TYPES
        if "authentication_result_class" in payload:
            assert payload["authentication_result_class"] in ALLOWED_AUTH_RESULT
        if "integrity_result_class" in payload:
            assert payload["integrity_result_class"] in ALLOWED_INTEGRITY_RESULT
        if "replay_result_class" in payload:
            assert payload["replay_result_class"] in ALLOWED_REPLAY_RESULT
        if "schema_validation_result_class" in payload:
            assert payload["schema_validation_result_class"] in ALLOWED_SCHEMA_RESULT
        if "redaction_result_class" in payload:
            assert payload["redaction_result_class"] in ALLOWED_REDACTION_RESULT
        assert payload["veritas_continuation_decision"] in ALLOWED_CONTINUATION
        assert payload["veritas_sandbox_commit_state"] == "SUSPENDED_NOT_COMMITTED"
        assert payload["required_next_action"] in ALLOWED_NEXT_ACTIONS


def test_positive_observability_events_do_not_grant_final_commit() -> None:
    fixtures = _load_all_event_fixtures()

    for fixture_name in POSITIVE_FIXTURES:
        payload = fixtures[fixture_name]
        _assert_no_final_commit(payload)

    safe_proceed = fixtures["valid_safe_proceed_decision_event_v1alpha1.json"]
    assert safe_proceed["veritas_continuation_decision"] == "CONTINUE_TO_BIND_BOUNDARY"
    assert safe_proceed["required_next_action"] == "CONTINUE_BOUNDARY_EVALUATION"
    assert safe_proceed["final_commit_approved"] is False

    density = fixtures["valid_density_throttled_decision_event_v1alpha1.json"]
    assert density["veritas_continuation_decision"] == "CONTINUE_WITH_UPSTREAM_INTERVENTION_LOGGED"

    humility = fixtures["valid_algorithmic_humility_decision_event_v1alpha1.json"]
    assert humility["veritas_continuation_decision"] == "PAUSE_FOR_HUMAN_REVIEW"

    deferral = fixtures["valid_deferral_decision_event_v1alpha1.json"]
    assert deferral["veritas_continuation_decision"] == "PAUSE_FOR_HUMAN_REVIEW"


def test_fail_closed_observability_events_map_to_pause_and_suspended() -> None:
    fixtures = _load_all_event_fixtures()
    allowed_fail_closed_actions = {
        "REQUEST_HUMAN_REVIEW_OR_RETRY_WITH_VALID_UPSTREAM_STATE",
        "REQUEST_VALID_SYNTHETIC_PAYLOAD_OR_HUMAN_REVIEW",
    }

    for fixture_name in FAIL_CLOSED_FIXTURES:
        payload = fixtures[fixture_name]
        _assert_fail_closed_event(payload)
        assert payload["required_next_action"] in allowed_fail_closed_actions
        assert payload["veritas_reason_code"].startswith("CONTROLLED_LIVE_")


def test_observability_event_forbidden_fields_are_absent() -> None:
    for payload in _load_all_event_fixtures().values():
        assert not _contains_forbidden_field(payload)


def test_observability_event_fixture_reference_metadata_is_synthetic() -> None:
    for fixture_name, payload in _load_all_event_fixtures().items():
        assert payload["request_id"].startswith("req_viki_")
        assert payload["correlation_id"].startswith("corr_viki_veritas_")
        if "fixture_name" in payload:
            assert payload["fixture_name"].endswith(".json")
        if "body_hash_prefix" in payload:
            assert payload["body_hash_prefix"].startswith("sha256:synthetic-prefix")
        if "latency_ms" in payload:
            assert isinstance(payload["latency_ms"], int)
            assert payload["latency_ms"] >= 0
        assert fixture_name.endswith(".json")


def test_observability_event_skeleton_uses_static_offline_inputs_only() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    module = ast.parse(source)

    disallowed_import_roots = {"requests", "httpx", "urllib", "socket"}
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in disallowed_import_roots
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] not in disallowed_import_roots

    assert "os.environ" not in source

    lowered = source.lower()
    banned_substrings = ["https://", "http://", "api_key", "bearer "]
    for token in banned_substrings:
        assert token not in lowered
