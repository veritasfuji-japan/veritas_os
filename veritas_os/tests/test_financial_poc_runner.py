# -*- coding: utf-8 -*-
"""Tests for financial PoC runner and EN quickstart documentation."""

from __future__ import annotations

import json
import re
from pathlib import Path

from veritas_os.scripts.financial_poc_runner import (
    compare_expected_semantics,
    load_questions,
    run_financial_poc,
)
from veritas_os.scripts.expected_semantics_compare import summarize_semantic_mismatches

POC_FIXTURE_PATH = Path("veritas_os/sample_data/governance/financial_poc_questions.json")
AML_KYC_PILOT_FIXTURE_PATH = Path(
    "veritas_os/sample_data/governance/aml_kyc_pilot_cases.json"
)
FAILURE_SCENARIO_PATH = Path(
    "veritas_os/sample_data/governance/aml_kyc_failure_scenarios.json"
)
BUNDLE_EXAMPLE_PATH = Path(
    "veritas_os/sample_data/governance/aml_kyc_expected_evidence_bundle_examples.json"
)
EN_QUICKSTART_PATH = Path("docs/en/guides/poc-pack-financial-quickstart.md")
SUCCESS_CRITERIA_DOC_PATH = Path("docs/en/guides/financial-poc-success-criteria.md")
PILOT_CHECKLIST_PATH = Path("docs/en/guides/aml-kyc-pilot-checklist.md")
RUNBOOK_PATH = Path("docs/en/guides/aml-kyc-operator-runbook.md")
HANDOFF_PATH = Path("docs/en/guides/aml-kyc-customer-handoff-path.md")


def _extract_markdown_links(content: str) -> list[str]:
    """Extract markdown links from document content."""
    return re.findall(r"\[[^\]]+\]\(([^)]+)\)", content)


def test_financial_poc_runner_loads_sample_fixture() -> None:
    """Runner should read the sample financial PoC question JSON fixture."""
    questions = load_questions(POC_FIXTURE_PATH)

    assert len(questions) >= 11
    assert all(question.question_id for question in questions)
    assert all(question.expected_semantics for question in questions)


def test_aml_kyc_pilot_fixture_is_runner_compatible() -> None:
    """AML/KYC pilot fixture should stay compatible with runner question model."""
    questions = load_questions(AML_KYC_PILOT_FIXTURE_PATH)

    assert len(questions) >= 6
    assert all(question.category == "aml_kyc" for question in questions)
    assert all(question.expected_semantics for question in questions)


def test_compare_expected_semantics_reports_field_level_diff() -> None:
    """Expected semantics comparator should return a machine-readable mismatch diff."""
    expected = {
        "gate_decision": "hold",
        "business_decision": "EVIDENCE_REQUIRED",
        "next_action": "COLLECT_REQUIRED_EVIDENCE",
        "required_evidence": ["evidence_a"],
        "missing_evidence": ["evidence_a"],
        "human_review_required": False,
    }
    actual = {
        "gate_decision": "proceed",
        "business_decision": "APPROVE",
        "next_action": "DO_NOT_EXECUTE",
        "required_evidence": [],
        "missing_evidence": [],
        "human_review_required": True,
    }

    diff = compare_expected_semantics(expected, actual)

    assert diff["gate_decision"]["expected"] == "hold"
    assert diff["gate_decision"]["actual"] == "proceed"
    assert diff["business_decision"]["expected"] == "EVIDENCE_REQUIRED"
    assert diff["business_decision"]["actual"] == "APPROVE"
    assert diff["next_action"]["expected"] == "COLLECT_REQUIRED_EVIDENCE"
    assert diff["next_action"]["actual"] == "DO_NOT_EXECUTE"
    assert diff["required_evidence"]["expected"] == ["evidence_a"]
    assert diff["required_evidence"]["actual"] == []
    assert diff["missing_evidence"]["expected"] == ["evidence_a"]
    assert diff["missing_evidence"]["actual"] == []
    assert diff["human_review_required"]["expected"] is False
    assert diff["human_review_required"]["actual"] is True


def test_compare_expected_semantics_accepts_same_next_action_family() -> None:
    """Next action mismatch is ignored when actions are in the same family."""
    expected = {"next_action": "PREPARE_HUMAN_REVIEW_PACKET"}
    actual = {"next_action": "ROUTE_TO_HUMAN_REVIEW"}

    diff = compare_expected_semantics(expected, actual)

    assert "next_action" not in diff


def test_compare_expected_semantics_canonicalizes_gate_aliases() -> None:
    """Comparator should treat legacy aliases and canonical gate values as equal."""
    expected = {"gate_decision": "deny"}
    actual = {"gate_decision": "block"}
    diff = compare_expected_semantics(expected, actual)
    assert "gate_decision" not in diff


def test_compare_expected_semantics_canonicalizes_business_aliases() -> None:
    """Comparator should treat business decision aliases as canonical equivalents."""
    expected = {"business_decision": "allow"}
    actual = {"business_decision": "APPROVE"}
    diff = compare_expected_semantics(expected, actual)
    assert "business_decision" not in diff


def test_mismatch_summary_is_readable() -> None:
    """Mismatch summary helper should produce concise field-first output."""
    summary = summarize_semantic_mismatches(
        {
            "gate_decision": {"expected": "hold", "actual": "proceed"},
            "human_review_required": {"expected": True, "actual": False},
        }
    )
    assert "gate_decision[hold→proceed]" in summary
    assert "human_review_required[True→False]" in summary


def test_financial_poc_runner_dry_run_produces_quantified_summary() -> None:
    """Dry-run mode should produce deterministic pass/fail/warning summary."""
    report = run_financial_poc(
        input_path=POC_FIXTURE_PATH,
        dry_run=True,
        api_url="http://localhost:8000/v1/decide",
        api_key="",
        timeout_seconds=5.0,
        required_evidence_mode="warn",
    )

    summary = report["summary"]
    counts = summary["counts"]

    assert summary["total"] >= 11
    assert summary["evaluated"] == summary["total"]
    assert counts["pass"] == summary["total"]
    assert counts["fail"] == 0
    assert counts["warning"] == 0
    assert summary["pass_rate"] == 1.0
    assert summary["warning_rate"] == 0.0
    assert summary["outcome"] == "pass"
    assert report["mismatch_overview"] == []


def test_compare_expected_semantics_exposes_evidence_runtime_warnings() -> None:
    """Comparator should highlight unknown/profile miss telemetry from runtime."""
    expected = {"required_evidence": ["kyc_profile"]}
    actual = {
        "required_evidence": ["kyc_profile"],
        "required_evidence_telemetry": {
            "top_unknown_keys": ["unknown_custom_doc"],
            "profile_missing_keys": ["approval_matrix"],
        },
    }

    diff = compare_expected_semantics(expected, actual)

    assert "required_evidence_runtime_warnings" in diff
    warning_payload = diff["required_evidence_runtime_warnings"]["actual"]
    assert warning_payload["unknown_keys"] == ["unknown_custom_doc"]
    assert warning_payload["profile_missing_keys"] == ["approval_matrix"]


def test_en_quickstart_and_pilot_docs_links_resolve() -> None:
    """Quickstart and pilot companion docs should resolve all relative links."""
    for path in [
        EN_QUICKSTART_PATH,
        SUCCESS_CRITERIA_DOC_PATH,
        PILOT_CHECKLIST_PATH,
        RUNBOOK_PATH,
        HANDOFF_PATH,
    ]:
        content = path.read_text(encoding="utf-8")
        links = _extract_markdown_links(content)
        relative_links = [
            link for link in links if not link.startswith(("http://", "https://", "#"))
        ]
        for link in relative_links:
            link_path = link.split("#", 1)[0]
            candidate = (path.parent / link_path).resolve()
            assert candidate.exists(), f"Broken link: {link} -> {candidate}"


def test_success_criteria_docs_cover_representative_cases() -> None:
    """Docs should explicitly describe required representative scenario contracts."""
    quickstart = EN_QUICKSTART_PATH.read_text(encoding="utf-8")
    criteria = SUCCESS_CRITERIA_DOC_PATH.read_text(encoding="utf-8")
    expected_markers = [
        "sanctions partial match",
        "source of funds missing",
        "policy definition missing",
        "sufficient evidence low-risk",
        "secure/prod controls missing",
    ]
    for marker in expected_markers:
        assert marker in quickstart
        assert marker in criteria


def test_failure_scenarios_are_bounded_to_implemented_behavior() -> None:
    """Failure scenario fixture must explicitly declare bounded implementation scope."""
    payload = json.loads(FAILURE_SCENARIO_PATH.read_text(encoding="utf-8"))

    assert len(payload) >= 5
    assert all(item["bounded_to_implemented_behavior"] is True for item in payload)


def test_expected_bundle_examples_are_structurally_complete() -> None:
    """Evidence bundle example fixture should include mandatory acceptance checks."""
    payload = json.loads(BUNDLE_EXAMPLE_PATH.read_text(encoding="utf-8"))
    examples = payload["bundle_examples"]

    assert payload["scope"] == "synthetic_only"
    assert len(examples) >= 3
    for example in examples:
        assert "manifest.json" in example["expected_files"]
        assert "acceptance_checklist.json" in example["expected_files"]
        assert "verification_report_present" in example["required_acceptance_checks"]
