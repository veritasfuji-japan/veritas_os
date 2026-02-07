#!/usr/bin/env python3
"""
VERITAS OS プロジェクト価値試算スクリプト (Project Valuation Estimator)

複数の評価手法を用いてプロジェクトの推定価値を算出する。

評価手法:
  1. COCOMO II ベース開発コスト法 (再構築コスト)
  2. ファンクションポイント法 (機能量ベース)
  3. 市場比較法 (AI Safety/Governance SaaS 市場)
  4. 知的財産価値法 (IP/特許/学術出版)

Usage:
    python -m veritas_os.scripts.project_valuation
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Average fully-loaded software engineer cost (USD/year) – Japan senior level
ENGINEER_COST_USD_PER_YEAR = 130_000

# COCOMO II calibration parameters (Semi-Detached mode for novel domain)
COCOMO_A = 3.0
COCOMO_B = 1.12  # Exponent for effort (semi-detached, high complexity)
COCOMO_C = 2.5   # Schedule coefficient
COCOMO_D = 0.35  # Schedule exponent

# Productivity adjustment factors for VERITAS OS
# (Security-critical, novel AI domain, research-grade quality)
EFFORT_ADJUSTMENT_FACTOR = 1.30  # Above-average complexity

# USD/JPY exchange rate (approximate)
USD_JPY = 150.0

# Function point weights
FP_WEIGHTS = {
    "external_inputs": 4.5,    # API endpoints receiving data
    "external_outputs": 5.0,   # API responses, logs, reports
    "external_inquiries": 4.0, # Read-only queries
    "internal_files": 10.0,    # Logical data groups maintained
    "external_interfaces": 7.0, # External system connections
}

# Cost per function point (USD) – industry range $500-$1500 for complex systems
COST_PER_FP_USD = 1_000


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CodebaseMetrics:
    """Raw codebase measurements."""
    total_python_files: int = 0
    source_files: int = 0
    test_files: int = 0
    total_loc: int = 0
    source_loc: int = 0
    test_loc: int = 0
    doc_loc: int = 0
    config_loc: int = 0
    shell_loc: int = 0


@dataclass
class ValuationResult:
    """Single valuation method result."""
    method: str
    description: str
    value_usd: float
    value_jpy: float
    details: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Codebase analysis
# ---------------------------------------------------------------------------

def count_loc(base_dir: Path, pattern: str) -> int:
    """Count lines of code matching a pattern."""
    try:
        r = subprocess.run(
            ["find", str(base_dir), "-name", pattern, "-exec", "wc", "-l", "{}", "+"],
            capture_output=True, text=True, timeout=30,
        )
        for line in reversed(r.stdout.strip().split("\n")):
            if "total" in line:
                return int(line.strip().split()[0])
            parts = line.strip().split()
            if parts and parts[0].isdigit():
                return int(parts[0])
    except Exception:
        pass
    return 0


def count_files(base_dir: Path, pattern: str) -> int:
    """Count files matching a pattern."""
    try:
        r = subprocess.run(
            ["find", str(base_dir), "-name", pattern, "-type", "f"],
            capture_output=True, text=True, timeout=30,
        )
        return len([l for l in r.stdout.strip().split("\n") if l])
    except Exception:
        return 0


def gather_metrics(project_root: Path) -> CodebaseMetrics:
    """Gather codebase metrics from the filesystem."""
    src_dir = project_root / "veritas_os"
    m = CodebaseMetrics()
    m.total_python_files = count_files(src_dir, "*.py")
    m.test_files = count_files(src_dir, "test_*.py")
    m.source_files = m.total_python_files - m.test_files
    m.total_loc = count_loc(src_dir, "*.py")

    # Source LOC (non-test)
    try:
        r = subprocess.run(
            ["find", str(src_dir), "-name", "*.py", "-not", "-name", "test_*",
             "-exec", "wc", "-l", "{}", "+"],
            capture_output=True, text=True, timeout=30,
        )
        for line in reversed(r.stdout.strip().split("\n")):
            if "total" in line:
                m.source_loc = int(line.strip().split()[0])
                break
            parts = line.strip().split()
            if parts and parts[0].isdigit():
                m.source_loc = int(parts[0])
                break
    except Exception:
        m.source_loc = m.total_loc - (m.test_files * 200)

    m.test_loc = m.total_loc - m.source_loc
    m.doc_loc = count_loc(project_root, "*.md")
    m.config_loc = count_loc(project_root, "*.yaml") + count_loc(project_root, "*.yml")
    m.shell_loc = count_loc(project_root, "*.sh")
    return m


# ---------------------------------------------------------------------------
# Valuation Method 1: COCOMO II
# ---------------------------------------------------------------------------

def cocomo_valuation(metrics: CodebaseMetrics) -> ValuationResult:
    """
    COCOMO II ベースの再構築コスト法。

    SLOC (Source Lines of Code) からプロジェクトの再構築に必要な
    人月 (Person-Months) を推定し、開発コストを算出する。
    """
    kloc = metrics.source_loc / 1000.0

    # Basic COCOMO II effort (person-months)
    effort_pm = COCOMO_A * (kloc ** COCOMO_B) * EFFORT_ADJUSTMENT_FACTOR

    # Schedule (months)
    schedule_months = COCOMO_C * (effort_pm ** COCOMO_D)

    # Average team size
    avg_team = effort_pm / schedule_months if schedule_months > 0 else 1

    # Cost calculation
    cost_per_pm = ENGINEER_COST_USD_PER_YEAR / 12
    total_cost_usd = effort_pm * cost_per_pm

    # Add overhead: project management (15%), testing infrastructure (10%),
    # documentation (5%), DevOps/CI (5%)
    overhead_factor = 1.35
    total_with_overhead = total_cost_usd * overhead_factor

    return ValuationResult(
        method="COCOMO II 再構築コスト法",
        description=(
            "ソースコード量 (SLOC) から COCOMO II モデルで再構築に必要な"
            "工数・期間・コストを推定。セミデタッチドモード（新規ドメイン）で算出。"
        ),
        value_usd=total_with_overhead,
        value_jpy=total_with_overhead * USD_JPY,
        details={
            "source_kloc": round(kloc, 1),
            "effort_person_months": round(effort_pm, 1),
            "schedule_months": round(schedule_months, 1),
            "avg_team_size": round(avg_team, 1),
            "cost_per_person_month_usd": round(cost_per_pm),
            "base_cost_usd": round(total_cost_usd),
            "overhead_factor": overhead_factor,
            "total_with_overhead_usd": round(total_with_overhead),
        },
    )


# ---------------------------------------------------------------------------
# Valuation Method 2: Function Point Analysis
# ---------------------------------------------------------------------------

def function_point_valuation(metrics: CodebaseMetrics) -> ValuationResult:
    """
    ファンクションポイント法。

    VERITAS OS の機能を FPA (Function Point Analysis) で定量化し、
    業界標準のコスト/FP 単価で価値を算出する。
    """
    # Count functional components of VERITAS OS
    components = {
        "external_inputs": {
            # API endpoints receiving data
            "items": [
                "POST /v1/decide",
                "POST /v1/fuji/validate",
                "POST /v1/memory/put",
                "POST /v1/decide (with web_search)",
                "POST /v1/decide (with plan)",
                "Dashboard login",
            ],
            "count": 6,
        },
        "external_outputs": {
            "items": [
                "DecideResponse (full pipeline)",
                "FujiValidation response",
                "TrustLog entries",
                "Health check response",
                "Dashboard HTML/metrics",
                "Doctor report",
                "Benchmark results",
                "Coverage report",
                "Memory search results",
                "Alert notifications (Slack)",
            ],
            "count": 10,
        },
        "external_inquiries": {
            "items": [
                "GET /health",
                "GET /v1/memory/get",
                "GET /v1/logs/trust/{id}",
                "Memory search query",
                "TrustLog verification",
            ],
            "count": 5,
        },
        "internal_files": {
            "items": [
                "TrustLog (JSONL chain)",
                "Episodic memory store",
                "Semantic memory store",
                "World model state",
                "Value weights config",
                "FUJI policy config",
                "Vector index (embeddings)",
                "AGI goals state",
                "Curriculum state",
                "Experiment records",
                "Adaptation history",
            ],
            "count": 11,
        },
        "external_interfaces": {
            "items": [
                "OpenAI API (GPT-4)",
                "Anthropic API (Claude)",
                "Web search (DuckDuckGo/Google)",
                "GitHub API",
                "LLM Safety API",
                "Sentence-transformers (embeddings)",
                "Slack webhook",
                "PDF ingestion",
            ],
            "count": 8,
        },
    }

    # Calculate unadjusted function points
    ufp = 0
    for category, data in components.items():
        weight = FP_WEIGHTS[category]
        ufp += data["count"] * weight

    # Value Adjustment Factor (VAF) for complexity
    # GSC ratings (0-5 scale) for 14 general system characteristics
    gsc = {
        "data_communications": 4,      # REST API, webhooks
        "distributed_processing": 3,   # Docker, API-based
        "performance": 3,              # Latency-sensitive decisions
        "heavily_used_config": 4,      # Multiple deployment targets
        "transaction_rate": 2,         # Moderate throughput
        "online_data_entry": 3,        # API-driven input
        "end_user_efficiency": 3,      # CLI + Dashboard + API
        "online_update": 3,            # Memory/world state updates
        "complex_processing": 5,       # AI pipeline, hash chains, safety gates
        "reusability": 4,              # Modular design, FUJI as standalone
        "installation_ease": 3,        # Docker, pip
        "operational_ease": 3,         # Doctor, monitoring scripts
        "multiple_sites": 2,           # Cloud + local deployment
        "facilitate_change": 4,        # Plugin architecture, YAML policies
    }

    total_gsc = sum(gsc.values())
    vaf = 0.65 + (0.01 * total_gsc)

    # Adjusted function points
    afp = ufp * vaf

    # Cost
    total_cost_usd = afp * COST_PER_FP_USD

    return ValuationResult(
        method="ファンクションポイント法 (FPA)",
        description=(
            "プロジェクトの機能量を IFPUG 基準の FPA で定量化。"
            "外部入出力・照会・内部ファイル・外部インターフェースを計測し、"
            "業界標準のコスト/FP 単価で価値を算出。"
        ),
        value_usd=total_cost_usd,
        value_jpy=total_cost_usd * USD_JPY,
        details={
            "components": {k: v["count"] for k, v in components.items()},
            "unadjusted_fp": round(ufp, 1),
            "value_adjustment_factor": round(vaf, 2),
            "adjusted_fp": round(afp, 1),
            "cost_per_fp_usd": COST_PER_FP_USD,
            "total_cost_usd": round(total_cost_usd),
        },
    )


# ---------------------------------------------------------------------------
# Valuation Method 3: Market Comparable
# ---------------------------------------------------------------------------

def market_comparable_valuation(metrics: CodebaseMetrics) -> ValuationResult:
    """
    市場比較法 (Comparable Transaction Method)。

    AI Safety / Governance SaaS 市場の類似企業・取引事例から
    収益マルチプルを適用して推定価値を算出する。
    """
    # AI Safety/Governance market comparables (2024-2025)
    # Reference companies: Robust Intelligence, Credo AI, Arthur AI, Patronus AI
    # Typical early-stage AI safety startup valuations: $5M-$50M
    # Revenue multiples for AI SaaS: 10x-20x ARR

    # VERITAS OS potential revenue scenarios
    scenarios = {
        "conservative": {
            "description": "OSS コア + 有料サポート/SaaS モデル",
            "potential_customers": 20,
            "arr_per_customer_usd": 30_000,  # $30K/year per enterprise
            "revenue_multiple": 10,
        },
        "base": {
            "description": "AI ガバナンス SaaS (中堅〜大企業向け)",
            "potential_customers": 50,
            "arr_per_customer_usd": 60_000,  # $60K/year per enterprise
            "revenue_multiple": 15,
        },
        "optimistic": {
            "description": "AI Safety プラットフォーム (グローバル展開)",
            "potential_customers": 150,
            "arr_per_customer_usd": 100_000,  # $100K/year per enterprise
            "revenue_multiple": 20,
        },
    }

    results = {}
    for scenario_name, s in scenarios.items():
        arr = s["potential_customers"] * s["arr_per_customer_usd"]
        valuation = arr * s["revenue_multiple"]
        results[scenario_name] = {
            "description": s["description"],
            "potential_arr_usd": arr,
            "revenue_multiple": s["revenue_multiple"],
            "valuation_usd": valuation,
        }

    base_valuation = results["base"]["valuation_usd"]

    return ValuationResult(
        method="市場比較法 (Revenue Multiple)",
        description=(
            "AI Safety/Governance SaaS 市場の類似企業（Robust Intelligence, "
            "Credo AI, Arthur AI 等）の取引事例から収益マルチプルを適用。"
            "3つの収益シナリオ（保守的・基準・楽観的）で算出。"
        ),
        value_usd=base_valuation,
        value_jpy=base_valuation * USD_JPY,
        details={"scenarios": results},
    )


# ---------------------------------------------------------------------------
# Valuation Method 4: IP / Intangible Asset Value
# ---------------------------------------------------------------------------

def ip_valuation(metrics: CodebaseMetrics) -> ValuationResult:
    """
    知的財産・無形資産価値法。

    ソフトウェア特許、アルゴリズム、データ、ブランド、学術出版物など
    の無形資産価値を個別に評価し積み上げる。
    """
    ip_assets = {
        "core_algorithms": {
            "description": "FUJI Gate, Hash-Chain TrustLog, ValueCore アルゴリズム",
            "value_usd": 500_000,
            "rationale": "特許出願可能な独自アルゴリズム3件相当",
        },
        "decision_pipeline": {
            "description": "Options→Evidence→Critique→Debate→Plan→Value→FUJI 7段階パイプライン",
            "value_usd": 300_000,
            "rationale": "独自の意思決定フレームワーク設計",
        },
        "memory_system": {
            "description": "MemoryOS (エピソード記憶+意味記憶+ベクトル検索)",
            "value_usd": 200_000,
            "rationale": "LLMエージェント用の独自メモリアーキテクチャ",
        },
        "safety_policies": {
            "description": "FUJI ポリシー定義 (YAML) + リスクスコアリングモデル",
            "value_usd": 150_000,
            "rationale": "ドメイン知識を体系化した安全性ポリシー",
        },
        "academic_publication": {
            "description": "Zenodo DOI 登録済み学術出版物 (英語・日本語)",
            "value_usd": 100_000,
            "rationale": "学術的信頼性・引用可能性",
        },
        "test_suite": {
            "description": f"76件の包括的テストスイート ({metrics.test_loc:,} LOC)",
            "value_usd": 150_000,
            "rationale": "品質保証基盤・回帰テスト資産",
        },
        "documentation": {
            "description": f"バイリンガル文書 ({metrics.doc_loc:,} LOC), OpenAPI仕様",
            "value_usd": 100_000,
            "rationale": "日英両言語の技術文書・API仕様",
        },
        "devops_infrastructure": {
            "description": "Docker, GitHub Actions CI/CD, GHCR パブリッシュ",
            "value_usd": 80_000,
            "rationale": "本番運用可能なデプロイメント基盤",
        },
    }

    total_ip_value = sum(a["value_usd"] for a in ip_assets.values())

    return ValuationResult(
        method="知的財産・無形資産価値法",
        description=(
            "ソフトウェアの知的財産（アルゴリズム、設計、データ、"
            "ブランド、学術出版物）を個別に評価し積み上げる手法。"
        ),
        value_usd=total_ip_value,
        value_jpy=total_ip_value * USD_JPY,
        details={"ip_assets": ip_assets, "total_usd": total_ip_value},
    )


# ---------------------------------------------------------------------------
# Comprehensive valuation
# ---------------------------------------------------------------------------

def calculate_comprehensive_valuation(
    project_root: Path,
) -> dict[str, Any]:
    """Run all valuation methods and produce a comprehensive report."""
    metrics = gather_metrics(project_root)
    results = [
        cocomo_valuation(metrics),
        function_point_valuation(metrics),
        market_comparable_valuation(metrics),
        ip_valuation(metrics),
    ]

    values_usd = [r.value_usd for r in results]
    avg_usd = sum(values_usd) / len(values_usd)

    # Weighted average (development cost methods get more weight for early-stage)
    weights = [0.30, 0.25, 0.25, 0.20]  # COCOMO, FPA, Market, IP
    weighted_usd = sum(v * w for v, w in zip(values_usd, weights))

    return {
        "project": "VERITAS OS v2.0",
        "description": "Auditable Decision OS for LLM Agents",
        "valuation_date": "2026-02-07",
        "exchange_rate_usd_jpy": USD_JPY,
        "codebase_metrics": {
            "total_python_files": metrics.total_python_files,
            "source_files": metrics.source_files,
            "test_files": metrics.test_files,
            "total_loc": metrics.total_loc,
            "source_loc": metrics.source_loc,
            "test_loc": metrics.test_loc,
            "documentation_loc": metrics.doc_loc,
            "config_loc": metrics.config_loc,
        },
        "valuation_methods": [
            {
                "method": r.method,
                "description": r.description,
                "value_usd": round(r.value_usd),
                "value_jpy": round(r.value_jpy),
                "details": r.details,
            }
            for r in results
        ],
        "summary": {
            "simple_average_usd": round(avg_usd),
            "simple_average_jpy": round(avg_usd * USD_JPY),
            "weighted_average_usd": round(weighted_usd),
            "weighted_average_jpy": round(weighted_usd * USD_JPY),
            "valuation_range_usd": {
                "low": round(min(values_usd)),
                "high": round(max(values_usd)),
            },
            "valuation_range_jpy": {
                "low": round(min(values_usd) * USD_JPY),
                "high": round(max(values_usd) * USD_JPY),
            },
            "weights": dict(zip(
                ["COCOMO II", "FPA", "Market Comparable", "IP Value"],
                weights,
            )),
        },
    }


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def format_currency(value: float, currency: str = "USD") -> str:
    """Format a number as currency."""
    if currency == "JPY":
        if value >= 1_000_000_000:
            return f"¥{value / 100_000_000:,.1f}億"
        elif value >= 10_000_000:
            return f"¥{value / 10_000:,.0f}万"
        return f"¥{value:,.0f}"
    else:
        if value >= 1_000_000:
            return f"${value / 1_000_000:,.2f}M"
        elif value >= 1_000:
            return f"${value / 1_000:,.1f}K"
        return f"${value:,.0f}"


def print_report(report: dict[str, Any]) -> None:
    """Print a formatted valuation report."""
    sep = "=" * 72
    sep2 = "-" * 72

    print()
    print(sep)
    print(f"  VERITAS OS プロジェクト価値試算レポート")
    print(f"  Project Valuation Report")
    print(sep)
    print(f"  プロジェクト: {report['project']}")
    print(f"  概要: {report['description']}")
    print(f"  試算日: {report['valuation_date']}")
    print(f"  為替レート: 1 USD = {report['exchange_rate_usd_jpy']} JPY")
    print()

    # Codebase metrics
    m = report["codebase_metrics"]
    print(f"  【コードベース概要】")
    print(f"  ソースファイル数:     {m['source_files']:>6} files")
    print(f"  テストファイル数:     {m['test_files']:>6} files")
    print(f"  ソースコード行数:     {m['source_loc']:>6,} LOC")
    print(f"  テストコード行数:     {m['test_loc']:>6,} LOC")
    print(f"  ドキュメント行数:     {m['documentation_loc']:>6,} LOC")
    print(f"  テストカバレッジ比:   {m['test_loc'] / max(m['source_loc'], 1) * 100:>5.1f}%")
    print()
    print(sep2)

    # Individual methods
    for i, method in enumerate(report["valuation_methods"], 1):
        usd = method["value_usd"]
        jpy = method["value_jpy"]
        print(f"\n  【評価手法 {i}】{method['method']}")
        print(f"  {method['description']}")
        print()
        print(f"    推定価値: {format_currency(usd)} ({format_currency(jpy, 'JPY')})")

        # Method-specific details
        details = method["details"]
        if "source_kloc" in details:
            print(f"    ├─ ソース KLOC:      {details['source_kloc']}")
            print(f"    ├─ 推定工数:         {details['effort_person_months']} 人月")
            print(f"    ├─ 推定期間:         {details['schedule_months']} ヶ月")
            print(f"    ├─ 平均チーム規模:   {details['avg_team_size']} 名")
            print(f"    └─ オーバーヘッド率:  {details['overhead_factor']}x")
        elif "adjusted_fp" in details:
            print(f"    ├─ 未調整 FP:        {details['unadjusted_fp']}")
            print(f"    ├─ 調整係数 (VAF):   {details['value_adjustment_factor']}")
            print(f"    ├─ 調整済 FP:        {details['adjusted_fp']}")
            print(f"    └─ FP 単価:          ${details['cost_per_fp_usd']:,}/FP")
        elif "scenarios" in details:
            for sname, sdata in details["scenarios"].items():
                label = {"conservative": "保守的", "base": "基準", "optimistic": "楽観的"}
                print(f"    [{label.get(sname, sname)}] {sdata['description']}")
                print(f"      ARR: {format_currency(sdata['potential_arr_usd'])} "
                      f"× {sdata['revenue_multiple']}x = "
                      f"{format_currency(sdata['valuation_usd'])}")
        elif "ip_assets" in details:
            for name, asset in details["ip_assets"].items():
                print(f"    ├─ {asset['description']}")
                print(f"    │  {format_currency(asset['value_usd'])} - {asset['rationale']}")
        print()
        print(sep2)

    # Summary
    s = report["summary"]
    print()
    print(sep)
    print(f"  【総合評価サマリー】")
    print(sep)
    print()
    r = s["valuation_range_usd"]
    rj = s["valuation_range_jpy"]
    print(f"  評価レンジ:       {format_currency(r['low'])} 〜 {format_currency(r['high'])}")
    print(f"                    ({format_currency(rj['low'], 'JPY')} 〜 {format_currency(rj['high'], 'JPY')})")
    print()
    print(f"  単純平均:         {format_currency(s['simple_average_usd'])} ({format_currency(s['simple_average_jpy'], 'JPY')})")
    print()
    print(f"  加重平均:         {format_currency(s['weighted_average_usd'])} ({format_currency(s['weighted_average_jpy'], 'JPY')})")
    print(f"    重み付け:")
    for method_name, weight in s["weights"].items():
        print(f"      {method_name}: {weight:.0%}")
    print()
    print(sep)
    print(f"  ※ 本試算は参考値です。実際の企業価値は市場環境、経営チーム、")
    print(f"    顧客基盤、収益実績等により大きく変動します。")
    print(f"  ※ プレマネー評価であり、負債・運転資金は含みません。")
    print(sep)
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    project_root = Path(__file__).resolve().parents[2]
    report = calculate_comprehensive_valuation(project_root)

    # Print formatted report
    print_report(report)

    # Save JSON report
    output_path = project_root / "veritas_os" / "scripts" / "valuation_report.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"  JSON レポート出力: {output_path}")
    print()


if __name__ == "__main__":
    main()
