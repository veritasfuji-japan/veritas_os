"""Docs checks for the release evidence reviewer handoff template."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = REPO_ROOT / "docs/en/validation/release-evidence-reviewer-handoff-template.md"
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def _template_text() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def _markdown_link_targets() -> list[str]:
    return MARKDOWN_LINK_RE.findall(_template_text())


def _link_file_part(target: str) -> str:
    return target.split("#", 1)[0].split("?", 1)[0]


def test_release_evidence_handoff_template_exists() -> None:
    assert TEMPLATE.exists()


def test_release_evidence_handoff_template_has_required_sections() -> None:
    text = _template_text()
    for section in [
        "## Purpose",
        "## Handoff summary",
        "## Release evidence scope",
        "## Environment and commit",
        "## Commands run",
        "## Evidence artifacts provided",
        "## Staged readiness interpretation",
        "## Compose and live provider subreports",
        "## Advisory findings review",
        "## Results summary",
        "## Known limitations",
        "## Non-claim boundaries",
        "## Open questions and follow-up",
        "## Reviewer acknowledgement",
        "## Related documents",
    ]:
        assert section in text


def test_release_evidence_handoff_template_has_required_commands() -> None:
    text = _template_text()
    for command in [
        "python scripts/quality/check_operational_docs_consistency.py",
        "pytest -q veritas_os/tests/test_operational_docs_certification_guard.py",
        "pytest -q veritas_os/tests/test_staged_readiness_report.py",
        "pytest -q veritas_os/tests/test_staged_readiness_make_targets.py",
        "make validate-staged-report",
        "make -n validate-staged-report-with-subreports",
    ]:
        assert command in text


def test_release_evidence_handoff_template_has_required_artifact_paths() -> None:
    text = _template_text()
    for artifact in [
        "release-artifacts/staged-readiness-report.json",
        "release-artifacts/staged-readiness-report.txt",
        "release-artifacts/compose-validation-report.json",
        "release-artifacts/live-provider-report.json",
    ]:
        assert artifact in text


def test_release_evidence_handoff_template_has_required_boundaries() -> None:
    text = _template_text().lower()
    for phrase in [
        "not production certification",
        "not third-party certification",
        "not customer-environment verification",
        "deployment_ready=true",
        "absent compose/live subreports are not evidence",
    ]:
        assert phrase in text


def test_release_evidence_handoff_template_related_links_exist() -> None:
    targets = _markdown_link_targets()
    assert targets

    for target in targets:
        if target.startswith(("http://", "https://", "#", "/")):
            continue

        file_part = _link_file_part(target)
        if not file_part:
            continue

        assert (TEMPLATE.parent / file_part).exists(), target


def test_release_evidence_handoff_template_avoids_positive_overclaim_phrases() -> None:
    text = _template_text().lower()
    for phrase in [
        "release certification",
        "full certification",
        "production certified",
        "certified for production",
        "compliance guaranteed",
        "guarantees compliance",
        "proves production readiness",
        "proves readiness",
        "certifies readiness",
        "certifies production readiness",
    ]:
        assert phrase not in text
