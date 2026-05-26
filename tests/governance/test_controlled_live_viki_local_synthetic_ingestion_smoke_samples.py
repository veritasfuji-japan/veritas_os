"""Local/offline smoke samples for controlled live V.I.K.I. synthetic ingestion.

These tests only exercise the in-process helper contract with committed fixtures.
They do not create servers, bind ports, call network transports, or connect to
live V.I.K.I. systems.
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
ENDPOINT_RUNTIME_PATH = Path(
    "veritas_os/governance/controlled_live_viki_synthetic_ingestion_endpoint.py"
)

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


def test_local_synthetic_ingestion_smoke_valid_safe_proceed_sample() -> None:
    response = handle_controlled_live_viki_synthetic_ingestion_request(
        _load_payload_fixture("valid_safe_proceed_v1alpha1.json"),
        feature_flag_value="true",
    )
    receiver_result = response["receiver_result"]
    assert response["endpoint_mode"] == "local_synthetic_runtime_skeleton"
    assert response["endpoint_enabled"] is True
    assert response["accepted_for_processing"] is True
    assert response["http_status"] == 202
    assert response["reason_code"] == "CONTROLLED_LIVE_RSA_HANDOFF_SAFE_PROCEED_NOT_FINAL"
    assert response["final_commit_approved"] is False
    assert isinstance(receiver_result, dict)
    assert receiver_result["rsa_status"] == "SAFE_PROCEED"
    assert receiver_result["upstream_signal_source"] == "RSA"
    assert receiver_result["final_commit_approved"] is False
    assert receiver_result["veritas_sandbox_commit_state"] == "SUSPENDED_NOT_COMMITTED"
    assert receiver_result["veritas_continuation_decision"] == "PAUSE_FOR_HUMAN_REVIEW"
    assert receiver_result["veritas_continuation_decision"] != "CONTINUE_TO_BIND_BOUNDARY"


def test_local_synthetic_ingestion_smoke_valid_non_safe_status_samples() -> None:
    cases = [
        (
            "valid_density_throttled_v1alpha1.json",
            "CONTROLLED_LIVE_RSA_HANDOFF_DENSITY_THROTTLED",
        ),
        (
            "valid_algorithmic_humility_engaged_v1alpha1.json",
            "CONTROLLED_LIVE_RSA_HANDOFF_ALGORITHMIC_HUMILITY_ENGAGED",
        ),
        (
            "valid_deferral_engaged_v1alpha1.json",
            "CONTROLLED_LIVE_RSA_HANDOFF_DEFERRAL_ENGAGED",
        ),
    ]

    for fixture_name, expected_reason in cases:
        response = handle_controlled_live_viki_synthetic_ingestion_request(
            _load_payload_fixture(fixture_name),
            feature_flag_value="true",
        )
        assert response["endpoint_enabled"] is True
        assert response["accepted_for_processing"] is True
        assert response["http_status"] == 202
        assert response["reason_code"] == expected_reason
        assert response["final_commit_approved"] is False
        assert response["receiver_result"]["final_commit_approved"] is False
        assert response["receiver_result"]["upstream_signal_source"] == "RSA"


def test_local_synthetic_ingestion_smoke_invalid_schema_samples_fail_closed() -> None:
    expected = {
        "invalid_missing_request_id_v1alpha1.json": "CONTROLLED_LIVE_MISSING_REQUIRED_FIELD",
        "invalid_forbidden_chain_of_thought_v1alpha1.json": "CONTROLLED_LIVE_FORBIDDEN_FIELD_PRESENT",
        "invalid_secret_access_token_v1alpha1.json": "CONTROLLED_LIVE_SECRET_LIKE_VALUE_PRESENT",
        "invalid_raw_kyc_record_v1alpha1.json": "CONTROLLED_LIVE_REGULATED_DATA_PRESENT",
    }

    for fixture_name, expected_reason in expected.items():
        response = handle_controlled_live_viki_synthetic_ingestion_request(
            _load_payload_fixture(fixture_name),
            feature_flag_value="true",
        )
        assert response["endpoint_enabled"] is True
        assert response["accepted_for_processing"] is False
        assert response["http_status"] == 422
        assert response["reason_code"].startswith("CONTROLLED_LIVE_")
        assert response["reason_code"] == expected_reason
        assert response["reason_code"] != "CONTROLLED_LIVE_DISABLED"
        assert response["reason_code"] != "CONTROLLED_LIVE_RSA_HANDOFF_SAFE_PROCEED_NOT_FINAL"
        assert response["final_commit_approved"] is False
        assert isinstance(response["receiver_result"], dict)
        assert response["receiver_result"]["final_commit_approved"] is False


def test_local_synthetic_ingestion_smoke_disabled_flag_sample() -> None:
    payload = _load_payload_fixture("valid_safe_proceed_v1alpha1.json")
    for feature_flag_value in [None, "false", "TRUE", "unexpected"]:
        response = handle_controlled_live_viki_synthetic_ingestion_request(
            payload,
            feature_flag_value=feature_flag_value,
        )
        assert response["endpoint_enabled"] is False
        assert response["accepted_for_processing"] is False
        assert response["http_status"] == 503
        assert response["reason_code"] == "CONTROLLED_LIVE_DISABLED"
        assert response["final_commit_approved"] is False
        if isinstance(response.get("receiver_result"), dict):
            assert response["receiver_result"]["final_commit_approved"] is False


def test_local_synthetic_ingestion_smoke_boundary_rejections() -> None:
    payload = _load_payload_fixture("valid_safe_proceed_v1alpha1.json")
    cases = [
        ({"method": "GET"}, 405, "CONTROLLED_LIVE_SYNTHETIC_ENDPOINT_METHOD_NOT_ALLOWED"),
        ({"path": "/wrong"}, 404, "CONTROLLED_LIVE_SYNTHETIC_ENDPOINT_PATH_NOT_FOUND"),
        (
            {"content_type": "text/plain"},
            415,
            "CONTROLLED_LIVE_SYNTHETIC_ENDPOINT_UNSUPPORTED_MEDIA_TYPE",
        ),
    ]

    for kwargs, expected_status, expected_reason in cases:
        response = handle_controlled_live_viki_synthetic_ingestion_request(
            payload,
            feature_flag_value="true",
            **kwargs,
        )
        assert response["accepted_for_processing"] is False
        assert response["http_status"] == expected_status
        assert response["reason_code"] == expected_reason
        assert response["final_commit_approved"] is False
        assert response["receiver_result"] is None


def test_local_synthetic_ingestion_smoke_output_does_not_echo_raw_or_sensitive_fields() -> None:
    fixtures = [
        "valid_safe_proceed_v1alpha1.json",
        "invalid_missing_request_id_v1alpha1.json",
    ]
    for fixture_name in fixtures:
        response = handle_controlled_live_viki_synthetic_ingestion_request(
            _load_payload_fixture(fixture_name),
            feature_flag_value="true",
        )
        serialized = json.dumps(response)
        for key in FORBIDDEN_FIELDS:
            assert key not in serialized


def test_local_synthetic_ingestion_smoke_samples_are_offline_static_no_network() -> None:
    source_paths = [Path(__file__), ENDPOINT_RUNTIME_PATH]
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
        "def test_local_synthetic_ingestion_smoke_samples_are_offline_static_no_network",
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
