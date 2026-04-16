# -*- coding: utf-8 -*-
"""Regression tests for the financial PoC pack documentation and fixtures."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from veritas_os.api.schemas import DecideResponse

POC_DOC_PATH = Path("docs/ja/guides/poc-pack-financial-quickstart.md")
POC_FIXTURE_PATH = Path("veritas_os/sample_data/governance/financial_poc_questions.json")


class ExpectedSemantics(BaseModel):
    """Expected decision semantics for one PoC question."""

    gate_decision: Literal[
        "proceed",
        "hold",
        "block",
        "human_review_required",
        "allow",
        "deny",
        "modify",
        "rejected",
        "abstain",
        "unknown",
    ]
    business_decision: Literal[
        "APPROVE",
        "DENY",
        "HOLD",
        "REVIEW_REQUIRED",
        "POLICY_DEFINITION_REQUIRED",
        "EVIDENCE_REQUIRED",
    ]
    next_action: str = Field(min_length=1)
    required_evidence: list[str] = Field(min_length=1)
    human_review_required: bool


class FinancialPocQuestion(BaseModel):
    """Canonical shape for financial PoC question samples."""

    question_id: str
    category: str
    question: str
    expected_semantics: ExpectedSemantics


def _load_poc_questions() -> list[FinancialPocQuestion]:
    """Load and validate PoC question fixtures."""
    raw_data = json.loads(POC_FIXTURE_PATH.read_text(encoding="utf-8"))
    return [FinancialPocQuestion.model_validate(item) for item in raw_data]


def _extract_markdown_links(content: str) -> list[str]:
    """Extract relative markdown links from a markdown document."""
    return re.findall(r"\[[^\]]+\]\(([^)]+)\)", content)


def test_financial_poc_quickstart_doc_exists_with_required_sections() -> None:
    """Quickstart doc should include required PoC pack sections."""
    content = POC_DOC_PATH.read_text(encoding="utf-8")

    required_sections = [
        "## 1日クイックスタート",
        "## expected decision semantics（期待セマンティクス）",
        "## 成功条件（PoC 合格ライン）",
        "## 失敗時の見方（デバッグ観点）",
        "## 監査 / ガバナンス製品としての見せ方",
        "## セキュリティ警告（PoC 実施時）",
    ]

    for marker in required_sections:
        assert marker in content


def test_financial_poc_questions_fixture_matches_expected_schema() -> None:
    """PoC sample questions must match expected decision semantics schema."""
    questions = _load_poc_questions()

    assert len(questions) >= 8
    assert all(item.question.strip() for item in questions)

    for item in questions:
        expected = item.expected_semantics
        payload = DecideResponse.model_validate(
            {
                "request_id": f"poc-{item.question_id}",
                "query": item.question,
                "gate_decision": expected.gate_decision,
                "business_decision": expected.business_decision,
                "next_action": expected.next_action,
                "required_evidence": expected.required_evidence,
                "human_review_required": expected.human_review_required,
                "rationale": "PoC semantics validation",
            }
        )

        assert payload.gate_decision == expected.gate_decision
        assert payload.business_decision == expected.business_decision


def test_financial_poc_doc_links_are_not_broken() -> None:
    """Relative links referenced by PoC quickstart doc should resolve."""
    content = POC_DOC_PATH.read_text(encoding="utf-8")
    links = _extract_markdown_links(content)

    relative_links = [
        link for link in links if not link.startswith(("http://", "https://", "#"))
    ]
    for link in relative_links:
        candidate = (POC_DOC_PATH.parent / link).resolve()
        assert candidate.exists(), f"Broken link: {link} -> {candidate}"


def test_financial_poc_sample_artifact_references_exist() -> None:
    """Sample artifacts referenced by the PoC doc should exist in the repository."""
    sample_paths = [
        Path("veritas_os/sample_data/governance/financial_poc_questions.json"),
        Path("veritas_os/sample_data/governance/financial_regulatory_templates.json"),
        Path("veritas_os/benchmarks/evidence/fixtures/financial_template_bundle_sample.json"),
    ]

    for path in sample_paths:
        assert path.exists(), f"Missing sample artifact: {path}"
