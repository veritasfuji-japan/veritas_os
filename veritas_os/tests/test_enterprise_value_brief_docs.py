"""Docs checks for enterprise value brief positioning boundaries."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EN_BRIEF = REPO_ROOT / "docs/en/positioning/enterprise-value-brief.md"
JA_BRIEF = REPO_ROOT / "docs/ja/positioning/enterprise-value-brief.md"


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_enterprise_value_brief_docs_exist() -> None:
    assert EN_BRIEF.exists()
    assert JA_BRIEF.exists()


def test_links_exist_in_readme_index_and_map() -> None:
    assert "docs/en/positioning/enterprise-value-brief.md" in _read("README.md")
    assert "enterprise-value-brief.md" in _read("docs/INDEX.md")
    assert "enterprise-value-brief.md" in _read("docs/DOCUMENTATION_MAP.md")


def test_required_sections_exist_in_en_brief() -> None:
    text = EN_BRIEF.read_text(encoding="utf-8")
    required_phrases = [
        "One-sentence value",
        "Who this is for",
        "The problem",
        "What VERITAS does",
        "What evidence VERITAS produces",
        "What can be verified in one day",
        "Current boundaries and non-claims",
        "Best-fit first use cases",
        "Next step",
    ]
    for phrase in required_phrases:
        assert phrase in text


def test_non_claim_boundaries_exist() -> None:
    en_text = EN_BRIEF.read_text(encoding="utf-8")
    ja_text = JA_BRIEF.read_text(encoding="utf-8")

    en_required = [
        "Not legal advice",
        "Not regulatory approval",
        "Not third-party certification",
        "Not production SLA",
        "Not 24/7 support",
        "Not proof of provider-neutral production readiness",
    ]
    ja_required = [
        "法的助言ではありません",
        "規制当局の承認ではありません",
        "第三者認証ではありません",
        "本番SLAではありません",
        "24/7サポートではありません",
    ]
    for phrase in en_required:
        assert phrase in en_text
    for phrase in ja_required:
        assert phrase in ja_text


def test_no_overclaim_expressions() -> None:
    combined = f"{EN_BRIEF.read_text(encoding='utf-8')}\n{JA_BRIEF.read_text(encoding='utf-8')}"
    combined_lower = combined.lower()
    banned_case_insensitive = [
        "guaranteed compliance",
        "fully compliant",
        "certified product",
        "eu ai act compliant product",
        "production sla guaranteed",
        "24/7 support guaranteed",
        "provider-neutral production-ready",
        "fully eliminates bus-factor risk",
    ]
    banned_ja_case_insensitive = [
        "完全準拠",
        "認証済み製品",
        "本番sla保証",
        "24時間365日サポート保証",
        "バスファクターリスクを完全に解消",
    ]

    for phrase in banned_case_insensitive:
        assert phrase not in combined_lower

    # Use lowercased combined text so mixed Japanese/Latin phrases such as
    # "本番SLA保証" are caught consistently.
    for phrase in banned_ja_case_insensitive:
        assert phrase.lower() not in combined_lower
