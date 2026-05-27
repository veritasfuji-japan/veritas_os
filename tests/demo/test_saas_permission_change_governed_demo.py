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
