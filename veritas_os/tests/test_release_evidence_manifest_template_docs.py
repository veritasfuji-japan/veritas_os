"""Docs checks for the release evidence manifest template."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EN_TEMPLATE = REPO_ROOT / "docs/en/validation/release-evidence-manifest-template.md"
JA_TEMPLATE = REPO_ROOT / "docs/ja/validation/release-evidence-manifest-template.md"
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def _link_file_part(target: str) -> str:
    return target.split("#", 1)[0].split("?", 1)[0]


def _check_relative_links_exist(base: Path, text: str) -> None:
    for target in MARKDOWN_LINK_RE.findall(text):
        if target.startswith(("http://", "https://", "#", "/")):
            continue
        file_part = _link_file_part(target)
        if file_part:
            assert (base.parent / file_part).exists(), target


def test_release_evidence_manifest_templates_exist() -> None:
    assert EN_TEMPLATE.exists()
    assert JA_TEMPLATE.exists()


def test_release_evidence_manifest_en_has_required_sections_and_content() -> None:
    text = EN_TEMPLATE.read_text(encoding="utf-8")
    for section in [
        "## Purpose",
        "## Package summary",
        "## Expected artifacts",
        "## Presence checklist",
        "## Staged readiness files",
        "## Compose and live provider files",
        "## Reviewer handoff file",
        "## Command log and CI references",
        "## Missing or intentionally absent artifacts",
        "## Redaction notes",
        "## Non-claim boundaries",
        "## Related documents",
    ]:
        assert section in text

    for artifact in [
        "release-artifacts/release-evidence-manifest.md",
        "release-artifacts/release-evidence-reviewer-handoff.md",
        "release-artifacts/release-evidence-checksums.sha256",
        "release-artifacts/staged-readiness-report.json",
        "release-artifacts/staged-readiness-report.txt",
        "release-artifacts/compose-validation-report.json",
        "release-artifacts/live-provider-report.json",
    ]:
        assert artifact in text

    for command in [
        "make prepare-release-evidence-manifest",
        "make prepare-release-evidence-handoff",
        "make prepare-release-evidence-checksums",
        "make prepare-release-evidence-package",
        "make validate-staged-report",
        "make -n validate-staged-report-with-subreports",
    ]:
        assert command in text


def test_release_evidence_manifest_boundary_phrases_and_banned_phrases() -> None:
    text = EN_TEMPLATE.read_text(encoding="utf-8").lower()
    for phrase in [
        "not production certification",
        "not third-party certification",
        "not third-party attestation",
        "not tamper-proof storage",
        "not customer-environment verification",
        "deployment_ready=true",
        "absent compose/live artifacts",
    ]:
        assert phrase in text

    for phrase in [
        "release certification",
        "full certification",
        "production certified",
        "certified for production",
        "compliance guaranteed",
        "guarantees compliance",
        "proves production readiness",
        "certifies readiness",
    ]:
        assert phrase not in text


def test_release_evidence_manifest_ja_required_content_and_banned_phrases() -> None:
    text = JA_TEMPLATE.read_text(encoding="utf-8")
    for phrase in [
        "# リリース証跡マニフェストテンプレート",
        "## 英語正本",
        "make prepare-release-evidence-manifest",
        "release-artifacts/release-evidence-manifest.md",
        "make prepare-release-evidence-handoff",
        "make prepare-release-evidence-checksums",
        "make prepare-release-evidence-package",
        "release-artifacts/release-evidence-reviewer-handoff.md",
        "release-artifacts/release-evidence-checksums.sha256",
        "本番認証ではない",
        "第三者認証ではない",
        "第三者証明ではない",
        "改ざん不能保管ではない",
        "顧客環境検証ではない",
    ]:
        assert phrase in text

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


def test_release_evidence_manifest_related_links_and_public_indexes() -> None:
    en_text = EN_TEMPLATE.read_text(encoding="utf-8")
    ja_text = JA_TEMPLATE.read_text(encoding="utf-8")
    _check_relative_links_exist(EN_TEMPLATE, en_text)
    _check_relative_links_exist(JA_TEMPLATE, ja_text)

    docs_index = (REPO_ROOT / "docs/INDEX.md").read_text(encoding="utf-8")
    docs_map = (REPO_ROOT / "docs/DOCUMENTATION_MAP.md").read_text(encoding="utf-8")
    assert "en/validation/release-evidence-manifest-template.md" in docs_index
    assert "ja/validation/release-evidence-manifest-template.md" in docs_index
    assert "docs/en/validation/release-evidence-manifest-template.md" in docs_map
    assert "docs/ja/validation/release-evidence-manifest-template.md" in docs_map
