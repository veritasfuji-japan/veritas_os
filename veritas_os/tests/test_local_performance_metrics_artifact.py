"""Regression tests for the local performance metrics artifact."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JSON_PATH = ROOT / "docs/en/benchmarks/local-performance-metrics.latest.json"
EN_MD_PATH = ROOT / "docs/en/benchmarks/local-performance-metrics.latest.md"
JA_MD_PATH = ROOT / "docs/ja/benchmarks/local-performance-metrics.latest.md"


def _read_json() -> dict:
    return json.loads(JSON_PATH.read_text(encoding="utf-8"))


def test_artifact_files_exist() -> None:
    assert JSON_PATH.exists()
    assert EN_MD_PATH.exists()
    assert JA_MD_PATH.exists()


def test_json_schema_basics() -> None:
    data = _read_json()
    assert data["schema_version"] == "performance_metrics.v1"
    assert data["iterations"] == 100
    assert data["warmup"] == 10

    metrics = data["metrics"]
    for key in (
        "total_wall_ms",
        "mean_ms",
        "median_ms",
        "p95_ms",
        "p99_ms",
        "min_ms",
        "max_ms",
    ):
        assert key in metrics

    assert data["counters"]["success"] == 100
    assert data["counters"]["failure"] == 0


def test_json_notes_contain_non_claim_boundaries() -> None:
    notes = _read_json()["notes"]
    assert "Deterministic local benchmark only." in notes
    assert "No external LLM/API calls." in notes
    assert "Not a production SLA." in notes
    assert "Not third-party certified." in notes
    assert "Not a customer environment measurement." in notes


def test_json_is_not_sample_only() -> None:
    data = _read_json()
    assert data["generated_at"] != "sample-only"
    assert data["scenario"] != "local_deterministic_smoke_sample"
    assert "Sample only; not a measured result." not in "\n".join(data["notes"])


def test_metrics_sanity() -> None:
    metrics = _read_json()["metrics"]
    for value in metrics.values():
        assert isinstance(value, (int, float))
        assert value >= 0

    assert metrics["min_ms"] <= metrics["median_ms"] <= metrics["max_ms"]
    assert metrics["min_ms"] <= metrics["mean_ms"] <= metrics["max_ms"]
    assert metrics["min_ms"] <= metrics["p95_ms"] <= metrics["max_ms"]
    assert metrics["min_ms"] <= metrics["p99_ms"] <= metrics["max_ms"]
    assert metrics["p95_ms"] <= metrics["p99_ms"]


def test_en_markdown_contains_boundaries() -> None:
    text = EN_MD_PATH.read_text(encoding="utf-8").lower()
    assert "deterministic local measurement artifact" in text
    assert "does not measure production latency" in text
    assert "does not call external llm/api providers" in text
    assert "not a production sla" in text
    assert "not third-party certified" in text
    assert "not a customer environment measurement" in text


def test_ja_markdown_contains_boundaries() -> None:
    text = JA_MD_PATH.read_text(encoding="utf-8")
    assert "英語版が正本" in text
    assert "本番レイテンシではない" in text
    assert "外部LLM/API" in text
    assert "本番SLAではない" in text
    assert "第三者認証ではない" in text
    assert "顧客環境" in text
    assert "## 英語正本" in text
    assert "../../en/benchmarks/local-performance-metrics.latest.md" in text
    assert "../../en/benchmarks/local-performance-metrics.latest.json" in text



def test_ja_performance_metrics_doc_links_to_en_canonical() -> None:
    text = (ROOT / "docs/ja/benchmarks/performance-metrics.md").read_text(encoding="utf-8")
    assert "## 英語正本" in text
    assert "../../en/benchmarks/performance-metrics.md" in text


def test_readme_and_docs_links_exist() -> None:
    readme_en = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_ja = (ROOT / "README_JP.md").read_text(encoding="utf-8")
    docs_index = (ROOT / "docs/INDEX.md").read_text(encoding="utf-8")
    docs_map = (ROOT / "docs/DOCUMENTATION_MAP.md").read_text(encoding="utf-8")

    assert "local-performance-metrics.latest.md" in readme_en
    assert "local-performance-metrics.latest.json" in readme_en
    assert "docs/ja/benchmarks/local-performance-metrics.latest.md" in readme_ja
    assert "docs/en/benchmarks/local-performance-metrics.latest.md" in readme_ja
    assert "docs/en/benchmarks/local-performance-metrics.latest.json" in readme_ja
    assert "local-performance-metrics.latest.md" in docs_index
    assert "local-performance-metrics.latest.md" in docs_map


def test_forbidden_claims_are_absent() -> None:
    data = _read_json()
    text = "\n".join(
        [
            json.dumps(data, ensure_ascii=False),
            EN_MD_PATH.read_text(encoding="utf-8"),
            JA_MD_PATH.read_text(encoding="utf-8"),
        ]
    ).lower()

    forbidden_terms = (
        "guaranteed",
        "production sla certified",
        "third-party certified benchmark",
        "customer measured",
        "customer environment verified",
        "cost per request measured",
    )
    for term in forbidden_terms:
        assert term not in text
