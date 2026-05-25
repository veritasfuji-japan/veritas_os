"""Test-only future wiring skeleton for receiver-to-schema-adapter behavior.

This module is intentionally offline and synthetic-fixture-only.
It does not implement runtime wiring, endpoint behavior, network behavior,
live V.I.K.I. integration, credentials, replay cache infrastructure, logging,
telemetry, observability runtime, or production behavior.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

from veritas_os.governance.controlled_live_viki_interface import (
    build_controlled_live_viki_disabled_decision,
    is_controlled_live_viki_enabled,
)
from veritas_os.governance.controlled_live_viki_schema_adapter import (
    ADAPTER_INVALID_JSON_OBJECT,
    ADAPTER_VALID,
    build_controlled_live_viki_schema_fail_closed_decision,
    classify_controlled_live_viki_schema_input,
    controlled_live_viki_reason_code_for_classification,
)


def _load_payload_fixture(name: str) -> dict:
    fixture_dir = Path(__file__).resolve().parent.parent / "fixtures" / "controlled_live_viki_payload_schema"
    return json.loads((fixture_dir / name).read_text(encoding="utf-8"))


def _future_receiver_schema_adapter_wiring_decision(
    payload: object,
    *,
    feature_flag_value: str | None,
    seen_request_ids: dict[str, str] | None = None,
) -> dict:
    """Model the expected future wiring contract without implementing runtime wiring."""
    if not is_controlled_live_viki_enabled(feature_flag_value):
        if isinstance(payload, dict):
            return build_controlled_live_viki_disabled_decision(
                request_id=str(payload.get("request_id") or "req_viki_disabled_001"),
                correlation_id=str(payload.get("correlation_id") or "corr_viki_veritas_disabled_001"),
                schema_version=str(payload.get("schema_version") or "v1alpha1"),
            )
        return build_controlled_live_viki_disabled_decision()

    classification = classify_controlled_live_viki_schema_input(payload, seen_request_ids=seen_request_ids)
    if classification != ADAPTER_VALID:
        reason_code = controlled_live_viki_reason_code_for_classification(classification)
        if reason_code is None:
            reason_code = "CONTROLLED_LIVE_INVALID_JSON_OBJECT"
        return build_controlled_live_viki_schema_fail_closed_decision(reason_code)

    valid_reason_code = "CONTROLLED_LIVE_SCHEMA_VALID_NOT_YET_WIRED"
    return build_controlled_live_viki_schema_fail_closed_decision(valid_reason_code)


def test_receiver_schema_adapter_wiring_disabled_flag_preserves_existing_receiver_fail_closed_behavior() -> None:
    payload = _load_payload_fixture("valid_safe_proceed_v1alpha1.json")
    disabled_values = [None, "", " ", "false", "0", "no", "off", "disabled", "TRUE", "True", "unexpected"]

    for feature_flag_value in disabled_values:
        result = _future_receiver_schema_adapter_wiring_decision(
            payload,
            feature_flag_value=feature_flag_value,
        )
        assert result["veritas_reason_code"] == "CONTROLLED_LIVE_DISABLED"
        assert result["veritas_continuation_decision"] == "PAUSE_FOR_HUMAN_REVIEW"
        assert result["veritas_sandbox_commit_state"] == "SUSPENDED_NOT_COMMITTED"
        assert result["final_commit_approved"] is False
        assert result["veritas_reason_code"] != "SAFE_PROCEED"
        dumped = json.dumps(result)
        assert "raw_payload_body" not in dumped


def test_receiver_schema_adapter_wiring_true_flag_invalid_payloads_fail_closed_by_schema_adapter() -> None:
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
        result = _future_receiver_schema_adapter_wiring_decision(
            _load_payload_fixture(fixture_name),
            feature_flag_value="true",
        )
        assert str(result["reason_code"]).startswith("CONTROLLED_LIVE_")
        assert result["reason_code"] != "CONTROLLED_LIVE_DISABLED"
        assert result["reason_code"] != "SAFE_PROCEED"
        assert result["veritas_continuation_decision"] == "PAUSE_FOR_HUMAN_REVIEW"
        assert result["veritas_sandbox_commit_state"] == "SUSPENDED_NOT_COMMITTED"
        assert result["final_commit_approved"] is False
        assert result["upstream_signal_source"] == "RSA"
        dumped = json.dumps(result)
        assert "raw_payload_body" not in dumped


def test_receiver_schema_adapter_wiring_true_flag_valid_safe_proceed_remains_not_final_approval() -> None:
    payload = _load_payload_fixture("valid_safe_proceed_v1alpha1.json")
    classification = classify_controlled_live_viki_schema_input(payload)
    result = _future_receiver_schema_adapter_wiring_decision(payload, feature_flag_value="true")

    assert classification == ADAPTER_VALID
    assert payload["rsa_status"] == "SAFE_PROCEED"
    assert result["reason_code"] in {
        "CONTROLLED_LIVE_RUNTIME_NOT_IMPLEMENTED",
        "CONTROLLED_LIVE_SCHEMA_VALID_NOT_YET_WIRED",
    }
    assert result["final_commit_approved"] is False
    assert result["veritas_sandbox_commit_state"] == "SUSPENDED_NOT_COMMITTED"
    assert result["veritas_continuation_decision"] == "PAUSE_FOR_HUMAN_REVIEW"
    assert result["veritas_continuation_decision"] != "CONTINUE_TO_BIND_BOUNDARY"


def test_receiver_schema_adapter_wiring_true_flag_valid_non_safe_proceed_statuses_remain_not_final_approval() -> None:
    fixtures = [
        "valid_density_throttled_v1alpha1.json",
        "valid_algorithmic_humility_engaged_v1alpha1.json",
        "valid_deferral_engaged_v1alpha1.json",
    ]
    for fixture_name in fixtures:
        payload = _load_payload_fixture(fixture_name)
        classification = classify_controlled_live_viki_schema_input(payload)
        result = _future_receiver_schema_adapter_wiring_decision(payload, feature_flag_value="true")

        assert classification == ADAPTER_VALID
        assert result["final_commit_approved"] is False
        assert result["veritas_sandbox_commit_state"] == "SUSPENDED_NOT_COMMITTED"
        assert result["reason_code"] == "CONTROLLED_LIVE_SCHEMA_VALID_NOT_YET_WIRED"


def test_receiver_schema_adapter_wiring_duplicate_request_id_fails_closed() -> None:
    scenario_a = _load_payload_fixture("invalid_duplicate_request_id_scenario_a_v1alpha1.json")
    scenario_b = _load_payload_fixture("invalid_duplicate_request_id_scenario_b_v1alpha1.json")
    seen_request_ids: dict[str, str] = {}

    first_result = _future_receiver_schema_adapter_wiring_decision(
        scenario_a,
        feature_flag_value="true",
        seen_request_ids=seen_request_ids,
    )
    second_result = _future_receiver_schema_adapter_wiring_decision(
        scenario_b,
        feature_flag_value="true",
        seen_request_ids=seen_request_ids,
    )

    assert first_result["final_commit_approved"] is False
    assert second_result["reason_code"] == "CONTROLLED_LIVE_REPLAY_DUPLICATE_REQUEST_ID"
    assert second_result["final_commit_approved"] is False
    assert second_result["veritas_sandbox_commit_state"] == "SUSPENDED_NOT_COMMITTED"
    assert len(seen_request_ids) == 1


def test_receiver_schema_adapter_wiring_forbidden_secret_and_kyc_fields_are_not_echoed() -> None:
    fixtures = [
        "invalid_forbidden_chain_of_thought_v1alpha1.json",
        "invalid_secret_access_token_v1alpha1.json",
        "invalid_raw_kyc_record_v1alpha1.json",
    ]
    for fixture_name in fixtures:
        result = _future_receiver_schema_adapter_wiring_decision(
            _load_payload_fixture(fixture_name),
            feature_flag_value="true",
        )
        dumped = json.dumps(result)
        assert result["final_commit_approved"] is False
        assert "chain_of_thought" not in dumped
        assert "raw_kyc_record" not in dumped
        assert "access_token" not in dumped
        assert "raw_payload_body" not in dumped


def test_receiver_schema_adapter_wiring_rejects_non_object_payloads() -> None:
    for payload in (None, [], "not-json-object", 123):
        result = _future_receiver_schema_adapter_wiring_decision(payload, feature_flag_value="true")
        assert result["reason_code"] == "CONTROLLED_LIVE_INVALID_JSON_OBJECT"
        assert result["final_commit_approved"] is False
        assert result["veritas_sandbox_commit_state"] == "SUSPENDED_NOT_COMMITTED"


def test_receiver_schema_adapter_wiring_behavior_skeleton_is_offline_static_and_no_network() -> None:
    source_path = Path(__file__)
    source = source_path.read_text(encoding="utf-8")
    module = ast.parse(source)

    disallowed_import_roots = {"requests", "httpx", "urllib", "socket"}
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in disallowed_import_roots
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] not in disallowed_import_roots

    precheck_source = source.split(
        "def test_receiver_schema_adapter_wiring_behavior_skeleton_is_offline_static_and_no_network",
        maxsplit=1,
    )[0].lower()
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
        assert token not in precheck_source


def test_receiver_schema_adapter_wiring_behavior_skeleton_does_not_modify_runtime_modules() -> None:
    interface_source = Path("veritas_os/governance/controlled_live_viki_interface.py").read_text(encoding="utf-8")
    adapter_source = Path("veritas_os/governance/controlled_live_viki_schema_adapter.py").read_text(encoding="utf-8")

    assert "receive_controlled_live_viki_payload" in interface_source
    assert "classify_controlled_live_viki_schema_input" in adapter_source
    assert "live_viki_client" not in interface_source.lower()
    assert "live_viki_client" not in adapter_source.lower()
