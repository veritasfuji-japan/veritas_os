"""Docs checks for reviewer entrypoint current enterprise review path."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = REPO_ROOT / "docs/REVIEWER_ENTRYPOINT.md"
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def _entrypoint_text() -> str:
    return ENTRYPOINT.read_text(encoding="utf-8")


def _markdown_link_targets() -> list[str]:
    return MARKDOWN_LINK_RE.findall(_entrypoint_text())


def _link_file_part(target: str) -> str:
    return target.split("#", 1)[0].split("?", 1)[0]


def test_reviewer_entrypoint_exists() -> None:
    assert ENTRYPOINT.exists()


def test_reviewer_entrypoint_markdown_links_are_relative_and_exist() -> None:
    targets = _markdown_link_targets()
    assert targets

    for target in targets:
        if target.startswith(("http://", "https://", "#", "/")):
            continue

        file_part = _link_file_part(target)
        if not file_part:
            continue

        assert not file_part.startswith("docs/"), (
            f"broken docs-relative link from docs/: {target}"
        )
        assert (ENTRYPOINT.parent / file_part).exists(), target


def test_reviewer_entrypoint_links_required_current_docs() -> None:
    targets = set(_markdown_link_targets())
    required_links = [
        "en/positioning/enterprise-value-brief.md",
        "en/validation/current-implementation-matrix.md",
        "en/poc/one-day-poc-reviewer-pack.md",
        "en/poc/one-day-poc-performance-report.md",
        "en/operations/provider-support-matrix.md",
        "en/operations/type-safety-baseline.md",
        "en/operations/maintainer-handoff.md",
    ]
    for link in required_links:
        assert link in targets


def test_reviewer_entrypoint_links_aml_kyc_use_case() -> None:
    targets = set(_markdown_link_targets())
    aml_kyc_path = "en/use-cases/aml-kyc-regulated-action-path.md"
    assert aml_kyc_path in targets
    assert (ENTRYPOINT.parent / aml_kyc_path).exists()


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
