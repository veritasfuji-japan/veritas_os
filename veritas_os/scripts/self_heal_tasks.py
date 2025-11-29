#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VERITAS Self-Heal Task Generator

ベンチマーク結果 + doctor_report → 具体的なコード変更タスク を生成

使用方法:
    python self_heal_tasks.py --bench latest
    python self_heal_tasks.py --bench agi_veritas_self_hosting_20250130.json
    python self_heal_tasks.py --all-recent  # 最近の全ベンチ
"""

import sys
import json
import argparse
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ===== パス設定 =====

SCRIPT_DIR = Path(__file__).resolve().parent
LOGS_DIR = SCRIPT_DIR / "logs"
BENCH_DIR = LOGS_DIR / "benchmarks"
DOCTOR_REPORT_PATH = LOGS_DIR / "doctor_report.json"
WORLD_STATE_PATH = LOGS_DIR / "world_state.json"
TASKS_OUTPUT_DIR = LOGS_DIR / "self_heal_tasks"

TASKS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ===== ユーティリティ =====

def load_json_file(path: Path, default: Any = None) -> Any:
    """JSONファイルを安全にロード"""
    if not path.exists():
        logger.debug(f"File not found: {path}")
        return default or {}
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load {path}: {e}")
        return default or {}


def find_latest_bench() -> Optional[Path]:
    """最新のベンチマーク結果を取得"""
    if not BENCH_DIR.exists():
        return None
    
    files = sorted(BENCH_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
    
    if not files:
        return None
    
    return files[-1]


def find_recent_benches(hours: int = 24) -> List[Path]:
    """最近N時間以内のベンチマーク結果を取得"""
    if not BENCH_DIR.exists():
        return []
    
    cutoff = datetime.now() - timedelta(hours=hours)
    recent = []
    
    for path in BENCH_DIR.glob("*.json"):
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        if mtime >= cutoff:
            recent.append(path)
    
    return sorted(recent, key=lambda p: p.stat().st_mtime)


# ===== ベンチ結果の正規化 =====

def normalize_bench_result(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    ベンチマーク結果を正規化
    
    入力形式:
    - run_benchmarks_improved.py 出力
    - 旧 bench.py 出力
    
    出力:
    {
        "bench_id": str,
        "changes": List[Dict],
        "tests": List[Dict],
        "world_snapshot": Dict,
        "bench_summary": Dict,
    }
    """
    if not isinstance(raw, dict):
        return {"changes": [], "tests": []}
    
    # すでに正規化済み
    if "changes" in raw or "tests" in raw:
        return raw
    
    bench_id = raw.get("bench_id", "unknown")
    response = raw.get("response_json") or raw.get("response") or {}
    extras = response.get("extras", {})
    
    # Planner steps → changes
    planner_data = extras.get("planner", {})
    steps = planner_data.get("steps", [])
    
    changes: List[Dict[str, Any]] = []
    
    for idx, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            continue
        
        step_id = step.get("id", f"step{idx}")
        title = step.get("title", f"Step {idx}")
        objective = step.get("objective", "")
        tasks = step.get("tasks", [])
        artifacts = step.get("artifacts", [])
        metrics = step.get("metrics", [])
        risks = step.get("risks", [])
        done_criteria = step.get("done_criteria", [])
        
        # target_path推定
        target_path = artifacts[0] if artifacts else None
        
        # target_module推定
        if target_path:
            if ".md" in target_path:
                target_module = "docs"
            elif ".py" in target_path:
                # パスから推定
                if "core/" in target_path:
                    target_module = "core"
                elif "api/" in target_path:
                    target_module = "api"
                elif "scripts/" in target_path:
                    target_module = "scripts"
                else:
                    target_module = "core"
            else:
                target_module = "unknown"
        else:
            target_module = "docs"
        
        # リスク評価
        risk_level = "medium"
        if risks:
            risk_text = " ".join(str(r) for r in risks).lower()
            if any(kw in risk_text for kw in ["暴走", "破損", "危険", "重大"]):
                risk_level = "high"
            elif any(kw in risk_text for kw in ["軽微", "低い"]):
                risk_level = "low"
        
        # impact評価
        impact_level = "medium"
        if "設計" in title or "アーキテクチャ" in title or "ループ" in title:
            impact_level = "high"
        elif "修正" in title or "改善" in title:
            impact_level = "medium"
        
        changes.append({
            "id": step_id,
            "title": title,
            "description": objective,
            "target_module": target_module,
            "target_path": target_path,
            "risk": risk_level,
            "impact": impact_level,
            "reason": f"{bench_id} planner step",
            "suggested_functions": [],
            "tasks": tasks,
            "artifacts": artifacts,
            "metrics": metrics,
            "risks": risks,
            "done_criteria": done_criteria,
        })
    
    # World snapshot
    veritas_agi = extras.get("veritas_agi", {})
    world_snapshot = veritas_agi.get("snapshot", {})
    
    # Bench summary
    bench_summary = {
        "status_code": raw.get("status_code"),
        "elapsed_sec": raw.get("elapsed_sec"),
        "decision_status": response.get("decision_status"),
        "telos_score": response.get("telos_score"),
        "fuji_status": (response.get("fuji", {}) or {}).get("status"),
        "run_at": raw.get("run_at"),
    }
    
    return {
        "bench_id": bench_id,
        "changes": changes,
        "tests": [],
        "world_snapshot": world_snapshot,
        "bench_summary": bench_summary,
    }


# ===== doctor_report連携 =====

def extract_doctor_issues(doctor_report: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    doctor_reportから改善が必要な項目を抽出
    
    Returns:
        List of {
            "id": str,
            "title": str,
            "description": str,
            "severity": "high" | "medium" | "low",
            "target_module": str,
        }
    """
    issues = []
    
    if not isinstance(doctor_report, dict):
        return issues
    
    # issues セクション
    report_issues = doctor_report.get("issues", [])
    
    for idx, issue in enumerate(report_issues, start=1):
        if not isinstance(issue, dict):
            continue
        
        issues.append({
            "id": f"doctor_issue_{idx}",
            "title": issue.get("title", f"Issue {idx}"),
            "description": issue.get("description", ""),
            "severity": issue.get("severity", "medium"),
            "target_module": issue.get("module", "core"),
        })
    
    # メトリクス異常
    metrics = doctor_report.get("metrics", {})
    
    if isinstance(metrics, dict):
        # latency異常
        latency = metrics.get("avg_latency_ms")
        if isinstance(latency, (int, float)) and latency > 5000:
            issues.append({
                "id": "doctor_perf_latency",
                "title": "高レイテンシの改善",
                "description": f"平均レイテンシが {latency}ms と高い",
                "severity": "medium",
                "target_module": "core",
            })
        
        # エラー率
        error_rate = metrics.get("error_rate")
        if isinstance(error_rate, (int, float)) and error_rate > 0.05:
            issues.append({
                "id": "doctor_error_rate",
                "title": "エラー率の改善",
                "description": f"エラー率が {error_rate:.1%} と高い",
                "severity": "high",
                "target_module": "core",
            })
    
    return issues


# ===== タスク生成 =====

def generate_self_heal_tasks(
    bench_results: List[Dict[str, Any]],
    doctor_report: Dict[str, Any],
    world_state: Dict[str, Any],
) -> Dict[str, Any]:
    """
    ベンチ結果 + doctor_report → 統合タスクリスト
    
    Returns:
    {
        "meta": {...},
        "tasks": [
            {
                "id": str,
                "type": "code_change" | "test" | "self_heal" | "doc",
                "priority": int (1-5, 1=highest),
                "title": str,
                "description": str,
                "target_module": str,
                "target_path": str or None,
                "risk": str,
                "impact": str,
                "source": "bench:{bench_id}" | "doctor",
                "tasks": List[str],
                "artifacts": List[str],
                "done_criteria": List[str],
            }
        ],
        "summary": {...},
    }
    """
    all_tasks = []
    task_id_counter = 1
    
    # ベンチマークからのタスク
    for bench in bench_results:
        bench_id = bench.get("bench_id", "unknown")
        changes = bench.get("changes", [])
        
        for change in changes:
            task = {
                "id": f"task_{task_id_counter:03d}",
                "type": _infer_task_type(change),
                "priority": _calc_priority(change),
                "title": change.get("title", ""),
                "description": change.get("description", ""),
                "target_module": change.get("target_module", ""),
                "target_path": change.get("target_path"),
                "risk": change.get("risk", "medium"),
                "impact": change.get("impact", "medium"),
                "source": f"bench:{bench_id}",
                "tasks": change.get("tasks", []),
                "artifacts": change.get("artifacts", []),
                "done_criteria": change.get("done_criteria", []),
                "metrics": change.get("metrics", []),
            }
            
            all_tasks.append(task)
            task_id_counter += 1
    
    # doctor_reportからのタスク
    doctor_issues = extract_doctor_issues(doctor_report)
    
    for issue in doctor_issues:
        task = {
            "id": f"task_{task_id_counter:03d}",
            "type": "self_heal",
            "priority": _severity_to_priority(issue.get("severity", "medium")),
            "title": issue.get("title", ""),
            "description": issue.get("description", ""),
            "target_module": issue.get("target_module", "core"),
            "target_path": None,
            "risk": "low",
            "impact": "medium",
            "source": "doctor",
            "tasks": [],
            "artifacts": [],
            "done_criteria": [],
        }
        
        all_tasks.append(task)
        task_id_counter += 1
    
    # 優先度順にソート
    all_tasks.sort(key=lambda t: (t["priority"], t["id"]))
    
    # サマリ
    summary = {
        "total_tasks": len(all_tasks),
        "by_type": {},
        "by_priority": {},
        "high_risk_count": sum(1 for t in all_tasks if t["risk"] == "high"),
        "high_impact_count": sum(1 for t in all_tasks if t["impact"] == "high"),
    }
    
    for task in all_tasks:
        task_type = task["type"]
        priority = task["priority"]
        
        summary["by_type"][task_type] = summary["by_type"].get(task_type, 0) + 1
        summary["by_priority"][priority] = summary["by_priority"].get(priority, 0) + 1
    
    # メタデータ
    meta = {
        "generated_at": datetime.now().isoformat(),
        "bench_count": len(bench_results),
        "doctor_issues_count": len(doctor_issues),
        "world_progress": world_state.get("veritas", {}).get("progress", 0.0),
        "world_decision_count": world_state.get("veritas", {}).get("decision_count", 0),
    }
    
    return {
        "meta": meta,
        "tasks": all_tasks,
        "summary": summary,
        "world_state": world_state.get("veritas", {}),
    }


def _infer_task_type(change: Dict[str, Any]) -> str:
    """タスクタイプを推定"""
    target_path = change.get("target_path", "")
    
    if not target_path:
        return "doc"
    
    if ".md" in target_path:
        return "doc"
    elif ".py" in target_path:
        if "test" in target_path.lower():
            return "test"
        else:
            return "code_change"
    else:
        return "code_change"


def _calc_priority(change: Dict[str, Any]) -> int:
    """優先度を計算（1=highest, 5=lowest）"""
    risk = change.get("risk", "medium")
    impact = change.get("impact", "medium")
    
    # リスク・インパクトマトリクス
    if risk == "high":
        if impact == "high":
            return 1  # Critical
        elif impact == "medium":
            return 2  # High
        else:
            return 3  # Medium
    elif risk == "medium":
        if impact == "high":
            return 2  # High
        elif impact == "medium":
            return 3  # Medium
        else:
            return 4  # Low
    else:  # risk == "low"
        if impact == "high":
            return 3  # Medium
        elif impact == "medium":
            return 4  # Low
        else:
            return 5  # Very Low
    
    return 3  # Default


def _severity_to_priority(severity: str) -> int:
    """Doctor severityをpriorityに変換"""
    mapping = {
        "critical": 1,
        "high": 2,
        "medium": 3,
        "low": 4,
    }
    return mapping.get(severity.lower(), 3)


# ===== メイン =====

def main():
    parser = argparse.ArgumentParser(
        description="Generate self-heal tasks from benchmarks and doctor_report"
    )
    
    parser.add_argument(
        "--bench",
        type=str,
        help="Specific benchmark result (e.g., 'latest' or filename)",
    )
    parser.add_argument(
        "--all-recent",
        action="store_true",
        help="Use all benchmarks from last 24 hours",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output path (default: auto-generated in logs/self_heal_tasks/)",
    )
    parser.add_argument(
        "--format",
        choices=["json", "markdown"],
        default="json",
        help="Output format (default: json)",
    )
    
    args = parser.parse_args()
    
    # ベンチマーク結果をロード
    bench_results = []
    
    if args.all_recent:
        bench_files = find_recent_benches(hours=24)
        logger.info(f"Found {len(bench_files)} recent benchmark(s)")
        
        for path in bench_files:
            raw = load_json_file(path)
            if raw:
                normalized = normalize_bench_result(raw)
                bench_results.append(normalized)
    
    elif args.bench:
        if args.bench == "latest":
            bench_file = find_latest_bench()
            if not bench_file:
                logger.error("No benchmark results found")
                return 1
        else:
            bench_file = BENCH_DIR / args.bench
            if not bench_file.exists():
                logger.error(f"Benchmark file not found: {bench_file}")
                return 1
        
        logger.info(f"Loading benchmark: {bench_file.name}")
        raw = load_json_file(bench_file)
        if raw:
            normalized = normalize_bench_result(raw)
            bench_results.append(normalized)
    
    else:
        # デフォルト: latest
        bench_file = find_latest_bench()
        if bench_file:
            logger.info(f"Using latest benchmark: {bench_file.name}")
            raw = load_json_file(bench_file)
            if raw:
                normalized = normalize_bench_result(raw)
                bench_results.append(normalized)
    
    if not bench_results:
        logger.warning("No valid benchmark results to process")
        return 1
    
    # doctor_report と world_state をロード
    doctor_report = load_json_file(DOCTOR_REPORT_PATH, default={})
    world_state = load_json_file(WORLD_STATE_PATH, default={})
    
    logger.info(f"Loaded {len(bench_results)} benchmark result(s)")
    logger.info(f"Doctor issues: {len(extract_doctor_issues(doctor_report))}")
    
    # タスク生成
    task_plan = generate_self_heal_tasks(bench_results, doctor_report, world_state)
    
    logger.info(f"Generated {task_plan['summary']['total_tasks']} tasks")
    logger.info(f"  By type: {task_plan['summary']['by_type']}")
    logger.info(f"  By priority: {task_plan['summary']['by_priority']}")
    
    # 出力
    if args.output:
        output_path = Path(args.output)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"self_heal_tasks_{timestamp}.json"
        output_path = TASKS_OUTPUT_DIR / filename
    
    if args.format == "json":
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(task_plan, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Saved task plan: {output_path}")
    
    elif args.format == "markdown":
        md_content = _format_as_markdown(task_plan)
        md_path = output_path.with_suffix(".md")
        
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        
        logger.info(f"Saved markdown: {md_path}")
    
    return 0


def _format_as_markdown(task_plan: Dict[str, Any]) -> str:
    """タスクプランをMarkdown形式に変換"""
    lines = []
    
    lines.append("# VERITAS Self-Heal Task Plan")
    lines.append("")
    
    meta = task_plan.get("meta", {})
    lines.append(f"**Generated**: {meta.get('generated_at', '')}")
    lines.append(f"**Benchmarks**: {meta.get('bench_count', 0)}")
    lines.append(f"**Doctor Issues**: {meta.get('doctor_issues_count', 0)}")
    lines.append("")
    
    summary = task_plan.get("summary", {})
    lines.append("## Summary")
    lines.append(f"- Total tasks: {summary.get('total_tasks', 0)}")
    lines.append(f"- High risk: {summary.get('high_risk_count', 0)}")
    lines.append(f"- High impact: {summary.get('high_impact_count', 0)}")
    lines.append("")
    
    lines.append("## Tasks")
    lines.append("")
    
    for task in task_plan.get("tasks", []):
        lines.append(f"### {task['id']}: {task['title']}")
        lines.append(f"- **Type**: {task['type']}")
        lines.append(f"- **Priority**: {task['priority']}")
        lines.append(f"- **Risk**: {task['risk']}, **Impact**: {task['impact']}")
        lines.append(f"- **Source**: {task['source']}")
        lines.append(f"- **Module**: {task['target_module']}")
        
        if task.get('target_path'):
            lines.append(f"- **Path**: `{task['target_path']}`")
        
        if task.get('description'):
            lines.append(f"\n{task['description']}\n")
        
        if task.get('tasks'):
            lines.append("**Tasks**:")
            for t in task['tasks']:
                lines.append(f"- {t}")
            lines.append("")
        
        if task.get('artifacts'):
            lines.append("**Artifacts**:")
            for a in task['artifacts']:
                lines.append(f"- `{a}`")
            lines.append("")
        
        lines.append("")
    
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
