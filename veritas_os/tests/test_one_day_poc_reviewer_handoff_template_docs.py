from pathlib import Path


def test_one_day_poc_reviewer_handoff_template_docs() -> None:
    repo_root = Path(__file__).resolve().parents[2]

    en_path = repo_root / "docs/en/poc/one-day-poc-reviewer-handoff-template.md"
    ja_path = repo_root / "docs/ja/poc/one-day-poc-reviewer-handoff-template.md"
    assert en_path.exists()
    assert ja_path.exists()

    en_text = en_path.read_text(encoding="utf-8")
    ja_text = ja_path.read_text(encoding="utf-8")

    for boundary in [
        "reviewer-facing handoff template",
        "not a production SLA",
        "not third-party certified",
        "not a customer environment measurement unless explicitly stated",
        "does not certify EU AI Act compliance",
        "External LLM/provider latency and cost are not measured",
    ]:
        assert boundary in en_text

    for boundary in [
        "英語版が正本",
        "## 英語正本",
        "../../en/poc/one-day-poc-reviewer-handoff-template.md",
        "本番SLAではない",
        "第三者認証ではない",
        "顧客環境測定ではない",
        "EU AI Act準拠を認証するものではない",
    ]:
        assert boundary in ja_text

    for section in [
        "## Purpose",
        "## Handoff summary",
        "## PoC scope",
        "## Environment and commit",
        "## Scenarios reviewed",
        "## Evidence provided",
        "## Results summary",
        "## Known limitations",
        "## Non-claim boundaries",
        "## Open questions and follow-up",
        "## Reviewer acknowledgement",
        "## Related documents",
    ]:
        assert section in en_text

    linked_tokens = [
        "one-day-poc-evidence-pack.md",
        "one-day-poc-operator-runbook.md",
        "one-day-poc-reviewer-pack.md",
        "one-day-poc-walkthrough.md",
        "one-day-poc-performance-report.md",
        "../benchmarks/local-performance-metrics.latest.md",
        "../benchmarks/performance-metrics.md",
    ]
    for token in linked_tokens:
        assert token in en_text

    for link in [
        "one-day-poc-evidence-pack.md",
        "one-day-poc-operator-runbook.md",
        "one-day-poc-reviewer-pack.md",
        "one-day-poc-walkthrough.md",
        "one-day-poc-performance-report.md",
        "../benchmarks/local-performance-metrics.latest.md",
        "../benchmarks/performance-metrics.md",
    ]:
        assert (en_path.parent / link).resolve().exists()

    for path in [
        repo_root / "docs/en/poc/one-day-poc-evidence-pack.md",
        repo_root / "docs/ja/poc/one-day-poc-evidence-pack.md",
        repo_root / "docs/en/poc/one-day-poc-operator-runbook.md",
        repo_root / "docs/ja/poc/one-day-poc-operator-runbook.md",
    ]:
        assert "one-day-poc-reviewer-handoff-template.md" in path.read_text(
            encoding="utf-8"
        )

    assert (
        "docs/en/poc/one-day-poc-reviewer-handoff-template.md"
        in (repo_root / "README.md").read_text(encoding="utf-8")
    )
    readme_jp = (repo_root / "README_JP.md").read_text(encoding="utf-8")
    assert "docs/ja/poc/one-day-poc-reviewer-handoff-template.md" in readme_jp
    assert "docs/en/poc/one-day-poc-reviewer-handoff-template.md" in readme_jp
    assert "one-day-poc-reviewer-handoff-template.md" in (
        repo_root / "docs/INDEX.md"
    ).read_text(encoding="utf-8")
    doc_map = (repo_root / "docs/DOCUMENTATION_MAP.md").read_text(encoding="utf-8")
    assert "one-day-poc-reviewer-handoff-template.md" in doc_map
    assert "\n\n| PoC: One-Day PoC reviewer handoff template |" not in doc_map

    combined = f"{en_text}\n{ja_text}".casefold()
    for forbidden in [
        "guaranteed compliance",
        "certified eu ai act compliant",
        "production sla certified",
        "third-party certified benchmark",
        "customer environment verified",
        "cost per request measured",
    ]:
        assert forbidden not in combined
