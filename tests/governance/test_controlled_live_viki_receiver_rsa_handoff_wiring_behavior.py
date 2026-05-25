"""Test-only controlled live V.I.K.I. receiver RSA handoff wiring behavior skeleton.

This file is intentionally offline and deterministic. It defines a local,
future-facing wiring contract model only and does not implement runtime
wiring, endpoint behavior, network behavior, live integration, credentials,
replay cache, logging, telemetry, or observability runtime.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
import types
from pathlib import Path

_FIXTURE_DIR = Path("tests/fixtures/controlled_live_viki_payload_schema")
_THIS_FILE = Path(__file__)
_INTERFACE_PATH = Path("veritas_os/governance/controlled_live_viki_interface.py")
_SCHEMA_ADAPTER_PATH = Path("veritas_os/governance/controlled_live_viki_schema_adapter.py")
_RSA_HANDOFF_PATH = Path("veritas_os/governance/controlled_live_viki_rsa_handoff.py")

_SCHEMA_ADAPTER_SPEC = importlib.util.spec_from_file_location(
    "controlled_live_viki_schema_adapter",
    _SCHEMA_ADAPTER_PATH,
)
assert _SCHEMA_ADAPTER_SPEC is not None
assert _SCHEMA_ADAPTER_SPEC.loader is not None
_SCHEMA_ADAPTER_MODULE = importlib.util.module_from_spec(_SCHEMA_ADAPTER_SPEC)
_SCHEMA_ADAPTER_SPEC.loader.exec_module(_SCHEMA_ADAPTER_MODULE)

ADAPTER_VALID = _SCHEMA_ADAPTER_MODULE.ADAPTER_VALID
classify_controlled_live_viki_schema_input = (
    _SCHEMA_ADAPTER_MODULE.classify_controlled_live_viki_schema_input
)

_RSA_HANDOFF_SPEC = importlib.util.spec_from_file_location(
    "controlled_live_viki_rsa_handoff",
    _RSA_HANDOFF_PATH,
)
assert _RSA_HANDOFF_SPEC is not None
assert _RSA_HANDOFF_SPEC.loader is not None
_RSA_HANDOFF_MODULE = importlib.util.module_from_spec(_RSA_HANDOFF_SPEC)
_RSA_HANDOFF_SPEC.loader.exec_module(_RSA_HANDOFF_MODULE)

build_controlled_live_viki_rsa_handoff_decision = (
    _RSA_HANDOFF_MODULE.build_controlled_live_viki_rsa_handoff_decision
)

_veritas_os_module = types.ModuleType("veritas_os")
_governance_module = types.ModuleType("veritas_os.governance")
sys.modules.setdefault("veritas_os", _veritas_os_module)
sys.modules.setdefault("veritas_os.governance", _governance_module)
sys.modules[
    "veritas_os.governance.controlled_live_viki_schema_adapter"
] = _SCHEMA_ADAPTER_MODULE
sys.modules["veritas_os.governance.controlled_live_viki_rsa_handoff"] = (
    _RSA_HANDOFF_MODULE
)

_INTERFACE_SPEC = importlib.util.spec_from_file_location(
    "controlled_live_viki_interface",
    _INTERFACE_PATH,
)
assert _INTERFACE_SPEC is not None
assert _INTERFACE_SPEC.loader is not None
_INTERFACE_MODULE = importlib.util.module_from_spec(_INTERFACE_SPEC)
_INTERFACE_SPEC.loader.exec_module(_INTERFACE_MODULE)

receive_controlled_live_viki_payload = _INTERFACE_MODULE.receive_controlled_live_viki_payload


def _load_payload_fixture(name: str) -> dict:
    return json.loads((_FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _reason_code(result: dict) -> str:
    return result.get("reason_code") or result.get("veritas_reason_code", "")


def _future_receiver_rsa_handoff_wiring_decision(
    payload: object,
    *,
    feature_flag_value: str | None,
) -> dict:
    if feature_flag_value != "true":
        return receive_controlled_live_viki_payload(
            payload,
            feature_flag_value=feature_flag_value,
        )

    adapter_result = classify_controlled_live_viki_schema_input(payload)
    if adapter_result != ADAPTER_VALID:
        return receive_controlled_live_viki_payload(
            payload,
            feature_flag_value=feature_flag_value,
        )

    return build_controlled_live_viki_rsa_handoff_decision(payload)


def _assert_fail_closed(decision: dict) -> None:
    assert decision["final_commit_approved"] is False
    assert decision["veritas_sandbox_commit_state"] == "SUSPENDED_NOT_COMMITTED"
    assert decision["veritas_continuation_decision"] == "PAUSE_FOR_HUMAN_REVIEW"


def _assert_no_raw_payload_echo(decision: dict) -> None:
    forbidden_fields = {
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
    for field_name in forbidden_fields:
        assert field_name not in decision


def test_receiver_rsa_handoff_wiring_disabled_flag_preserves_existing_receiver_fail_closed_behavior() -> None:
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

    for disabled_value in disabled_values:
        decision = _future_receiver_rsa_handoff_wiring_decision(
            payload,
            feature_flag_value=disabled_value,
        )

        assert _reason_code(decision) == "CONTROLLED_LIVE_DISABLED"
        _assert_fail_closed(decision)
        assert decision["veritas_continuation_decision"] != "CONTINUE_TO_BIND_BOUNDARY"
        _assert_no_raw_payload_echo(decision)


def test_receiver_rsa_handoff_wiring_true_flag_invalid_schema_payloads_fail_closed_before_handoff() -> None:
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
        payload = _load_payload_fixture(fixture_name)

        assert classify_controlled_live_viki_schema_input(payload) != ADAPTER_VALID

        decision = _future_receiver_rsa_handoff_wiring_decision(
            payload,
            feature_flag_value="true",
        )

        assert _reason_code(decision).startswith("CONTROLLED_LIVE_")
        assert _reason_code(decision) != "CONTROLLED_LIVE_DISABLED"
        assert (
            _reason_code(decision)
            != "CONTROLLED_LIVE_RSA_HANDOFF_SAFE_PROCEED_NOT_FINAL"
        )
        _assert_fail_closed(decision)
        assert decision["upstream_signal_source"] == "RSA"
        _assert_no_raw_payload_echo(decision)


def test_receiver_rsa_handoff_wiring_true_flag_valid_safe_proceed_uses_rsa_handoff_not_final_approval() -> None:
    payload = _load_payload_fixture("valid_safe_proceed_v1alpha1.json")

    assert classify_controlled_live_viki_schema_input(payload) == ADAPTER_VALID
    assert payload["rsa_status"] == "SAFE_PROCEED"

    decision = _future_receiver_rsa_handoff_wiring_decision(
        payload,
        feature_flag_value="true",
    )

    assert _reason_code(decision) == "CONTROLLED_LIVE_RSA_HANDOFF_SAFE_PROCEED_NOT_FINAL"
    assert decision["rsa_status"] == "SAFE_PROCEED"
    assert decision["upstream_signal_source"] == "RSA"
    _assert_fail_closed(decision)
    assert decision["veritas_continuation_decision"] != "CONTINUE_TO_BIND_BOUNDARY"
    _assert_no_raw_payload_echo(decision)


def test_receiver_rsa_handoff_wiring_true_flag_valid_density_throttled_uses_rsa_handoff() -> None:
    payload = _load_payload_fixture("valid_density_throttled_v1alpha1.json")

    assert classify_controlled_live_viki_schema_input(payload) == ADAPTER_VALID

    decision = _future_receiver_rsa_handoff_wiring_decision(
        payload,
        feature_flag_value="true",
    )

    assert decision["rsa_status"] == "DENSITY_THROTTLED"
    assert _reason_code(decision) == "CONTROLLED_LIVE_RSA_HANDOFF_DENSITY_THROTTLED"
    _assert_fail_closed(decision)
    assert decision["upstream_signal_source"] == "RSA"


def test_receiver_rsa_handoff_wiring_true_flag_valid_algorithmic_humility_uses_rsa_handoff() -> None:
    payload = _load_payload_fixture("valid_algorithmic_humility_engaged_v1alpha1.json")

    assert classify_controlled_live_viki_schema_input(payload) == ADAPTER_VALID

    decision = _future_receiver_rsa_handoff_wiring_decision(
        payload,
        feature_flag_value="true",
    )

    assert decision["rsa_status"] == "ALGORITHMIC_HUMILITY_ENGAGED"
    assert (
        _reason_code(decision)
        == "CONTROLLED_LIVE_RSA_HANDOFF_ALGORITHMIC_HUMILITY_ENGAGED"
    )
    _assert_fail_closed(decision)
    assert decision["upstream_signal_source"] == "RSA"


def test_receiver_rsa_handoff_wiring_true_flag_valid_deferral_uses_rsa_handoff() -> None:
    payload = _load_payload_fixture("valid_deferral_engaged_v1alpha1.json")

    assert classify_controlled_live_viki_schema_input(payload) == ADAPTER_VALID

    decision = _future_receiver_rsa_handoff_wiring_decision(
        payload,
        feature_flag_value="true",
    )

    assert decision["rsa_status"] == "DEFERRAL_ENGAGED"
    assert _reason_code(decision) == "CONTROLLED_LIVE_RSA_HANDOFF_DEFERRAL_ENGAGED"
    _assert_fail_closed(decision)
    assert decision["upstream_signal_source"] == "RSA"


def test_receiver_rsa_handoff_wiring_preserves_safe_identity_fields_only() -> None:
    fixture_names = [
        "valid_safe_proceed_v1alpha1.json",
        "valid_density_throttled_v1alpha1.json",
        "valid_algorithmic_humility_engaged_v1alpha1.json",
        "valid_deferral_engaged_v1alpha1.json",
    ]

    for fixture_name in fixture_names:
        payload = _load_payload_fixture(fixture_name)
        decision = _future_receiver_rsa_handoff_wiring_decision(
            payload,
            feature_flag_value="true",
        )

        assert decision["request_id"] == payload["request_id"]
        assert decision["correlation_id"] == payload["correlation_id"]
        assert decision["schema_version"] == payload["schema_version"]
        assert decision["rsa_status"] == payload["rsa_status"]
        assert decision["upstream_signal_source"] == "RSA"
        _assert_no_raw_payload_echo(decision)


def test_receiver_rsa_handoff_wiring_does_not_introduce_viki_specific_downstream_contract() -> None:
    payload = _load_payload_fixture("valid_safe_proceed_v1alpha1.json")
    decision = _future_receiver_rsa_handoff_wiring_decision(
        payload,
        feature_flag_value="true",
    )

    assert "viki_status" not in decision
    assert "VIKIPayload" not in decision
    assert decision["rsa_status"] == "SAFE_PROCEED"
    assert decision["upstream_signal_source"] == "RSA"



def test_receiver_rsa_handoff_wiring_behavior_skeleton_is_offline_static_and_no_network() -> None:
    source = _THIS_FILE.read_text(encoding="utf-8")
    before_static_check = source.split(
        "def test_receiver_rsa_handoff_wiring_behavior_skeleton_is_offline_static_and_no_network",
        maxsplit=1,
    )[0]
    module = ast.parse(source)

    disallowed_import_roots = {
        "requests",
        "httpx",
        "urllib",
        "socket",
        "opentelemetry",
        "sentry_sdk",
    }

    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in disallowed_import_roots
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] not in disallowed_import_roots

    lowered = before_static_check.lower()
    for token in ("fastapi", "flask", "viki_live_client"):
        assert token not in lowered

    split_forbidden_literals = (
        "api" + "_" + "key=",
        "bear" + "er" + " ",
        "http" + "://",
        "https" + "://",
    )
    for token in split_forbidden_literals:
        assert token not in lowered


def test_receiver_rsa_handoff_wiring_behavior_skeleton_does_not_modify_runtime_modules() -> None:
    module_paths = (
        Path("veritas_os/governance/controlled_live_viki_interface.py"),
        Path("veritas_os/governance/controlled_live_viki_schema_adapter.py"),
        Path("veritas_os/governance/controlled_live_viki_rsa_handoff.py"),
        Path("veritas_os/governance/rsa_sandbox_receiver.py"),
    )

    payload = _load_payload_fixture("valid_safe_proceed_v1alpha1.json")
    runtime_result = receive_controlled_live_viki_payload(
        payload,
        feature_flag_value="true",
    )
    assert _reason_code(runtime_result) == "CONTROLLED_LIVE_SCHEMA_VALID_NOT_YET_WIRED"

    disallowed_import_roots = {"requests", "httpx", "urllib", "socket"}

    for module_path in module_paths:
        source = module_path.read_text(encoding="utf-8")
        parsed = ast.parse(source)
        for node in ast.walk(parsed):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in disallowed_import_roots
            if isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in disallowed_import_roots

        lowered = source.lower()
        assert "@app.route" not in lowered
        assert "@router." not in lowered
        assert "viki_live_client" not in lowered
