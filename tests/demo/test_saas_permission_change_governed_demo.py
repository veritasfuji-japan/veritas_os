"""Tests for deterministic local/offline SaaS permission-change governed demo."""

from __future__ import annotations

from scripts.demo.saas_permission_change_governed_demo import (
    BOUNDARY_NOTE,
    run_saas_permission_change_governed_demo,
)


def _case_by_id(payload: dict[str, object], case_id: str) -> dict[str, object]:
    for case in payload["cases"]:  # type: ignore[index]
        if case["case_id"] == case_id:  # type: ignore[index]
            return case
    raise AssertionError(f"missing case: {case_id}")


def test_missing_authority_blocks() -> None:
    payload = run_saas_permission_change_governed_demo()
    case = _case_by_id(payload, "missing_authority")
    assert case["actual_outcome"] == "block"
    assert case["passed"] is True


def test_missing_human_approval_blocks() -> None:
    payload = run_saas_permission_change_governed_demo()
    case = _case_by_id(payload, "missing_human_approval")
    assert case["actual_outcome"] == "block"
    assert case["passed"] is True


def test_expired_human_approval_blocks() -> None:
    payload = run_saas_permission_change_governed_demo()
    case = _case_by_id(payload, "expired_human_approval")
    assert case["actual_outcome"] == "block"
    assert case["passed"] is True


def test_scope_mismatch_blocks() -> None:
    payload = run_saas_permission_change_governed_demo()
    case = _case_by_id(payload, "scope_mismatch")
    assert case["actual_outcome"] == "block"
    assert case["passed"] is True


def test_valid_authority_and_approval_allows_commit_boundary() -> None:
    payload = run_saas_permission_change_governed_demo()
    case = _case_by_id(payload, "valid_authority_and_approval")
    assert case["actual_outcome"] in {"commit", "commit_eligible"}
    assert case["passed"] is True


def test_output_contains_deterministic_case_ids() -> None:
    payload = run_saas_permission_change_governed_demo()
    case_ids = [case["case_id"] for case in payload["cases"]]  # type: ignore[index]
    assert case_ids == [
        "missing_authority",
        "missing_human_approval",
        "expired_human_approval",
        "scope_mismatch",
        "valid_authority_and_approval",
    ]


def test_output_contains_local_offline_boundary_note() -> None:
    payload = run_saas_permission_change_governed_demo()
    assert payload["boundary_note"] == BOUNDARY_NOTE
    for case in payload["cases"]:  # type: ignore[index]
        assert case["boundary_note"] == BOUNDARY_NOTE


def test_every_case_includes_outcome_receipt_summary() -> None:
    payload = run_saas_permission_change_governed_demo()
    for case in payload["cases"]:  # type: ignore[index]
        summary = case["outcome_receipt_summary"]  # type: ignore[index]
        assert isinstance(summary, dict)
        assert summary["outcome_hash"]  # type: ignore[index]


def test_blocked_cases_mark_committed_false_and_blocked_true() -> None:
    payload = run_saas_permission_change_governed_demo()
    for case_id in [
        "missing_authority",
        "missing_human_approval",
        "expired_human_approval",
        "scope_mismatch",
    ]:
        summary = _case_by_id(payload, case_id)["outcome_receipt_summary"]
        assert summary["committed"] is False  # type: ignore[index]
        assert summary["blocked"] is True  # type: ignore[index]


def test_valid_case_has_committed_true_and_postcondition_passed() -> None:
    payload = run_saas_permission_change_governed_demo()
    summary = _case_by_id(payload, "valid_authority_and_approval")["outcome_receipt_summary"]
    assert summary["committed"] is True  # type: ignore[index]
    assert summary["postcondition_status"] == "passed"  # type: ignore[index]


def test_valid_case_observed_effects_include_local_offline_permission_grant_fixture() -> None:
    payload = run_saas_permission_change_governed_demo()
    summary = _case_by_id(payload, "valid_authority_and_approval")["outcome_receipt_summary"]
    effects = summary["observed_effects"]  # type: ignore[index]
    assert {
        "effect_type": "permission_grant",
        "permission": "saas:grant_admin",
        "target_resource": "contractor:external.user@example.test",
        "fixture_only": True,
    } in effects


def test_demo_has_no_network_or_environment_dependency() -> None:
    payload = run_saas_permission_change_governed_demo()
    assert payload["demo_id"] == "saas_permission_change_governed_execution_v1"
