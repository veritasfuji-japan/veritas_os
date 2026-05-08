"""Docs checks for reviewer entrypoint current enterprise review path."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = REPO_ROOT / "docs/REVIEWER_ENTRYPOINT.md"


def _entrypoint_text() -> str:
    return ENTRYPOINT.read_text(encoding="utf-8")


def test_reviewer_entrypoint_exists() -> None:
    assert ENTRYPOINT.exists()


def test_reviewer_entrypoint_links_required_current_docs() -> None:
    text = _entrypoint_text()
    required_links = [
        "docs/en/positioning/enterprise-value-brief.md",
        "docs/en/validation/current-implementation-matrix.md",
        "docs/en/poc/one-day-poc-reviewer-pack.md",
        "docs/en/poc/one-day-poc-performance-report.md",
        "docs/en/operations/provider-support-matrix.md",
        "docs/en/operations/type-safety-baseline.md",
        "docs/en/operations/maintainer-handoff.md",
    ]
    for link in required_links:
        assert link in text


def test_reviewer_entrypoint_has_required_sections() -> None:
    text = _entrypoint_text()
    required_sections = [
        "## 10-minute review path",
        "## 30-minute technical review path",
        "## What to verify first",
        "## Current proof assets",
        "## Recommended validation commands",
        "## Current boundaries and non-claims",
        "## Provider and model boundary",
        "## Compliance positioning boundary",
        "## Technical appendix: Observe Mode foundation",
        "## Reviewer checklist",
        "## Open questions / limitations",
    ]
    for section in required_sections:
        assert section in text


def test_reviewer_entrypoint_has_required_non_claim_boundaries() -> None:
    text = _entrypoint_text()
    required_boundaries = [
        "Not legal advice",
        "Not regulatory approval",
        "Not third-party certification",
        "Not production SLA",
        "Not 24/7 support",
        "Not proof of provider-neutral production readiness",
        "Not full repository strict typing",
        "Not elimination of bus-factor risk",
    ]
    for boundary in required_boundaries:
        assert boundary in text


def test_reviewer_entrypoint_does_not_include_overclaim_phrases() -> None:
    text = _entrypoint_text().lower()
    banned_phrases = [
        "guaranteed compliance",
        "fully compliant",
        "certified product",
        "eu ai act compliant product",
        "production sla guaranteed",
        "24/7 support guaranteed",
        "provider-neutral production-ready",
        "fully eliminates bus-factor risk",
        "完全準拠",
        "認証済み製品",
        "本番sla保証",
        "24時間365日サポート保証",
        "バスファクターリスクを完全に解消",
    ]
    for phrase in banned_phrases:
        assert phrase not in text


def test_reviewer_entrypoint_keeps_observe_mode_appendix() -> None:
    text = _entrypoint_text()
    assert "observe_mode_proof_pack.md" in text
    assert "/dev/mission-fixture" in text
    assert "Observe Mode runtime is not enabled" in text
