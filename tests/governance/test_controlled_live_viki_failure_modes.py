"""Offline failure-mode skeleton for controlled live V.I.K.I. sandbox decisions."""

from __future__ import annotations

from pathlib import Path

from tests.governance.test_controlled_live_viki_fixture_validation import (
    _classify_fixture,
    _load_fixture,
)

FAIL_CLOSED_CONTINUATION = "PAUSE_FOR_HUMAN_REVIEW"
FAIL_CLOSED_COMMIT_STATE = "SUSPENDED_NOT_COMMITTED"
FAIL_CLOSED_NEXT_ACTION = "REQUEST_HUMAN_REVIEW_OR_RETRY_WITH_VALID_UPSTREAM_STATE"
FAIL_CLOSED_SYNTHETIC_RETRY_ACTION = "REQUEST_VALID_SYNTHETIC_PAYLOAD_OR_HUMAN_REVIEW"


def _expected_fail_closed_decision(
    reason_code: str,
    *,
    required_next_action: str = FAIL_CLOSED_NEXT_ACTION,
) -> dict:
    return {
        "continuation_decision": FAIL_CLOSED_CONTINUATION,
        "sandbox_commit_state": FAIL_CLOSED_COMMIT_STATE,
        "required_next_action": required_next_action,
        "final_commit_approved": False,
        "reason_code": reason_code,
    }


def _expected_valid_fixture_decision(rsa_status: str) -> dict:
    decision_map = {
        "SAFE_PROCEED": {
            "continuation_decision": "CONTINUE_TO_BIND_BOUNDARY",
            "sandbox_commit_state": "SUSPENDED_NOT_COMMITTED",
            "required_next_action": "CONTINUE_BOUNDARY_EVALUATION",
            "final_commit_approved": False,
            "reason_code": "UPSTREAM_SAFE_PROCEED_SIGNAL",
        },
        "DENSITY_THROTTLED": {
            "continuation_decision": "CONTINUE_WITH_UPSTREAM_INTERVENTION_LOGGED",
            "sandbox_commit_state": "SUSPENDED_NOT_COMMITTED",
            "required_next_action": "CONTINUE_BOUNDARY_EVALUATION_WITH_INTERVENTION_AUDIT",
            "final_commit_approved": False,
            "reason_code": "UPSTREAM_DENSITY_THROTTLED_SIGNAL",
        },
        "ALGORITHMIC_HUMILITY_ENGAGED": _expected_fail_closed_decision(
            "UPSTREAM_ALGORITHMIC_HUMILITY_SIGNAL"
        ),
        "DEFERRAL_ENGAGED": _expected_fail_closed_decision("UPSTREAM_DEFERRAL_SIGNAL"),
    }
    return decision_map[rsa_status]


def _assert_fail_closed(decision: dict) -> None:
    assert decision["continuation_decision"] == FAIL_CLOSED_CONTINUATION
    assert decision["sandbox_commit_state"] == FAIL_CLOSED_COMMIT_STATE
    assert decision["final_commit_approved"] is False


def _assert_not_final_commit(decision: dict) -> None:
    assert decision["final_commit_approved"] is False
    assert decision["sandbox_commit_state"] == "SUSPENDED_NOT_COMMITTED"


def test_valid_fixture_statuses_do_not_grant_final_commit() -> None:
    valid_fixtures = [
        "valid_safe_proceed_v1alpha1.json",
        "valid_density_throttled_v1alpha1.json",
        "valid_algorithmic_humility_engaged_v1alpha1.json",
        "valid_deferral_engaged_v1alpha1.json",
    ]

    for fixture_name in valid_fixtures:
        payload = _load_fixture(fixture_name)
        decision = _expected_valid_fixture_decision(payload["rsa_status"])
        _assert_not_final_commit(decision)
        if payload["rsa_status"] == "SAFE_PROCEED":
            assert decision["continuation_decision"] == "CONTINUE_TO_BIND_BOUNDARY"
            assert decision["final_commit_approved"] is False


def test_invalid_fixture_classes_map_to_fail_closed_decisions() -> None:
    expected_by_classification = {
        "FIXTURE_UNKNOWN_RSA_STATUS": _expected_fail_closed_decision(
            "CONTROLLED_LIVE_UNKNOWN_RSA_STATUS"
        ),
        "FIXTURE_MISSING_REQUIRED_FIELD": _expected_fail_closed_decision(
            "CONTROLLED_LIVE_MISSING_REQUIRED_FIELD",
            required_next_action=FAIL_CLOSED_SYNTHETIC_RETRY_ACTION,
        ),
        "FIXTURE_INVALID_TIMESTAMP": _expected_fail_closed_decision(
            "CONTROLLED_LIVE_INVALID_TIMESTAMP"
        ),
        "FIXTURE_UNSUPPORTED_SCHEMA_VERSION": _expected_fail_closed_decision(
            "CONTROLLED_LIVE_UNSUPPORTED_SCHEMA_VERSION",
            required_next_action=FAIL_CLOSED_SYNTHETIC_RETRY_ACTION,
        ),
        "FIXTURE_FORBIDDEN_FIELD_PRESENT": _expected_fail_closed_decision(
            "CONTROLLED_LIVE_FORBIDDEN_FIELD_PRESENT"
        ),
        "FIXTURE_SECRET_LIKE_VALUE_PRESENT": _expected_fail_closed_decision(
            "CONTROLLED_LIVE_SECRET_LIKE_VALUE_PRESENT"
        ),
        "FIXTURE_REGULATED_DATA_PRESENT": _expected_fail_closed_decision(
            "CONTROLLED_LIVE_REGULATED_DATA_PRESENT"
        ),
    }

    invalid_fixtures = [
        "invalid_unknown_rsa_status_v1alpha1.json",
        "invalid_missing_request_id_v1alpha1.json",
        "invalid_missing_correlation_id_v1alpha1.json",
        "invalid_forbidden_chain_of_thought_v1alpha1.json",
        "invalid_secret_access_token_v1alpha1.json",
        "invalid_raw_kyc_record_v1alpha1.json",
        "invalid_naive_timestamp_v1alpha1.json",
        "invalid_payload_issued_at_future_skew_v1alpha1.json",
        "invalid_unsupported_schema_version.json",
    ]

    for fixture_name in invalid_fixtures:
        payload = _load_fixture(fixture_name)
        classification = _classify_fixture(fixture_name, payload)
        decision = expected_by_classification[classification]
        _assert_fail_closed(decision)
        assert decision["continuation_decision"] != "CONTINUE_TO_BIND_BOUNDARY"


def test_duplicate_request_id_maps_to_replay_fail_closed() -> None:
    scenario_a_name = "invalid_duplicate_request_id_scenario_a_v1alpha1.json"
    scenario_b_name = "invalid_duplicate_request_id_scenario_b_v1alpha1.json"
    scenario_a = _load_fixture(scenario_a_name)
    scenario_b = _load_fixture(scenario_b_name)

    seen_request_ids: dict[str, str] = {}
    assert _classify_fixture(scenario_a_name, scenario_a, seen_request_ids=seen_request_ids) == "FIXTURE_VALID"
    classification_b = _classify_fixture(scenario_b_name, scenario_b, seen_request_ids=seen_request_ids)
    assert classification_b == "FIXTURE_REPLAY_SCENARIO_DUPLICATE"

    decision = _expected_fail_closed_decision("CONTROLLED_LIVE_REPLAY_DUPLICATE_REQUEST_ID")
    _assert_fail_closed(decision)
    assert decision["reason_code"] == "CONTROLLED_LIVE_REPLAY_DUPLICATE_REQUEST_ID"


def test_forbidden_content_failure_modes_never_continue() -> None:
    forbidden_cases = {
        "invalid_forbidden_chain_of_thought_v1alpha1.json": "FIXTURE_FORBIDDEN_FIELD_PRESENT",
        "invalid_secret_access_token_v1alpha1.json": "FIXTURE_SECRET_LIKE_VALUE_PRESENT",
        "invalid_raw_kyc_record_v1alpha1.json": "FIXTURE_REGULATED_DATA_PRESENT",
    }
    class_to_reason = {
        "FIXTURE_FORBIDDEN_FIELD_PRESENT": "CONTROLLED_LIVE_FORBIDDEN_FIELD_PRESENT",
        "FIXTURE_SECRET_LIKE_VALUE_PRESENT": "CONTROLLED_LIVE_SECRET_LIKE_VALUE_PRESENT",
        "FIXTURE_REGULATED_DATA_PRESENT": "CONTROLLED_LIVE_REGULATED_DATA_PRESENT",
    }

    for fixture_name, expected_classification in forbidden_cases.items():
        payload = _load_fixture(fixture_name)
        classification = _classify_fixture(fixture_name, payload)
        assert classification == expected_classification
        decision = _expected_fail_closed_decision(class_to_reason[classification])
        _assert_fail_closed(decision)
        assert decision["continuation_decision"] != "CONTINUE_TO_BIND_BOUNDARY"


def test_transport_and_upstream_failure_modes_fail_closed() -> None:
    simulated_failures = {
        "TIMEOUT": "CONTROLLED_LIVE_UPSTREAM_TIMEOUT",
        "UPSTREAM_UNAVAILABLE": "CONTROLLED_LIVE_UPSTREAM_UNAVAILABLE",
        "TRANSPORT_AUTH_FAILED": "CONTROLLED_LIVE_TRANSPORT_AUTH_FAILED",
        "MESSAGE_INTEGRITY_FAILED": "CONTROLLED_LIVE_MESSAGE_INTEGRITY_FAILED",
        "REPLAY_CACHE_UNAVAILABLE": "CONTROLLED_LIVE_REPLAY_CACHE_UNAVAILABLE",
    }

    for reason_code in simulated_failures.values():
        decision = _expected_fail_closed_decision(reason_code)
        _assert_fail_closed(decision)
        assert decision["required_next_action"] == FAIL_CLOSED_NEXT_ACTION


def test_failure_mode_skeleton_uses_static_offline_inputs_only() -> None:
    import ast

    source = Path(__file__).read_text(encoding="utf-8")
    module = ast.parse(source)

    disallowed_import_roots = {"requests", "httpx", "urllib", "socket"}
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in disallowed_import_roots
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] not in disallowed_import_roots

    forbidden_env_access = "os" + "." + "environ"
    assert forbidden_env_access not in source

    precheck_source = source.split("def test_failure_mode_skeleton_uses_static_offline_inputs_only", maxsplit=1)[0]
    banned_substrings = ["https://", "http://", "bearer ", "authorization:"]
    lowered_source = precheck_source.lower()
    for token in banned_substrings:
        assert token not in lowered_source
