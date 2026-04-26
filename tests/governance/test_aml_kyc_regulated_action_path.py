"""Tests for deterministic AML/KYC regulated action path fixture."""

from __future__ import annotations

from veritas_os.governance.regulated_action_path import run_all_regulated_action_scenarios


def _by_name() -> dict[str, object]:
    return {item.scenario_name: item for item in run_all_regulated_action_scenarios()}


def test_allowed_internal_escalation_commits() -> None:
    scenario = _by_name()["scenario_a_allowed_internal_escalation"]
    assert scenario.actual_outcome == "commit"


def test_prohibited_account_freeze_blocks() -> None:
    scenario = _by_name()["scenario_b_prohibited_account_freeze"]
    assert scenario.actual_outcome == "block"


def test_prohibited_customer_notification_blocks() -> None:
    scenario = _by_name()["scenario_c_prohibited_customer_notification"]
    assert scenario.actual_outcome == "block"


def test_stale_sanctions_screening_escalates_deterministically() -> None:
    scenario = _by_name()["scenario_d_stale_sanctions_screening"]
    assert scenario.actual_outcome == "escalate"


def test_missing_authority_blocks() -> None:
    scenario = _by_name()["scenario_e_missing_authority"]
    assert scenario.actual_outcome == "block"


def test_high_irreversibility_without_human_approval_blocks() -> None:
    scenario = _by_name()["scenario_f_high_irreversibility_without_human_approval"]
    assert scenario.actual_outcome == "block"


def test_unresolved_policy_snapshot_blocks_deterministically() -> None:
    scenario = _by_name()["scenario_g_policy_uncertainty"]
    assert scenario.actual_outcome == "block"


def test_bind_receipt_contains_action_contract_id() -> None:
    scenario = _by_name()["scenario_a_allowed_internal_escalation"]
    assert scenario.action_contract_id == "aml_kyc_customer_risk_escalation"


def test_commit_receipt_contains_authority_evidence_hash() -> None:
    scenario = _by_name()["scenario_a_allowed_internal_escalation"]
    assert scenario.metadata["authority_evidence_hash"] == "hash-a"


def test_all_scenarios_are_deterministic() -> None:
    first = [item.to_dict() for item in run_all_regulated_action_scenarios()]
    second = [item.to_dict() for item in run_all_regulated_action_scenarios()]
    assert first == second
