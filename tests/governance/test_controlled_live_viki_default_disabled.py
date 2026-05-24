"""Offline default-disabled behavior skeleton for controlled live V.I.K.I."""

from __future__ import annotations

import ast
import json
from pathlib import Path

FEATURE_FLAG_NAME = "VERITAS_CONTROLLED_LIVE_VIKI_ENABLE"

EXPECTED_CONTINUATION = "PAUSE_FOR_HUMAN_REVIEW"
EXPECTED_COMMIT_STATE = "SUSPENDED_NOT_COMMITTED"
EXPECTED_REQUIRED_NEXT_ACTION = "REQUEST_HUMAN_REVIEW_OR_RETRY_WITH_VALID_UPSTREAM_STATE"
EXPECTED_REASON_CODE = "CONTROLLED_LIVE_DISABLED"
EXPECTED_UPSTREAM_SOURCE = "RSA"
EXPECTED_DECISION_SOURCE = "controlled_live_viki_default_disabled_skeleton"


def _is_enabled_flag_value(value: str | None) -> bool:
    return value == "true"


def _default_disabled_decision(
    *,
    request_id: str = "req_viki_disabled_001",
    correlation_id: str = "corr_viki_veritas_disabled_001",
    schema_version: str = "v1alpha1",
) -> dict:
    return {
        "veritas_continuation_decision": EXPECTED_CONTINUATION,
        "veritas_reason_code": EXPECTED_REASON_CODE,
        "veritas_sandbox_commit_state": EXPECTED_COMMIT_STATE,
        "required_next_action": EXPECTED_REQUIRED_NEXT_ACTION,
        "final_commit_approved": False,
        "upstream_signal_source": EXPECTED_UPSTREAM_SOURCE,
        "request_id": request_id,
        "correlation_id": correlation_id,
        "schema_version": schema_version,
        "decision_source": EXPECTED_DECISION_SOURCE,
    }


def _assert_disabled_fail_closed(decision: dict) -> None:
    assert decision["veritas_continuation_decision"] == EXPECTED_CONTINUATION
    assert decision["veritas_sandbox_commit_state"] == EXPECTED_COMMIT_STATE
    assert decision["veritas_reason_code"] == EXPECTED_REASON_CODE
    assert decision["required_next_action"] == EXPECTED_REQUIRED_NEXT_ACTION


def _assert_no_final_commit(decision: dict) -> None:
    assert decision["final_commit_approved"] is False
    assert decision["veritas_sandbox_commit_state"] == EXPECTED_COMMIT_STATE


def test_controlled_live_feature_flag_missing_is_disabled() -> None:
    assert _is_enabled_flag_value(None) is False

    decision = _default_disabled_decision()
    assert decision["veritas_reason_code"] == EXPECTED_REASON_CODE
    assert decision["veritas_continuation_decision"] == EXPECTED_CONTINUATION
    assert decision["veritas_sandbox_commit_state"] == EXPECTED_COMMIT_STATE
    assert decision["final_commit_approved"] is False


def test_controlled_live_feature_flag_empty_false_or_unknown_is_disabled() -> None:
    disabled_values = ["", " ", "false", "0", "no", "off", "disabled", "TRUE", "True", "unexpected"]

    for value in disabled_values:
        assert _is_enabled_flag_value(value) is False
        decision = _default_disabled_decision()
        _assert_disabled_fail_closed(decision)
        _assert_no_final_commit(decision)
        assert decision["veritas_continuation_decision"] != "SAFE_PROCEED"


def test_controlled_live_feature_flag_true_is_the_only_enabled_value() -> None:
    assert _is_enabled_flag_value("true") is True
    assert _is_enabled_flag_value("TRUE") is False
    assert _is_enabled_flag_value("True") is False


def test_default_disabled_decision_shape_is_deterministic() -> None:
    decision = _default_disabled_decision()

    required_keys = {
        "veritas_continuation_decision",
        "veritas_reason_code",
        "veritas_sandbox_commit_state",
        "required_next_action",
        "final_commit_approved",
        "upstream_signal_source",
        "request_id",
        "correlation_id",
        "schema_version",
        "decision_source",
    }
    assert required_keys.issubset(decision.keys())

    assert decision["veritas_continuation_decision"] == EXPECTED_CONTINUATION
    assert decision["veritas_reason_code"] == EXPECTED_REASON_CODE
    assert decision["veritas_sandbox_commit_state"] == EXPECTED_COMMIT_STATE
    assert decision["required_next_action"] == EXPECTED_REQUIRED_NEXT_ACTION
    assert decision["final_commit_approved"] is False
    assert decision["upstream_signal_source"] == EXPECTED_UPSTREAM_SOURCE
    assert decision["schema_version"] == "v1alpha1"


def test_default_disabled_does_not_grant_safe_proceed_or_final_commit() -> None:
    decision = _default_disabled_decision()

    assert decision.get("rsa_status") != "SAFE_PROCEED"
    assert "CONTINUE_TO_BIND_BOUNDARY" not in decision.values()
    assert "CONTINUE_WITH_UPSTREAM_INTERVENTION_LOGGED" not in decision.values()
    assert decision["final_commit_approved"] is False
    assert decision["veritas_sandbox_commit_state"] == EXPECTED_COMMIT_STATE


def test_default_disabled_preserves_synthetic_request_and_correlation_ids() -> None:
    decision = _default_disabled_decision()

    request_id = decision["request_id"]
    correlation_id = decision["correlation_id"]

    assert isinstance(request_id, str) and request_id
    assert isinstance(correlation_id, str) and correlation_id
    assert request_id.startswith("req_viki_")
    assert correlation_id.startswith("corr_viki_veritas_")

    combined = (request_id + " " + correlation_id).lower()
    token_word = "to" + "ken"
    banned_markers = ["secret", "credential", "access_" + token_word, "bearer", "raw_payload"]
    for marker in banned_markers:
        assert marker not in combined


def test_default_disabled_skeleton_is_offline_static_and_no_network() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    module = ast.parse(source)

    disallowed_import_roots = {"requests", "httpx", "urllib", "socket"}
    disallowed_sdk_roots = {"opentelemetry", "sentry_sdk"}

    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root not in disallowed_import_roots
                assert root not in disallowed_sdk_roots
        if isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            assert root not in disallowed_import_roots
            assert root not in disallowed_sdk_roots

    precheck_source = source.split(
        "def test_default_disabled_skeleton_is_offline_static_and_no_network", maxsplit=1
    )[0]
    lowered_source = precheck_source.lower()
    forbidden_strings = ["https://", "http://", "viki_live_client", "api_key", "bearer "]
    for token in forbidden_strings:
        assert token not in lowered_source


def test_default_disabled_skeleton_does_not_touch_runtime_modules() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    module = ast.parse(source)

    for node in ast.walk(module):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not node.module.startswith("veritas_os")
            assert "controlled_live_viki" not in node.module
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("veritas_os")
                assert "controlled_live_viki" not in alias.name


def test_safe_proceed_fixture_still_does_not_mean_final_approval_under_default_disabled_contract() -> None:
    fixture_path = Path("tests/fixtures/controlled_live_viki_payload_schema/valid_safe_proceed_v1alpha1.json")
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))

    assert payload["rsa_status"] == "SAFE_PROCEED"

    decision = _default_disabled_decision(
        request_id=payload["request_id"],
        correlation_id=payload["correlation_id"],
        schema_version=payload["schema_version"],
    )
    assert decision["veritas_reason_code"] == EXPECTED_REASON_CODE
    assert decision["final_commit_approved"] is False
    assert decision["veritas_continuation_decision"] != "SAFE_PROCEED"
