from __future__ import annotations

from pathlib import Path

from veritas_os.governance.action_contracts import load_action_class_contract


CONTRACT_PATH = (
    Path(__file__).resolve().parents[2]
    / "policies"
    / "action_contracts"
    / "aml_kyc_customer_risk_escalation.v1.yaml"
)


def test_aml_kyc_contract_loads() -> None:
    contract = load_action_class_contract(CONTRACT_PATH)

    assert contract.id == "aml_kyc_customer_risk_escalation"


def test_aml_kyc_contract_passes_schema_validation() -> None:
    contract = load_action_class_contract(CONTRACT_PATH)

    assert contract.metadata["regulated"] is True


def test_allowed_internal_escalation_scope_exists() -> None:
    contract = load_action_class_contract(CONTRACT_PATH)

    assert "create_internal_risk_escalation" in contract.allowed_scope


def test_prohibited_account_freeze_exists() -> None:
    contract = load_action_class_contract(CONTRACT_PATH)

    assert "freeze_account" in contract.prohibited_scope


def test_prohibited_customer_notification_exists() -> None:
    contract = load_action_class_contract(CONTRACT_PATH)

    assert "notify_customer" in contract.prohibited_scope


def test_required_evidence_includes_sanctions_screening_result() -> None:
    contract = load_action_class_contract(CONTRACT_PATH)

    assert "sanctions_screening_trace" in contract.required_evidence


def test_default_failure_mode_is_fail_closed() -> None:
    contract = load_action_class_contract(CONTRACT_PATH)

    assert contract.default_failure_mode == "fail_closed"


def test_high_irreversibility_requires_human_approval() -> None:
    contract = load_action_class_contract(CONTRACT_PATH)

    assert "irreversibility_high" in contract.human_approval_rules["required_when"]


def test_serialization_is_deterministic() -> None:
    contract = load_action_class_contract(CONTRACT_PATH)

    assert contract.deterministic_serialization() == contract.deterministic_serialization()


def test_contract_id_and_version_are_stable() -> None:
    contract = load_action_class_contract(CONTRACT_PATH)

    assert contract.id == "aml_kyc_customer_risk_escalation"
    assert contract.version == "v1"
