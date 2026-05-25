"""Test-only synthetic ingestion endpoint behavior skeleton.

This module models a future controlled live V.I.K.I. synthetic ingestion
endpoint contract in a fully local/offline manner. It does not implement an
endpoint, server, route, network transport, credentials, telemetry, or live
integration.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
import types
from pathlib import Path

FIXTURE_DIR = (
    Path(__file__).resolve().parent.parent
    / "fixtures"
    / "controlled_live_viki_payload_schema"
)
INTERFACE_PATH = Path("veritas_os/governance/controlled_live_viki_interface.py")
SCHEMA_ADAPTER_PATH = Path("veritas_os/governance/controlled_live_viki_schema_adapter.py")
RSA_HANDOFF_PATH = Path("veritas_os/governance/controlled_live_viki_rsa_handoff.py")
ENDPOINT_RUNTIME_PATH = Path("veritas_os/governance/controlled_live_viki_synthetic_ingestion_endpoint.py")

SCHEMA_ADAPTER_SPEC = importlib.util.spec_from_file_location(
    "controlled_live_viki_schema_adapter_runtime",
    SCHEMA_ADAPTER_PATH,
)
assert SCHEMA_ADAPTER_SPEC is not None
assert SCHEMA_ADAPTER_SPEC.loader is not None
SCHEMA_ADAPTER_MODULE = importlib.util.module_from_spec(SCHEMA_ADAPTER_SPEC)
SCHEMA_ADAPTER_SPEC.loader.exec_module(SCHEMA_ADAPTER_MODULE)

RSA_HANDOFF_SPEC = importlib.util.spec_from_file_location(
    "controlled_live_viki_rsa_handoff_runtime",
    RSA_HANDOFF_PATH,
)
assert RSA_HANDOFF_SPEC is not None
assert RSA_HANDOFF_SPEC.loader is not None
RSA_HANDOFF_MODULE = importlib.util.module_from_spec(RSA_HANDOFF_SPEC)
RSA_HANDOFF_SPEC.loader.exec_module(RSA_HANDOFF_MODULE)

_veritas_os_module = types.ModuleType("veritas_os")
_governance_module = types.ModuleType("veritas_os.governance")
sys.modules.setdefault("veritas_os", _veritas_os_module)
sys.modules.setdefault("veritas_os.governance", _governance_module)
sys.modules["veritas_os.governance.controlled_live_viki_schema_adapter"] = (
    SCHEMA_ADAPTER_MODULE
)
sys.modules["veritas_os.governance.controlled_live_viki_rsa_handoff"] = RSA_HANDOFF_MODULE

INTERFACE_SPEC = importlib.util.spec_from_file_location(
    "controlled_live_viki_interface_runtime",
    INTERFACE_PATH,
)
assert INTERFACE_SPEC is not None
assert INTERFACE_SPEC.loader is not None
INTERFACE_MODULE = importlib.util.module_from_spec(INTERFACE_SPEC)
INTERFACE_SPEC.loader.exec_module(INTERFACE_MODULE)
sys.modules["veritas_os.governance.controlled_live_viki_interface"] = INTERFACE_MODULE
receive_controlled_live_viki_payload = INTERFACE_MODULE.receive_controlled_live_viki_payload

ENDPOINT_SPEC = importlib.util.spec_from_file_location(
    "controlled_live_viki_synthetic_endpoint_runtime",
    ENDPOINT_RUNTIME_PATH,
)
assert ENDPOINT_SPEC is not None
assert ENDPOINT_SPEC.loader is not None
ENDPOINT_MODULE = importlib.util.module_from_spec(ENDPOINT_SPEC)
ENDPOINT_SPEC.loader.exec_module(ENDPOINT_MODULE)
handle_controlled_live_viki_synthetic_ingestion_request = (
    ENDPOINT_MODULE.handle_controlled_live_viki_synthetic_ingestion_request
)

EXPECTED_PATH = "/synthetic/controlled-live-viki"
EXPECTED_METHOD = "POST"
EXPECTED_CONTENT_TYPE = "application/json"

FORBIDDEN_FIELDS = {
    "raw_payload_body",
    "raw_request_body",
    "raw_response_body",
    "chain_of_thought",
    "hidden_model_state",
    "raw_llm_reasoning",
    "raw_viki_reasoning",
    "raw_llm_text",
    "raw_kyc_record",
    "customer_pii",
    "unredacted_regulated_data",
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


def _load_payload_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _reason_code(result: dict) -> str:
    return str(result.get("reason_code") or result.get("veritas_reason_code") or "")


def _assert_endpoint_fail_closed(response: dict) -> None:
    assert response["final_commit_approved"] is False
    receiver_result = response.get("receiver_result")
    if isinstance(receiver_result, dict):
        assert receiver_result["final_commit_approved"] is False


def _assert_no_raw_payload_echo(value: object) -> None:
    serialized = json.dumps(value)
    for key in FORBIDDEN_FIELDS:
        assert key not in serialized


def test_synthetic_ingestion_endpoint_disabled_flag_is_fail_closed() -> None:
    payload = _load_payload_fixture("valid_safe_proceed_v1alpha1.json")
    disabled_values = [
        None,
        "",
        " ",
        "false",
        "0",
        "no",
        "off",
        "disabled",
        "TRUE",
        "True",
        "unexpected",
    ]

    for value in disabled_values:
        response = handle_controlled_live_viki_synthetic_ingestion_request(
            payload,
            feature_flag_value=value,
        )
        assert response["endpoint_enabled"] is False
        assert response["accepted_for_processing"] is False
        assert response["http_status"] == 503
        assert response["reason_code"] == "CONTROLLED_LIVE_DISABLED"
        _assert_endpoint_fail_closed(response)
        _assert_no_raw_payload_echo(response)


def test_synthetic_ingestion_endpoint_rejects_wrong_method_path_and_content_type() -> None:
    payload = _load_payload_fixture("valid_safe_proceed_v1alpha1.json")
    cases = [
        (
            {"method": "GET"},
            "CONTROLLED_LIVE_SYNTHETIC_ENDPOINT_METHOD_NOT_ALLOWED",
            405,
        ),
        (
            {"path": "/wrong"},
            "CONTROLLED_LIVE_SYNTHETIC_ENDPOINT_PATH_NOT_FOUND",
            404,
        ),
        (
            {"content_type": "text/plain"},
            "CONTROLLED_LIVE_SYNTHETIC_ENDPOINT_UNSUPPORTED_MEDIA_TYPE",
            415,
        ),
    ]

    for kwargs, expected_reason, expected_status in cases:
        response = handle_controlled_live_viki_synthetic_ingestion_request(
            payload,
            feature_flag_value="true",
            **kwargs,
        )
        assert response["accepted_for_processing"] is False
        assert response["receiver_result"] is None
        assert response["reason_code"] == expected_reason
        assert response["http_status"] == expected_status
        _assert_endpoint_fail_closed(response)
        _assert_no_raw_payload_echo(response)


def test_synthetic_ingestion_endpoint_true_flag_invalid_schema_payloads_fail_closed() -> None:
    fixtures = [
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

    for fixture_name in fixtures:
        response = handle_controlled_live_viki_synthetic_ingestion_request(
            _load_payload_fixture(fixture_name),
            feature_flag_value="true",
        )
        assert response["endpoint_enabled"] is True
        assert response["accepted_for_processing"] is False
        assert response["http_status"] == 422
        assert isinstance(response["receiver_result"], dict)
        assert response["reason_code"] == _reason_code(response["receiver_result"])
        assert response["reason_code"].startswith("CONTROLLED_LIVE_")
        assert response["reason_code"] != "CONTROLLED_LIVE_DISABLED"
        assert response["reason_code"] != "CONTROLLED_LIVE_RSA_HANDOFF_SAFE_PROCEED_NOT_FINAL"
        _assert_endpoint_fail_closed(response)
        _assert_no_raw_payload_echo(response)


def test_synthetic_ingestion_endpoint_true_flag_valid_safe_proceed_reaches_rsa_handoff_without_final_approval() -> None:
    response = handle_controlled_live_viki_synthetic_ingestion_request(
        _load_payload_fixture("valid_safe_proceed_v1alpha1.json"),
        feature_flag_value="true",
    )
    receiver_result = response["receiver_result"]
    assert response["endpoint_enabled"] is True
    assert response["accepted_for_processing"] is True
    assert response["http_status"] == 202
    assert isinstance(receiver_result, dict)
    assert response["reason_code"] == "CONTROLLED_LIVE_RSA_HANDOFF_SAFE_PROCEED_NOT_FINAL"
    assert receiver_result["rsa_status"] == "SAFE_PROCEED"
    assert receiver_result["upstream_signal_source"] == "RSA"
    _assert_endpoint_fail_closed(response)
    assert receiver_result["veritas_sandbox_commit_state"] == "SUSPENDED_NOT_COMMITTED"
    assert receiver_result["veritas_continuation_decision"] == "PAUSE_FOR_HUMAN_REVIEW"
    assert receiver_result["veritas_continuation_decision"] != "CONTINUE_TO_BIND_BOUNDARY"
    _assert_no_raw_payload_echo(response)


def test_synthetic_ingestion_endpoint_true_flag_valid_density_throttled_reaches_rsa_handoff() -> None:
    response = handle_controlled_live_viki_synthetic_ingestion_request(
        _load_payload_fixture("valid_density_throttled_v1alpha1.json"),
        feature_flag_value="true",
    )
    assert response["http_status"] == 202
    assert response["accepted_for_processing"] is True
    assert response["reason_code"] == "CONTROLLED_LIVE_RSA_HANDOFF_DENSITY_THROTTLED"
    _assert_endpoint_fail_closed(response)
    assert response["receiver_result"]["upstream_signal_source"] == "RSA"


def test_synthetic_ingestion_endpoint_true_flag_valid_algorithmic_humility_reaches_rsa_handoff() -> None:
    response = handle_controlled_live_viki_synthetic_ingestion_request(
        _load_payload_fixture("valid_algorithmic_humility_engaged_v1alpha1.json"),
        feature_flag_value="true",
    )
    assert response["http_status"] == 202
    assert response["accepted_for_processing"] is True
    assert (
        response["reason_code"]
        == "CONTROLLED_LIVE_RSA_HANDOFF_ALGORITHMIC_HUMILITY_ENGAGED"
    )
    _assert_endpoint_fail_closed(response)
    assert response["receiver_result"]["upstream_signal_source"] == "RSA"


def test_synthetic_ingestion_endpoint_true_flag_valid_deferral_reaches_rsa_handoff() -> None:
    response = handle_controlled_live_viki_synthetic_ingestion_request(
        _load_payload_fixture("valid_deferral_engaged_v1alpha1.json"),
        feature_flag_value="true",
    )
    assert response["http_status"] == 202
    assert response["accepted_for_processing"] is True
    assert response["reason_code"] == "CONTROLLED_LIVE_RSA_HANDOFF_DEFERRAL_ENGAGED"
    _assert_endpoint_fail_closed(response)
    assert response["receiver_result"]["upstream_signal_source"] == "RSA"


def test_synthetic_ingestion_endpoint_response_preserves_safe_identity_fields_only() -> None:
    fixtures = [
        "valid_safe_proceed_v1alpha1.json",
        "valid_density_throttled_v1alpha1.json",
        "valid_algorithmic_humility_engaged_v1alpha1.json",
        "valid_deferral_engaged_v1alpha1.json",
    ]
    for fixture_name in fixtures:
        response = handle_controlled_live_viki_synthetic_ingestion_request(
            _load_payload_fixture(fixture_name),
            feature_flag_value="true",
        )
        receiver_result = response["receiver_result"]
        assert isinstance(receiver_result, dict)
        for key in (
            "request_id",
            "correlation_id",
            "schema_version",
            "rsa_status",
            "upstream_signal_source",
        ):
            assert key in receiver_result
        for key in FORBIDDEN_FIELDS:
            assert key not in response
            assert key not in receiver_result


def test_synthetic_ingestion_endpoint_does_not_introduce_viki_specific_downstream_contract() -> None:
    response = handle_controlled_live_viki_synthetic_ingestion_request(
        _load_payload_fixture("valid_safe_proceed_v1alpha1.json"),
        feature_flag_value="true",
    )
    receiver_result = response["receiver_result"]
    assert isinstance(receiver_result, dict)
    assert "viki_status" not in response
    assert "VIKIPayload" not in response
    assert "viki_status" not in receiver_result
    assert "VIKIPayload" not in receiver_result
    assert receiver_result["rsa_status"] == "SAFE_PROCEED"
    assert receiver_result["upstream_signal_source"] == "RSA"


def test_synthetic_ingestion_endpoint_behavior_skeleton_is_offline_static_and_no_network() -> None:
    source_paths = [Path(__file__), INTERFACE_PATH]
    disallowed = {"requests", "httpx", "urllib", "socket", "fastapi", "flask", "starlette"}

    for source_path in source_paths:
        source = source_path.read_text(encoding="utf-8")
        module = ast.parse(source)
        for node in ast.walk(module):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0].lower() not in disallowed
            if isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0].lower() not in disallowed

    test_source = Path(__file__).read_text(encoding="utf-8").lower()
    precheck_source = test_source.split(
        "def test_synthetic_ingestion_endpoint_behavior_skeleton_is_offline_static_and_no_network",
        maxsplit=1,
    )[0]
    forbidden_literals = [
        "http" + "://",
        "https" + "://",
        "bear" + "er" + " ",
        "api" + "_" + "key=",
        "fast" + "api",
        "star" + "lette",
        "uvicorn",
        "@app.route",
        "@router",
        "live_viki_client",
        "viki_live_client",
        "telemetrysdk",
    ]
    for token in forbidden_literals:
        assert token not in precheck_source


def test_synthetic_ingestion_endpoint_behavior_skeleton_does_not_modify_runtime_modules() -> None:
    runtime_source = INTERFACE_PATH.read_text(encoding="utf-8")
    assert "receive_controlled_live_viki_payload" in runtime_source

    response = handle_controlled_live_viki_synthetic_ingestion_request(
        _load_payload_fixture("valid_safe_proceed_v1alpha1.json"),
        feature_flag_value="true",
    )
    assert response["reason_code"] == "CONTROLLED_LIVE_RSA_HANDOFF_SAFE_PROCEED_NOT_FINAL"
    assert response["receiver_result"]["final_commit_approved"] is False


def test_synthetic_ingestion_endpoint_runtime_module_exists() -> None:
    assert ENDPOINT_RUNTIME_PATH.exists()
