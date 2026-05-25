"""Test-only schema-valid RSA handoff behavior skeleton for controlled live V.I.K.I.

This file is intentionally offline and deterministic. It defines a local,
future-facing handoff contract model only and does not implement runtime
handoff, endpoint behavior, network behavior, live integration, credentials,
replay cache, logging, telemetry, or observability runtime.
"""

from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path

_FIXTURE_DIR = Path("tests/fixtures/controlled_live_viki_payload_schema")
_THIS_FILE = Path(__file__)
_SCHEMA_ADAPTER_PATH = Path("veritas_os/governance/controlled_live_viki_schema_adapter.py")
_RSA_RECEIVER_PATH = Path("veritas_os/governance/rsa_sandbox_receiver.py")

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

try:
    _RSA_RECEIVER_SPEC = importlib.util.spec_from_file_location(
        "rsa_sandbox_receiver",
        _RSA_RECEIVER_PATH,
    )
    assert _RSA_RECEIVER_SPEC is not None
    assert _RSA_RECEIVER_SPEC.loader is not None
    _RSA_RECEIVER_MODULE = importlib.util.module_from_spec(_RSA_RECEIVER_SPEC)
    _RSA_RECEIVER_SPEC.loader.exec_module(_RSA_RECEIVER_MODULE)
    RSASandboxPayload = _RSA_RECEIVER_MODULE.RSASandboxPayload
    evaluate_rsa_sandbox_signal = _RSA_RECEIVER_MODULE.evaluate_rsa_sandbox_signal
except Exception:  # pragma: no cover - defensive import fallback for boundary test
    RSASandboxPayload = None
    evaluate_rsa_sandbox_signal = None

_HANDOFF_STATUS_MAP = {
    "SAFE_PROCEED": "CONTROLLED_LIVE_RSA_HANDOFF_SAFE_PROCEED_NOT_FINAL",
    "DENSITY_THROTTLED": "CONTROLLED_LIVE_RSA_HANDOFF_DENSITY_THROTTLED",
    "ALGORITHMIC_HUMILITY_ENGAGED": "CONTROLLED_LIVE_RSA_HANDOFF_ALGORITHMIC_HUMILITY_ENGAGED",
    "DEFERRAL_ENGAGED": "CONTROLLED_LIVE_RSA_HANDOFF_DEFERRAL_ENGAGED",
}


def _load_payload_fixture(name: str) -> dict:
    return json.loads((_FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _model_schema_valid_handoff_fail_closed_decision(
    payload: dict,
    *,
    handoff_status: str,
) -> dict:
    return {
        "reason_code": handoff_status,
        "veritas_continuation_decision": "PAUSE_FOR_HUMAN_REVIEW",
        "veritas_sandbox_commit_state": "SUSPENDED_NOT_COMMITTED",
        "final_commit_approved": False,
        "required_next_action": "REQUEST_HUMAN_REVIEW_OR_RETRY_WITH_VALID_UPSTREAM_STATE",
        "upstream_signal_source": "RSA",
        "decision_source": "controlled_live_viki_schema_valid_rsa_handoff_behavior_skeleton",
        "request_id": payload["request_id"],
        "correlation_id": payload["correlation_id"],
        "schema_version": payload["schema_version"],
        "rsa_status": payload["rsa_status"],
    }


def _model_schema_valid_rsa_handoff(payload: dict) -> dict:
    handoff_status = _HANDOFF_STATUS_MAP[payload["rsa_status"]]
    return _model_schema_valid_handoff_fail_closed_decision(
        payload,
        handoff_status=handoff_status,
    )


def _assert_no_final_commit(decision: dict) -> None:
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


def test_schema_valid_rsa_handoff_safe_proceed_remains_upstream_signal_not_final_approval() -> None:
    payload = _load_payload_fixture("valid_safe_proceed_v1alpha1.json")

    assert classify_controlled_live_viki_schema_input(payload) == ADAPTER_VALID
    assert payload["rsa_status"] == "SAFE_PROCEED"

    decision = _model_schema_valid_rsa_handoff(payload)
    assert decision["rsa_status"] == "SAFE_PROCEED"
    assert decision["upstream_signal_source"] == "RSA"
    assert decision["reason_code"] == "CONTROLLED_LIVE_RSA_HANDOFF_SAFE_PROCEED_NOT_FINAL"
    _assert_no_final_commit(decision)
    assert decision["veritas_continuation_decision"] != "CONTINUE_TO_BIND_BOUNDARY"


def test_schema_valid_rsa_handoff_density_throttled_maps_to_fail_closed_review() -> None:
    payload = _load_payload_fixture("valid_density_throttled_v1alpha1.json")

    assert classify_controlled_live_viki_schema_input(payload) == ADAPTER_VALID
    assert payload["rsa_status"] == "DENSITY_THROTTLED"

    decision = _model_schema_valid_rsa_handoff(payload)
    assert decision["reason_code"] == "CONTROLLED_LIVE_RSA_HANDOFF_DENSITY_THROTTLED"
    _assert_no_final_commit(decision)
    assert decision["upstream_signal_source"] == "RSA"


def test_schema_valid_rsa_handoff_algorithmic_humility_maps_to_fail_closed_review() -> None:
    payload = _load_payload_fixture("valid_algorithmic_humility_engaged_v1alpha1.json")

    assert classify_controlled_live_viki_schema_input(payload) == ADAPTER_VALID
    assert payload["rsa_status"] == "ALGORITHMIC_HUMILITY_ENGAGED"

    decision = _model_schema_valid_rsa_handoff(payload)
    assert (
        decision["reason_code"]
        == "CONTROLLED_LIVE_RSA_HANDOFF_ALGORITHMIC_HUMILITY_ENGAGED"
    )
    _assert_no_final_commit(decision)
    assert decision["upstream_signal_source"] == "RSA"


def test_schema_valid_rsa_handoff_deferral_maps_to_fail_closed_review() -> None:
    payload = _load_payload_fixture("valid_deferral_engaged_v1alpha1.json")

    assert classify_controlled_live_viki_schema_input(payload) == ADAPTER_VALID
    assert payload["rsa_status"] == "DEFERRAL_ENGAGED"

    decision = _model_schema_valid_rsa_handoff(payload)
    assert decision["reason_code"] == "CONTROLLED_LIVE_RSA_HANDOFF_DEFERRAL_ENGAGED"
    _assert_no_final_commit(decision)
    assert decision["upstream_signal_source"] == "RSA"


def test_schema_valid_rsa_handoff_preserves_safe_identity_fields_only() -> None:
    fixture_names = [
        "valid_safe_proceed_v1alpha1.json",
        "valid_density_throttled_v1alpha1.json",
        "valid_algorithmic_humility_engaged_v1alpha1.json",
        "valid_deferral_engaged_v1alpha1.json",
    ]

    for fixture_name in fixture_names:
        payload = _load_payload_fixture(fixture_name)
        decision = _model_schema_valid_rsa_handoff(payload)

        assert decision["request_id"] == payload["request_id"]
        assert decision["correlation_id"] == payload["correlation_id"]
        assert decision["schema_version"] == payload["schema_version"]
        assert decision["rsa_status"] == payload["rsa_status"]
        assert decision["upstream_signal_source"] == "RSA"
        _assert_no_raw_payload_echo(decision)


def test_schema_valid_rsa_handoff_does_not_introduce_viki_specific_downstream_contract() -> None:
    payload = _load_payload_fixture("valid_safe_proceed_v1alpha1.json")
    decision = _model_schema_valid_rsa_handoff(payload)

    assert "viki_status" not in decision
    assert "VIKIPayload" not in decision
    assert decision["rsa_status"] == "SAFE_PROCEED"
    assert decision["upstream_signal_source"] == "RSA"


def test_schema_valid_rsa_handoff_evaluate_rsa_sandbox_signal_boundary_is_not_bypassed() -> None:
    payload = _load_payload_fixture("valid_safe_proceed_v1alpha1.json")

    decision = _model_schema_valid_rsa_handoff(payload)
    _assert_no_final_commit(decision)

    if RSASandboxPayload is not None and evaluate_rsa_sandbox_signal is not None:
        rsa_payload = RSASandboxPayload(
            rsa_status=payload["rsa_status"],
            trigger_source=payload["trigger_source"],
            original_llm_intent="synthetic_intent",
            rsa_action_taken="synthetic_action",
            timestamp=payload["timestamp"],
        )
        sandbox_result = evaluate_rsa_sandbox_signal(rsa_payload)
        assert (
            sandbox_result["audit_entry"]["veritas_sandbox_commit_state"]
            != "FINAL_COMMIT_APPROVED"
        )
    else:
        assert decision["decision_source"] == (
            "controlled_live_viki_schema_valid_rsa_handoff_behavior_skeleton"
        )

    assert decision["rsa_status"] == "SAFE_PROCEED"
    assert decision["final_commit_approved"] is False


def test_schema_valid_rsa_handoff_behavior_skeleton_is_offline_static_and_no_network() -> None:
    source = _THIS_FILE.read_text(encoding="utf-8")
    before_static_check = source.split(
        "def test_schema_valid_rsa_handoff_behavior_skeleton_is_offline_static_and_no_network",
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


def test_schema_valid_rsa_handoff_behavior_skeleton_does_not_modify_runtime_modules() -> None:
    module_paths = (
        Path("veritas_os/governance/controlled_live_viki_interface.py"),
        Path("veritas_os/governance/controlled_live_viki_schema_adapter.py"),
        Path("veritas_os/governance/rsa_sandbox_receiver.py"),
    )

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
