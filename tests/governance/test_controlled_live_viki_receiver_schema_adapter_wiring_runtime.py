"""Runtime wiring tests for controlled live V.I.K.I. receiver + schema adapter.

This suite verifies local/offline fail-closed wiring only.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

from veritas_os.governance.controlled_live_viki_interface import (
    receive_controlled_live_viki_payload,
)
from veritas_os.governance.controlled_live_viki_schema_adapter import (
    ADAPTER_VALID,
    classify_controlled_live_viki_schema_input,
)


FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "controlled_live_viki_payload_schema"


def _load_payload_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _reason_code(result: dict[str, object]) -> str:
    return str(result.get("reason_code") or result.get("veritas_reason_code") or "")


def test_receiver_schema_adapter_runtime_wiring_disabled_flag_preserves_existing_fail_closed_behavior() -> None:
    payload = _load_payload_fixture("valid_safe_proceed_v1alpha1.json")
    disabled_values = [None, "", " ", "false", "0", "no", "off", "disabled", "TRUE", "True", "unexpected"]

    for value in disabled_values:
        result = receive_controlled_live_viki_payload(payload, feature_flag_value=value)
        assert _reason_code(result) == "CONTROLLED_LIVE_DISABLED"
        assert result["veritas_continuation_decision"] == "PAUSE_FOR_HUMAN_REVIEW"
        assert result["veritas_sandbox_commit_state"] == "SUSPENDED_NOT_COMMITTED"
        assert result["final_commit_approved"] is False
        assert result["veritas_continuation_decision"] != "SAFE_PROCEED"
        dumped = json.dumps(result)
        assert "raw_payload_body" not in dumped


def test_receiver_schema_adapter_runtime_wiring_true_flag_invalid_payloads_fail_closed_by_schema_adapter() -> None:
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
        result = receive_controlled_live_viki_payload(
            _load_payload_fixture(fixture_name),
            feature_flag_value="true",
        )
        reason_code = _reason_code(result)
        assert reason_code.startswith("CONTROLLED_LIVE_")
        assert reason_code != "CONTROLLED_LIVE_DISABLED"
        assert reason_code != "SAFE_PROCEED"
        assert result["veritas_continuation_decision"] == "PAUSE_FOR_HUMAN_REVIEW"
        assert result["veritas_sandbox_commit_state"] == "SUSPENDED_NOT_COMMITTED"
        assert result["final_commit_approved"] is False
        assert result["upstream_signal_source"] == "RSA"
        dumped = json.dumps(result)
        assert "raw_payload_body" not in dumped


def test_receiver_schema_adapter_runtime_wiring_true_flag_valid_safe_proceed_remains_not_final_approval() -> None:
    payload = _load_payload_fixture("valid_safe_proceed_v1alpha1.json")

    assert classify_controlled_live_viki_schema_input(payload) == ADAPTER_VALID
    assert payload["rsa_status"] == "SAFE_PROCEED"

    result = receive_controlled_live_viki_payload(payload, feature_flag_value="true")
    assert _reason_code(result) == "CONTROLLED_LIVE_RSA_HANDOFF_SAFE_PROCEED_NOT_FINAL"
    assert result["final_commit_approved"] is False
    assert result["veritas_sandbox_commit_state"] == "SUSPENDED_NOT_COMMITTED"
    assert result["veritas_continuation_decision"] == "PAUSE_FOR_HUMAN_REVIEW"
    assert result["veritas_continuation_decision"] != "CONTINUE_TO_BIND_BOUNDARY"


def test_receiver_schema_adapter_runtime_wiring_true_flag_valid_non_safe_proceed_statuses_remain_not_final_approval() -> None:
    fixtures = [
        "valid_density_throttled_v1alpha1.json",
        "valid_algorithmic_humility_engaged_v1alpha1.json",
        "valid_deferral_engaged_v1alpha1.json",
    ]

    expected = {
        "valid_density_throttled_v1alpha1.json": (
            "CONTROLLED_LIVE_RSA_HANDOFF_DENSITY_THROTTLED"
        ),
        "valid_algorithmic_humility_engaged_v1alpha1.json": (
            "CONTROLLED_LIVE_RSA_HANDOFF_ALGORITHMIC_HUMILITY_ENGAGED"
        ),
        "valid_deferral_engaged_v1alpha1.json": (
            "CONTROLLED_LIVE_RSA_HANDOFF_DEFERRAL_ENGAGED"
        ),
    }

    for fixture_name in fixtures:
        payload = _load_payload_fixture(fixture_name)
        assert classify_controlled_live_viki_schema_input(payload) == ADAPTER_VALID

        result = receive_controlled_live_viki_payload(payload, feature_flag_value="true")
        assert _reason_code(result) == expected[fixture_name]
        assert result["final_commit_approved"] is False
        assert result["veritas_sandbox_commit_state"] == "SUSPENDED_NOT_COMMITTED"


def test_receiver_schema_adapter_runtime_wiring_duplicate_request_id_fails_closed() -> None:
    scenario_a = _load_payload_fixture("invalid_duplicate_request_id_scenario_a_v1alpha1.json")
    scenario_b = _load_payload_fixture("invalid_duplicate_request_id_scenario_b_v1alpha1.json")
    seen_request_ids: dict[str, str] = {}

    result_a = receive_controlled_live_viki_payload(
        scenario_a,
        feature_flag_value="true",
        seen_request_ids=seen_request_ids,
    )
    result_b = receive_controlled_live_viki_payload(
        scenario_b,
        feature_flag_value="true",
        seen_request_ids=seen_request_ids,
    )

    assert _reason_code(result_a) == "CONTROLLED_LIVE_RSA_HANDOFF_SAFE_PROCEED_NOT_FINAL"
    assert _reason_code(result_b) == "CONTROLLED_LIVE_REPLAY_DUPLICATE_REQUEST_ID"
    assert result_b["final_commit_approved"] is False
    assert result_b["veritas_sandbox_commit_state"] == "SUSPENDED_NOT_COMMITTED"
    assert len(seen_request_ids) == 1


def test_receiver_schema_adapter_runtime_wiring_forbidden_secret_and_kyc_fields_are_not_echoed() -> None:
    fixtures = [
        "invalid_forbidden_chain_of_thought_v1alpha1.json",
        "invalid_secret_access_token_v1alpha1.json",
        "invalid_raw_kyc_record_v1alpha1.json",
    ]

    for fixture_name in fixtures:
        result = receive_controlled_live_viki_payload(
            _load_payload_fixture(fixture_name),
            feature_flag_value="true",
        )
        dumped = json.dumps(result)
        assert result["final_commit_approved"] is False
        assert "chain_of_thought" not in dumped
        assert "raw_kyc_record" not in dumped
        assert "access_token" not in dumped
        assert "raw_payload_body" not in dumped


def test_receiver_schema_adapter_runtime_wiring_rejects_non_object_payloads() -> None:
    for payload in (None, [], "not-json-object", 123):
        result = receive_controlled_live_viki_payload(payload, feature_flag_value="true")
        assert _reason_code(result) == "CONTROLLED_LIVE_INVALID_JSON_OBJECT"
        assert result["final_commit_approved"] is False
        assert result["veritas_sandbox_commit_state"] == "SUSPENDED_NOT_COMMITTED"


def test_receiver_schema_adapter_runtime_wiring_module_is_no_network_no_endpoint_no_telemetry() -> None:
    source_paths = [
        Path("veritas_os/governance/controlled_live_viki_interface.py"),
        Path("veritas_os/governance/controlled_live_viki_schema_adapter.py"),
        Path(__file__),
    ]

    disallowed_import_roots = {"requests", "httpx", "urllib", "socket", "opentelemetry", "sentry_sdk"}
    for source_path in source_paths:
        source = source_path.read_text(encoding="utf-8")
        module = ast.parse(source)
        for node in ast.walk(module):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in disallowed_import_roots
            if isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in disallowed_import_roots

    test_source = Path(__file__).read_text(encoding="utf-8")
    precheck_source = test_source.split(
        "def test_receiver_schema_adapter_runtime_wiring_module_is_no_network_no_endpoint_no_telemetry",
        maxsplit=1,
    )[0].lower()
    forbidden_literals = [
        "http" + "://",
        "https" + "://",
        "bear" + "er" + " ",
        "api" + "_" + "key=",
        "fastapi",
        "flask",
        "viki_live_client",
        "live_viki_client",
        "telemetrysdk",
    ]
    for token in forbidden_literals:
        assert token not in precheck_source


def test_receiver_schema_adapter_runtime_wiring_does_not_touch_downstream_contract() -> None:
    interface_source = Path("veritas_os/governance/controlled_live_viki_interface.py").read_text(encoding="utf-8")
    adapter_source = Path("veritas_os/governance/controlled_live_viki_schema_adapter.py").read_text(
        encoding="utf-8",
    )
    payload = _load_payload_fixture("valid_safe_proceed_v1alpha1.json")

    assert "viki_status" not in interface_source
    assert "VIKIPayload" not in interface_source
    assert "rsa_status" in adapter_source
    assert payload["rsa_status"] == "SAFE_PROCEED"
    assert classify_controlled_live_viki_schema_input(payload) == ADAPTER_VALID

    result = receive_controlled_live_viki_payload(feature_flag_value=None)
    assert result["upstream_signal_source"] == "RSA"
