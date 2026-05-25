"""Runtime tests for controlled live V.I.K.I. receiver RSA handoff wiring.

This suite verifies local/offline fail-closed behavior only.
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
sys.modules["veritas_os.governance.controlled_live_viki_rsa_handoff"] = (
    RSA_HANDOFF_MODULE
)

INTERFACE_SPEC = importlib.util.spec_from_file_location(
    "controlled_live_viki_interface_runtime",
    INTERFACE_PATH,
)
assert INTERFACE_SPEC is not None
assert INTERFACE_SPEC.loader is not None
INTERFACE_MODULE = importlib.util.module_from_spec(INTERFACE_SPEC)
INTERFACE_SPEC.loader.exec_module(INTERFACE_MODULE)

receive_controlled_live_viki_payload = INTERFACE_MODULE.receive_controlled_live_viki_payload
ADAPTER_VALID = SCHEMA_ADAPTER_MODULE.ADAPTER_VALID
classify_controlled_live_viki_schema_input = (
    SCHEMA_ADAPTER_MODULE.classify_controlled_live_viki_schema_input
)


def _load_payload_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _reason_code(result: dict[str, object]) -> str:
    return str(result.get("reason_code") or result.get("veritas_reason_code") or "")


def _assert_fail_closed(result: dict[str, object]) -> None:
    assert result["final_commit_approved"] is False
    assert result["veritas_sandbox_commit_state"] == "SUSPENDED_NOT_COMMITTED"
    assert result["veritas_continuation_decision"] == "PAUSE_FOR_HUMAN_REVIEW"


def test_receiver_rsa_handoff_runtime_disabled_flag_preserves_existing_receiver_fail_closed_behavior() -> None:
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
        result = receive_controlled_live_viki_payload(payload, feature_flag_value=value)
        assert _reason_code(result) == "CONTROLLED_LIVE_DISABLED"
        _assert_fail_closed(result)
        assert result["veritas_continuation_decision"] != "CONTINUE_TO_BIND_BOUNDARY"
        assert "raw_payload_body" not in json.dumps(result)


def test_receiver_rsa_handoff_runtime_true_flag_invalid_schema_payloads_fail_closed_before_handoff() -> None:
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
        payload = _load_payload_fixture(fixture_name)
        assert classify_controlled_live_viki_schema_input(payload) != ADAPTER_VALID

        result = receive_controlled_live_viki_payload(payload, feature_flag_value="true")
        reason_code = _reason_code(result)
        assert reason_code.startswith("CONTROLLED_LIVE_")
        assert reason_code != "CONTROLLED_LIVE_DISABLED"
        assert reason_code != "CONTROLLED_LIVE_RSA_HANDOFF_SAFE_PROCEED_NOT_FINAL"
        _assert_fail_closed(result)
        assert result["upstream_signal_source"] == "RSA"


def test_receiver_rsa_handoff_runtime_true_flag_valid_safe_proceed_uses_rsa_handoff_not_final_approval() -> None:
    payload = _load_payload_fixture("valid_safe_proceed_v1alpha1.json")
    assert classify_controlled_live_viki_schema_input(payload) == ADAPTER_VALID
    assert payload["rsa_status"] == "SAFE_PROCEED"

    result = receive_controlled_live_viki_payload(payload, feature_flag_value="true")
    assert _reason_code(result) == "CONTROLLED_LIVE_RSA_HANDOFF_SAFE_PROCEED_NOT_FINAL"
    assert result["rsa_status"] == "SAFE_PROCEED"
    assert result["upstream_signal_source"] == "RSA"
    _assert_fail_closed(result)
    assert result["veritas_continuation_decision"] != "CONTINUE_TO_BIND_BOUNDARY"


def test_receiver_rsa_handoff_runtime_true_flag_valid_density_throttled_uses_rsa_handoff() -> None:
    payload = _load_payload_fixture("valid_density_throttled_v1alpha1.json")
    assert classify_controlled_live_viki_schema_input(payload) == ADAPTER_VALID

    result = receive_controlled_live_viki_payload(payload, feature_flag_value="true")
    assert result["rsa_status"] == "DENSITY_THROTTLED"
    assert _reason_code(result) == "CONTROLLED_LIVE_RSA_HANDOFF_DENSITY_THROTTLED"
    _assert_fail_closed(result)
    assert result["upstream_signal_source"] == "RSA"


def test_receiver_rsa_handoff_runtime_true_flag_valid_algorithmic_humility_uses_rsa_handoff() -> None:
    payload = _load_payload_fixture("valid_algorithmic_humility_engaged_v1alpha1.json")
    assert classify_controlled_live_viki_schema_input(payload) == ADAPTER_VALID

    result = receive_controlled_live_viki_payload(payload, feature_flag_value="true")
    assert result["rsa_status"] == "ALGORITHMIC_HUMILITY_ENGAGED"
    assert (
        _reason_code(result)
        == "CONTROLLED_LIVE_RSA_HANDOFF_ALGORITHMIC_HUMILITY_ENGAGED"
    )
    _assert_fail_closed(result)
    assert result["upstream_signal_source"] == "RSA"


def test_receiver_rsa_handoff_runtime_true_flag_valid_deferral_uses_rsa_handoff() -> None:
    payload = _load_payload_fixture("valid_deferral_engaged_v1alpha1.json")
    assert classify_controlled_live_viki_schema_input(payload) == ADAPTER_VALID

    result = receive_controlled_live_viki_payload(payload, feature_flag_value="true")
    assert result["rsa_status"] == "DEFERRAL_ENGAGED"
    assert _reason_code(result) == "CONTROLLED_LIVE_RSA_HANDOFF_DEFERRAL_ENGAGED"
    _assert_fail_closed(result)
    assert result["upstream_signal_source"] == "RSA"


def test_receiver_rsa_handoff_runtime_preserves_safe_identity_fields_only() -> None:
    fixtures = [
        "valid_safe_proceed_v1alpha1.json",
        "valid_density_throttled_v1alpha1.json",
        "valid_algorithmic_humility_engaged_v1alpha1.json",
        "valid_deferral_engaged_v1alpha1.json",
    ]
    forbidden = {
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

    for fixture_name in fixtures:
        result = receive_controlled_live_viki_payload(
            _load_payload_fixture(fixture_name),
            feature_flag_value="true",
        )
        for key in (
            "request_id",
            "correlation_id",
            "schema_version",
            "rsa_status",
            "upstream_signal_source",
        ):
            assert key in result
        for key in forbidden:
            assert key not in result


def test_receiver_rsa_handoff_runtime_does_not_introduce_viki_specific_downstream_contract() -> None:
    result = receive_controlled_live_viki_payload(
        _load_payload_fixture("valid_safe_proceed_v1alpha1.json"),
        feature_flag_value="true",
    )
    assert "viki_status" not in result
    assert "VIKIPayload" not in result
    assert result["rsa_status"] == "SAFE_PROCEED"
    assert result["upstream_signal_source"] == "RSA"


def test_receiver_rsa_handoff_runtime_module_is_offline_static_and_no_network() -> None:
    source_paths = [
        Path("veritas_os/governance/controlled_live_viki_interface.py"),
        Path("veritas_os/governance/controlled_live_viki_rsa_handoff.py"),
        Path(__file__),
    ]
    disallowed = {"requests", "httpx", "urllib", "socket", "opentelemetry", "sentry_sdk"}
    for source_path in source_paths:
        source = source_path.read_text(encoding="utf-8")
        module = ast.parse(source)
        for node in ast.walk(module):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in disallowed
            if isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in disallowed

    test_source = Path(__file__).read_text(encoding="utf-8").lower()
    precheck_source = test_source.split(
        "def test_receiver_rsa_handoff_runtime_module_is_offline_static_and_no_network",
        maxsplit=1,
    )[0]
    forbidden_literals = [
        "http" + "://",
        "https" + "://",
        "bear" + "er" + " ",
        "api" + "_" + "key=",
        "fastapi",
        "flask",
        "live_viki_client",
        "viki_live_client",
        "telemetrysdk",
    ]
    for token in forbidden_literals:
        assert token not in precheck_source


def test_receiver_rsa_handoff_runtime_updates_previous_not_ready_behavior_for_valid_payloads() -> None:
    valid_payload = _load_payload_fixture("valid_safe_proceed_v1alpha1.json")
    result = receive_controlled_live_viki_payload(valid_payload, feature_flag_value="true")
    assert _reason_code(result) != "CONTROLLED_LIVE_SCHEMA_VALID_NOT_YET_WIRED"
    assert _reason_code(result) == "CONTROLLED_LIVE_RSA_HANDOFF_SAFE_PROCEED_NOT_FINAL"

    invalid_payload = _load_payload_fixture("invalid_missing_request_id_v1alpha1.json")
    invalid_result = receive_controlled_live_viki_payload(
        invalid_payload,
        feature_flag_value="true",
    )
    assert _reason_code(invalid_result).startswith("CONTROLLED_LIVE_")

    disabled_result = receive_controlled_live_viki_payload(
        valid_payload,
        feature_flag_value="false",
    )
    assert _reason_code(disabled_result) == "CONTROLLED_LIVE_DISABLED"
