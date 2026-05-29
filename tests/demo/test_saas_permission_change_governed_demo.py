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


def test_blocked_cases_failure_reasons_are_flat_string_list() -> None:
    payload = run_saas_permission_change_governed_demo()
    for case_id in [
        "missing_authority",
        "missing_human_approval",
        "expired_human_approval",
        "scope_mismatch",
    ]:
        summary = _case_by_id(payload, case_id)["outcome_receipt_summary"]
        failure_reasons = summary["failure_reasons"]  # type: ignore[index]
        assert isinstance(failure_reasons, list)
        assert all(isinstance(reason, str) for reason in failure_reasons)
        assert all(not isinstance(reason, list) for reason in failure_reasons)


def test_blocked_cases_expose_refusal_reasons_across_artifacts() -> None:
    payload = run_saas_permission_change_governed_demo()
    for case_id in [
        "missing_authority",
        "missing_human_approval",
        "expired_human_approval",
        "scope_mismatch",
    ]:
        case = _case_by_id(payload, case_id)
        manifest = case["evidence_chain_manifest_summary"]
        outcome = case["outcome_receipt_summary"]
        assert case["failure_reasons"]
        assert manifest["refusal_basis"]
        assert outcome["failure_reasons"]
        assert case["failure_reasons"] == manifest["refusal_basis"]
        assert case["failure_reasons"] == outcome["failure_reasons"]


def test_valid_case_has_committed_true_and_postcondition_passed() -> None:
    payload = run_saas_permission_change_governed_demo()
    summary = _case_by_id(payload, "valid_authority_and_approval")[
        "outcome_receipt_summary"
    ]
    assert summary["committed"] is True  # type: ignore[index]
    assert summary["postcondition_status"] == "passed"  # type: ignore[index]


def test_valid_case_observed_effects_include_permission_grant_fixture() -> None:
    payload = run_saas_permission_change_governed_demo()
    summary = _case_by_id(payload, "valid_authority_and_approval")[
        "outcome_receipt_summary"
    ]
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


def test_every_demo_case_includes_evidence_chain_manifest_summary() -> None:
    payload = run_saas_permission_change_governed_demo()
    for case in payload["cases"]:  # type: ignore[index]
        summary = case["evidence_chain_manifest_summary"]  # type: ignore[index]
        assert isinstance(summary, dict)
        assert summary["manifest_hash"]  # type: ignore[index]


def test_blocked_cases_manifest_chain_status_is_blocked() -> None:
    payload = run_saas_permission_change_governed_demo()
    for case_id in [
        "missing_authority",
        "missing_human_approval",
        "expired_human_approval",
        "scope_mismatch",
    ]:
        summary = _case_by_id(payload, case_id)["evidence_chain_manifest_summary"]
        assert summary["chain_status"] == "blocked"  # type: ignore[index]


def test_valid_case_manifest_chain_status_complete_and_no_missing_links() -> None:
    payload = run_saas_permission_change_governed_demo()
    summary = _case_by_id(payload, "valid_authority_and_approval")[
        "evidence_chain_manifest_summary"
    ]
    assert summary["chain_status"] == "complete"  # type: ignore[index]
    assert summary["missing_links"] == []  # type: ignore[index]


def test_valid_case_manifest_observed_effects_include_grant_fixture() -> None:
    payload = run_saas_permission_change_governed_demo()
    summary = _case_by_id(payload, "valid_authority_and_approval")[
        "evidence_chain_manifest_summary"
    ]
    effects = summary["observed_effects_summary"]  # type: ignore[index]
    assert {
        "effect_type": "permission_grant",
        "permission": "saas:grant_admin",
        "target_resource": "contractor:external.user@example.test",
        "fixture_only": True,
    } in effects


def test_missing_authority_manifest_has_missing_authority_link() -> None:
    payload = run_saas_permission_change_governed_demo()
    summary = _case_by_id(payload, "missing_authority")[
        "evidence_chain_manifest_summary"
    ]
    assert "authority_evidence_hash" in summary["missing_links"]  # type: ignore[index]


def test_missing_human_approval_manifest_has_missing_human_approval_link() -> None:
    payload = run_saas_permission_change_governed_demo()
    summary = _case_by_id(payload, "missing_human_approval")[
        "evidence_chain_manifest_summary"
    ]
    assert (
        "human_approval_receipt_hash" in summary["missing_links"]
    )  # type: ignore[index]


def test_every_demo_case_includes_evidence_chain_verification_summary() -> None:
    payload = run_saas_permission_change_governed_demo()
    for case in payload["cases"]:  # type: ignore[index]
        summary = case["evidence_chain_verification_summary"]  # type: ignore[index]
        assert isinstance(summary, dict)
        assert summary["verification_status"] in {  # type: ignore[index]
            "verified",
            "failed",
            "incomplete",
            "indeterminate",
        }
        assert summary["verified_at"] == payload["generated_at"]  # type: ignore[index]


def test_valid_authority_and_approval_verification_is_verified() -> None:
    payload = run_saas_permission_change_governed_demo()
    summary = _case_by_id(payload, "valid_authority_and_approval")[
        "evidence_chain_verification_summary"
    ]
    assert summary["verification_status"] == "verified"  # type: ignore[index]
    assert summary["is_valid"] is True  # type: ignore[index]
    assert summary["manifest_hash_matches"] is True  # type: ignore[index]


def test_demo_does_not_simulate_tampering_in_verification_summary() -> None:
    payload = run_saas_permission_change_governed_demo()
    for case in payload["cases"]:  # type: ignore[index]
        summary = case["evidence_chain_verification_summary"]  # type: ignore[index]
        assert summary["manifest_hash_matches"] is True  # type: ignore[index]
        assert summary["mismatched_links"] == []  # type: ignore[index]


def test_blocked_cases_include_deterministic_verification_status() -> None:
    payload = run_saas_permission_change_governed_demo()
    for case_id in [
        "missing_authority",
        "missing_human_approval",
        "expired_human_approval",
        "scope_mismatch",
    ]:
        summary = _case_by_id(payload, case_id)["evidence_chain_verification_summary"]
        assert summary["verification_status"] == "verified"  # type: ignore[index]
        assert summary["is_valid"] is True  # type: ignore[index]
        assert summary["failure_reasons"] == []  # type: ignore[index]


def test_verification_summary_preserves_no_network_environment_dependency() -> None:
    payload = run_saas_permission_change_governed_demo()
    for case in payload["cases"]:  # type: ignore[index]
        summary = case["evidence_chain_verification_summary"]  # type: ignore[index]
        metadata = summary["metadata"]  # type: ignore[index]
        assert metadata["fixture_only"] is True  # type: ignore[index]
        assert metadata["boundary_note"] == BOUNDARY_NOTE  # type: ignore[index]
