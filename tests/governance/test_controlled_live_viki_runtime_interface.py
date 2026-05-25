"""Runtime tests for local disabled-by-default controlled live V.I.K.I. interface."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

_RUNTIME_MODULE_PATH = Path("veritas_os/governance/controlled_live_viki_interface.py")
_RUNTIME_SPEC = importlib.util.spec_from_file_location(
    "controlled_live_viki_interface",
    _RUNTIME_MODULE_PATH,
)
assert _RUNTIME_SPEC is not None
assert _RUNTIME_SPEC.loader is not None
_RUNTIME_MODULE = importlib.util.module_from_spec(_RUNTIME_SPEC)
_RUNTIME_SPEC.loader.exec_module(_RUNTIME_MODULE)

is_controlled_live_viki_enabled = _RUNTIME_MODULE.is_controlled_live_viki_enabled
receive_controlled_live_viki_payload = _RUNTIME_MODULE.receive_controlled_live_viki_payload


EXPECTED_CONTINUATION = "PAUSE_FOR_HUMAN_REVIEW"
EXPECTED_COMMIT_STATE = "SUSPENDED_NOT_COMMITTED"
EXPECTED_NEXT_ACTION = "REQUEST_HUMAN_REVIEW_OR_RETRY_WITH_VALID_UPSTREAM_STATE"


def test_runtime_interface_feature_flag_missing_is_disabled() -> None:
    decision = receive_controlled_live_viki_payload(feature_flag_value=None)

    assert decision["veritas_reason_code"] == "CONTROLLED_LIVE_DISABLED"
    assert decision["veritas_continuation_decision"] == EXPECTED_CONTINUATION
    assert decision["veritas_sandbox_commit_state"] == EXPECTED_COMMIT_STATE
    assert decision["final_commit_approved"] is False


def test_runtime_interface_feature_flag_empty_false_or_unknown_is_disabled() -> None:
    disabled_values = ["", " ", "false", "0", "no", "off", "disabled", "TRUE", "True", "unexpected"]

    for value in disabled_values:
        assert is_controlled_live_viki_enabled(value) is False
        decision = receive_controlled_live_viki_payload(feature_flag_value=value)
        assert decision["veritas_reason_code"] == "CONTROLLED_LIVE_DISABLED"
        assert decision["final_commit_approved"] is False
        assert decision["veritas_continuation_decision"] != "SAFE_PROCEED"


def test_runtime_interface_true_is_only_enabled_value_but_remains_fail_closed_not_ready() -> None:
    assert is_controlled_live_viki_enabled("true") is True

    decision = receive_controlled_live_viki_payload(feature_flag_value="true")
    assert decision["reason_code"] == "CONTROLLED_LIVE_INVALID_JSON_OBJECT"
    assert decision["veritas_continuation_decision"] == EXPECTED_CONTINUATION
    assert decision["veritas_sandbox_commit_state"] == EXPECTED_COMMIT_STATE
    assert decision["required_next_action"] == EXPECTED_NEXT_ACTION
    assert decision["final_commit_approved"] is False


def test_runtime_interface_disabled_decision_shape_is_deterministic() -> None:
    decision = receive_controlled_live_viki_payload(feature_flag_value=None)

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


def test_runtime_interface_preserves_synthetic_request_and_correlation_ids() -> None:
    payload = {
        "schema_version": "v1alpha1",
        "rsa_status": "SAFE_PROCEED",
        "request_id": "req_viki_runtime_001",
        "correlation_id": "corr_viki_veritas_runtime_001",
    }
    decision = receive_controlled_live_viki_payload(payload=payload, feature_flag_value=None)

    assert decision["request_id"] == "req_viki_runtime_001"
    assert decision["correlation_id"] == "corr_viki_veritas_runtime_001"
    assert decision["schema_version"] == "v1alpha1"
    assert decision["final_commit_approved"] is False
    assert decision["veritas_continuation_decision"] != "SAFE_PROCEED"


def test_runtime_interface_does_not_emit_raw_payload_or_forbidden_fields() -> None:
    payload = {
        "request_id": "req_viki_runtime_002",
        "correlation_id": "corr_viki_veritas_runtime_002",
        "schema_version": "v1alpha1",
        "chain_of_thought": "synthetic",
        "raw_kyc_record": "synthetic",
        "access_token": "synthetic",
        "raw_payload_body": "synthetic",
    }
    decision = receive_controlled_live_viki_payload(payload=payload, feature_flag_value=None)

    assert decision["veritas_reason_code"] == "CONTROLLED_LIVE_DISABLED"
    assert decision["final_commit_approved"] is False
    for forbidden_key in ("chain_of_thought", "raw_kyc_record", "access_token", "raw_payload_body"):
        assert forbidden_key not in decision


def test_runtime_interface_module_is_no_network_no_endpoint_no_telemetry() -> None:
    source = _RUNTIME_MODULE_PATH.read_text(encoding="utf-8")
    module = ast.parse(source)

    disallowed_import_roots = {"requests", "httpx", "urllib", "socket", "opentelemetry", "sentry_sdk"}

    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root not in disallowed_import_roots
        if isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            assert root not in disallowed_import_roots

    lowered_source = source.lower()
    forbidden_strings = [
        "fastapi",
        "flask",
        "viki_live_client",
        "api" + "_" + "key",
        "bearer" + " ",
        "http" + "://",
        "https" + "://",
    ]
    for token in forbidden_strings:
        assert token not in lowered_source
