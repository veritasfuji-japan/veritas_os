from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EN_TEMPLATE = ROOT / "docs/en/poc/one-day-poc-reviewer-handoff-template.md"
JA_TEMPLATE = ROOT / "docs/ja/poc/one-day-poc-reviewer-handoff-template.md"
EN_EVIDENCE_PACK = ROOT / "docs/en/poc/one-day-poc-evidence-pack.md"
JA_EVIDENCE_PACK = ROOT / "docs/ja/poc/one-day-poc-evidence-pack.md"
EN_OPERATOR_RUNBOOK = ROOT / "docs/en/poc/one-day-poc-operator-runbook.md"
JA_OPERATOR_RUNBOOK = ROOT / "docs/ja/poc/one-day-poc-operator-runbook.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_handoff_template_files_exist() -> None:
    assert EN_TEMPLATE.exists()
    assert JA_TEMPLATE.exists()


def test_en_handoff_template_contains_required_boundaries() -> None:
    content = _read(EN_TEMPLATE)
    required = [
        "reviewer-facing handoff template",
        "not a production SLA",
        "not third-party certified",
        "not a customer environment measurement unless explicitly stated",
        "does not certify EU AI Act compliance",
        "External LLM/provider latency and cost are not measured",
    ]
    for item in required:
        assert item in content


def test_ja_handoff_template_contains_required_boundaries() -> None:
    content = _read(JA_TEMPLATE)
    required = [
        "英語版が正本",
        "## 英語正本",
        "../../en/poc/one-day-poc-reviewer-handoff-template.md",
        "本番SLAではない",
        "第三者認証ではない",
        "顧客環境測定ではない",
        "EU AI Act準拠を認証するものではない",
    ]
    for item in required:
        assert item in content


def test_en_handoff_template_contains_key_sections() -> None:
    content = _read(EN_TEMPLATE)
    sections = [
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
    ]
    for section in sections:
        assert section in content


def test_en_handoff_template_links_to_existing_docs() -> None:
    content = _read(EN_TEMPLATE)
    links = [
        "one-day-poc-evidence-pack.md",
        "one-day-poc-operator-runbook.md",
        "one-day-poc-reviewer-pack.md",
        "one-day-poc-walkthrough.md",
        "one-day-poc-performance-report.md",
        "../benchmarks/local-performance-metrics.latest.md",
        "../benchmarks/performance-metrics.md",
    ]
    for link in links:
        assert link in content
        assert (EN_TEMPLATE.parent / link).resolve().exists()


def test_evidence_pack_and_operator_runbook_link_to_handoff_template() -> None:
    for path in [
        EN_EVIDENCE_PACK,
        JA_EVIDENCE_PACK,
        EN_OPERATOR_RUNBOOK,
        JA_OPERATOR_RUNBOOK,
    ]:
        assert "one-day-poc-reviewer-handoff-template.md" in _read(path)


def test_readme_and_index_links_present() -> None:
    assert "docs/en/poc/one-day-poc-reviewer-handoff-template.md" in _read(
        ROOT / "README.md"
    )
    readme_jp = _read(ROOT / "README_JP.md")
    assert "docs/ja/poc/one-day-poc-reviewer-handoff-template.md" in readme_jp
    assert "docs/en/poc/one-day-poc-reviewer-handoff-template.md" in readme_jp
    assert "one-day-poc-reviewer-handoff-template.md" in _read(ROOT / "docs/INDEX.md")
    assert "one-day-poc-reviewer-handoff-template.md" in _read(
        ROOT / "docs/DOCUMENTATION_MAP.md"
    )


def test_documentation_map_table_is_not_split() -> None:
    content = _read(ROOT / "docs/DOCUMENTATION_MAP.md")
    assert "\n\n| PoC: One-Day PoC reviewer handoff template |" not in content


def test_unsupported_claims_absent_from_handoff_templates() -> None:
    combined = f"{_read(EN_TEMPLATE)}\n{_read(JA_TEMPLATE)}".casefold()
    forbidden = [
        "guaranteed compliance",
        "certified EU AI Act compliant",
        "production SLA certified",
        "third-party certified benchmark",
        "customer environment verified",
        "cost per request measured",
    ]
    for claim in forbidden:
        assert claim.casefold() not in combined
