from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path

_FIXTURE_DIR = Path("tests/fixtures/controlled_live_viki_payload_schema")
_HANDOFF_MODULE_PATH = Path("veritas_os/governance/controlled_live_viki_rsa_handoff.py")
_SCHEMA_ADAPTER_PATH = Path("veritas_os/governance/controlled_live_viki_schema_adapter.py")
_THIS_FILE = Path(__file__)


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_HANDOFF_MODULE = _load_module(_HANDOFF_MODULE_PATH, "controlled_live_viki_rsa_handoff")
_SCHEMA_ADAPTER_MODULE = _load_module(_SCHEMA_ADAPTER_PATH, "controlled_live_viki_schema_adapter")

build_controlled_live_viki_rsa_handoff_decision = (
    _HANDOFF_MODULE.build_controlled_live_viki_rsa_handoff_decision
)
CONTROLLED_LIVE_RSA_HANDOFF_DENSITY_THROTTLED = (
    _HANDOFF_MODULE.CONTROLLED_LIVE_RSA_HANDOFF_DENSITY_THROTTLED
)
CONTROLLED_LIVE_RSA_HANDOFF_MISSING_REQUIRED_FIELD = (
    _HANDOFF_MODULE.CONTROLLED_LIVE_RSA_HANDOFF_MISSING_REQUIRED_FIELD
)
CONTROLLED_LIVE_RSA_HANDOFF_SAFE_PROCEED_NOT_FINAL = (
    _HANDOFF_MODULE.CONTROLLED_LIVE_RSA_HANDOFF_SAFE_PROCEED_NOT_FINAL
)
CONTROLLED_LIVE_RSA_HANDOFF_UNSUPPORTED_STATUS = (
    _HANDOFF_MODULE.CONTROLLED_LIVE_RSA_HANDOFF_UNSUPPORTED_STATUS
)
ADAPTER_VALID = _SCHEMA_ADAPTER_MODULE.ADAPTER_VALID
classify_controlled_live_viki_schema_input = (
    _SCHEMA_ADAPTER_MODULE.classify_controlled_live_viki_schema_input
)


def _load_payload_fixture(name: str) -> dict[str, object]:
    return json.loads((_FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _assert_fail_closed(decision: dict[str, object]) -> None:
    assert decision["final_commit_approved"] is False
    assert decision["veritas_sandbox_commit_state"] == "SUSPENDED_NOT_COMMITTED"
    assert decision["veritas_continuation_decision"] == "PAUSE_FOR_HUMAN_REVIEW"


# ... tests unchanged minimal from prior

def test_rsa_handoff_runtime_safe_proceed_remains_upstream_signal_not_final_approval() -> None:
    payload = _load_payload_fixture("valid_safe_proceed_v1alpha1.json")
    assert classify_controlled_live_viki_schema_input(payload) == ADAPTER_VALID
    assert payload["rsa_status"] == "SAFE_PROCEED"
    decision = build_controlled_live_viki_rsa_handoff_decision(payload)
    assert decision["rsa_status"] == "SAFE_PROCEED"
    assert decision["upstream_signal_source"] == "RSA"
    assert decision["reason_code"] == CONTROLLED_LIVE_RSA_HANDOFF_SAFE_PROCEED_NOT_FINAL
    _assert_fail_closed(decision)
    assert decision["veritas_continuation_decision"] != "CONTINUE_TO_BIND_BOUNDARY"


def test_rsa_handoff_runtime_density_throttled_maps_to_fail_closed_review() -> None:
    payload = _load_payload_fixture("valid_density_throttled_v1alpha1.json")
    assert classify_controlled_live_viki_schema_input(payload) == ADAPTER_VALID
    decision = build_controlled_live_viki_rsa_handoff_decision(payload)
    assert decision["reason_code"] == CONTROLLED_LIVE_RSA_HANDOFF_DENSITY_THROTTLED
    _assert_fail_closed(decision)


def test_rsa_handoff_runtime_algorithmic_humility_maps_to_fail_closed_review() -> None:
    payload = _load_payload_fixture("valid_algorithmic_humility_engaged_v1alpha1.json")
    assert classify_controlled_live_viki_schema_input(payload) == ADAPTER_VALID
    decision = build_controlled_live_viki_rsa_handoff_decision(payload)
    assert decision["reason_code"] == "CONTROLLED_LIVE_RSA_HANDOFF_ALGORITHMIC_HUMILITY_ENGAGED"
    _assert_fail_closed(decision)


def test_rsa_handoff_runtime_deferral_maps_to_fail_closed_review() -> None:
    payload = _load_payload_fixture("valid_deferral_engaged_v1alpha1.json")
    assert classify_controlled_live_viki_schema_input(payload) == ADAPTER_VALID
    decision = build_controlled_live_viki_rsa_handoff_decision(payload)
    assert decision["reason_code"] == "CONTROLLED_LIVE_RSA_HANDOFF_DEFERRAL_ENGAGED"
    _assert_fail_closed(decision)


def test_rsa_handoff_runtime_preserves_safe_identity_fields_only() -> None:
    payload = _load_payload_fixture("valid_safe_proceed_v1alpha1.json")
    decision = build_controlled_live_viki_rsa_handoff_decision(payload)
    for name in ["request_id", "correlation_id", "schema_version", "rsa_status", "upstream_signal_source"]:
        assert name in decision


def test_rsa_handoff_runtime_does_not_introduce_viki_specific_downstream_contract() -> None:
    decision = build_controlled_live_viki_rsa_handoff_decision(
        _load_payload_fixture("valid_safe_proceed_v1alpha1.json")
    )
    assert "viki_status" not in decision
    assert "VIKIPayload" not in decision
    source = _HANDOFF_MODULE_PATH.read_text(encoding="utf-8")
    assert "viki_status" not in source
    assert "VIKIPayload" not in source


def test_rsa_handoff_runtime_invalid_or_missing_required_fields_fail_closed() -> None:
    cases = [{}, {"rsa_status": "SAFE_PROCEED"}, {"request_id": "req_only"}, {"request_id": "req", "correlation_id": "corr", "schema_version": "v1alpha1", "rsa_status": "UNKNOWN_STATUS"}]
    for payload in cases:
        decision = build_controlled_live_viki_rsa_handoff_decision(payload)
        assert decision["reason_code"] in {CONTROLLED_LIVE_RSA_HANDOFF_MISSING_REQUIRED_FIELD, CONTROLLED_LIVE_RSA_HANDOFF_UNSUPPORTED_STATUS}
        _assert_fail_closed(decision)


def test_rsa_handoff_runtime_evaluate_rsa_sandbox_signal_boundary_is_not_bypassed() -> None:
    decision = build_controlled_live_viki_rsa_handoff_decision(
        _load_payload_fixture("valid_safe_proceed_v1alpha1.json")
    )
    assert decision["final_commit_approved"] is False


def test_rsa_handoff_runtime_module_is_offline_static_and_no_network() -> None:
    source = _HANDOFF_MODULE_PATH.read_text(encoding="utf-8")
    parsed = ast.parse(source)
    for node in ast.walk(parsed):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in {"requests", "httpx", "urllib", "socket"}
    assert "fastapi" not in source.lower()
    assert "flask" not in source.lower()
    before = _THIS_FILE.read_text(encoding="utf-8").split("def test_rsa_handoff_runtime_module_is_offline_static_and_no_network", maxsplit=1)[0].lower()
    for token in ("http" + "://", "https" + "://"):
        assert token not in source.lower()
        assert token not in before


def test_rsa_handoff_runtime_does_not_modify_receiver_or_schema_adapter_behavior() -> None:
    payload = _load_payload_fixture("valid_safe_proceed_v1alpha1.json")
    assert classify_controlled_live_viki_schema_input(payload) == ADAPTER_VALID
    interface_source = Path("veritas_os/governance/controlled_live_viki_interface.py").read_text(encoding="utf-8")
    assert "CONTROLLED_LIVE_DISABLED" in interface_source
    assert "CONTROLLED_LIVE_SCHEMA_VALID_NOT_YET_WIRED" in interface_source
