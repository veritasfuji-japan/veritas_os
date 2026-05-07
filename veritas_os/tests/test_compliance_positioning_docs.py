from pathlib import Path


def test_compliance_positioning_disclaimers_present() -> None:
    required = {
        "README.md": "not legal certification",
        "docs/eu_ai_act/technical_documentation.md": "法的助言",
        "docs/en/poc/one-day-poc-reviewer-pack.md": "Not legal certification.",
        "docs/ja/poc/one-day-poc-reviewer-pack.md": "法的認証ではありません。",
    }
    for file_path, expected in required.items():
        text = Path(file_path).read_text(encoding="utf-8")
        assert expected in text


def test_overstated_claims_absent_in_target_docs() -> None:
    targets = [
        "README.md",
        "docs/eu_ai_act/technical_documentation.md",
        "docs/en/poc/one-day-poc-reviewer-pack.md",
        "docs/ja/poc/one-day-poc-reviewer-pack.md",
        "docs/en/poc/one-day-poc-performance-report.md",
        "docs/ja/poc/one-day-poc-performance-report.md",
    ]
    banned = [
        "guarantees EU AI Act compliance",
        "is EU AI Act compliant",
        "fully compliant with the EU AI Act",
        "EU AI Act準拠製品",
        "法的認証済み",
    ]
    for file_path in targets:
        text = Path(file_path).read_text(encoding="utf-8")
        for phrase in banned:
            assert phrase not in text
