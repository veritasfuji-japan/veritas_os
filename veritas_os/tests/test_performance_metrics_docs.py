"""Documentation checks for performance metrics harness artifacts."""

from __future__ import annotations

import json
from pathlib import Path


def test_docs_exist() -> None:
    assert Path("docs/en/benchmarks/performance-metrics.md").exists()
    assert Path("docs/ja/benchmarks/performance-metrics.md").exists()


def test_en_doc_required_strings() -> None:
    content = Path("docs/en/benchmarks/performance-metrics.md").read_text(encoding="utf-8")
    for needle in [
        "deterministic local harness",
        "does not call external LLM providers",
        "does not claim production SLA",
        "not third-party certified",
        "JSON output schema",
    ]:
        assert needle in content


def test_ja_doc_required_strings() -> None:
    content = Path("docs/ja/benchmarks/performance-metrics.md").read_text(encoding="utf-8")
    for needle in ["英語版が正本", "外部LLM", "本番SLAではない", "第三者認証"]:
        assert needle in content


def test_sample_json() -> None:
    path = Path("docs/en/benchmarks/sample-performance-metrics.json")
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "performance_metrics.v1"
    notes = "\n".join(payload["notes"])
    assert "Sample only; not a measured result." in notes


def test_link_surfaces() -> None:
    targets = [
        "README.md",
        "README_JP.md",
        "docs/INDEX.md",
        "docs/DOCUMENTATION_MAP.md",
    ]
    for target in targets:
        content = Path(target).read_text(encoding="utf-8")
        assert "performance-metrics.md" in content
