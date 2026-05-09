"""Boundary checks for One-Day PoC benchmark claims and docs guidance."""

from __future__ import annotations

from pathlib import Path

import scripts.demo.one_day_poc_benchmark as bench

REQUIRED_LIMITATIONS = (
    "Local benchmark only; not a production SLA.",
    "Not a customer environment measurement.",
    "Not third-party certified.",
    "Does not measure external LLM/provider latency unless the configured local "
    "server explicitly invokes such providers.",
    "This benchmark does not certify EU AI Act compliance.",
)


def _sample_row() -> dict[str, float | int]:
    return {
        "success_count": 1,
        "failure_count": 0,
        "min_ms": 1.0,
        "p50_ms": 1.0,
        "p95_ms": 1.0,
        "p99_ms": 1.0,
        "max_ms": 1.0,
        "mean_ms": 1.0,
        "stdev_ms": 0.0,
    }


def _sample_packet() -> dict[str, object]:
    return {
        "measured_at": "sample",
        "runs": 1,
        "warmup": 0,
        "environment": {
            "python_version": "3.12",
            "platform": "test",
            "base_url": "redacted-local-or-configured",
        },
        "benchmarks": {
            "observability_capabilities": _sample_row(),
            "governance_policy_read": _sample_row(),
            "smoke_equivalent_end_to_end": _sample_row(),
        },
    }


def test_benchmark_limitations_constant_contains_required_boundaries() -> None:
    assert isinstance(bench.BENCHMARK_LIMITATIONS, list)
    assert len(bench.BENCHMARK_LIMITATIONS) >= 6
    for needle in REQUIRED_LIMITATIONS:
        assert needle in bench.BENCHMARK_LIMITATIONS


def test_benchmark_markdown_limitations_include_required_boundaries() -> None:
    markdown = bench._build_markdown(_sample_packet())
    for limitation in bench.BENCHMARK_LIMITATIONS:
        assert f"- {limitation}" in markdown


def test_packet_limitations_wiring_uses_benchmark_limitations_constant() -> None:
    source = Path("scripts/demo/one_day_poc_benchmark.py").read_text(encoding="utf-8")
    assert '"limitations": list(BENCHMARK_LIMITATIONS)' in source


def test_en_poc_doc_boundaries() -> None:
    content = Path("docs/en/poc/one-day-poc-performance-report.md").read_text(
        encoding="utf-8"
    )
    for needle in [
        "local HTTP PoC benchmark",
        "VERITAS_API_KEY",
        "not a production latency benchmark",
        "not a production SLA",
        "not third-party certified",
        "not a customer environment measurement",
        "local-performance-metrics.latest.md",
    ]:
        assert needle in content


def test_ja_poc_doc_boundaries() -> None:
    content = Path("docs/ja/poc/one-day-poc-performance-report.md").read_text(
        encoding="utf-8"
    )
    for needle in [
        "## 英語正本",
        "../../en/poc/one-day-poc-performance-report.md",
        "VERITAS_API_KEY",
        "本番レイテンシ",
        "本番SLAではない",
        "第三者認証ではない",
        "顧客環境測定ではない",
        "local-performance-metrics.latest.md",
    ]:
        assert needle in content
    assert "local HTTP PoC benchmark" in content or "local HTTP" in content


def test_en_performance_metrics_relationship_note() -> None:
    content = Path("docs/en/benchmarks/performance-metrics.md").read_text(
        encoding="utf-8"
    )
    for needle in [
        "Relationship to One-Day PoC benchmark",
        "scripts/demo/one_day_poc_benchmark.py",
        "VERITAS_API_KEY",
        "not a production SLA",
    ]:
        assert needle in content


def test_ja_performance_metrics_relationship_note() -> None:
    content = Path("docs/ja/benchmarks/performance-metrics.md").read_text(
        encoding="utf-8"
    )
    for needle in [
        "One-Day PoC benchmarkとの違い",
        "scripts/demo/one_day_poc_benchmark.py",
        "VERITAS_API_KEY",
        "本番SLA",
    ]:
        assert needle in content


def test_readme_non_claim_warning() -> None:
    en_content = Path("README.md").read_text(encoding="utf-8")
    ja_content = Path("README_JP.md").read_text(encoding="utf-8")
    assert "not a production SLA" in en_content or "not production SLA" in en_content
    assert "customer environment" in en_content
    assert "本番SLA" in ja_content
    assert "顧客環境測定" in ja_content
