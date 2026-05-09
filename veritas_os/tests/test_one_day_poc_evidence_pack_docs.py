"""Documentation checks for One-Day PoC evidence pack docs."""

from __future__ import annotations

from pathlib import Path


def test_evidence_pack_files_exist() -> None:
    assert Path("docs/en/poc/one-day-poc-evidence-pack.md").exists()
    assert Path("docs/ja/poc/one-day-poc-evidence-pack.md").exists()


def test_en_evidence_pack_boundaries() -> None:
    content = Path("docs/en/poc/one-day-poc-evidence-pack.md").read_text(encoding="utf-8")
    for needle in [
        "reviewer-facing evidence pack",
        "not a production SLA",
        "not third-party certified",
        "not a customer environment measurement",
        "does not certify EU AI Act compliance",
        "External LLM/provider latency and cost are not measured",
    ]:
        assert needle in content


def test_ja_evidence_pack_boundaries() -> None:
    content = Path("docs/ja/poc/one-day-poc-evidence-pack.md").read_text(encoding="utf-8")
    for needle in [
        "英語版が正本",
        "## 英語正本",
        "../../en/poc/one-day-poc-evidence-pack.md",
        "本番SLAではない",
        "第三者認証ではない",
        "顧客環境測定ではない",
        "EU AI Act準拠を認証するものではない",
    ]:
        assert needle in content


def test_en_evidence_pack_sections() -> None:
    content = Path("docs/en/poc/one-day-poc-evidence-pack.md").read_text(encoding="utf-8")
    for needle in [
        "## Purpose",
        "## What this PoC demonstrates",
        "## What this PoC does not prove",
        "## Evidence checklist",
        "## Suggested walkthrough scenarios",
        "## Success criteria",
        "## Failure criteria",
        "## Artifacts to collect",
        "## Related documents",
    ]:
        assert needle in content


def test_en_evidence_pack_links() -> None:
    pack_path = Path("docs/en/poc/one-day-poc-evidence-pack.md")
    content = pack_path.read_text(encoding="utf-8")
    expected_links = [
        "../benchmarks/local-performance-metrics.latest.md",
        "../benchmarks/local-performance-metrics.latest.json",
        "../benchmarks/performance-metrics.md",
        "one-day-poc-performance-report.md",
    ]
    for link in expected_links:
        assert link in content
        assert (pack_path.parent / link).resolve().exists()


def test_link_surfaces_updated() -> None:
    checks = {
        "README.md": ["docs/en/poc/one-day-poc-evidence-pack.md"],
        "README_JP.md": [
            "docs/ja/poc/one-day-poc-evidence-pack.md",
            "docs/en/poc/one-day-poc-evidence-pack.md",
        ],
        "docs/INDEX.md": ["one-day-poc-evidence-pack.md"],
        "docs/DOCUMENTATION_MAP.md": ["one-day-poc-evidence-pack.md"],
    }
    for path, needles in checks.items():
        content = Path(path).read_text(encoding="utf-8")
        for needle in needles:
            assert needle in content


def test_performance_report_related_links() -> None:
    en_content = Path("docs/en/poc/one-day-poc-performance-report.md").read_text(
        encoding="utf-8"
    )
    ja_content = Path("docs/ja/poc/one-day-poc-performance-report.md").read_text(
        encoding="utf-8"
    )
    assert "Related evidence pack" in en_content
    assert "one-day-poc-evidence-pack.md" in en_content
    assert "関連する証跡パック" in ja_content
    assert "one-day-poc-evidence-pack.md" in ja_content


def test_forbidden_claims_absent() -> None:
    combined = "\n".join(
        [
            Path("docs/en/poc/one-day-poc-evidence-pack.md").read_text(encoding="utf-8"),
            Path("docs/ja/poc/one-day-poc-evidence-pack.md").read_text(encoding="utf-8"),
        ]
    ).casefold()
    for needle in [
        "guaranteed compliance",
        "certified EU AI Act compliant",
        "production SLA certified",
        "third-party certified benchmark",
        "customer environment verified",
        "cost per request measured",
    ]:
        assert needle.casefold() not in combined


def test_documentation_map_table_not_split() -> None:
    content = Path("docs/DOCUMENTATION_MAP.md").read_text(encoding="utf-8")
    assert "| EN notes |" in content
    assert "| PoC: One-Day PoC evidence pack |" in content
    assert "\n\n| PoC: One-Day PoC evidence pack |" not in content
