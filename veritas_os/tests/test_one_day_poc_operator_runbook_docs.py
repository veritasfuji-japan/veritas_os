"""Documentation guardrails for the One-Day PoC operator runbook."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EN_RUNBOOK = ROOT / "docs/en/poc/one-day-poc-operator-runbook.md"
JA_RUNBOOK = ROOT / "docs/ja/poc/one-day-poc-operator-runbook.md"
EN_EVIDENCE_PACK = ROOT / "docs/en/poc/one-day-poc-evidence-pack.md"
JA_EVIDENCE_PACK = ROOT / "docs/ja/poc/one-day-poc-evidence-pack.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_runbook_files_exist() -> None:
    assert EN_RUNBOOK.exists()
    assert JA_RUNBOOK.exists()


def test_en_runbook_contains_required_boundaries() -> None:
    content = _read(EN_RUNBOOK)
    required = [
        "operator-facing runbook",
        "not a production deployment guide",
        "not a production SLA",
        "not third-party certified",
        "not a customer environment measurement",
        "does not certify EU AI Act compliance",
        "External LLM/provider latency and cost are not measured",
    ]
    for item in required:
        assert item in content


def test_ja_runbook_contains_required_boundaries() -> None:
    content = _read(JA_RUNBOOK)
    required = [
        "英語版が正本",
        "## 英語正本",
        "../../en/poc/one-day-poc-operator-runbook.md",
        "本番デプロイ手順ではない",
        "本番SLAではない",
        "第三者認証ではない",
        "顧客環境測定ではない",
        "EU AI Act準拠を認証するものではない",
    ]
    for item in required:
        assert item in content


def test_en_runbook_contains_key_sections() -> None:
    content = _read(EN_RUNBOOK)
    sections = [
        "## Purpose",
        "## Operator responsibilities",
        "## Pre-flight checklist",
        "## Recommended evidence folder layout",
        "## Run sequence",
        "## Evidence collection checklist",
        "## What to record for each run",
        "## Review handoff package",
        "## Common failure modes",
        "## Non-claim boundaries",
        "## Related documents",
    ]
    for section in sections:
        assert section in content


def test_en_runbook_links_to_existing_docs() -> None:
    content = _read(EN_RUNBOOK)
    links = [
        "one-day-poc-evidence-pack.md",
        "one-day-poc-reviewer-pack.md",
        "one-day-poc-walkthrough.md",
        "one-day-poc-performance-report.md",
        "../benchmarks/local-performance-metrics.latest.md",
        "../benchmarks/performance-metrics.md",
    ]
    pack_path = EN_RUNBOOK
    for link in links:
        assert link in content
        assert (pack_path.parent / link).resolve().exists()


def test_evidence_pack_links_back_to_operator_runbook() -> None:
    assert "one-day-poc-operator-runbook.md" in _read(EN_EVIDENCE_PACK)
    assert "one-day-poc-operator-runbook.md" in _read(JA_EVIDENCE_PACK)


def test_readme_and_index_links_present() -> None:
    assert "docs/en/poc/one-day-poc-operator-runbook.md" in _read(ROOT / "README.md")
    ja_readme = _read(ROOT / "README_JP.md")
    assert "docs/ja/poc/one-day-poc-operator-runbook.md" in ja_readme
    assert "docs/en/poc/one-day-poc-operator-runbook.md" in ja_readme
    assert "one-day-poc-operator-runbook.md" in _read(ROOT / "docs/INDEX.md")
    assert "one-day-poc-operator-runbook.md" in _read(
        ROOT / "docs/DOCUMENTATION_MAP.md"
    )


def test_documentation_map_table_is_not_split() -> None:
    content = _read(ROOT / "docs/DOCUMENTATION_MAP.md")
    assert "\n\n| PoC: One-Day PoC operator runbook |" not in content


def test_unsupported_claims_absent_from_runbooks() -> None:
    combined = f"{_read(EN_RUNBOOK)}\n{_read(JA_RUNBOOK)}".casefold()
    forbidden = [
        "guaranteed compliance",
        "certified eu ai act compliant",
        "production sla certified",
        "third-party certified benchmark",
        "customer environment verified",
        "cost per request measured",
    ]
    for claim in forbidden:
        assert claim not in combined
