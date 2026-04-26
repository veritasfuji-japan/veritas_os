from __future__ import annotations

import json
from pathlib import Path

import pytest

from veritas_os.governance.action_contracts import (
    ActionClassContractValidationError,
    load_action_class_contract,
)


def _minimal_contract() -> dict:
    return {
        "id": "contract.financial.transfer",
        "version": "1.0.0",
        "domain": "financial",
        "action_class": "wire_transfer",
        "description": "Govern regulated transfer actions.",
        "declared_intent": "Transfer customer funds after authorization.",
        "allowed_scope": ["customer_account:verified"],
        "prohibited_scope": ["sanctioned_recipient"],
        "authority_sources": ["policy.register.financial"],
        "required_evidence": ["kyc_status", "sanctions_screening"],
        "evidence_freshness": {"kyc_status": "P30D"},
        "irreversibility": {"boundary": "funds_committed", "level": "high"},
        "human_approval_rules": {"minimum_approvals": 1},
        "refusal_conditions": ["evidence_missing"],
        "escalation_conditions": ["high_risk_flag"],
        "default_failure_mode": "fail_closed",
        "metadata": {"regulated": True},
    }


def _write_contract(path: Path, payload: dict) -> Path:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def test_valid_minimal_contract_loads(tmp_path: Path) -> None:
    contract_file = _write_contract(tmp_path / "contract.json", _minimal_contract())

    loaded = load_action_class_contract(contract_file)

    assert loaded.id == "contract.financial.transfer"
    assert loaded.default_failure_mode == "fail_closed"


@pytest.mark.parametrize(
    "missing_field",
    ["id", "version", "allowed_scope", "prohibited_scope", "irreversibility"],
)
def test_missing_required_fields_fail_validation(tmp_path: Path, missing_field: str) -> None:
    payload = _minimal_contract()
    payload.pop(missing_field)
    contract_file = _write_contract(
        tmp_path / f"missing_{missing_field}.json",
        payload,
    )

    with pytest.raises(ActionClassContractValidationError, match=missing_field):
        load_action_class_contract(contract_file)


@pytest.mark.parametrize("mode", ["fail_closed", "deny", "escalate"])
def test_default_failure_mode_accepts_supported_values(tmp_path: Path, mode: str) -> None:
    payload = _minimal_contract()
    payload["default_failure_mode"] = mode
    contract_file = _write_contract(tmp_path / f"mode_{mode}.json", payload)

    loaded = load_action_class_contract(contract_file)

    assert loaded.default_failure_mode == mode


def test_unknown_critical_field_is_rejected(tmp_path: Path) -> None:
    payload = _minimal_contract()
    payload["critical_unapproved_field"] = "must-not-pass"
    contract_file = _write_contract(tmp_path / "critical.json", payload)

    with pytest.raises(
        ActionClassContractValidationError,
        match="unknown critical field",
    ):
        load_action_class_contract(contract_file)


def test_serialization_is_deterministic(tmp_path: Path) -> None:
    contract_file = _write_contract(tmp_path / "stable.json", _minimal_contract())

    loaded = load_action_class_contract(contract_file)

    assert (
        loaded.deterministic_serialization()
        == loaded.deterministic_serialization()
    )
    assert loaded.deterministic_digest() == loaded.deterministic_digest()


def test_contract_identity_fields_are_stable(tmp_path: Path) -> None:
    contract_file = _write_contract(tmp_path / "identity.json", _minimal_contract())

    loaded = load_action_class_contract(contract_file)

    assert loaded.id == "contract.financial.transfer"
    assert loaded.version == "1.0.0"
