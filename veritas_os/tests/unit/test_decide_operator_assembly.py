"""Unit tests for /v1/decide operator assembly helpers."""

from __future__ import annotations

from veritas_os.api.decide_operator_assembly import (
    attach_bind_operator_surface,
    attach_wat_contract_fields,
    normalize_wat_drift_vector,
    resolve_operator_verbosity,
)


def test_resolve_operator_verbosity_falls_back_to_minimal() -> None:
    assert resolve_operator_verbosity(None) == "minimal"
    assert resolve_operator_verbosity("verbose") == "minimal"
    assert resolve_operator_verbosity("expanded") == "expanded"


def test_normalize_wat_drift_vector_maps_legacy_keys() -> None:
    normalized = normalize_wat_drift_vector(
        {"policy_drift": 0.4, "signature": 0.1, "observable_drift": 0.2}
    )

    assert normalized == {
        "policy": 0.4,
        "signature": 0.1,
        "observable": 0.2,
        "temporal": 0.0,
    }


def test_attach_bind_operator_surface_role_gates_detail() -> None:
    payload = {
        "bind_summary": {
            "outcome": "BLOCKED",
            "reason_code": "reason-x",
            "bind_receipt_id": "br-1",
            "execution_intent_id": "ei-1",
        },
        "authority_check_result": {"status": "denied"},
    }

    attach_bind_operator_surface(
        payload=payload,
        policy={"operator_verbosity": "expanded"},
        role="operator",
    )

    assert payload["bind_operator_summary"]["operator_verbosity"] == "minimal"
    assert "bind_operator_detail" not in payload


def test_attach_wat_contract_fields_attaches_summary_and_optional_detail() -> None:
    payload = {"request_id": "rid-1"}
    attach_wat_contract_fields(
        payload,
        {
            "wat_id": "wat-1",
            "validation_status": "valid",
            "admissibility_state": "admissible",
            "operator_verbosity": "expanded",
            "drift_vector": {"policy": 0.1},
            "event_lane_details": {"validation_status": "valid"},
        },
    )

    assert payload["wat_integrity"]["integrity_state"] == "healthy"
    assert payload["wat_operator_summary"]["operator_verbosity"] == "expanded"
    assert payload["wat_operator_detail"]["drift_vector"]["policy"] == 0.1
