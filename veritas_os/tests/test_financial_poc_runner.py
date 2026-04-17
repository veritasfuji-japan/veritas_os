# -*- coding: utf-8 -*-
"""Tests for financial PoC runner and EN quickstart documentation."""

from __future__ import annotations

import re
from pathlib import Path

from veritas_os.scripts.financial_poc_runner import (
    compare_expected_semantics,
    load_questions,
    run_financial_poc,
)

POC_FIXTURE_PATH = Path("veritas_os/sample_data/governance/financial_poc_questions.json")
EN_QUICKSTART_PATH = Path("docs/en/guides/poc-pack-financial-quickstart.md")
SUCCESS_CRITERIA_DOC_PATH = Path("docs/en/guides/financial-poc-success-criteria.md")


def _extract_markdown_links(content: str) -> list[str]:
    """Extract markdown links from document content."""
    return re.findall(r"\[[^\]]+\]\(([^)]+)\)", content)


def test_financial_poc_runner_loads_sample_fixture() -> None:
    """Runner should read the sample financial PoC question JSON fixture."""
    questions = load_questions(POC_FIXTURE_PATH)

    assert len(questions) >= 8
    assert all(question.question_id for question in questions)
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


def test_financial_poc_runner_dry_run_produces_quantified_summary() -> None:
    """Dry-run mode should produce deterministic pass/fail/warning summary."""
    report = run_financial_poc(
        input_path=POC_FIXTURE_PATH,
        dry_run=True,
        api_url="http://localhost:8000/v1/decide",
        api_key="",
        timeout_seconds=5.0,
    )

    summary = report["summary"]
    counts = summary["counts"]

    assert summary["total"] >= 8
    assert counts["pass"] == summary["total"]
    assert counts["fail"] == 0
    assert counts["warning"] == 0
    assert summary["pass_rate"] == 1.0


def test_en_quickstart_links_resolve_and_success_criteria_doc_exists() -> None:
    """EN quickstart should have valid relative links and success criteria doc."""
    content = EN_QUICKSTART_PATH.read_text(encoding="utf-8")
    links = _extract_markdown_links(content)

    relative_links = [
        link for link in links if not link.startswith(("http://", "https://", "#"))
    ]

    for link in relative_links:
        candidate = (EN_QUICKSTART_PATH.parent / link).resolve()
        assert candidate.exists(), f"Broken link: {link} -> {candidate}"

    assert SUCCESS_CRITERIA_DOC_PATH.exists()
