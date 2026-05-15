"""Docs checks for the release evidence reviewer handoff template."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = REPO_ROOT / "docs/en/validation/release-evidence-reviewer-handoff-template.md"
JA_TEMPLATE = REPO_ROOT / "docs/ja/validation/release-evidence-reviewer-handoff-template.md"
INDEX_PATHS = [
    REPO_ROOT / "docs/INDEX.md",
    REPO_ROOT / "docs/DOCUMENTATION_MAP.md",
]
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
        "release-artifacts/release-evidence-checksums.sha256",
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


def _ja_template_text() -> str:
    return JA_TEMPLATE.read_text(encoding="utf-8")


def _markdown_link_targets_from_text(text: str) -> list[str]:
    return MARKDOWN_LINK_RE.findall(text)


def test_release_evidence_handoff_ja_explanation_exists() -> None:
    assert JA_TEMPLATE.exists()


def test_release_evidence_handoff_ja_explanation_has_required_content() -> None:
    text = _ja_template_text()
    for phrase in [
        "# リリース証跡レビュー引き渡しテンプレート",
        "docs/en/validation/release-evidence-reviewer-handoff-template.md",
        "docs/REVIEWER_ENTRYPOINT.md",
        "`deployment_ready`",
        "compose/live subreport",
        "未添付",
        "認証ではない",
        "顧客環境検証ではない",
        "make prepare-release-evidence-handoff",
        "release-artifacts/release-evidence-reviewer-handoff.md",
    ]:
        assert phrase in text


def test_release_evidence_handoff_ja_related_links_exist() -> None:
    targets = _markdown_link_targets_from_text(_ja_template_text())
    assert targets

    for target in targets:
        if target.startswith(("http://", "https://", "#", "/")):
            continue

        file_part = _link_file_part(target)
        if not file_part:
            continue

        assert (JA_TEMPLATE.parent / file_part).exists(), target


def test_release_evidence_handoff_templates_are_linked_from_public_indexes() -> None:
    docs_index = (REPO_ROOT / "docs/INDEX.md").read_text(encoding="utf-8")
    docs_map = (REPO_ROOT / "docs/DOCUMENTATION_MAP.md").read_text(
        encoding="utf-8"
    )

    assert "en/validation/release-evidence-reviewer-handoff-template.md" in docs_index
    assert "ja/validation/release-evidence-reviewer-handoff-template.md" in docs_index
    assert "docs/en/validation/release-evidence-reviewer-handoff-template.md" in docs_map
    assert "docs/ja/validation/release-evidence-reviewer-handoff-template.md" in docs_map


def test_release_evidence_handoff_ja_avoids_positive_overclaim_phrases() -> None:
    text = _ja_template_text()
    for phrase in [
        "完全準拠",
        "認証済み製品",
        "本番SLA保証",
        "24時間365日サポート保証",
        "本番準備完了を証明",
        "コンプライアンス保証",
        "法的保証",
        "規制承認済み",
    ]:
        assert phrase not in text


def test_release_evidence_handoff_ja_explanation_exposes_english_canonical() -> None:
    text = _ja_template_text()
    assert "## 英語正本" in text
    assert (
        "../../en/validation/release-evidence-reviewer-handoff-template.md" in text
    )
