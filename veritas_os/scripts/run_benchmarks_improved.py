#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VERITAS Benchmark Runner (改善版)

主な改善点:
1. 複数ベンチマーク対応
2. 結果からcode_change_planへの自動変換
3. WorldModel / MemoryOS連携強化
4. 詳細なログとメトリクス
"""

import os
import sys
import json
import time
import datetime
import argparse
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
import yaml

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ===== 設定 =====

API_BASE = os.getenv("VERITAS_API_BASE", "http://127.0.0.1:8000")
API_KEY = os.getenv("VERITAS_API_KEY", "dev-key")

REPO_ROOT = Path(__file__).resolve().parents[1]  # .../veritas_os
BENCH_DIR = REPO_ROOT / "benchmarks"
LOG_DIR = REPO_ROOT / "scripts" / "logs"
BENCH_RESULTS_DIR = LOG_DIR / "benchmarks"

# ディレクトリ作成
LOG_DIR.mkdir(parents=True, exist_ok=True)
BENCH_RESULTS_DIR.mkdir(parents=True, exist_ok=True)


# ===== ベンチマーク実行 =====

class BenchmarkRunner:
    """ベンチマーク実行管理クラス"""
    
    def __init__(
        self,
        api_base: str = API_BASE,
        api_key: str = API_KEY,
        timeout: int = 180,
    ):
        self.api_base = api_base
        self.api_key = api_key
        self.timeout = timeout
        
    def load_benchmark(self, yaml_path: Path) -> Dict[str, Any]:
        """YAMLベンチマークをロード"""
        if not yaml_path.exists():
            raise FileNotFoundError(f"Benchmark file not found: {yaml_path}")
        
        with open(yaml_path, "r", encoding="utf-8") as f:
            bench = yaml.safe_load(f)
        
        if not isinstance(bench, dict):
            raise ValueError(f"Invalid benchmark format: {yaml_path}")
        
        return bench
    
    def run_benchmark(
        self,
        bench_data: Dict[str, Any],
        bench_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        ベンチマークを実行
        
        Returns:
            {
                "bench_id": str,
                "name": str,
                "status_code": int,
                "elapsed_sec": float,
                "request": dict,
                "response_json": dict,
                "error": str or None,
                "run_at": str,
            }
        """
        bench_id = bench_id or bench_data.get("id", "unknown")
        name = bench_data.get("name", "")
        req_payload = bench_data.get("request") or {}
        
        url = f"{self.api_base}/v1/decide"
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key,
        }
        
        logger.info(f"Running benchmark: {bench_id}")
        logger.info(f"  Name: {name}")
        logger.info(f"  URL: {url}")
        
        start_time = time.time()
        
        try:
            resp = requests.post(
                url,
                headers=headers,
                json=req_payload,
                timeout=self.timeout
            )
            
            elapsed = time.time() - start_time
            status_code = resp.status_code
            
            logger.info(f"  HTTP Status: {status_code}")
            logger.info(f"  Elapsed: {elapsed:.2f}s")
            
            # レスポンスをパース
            try:
                body = resp.json()
            except Exception as e:
                logger.error(f"Failed to parse response JSON: {e}")
                body = {"error": "JSON parse failed", "text": resp.text[:500]}
            
            result = {
                "bench_id": bench_id,
                "name": name,
                "status_code": status_code,
                "elapsed_sec": round(elapsed, 3),
                "request": req_payload,
                "response_json": body,
                "error": None if status_code == 200 else f"HTTP {status_code}",
                "run_at": datetime.datetime.now().isoformat(),
            }
            
            # サマリ出力
            if status_code == 200:
                self._print_summary(result)
            else:
                logger.warning(f"  Error: {result['error']}")
            
            return result
            
        except requests.Timeout:
            elapsed = time.time() - start_time
            logger.error(f"  Timeout after {elapsed:.2f}s")
            
            return {
                "bench_id": bench_id,
                "name": name,
                "status_code": 0,
                "elapsed_sec": round(elapsed, 3),
                "request": req_payload,
                "response_json": {},
                "error": "Timeout",
                "run_at": datetime.datetime.now().isoformat(),
            }
            
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"  Exception: {e}")
            
            return {
                "bench_id": bench_id,
                "name": name,
                "status_code": 0,
                "elapsed_sec": round(elapsed, 3),
                "request": req_payload,
                "response_json": {},
                "error": str(e),
                "run_at": datetime.datetime.now().isoformat(),
            }
    
    def _print_summary(self, result: Dict[str, Any]):
        """結果のサマリを出力"""
        body = result.get("response_json", {})
        
        chosen = body.get("chosen") or {}
        fuji = body.get("fuji") or {}
        extras = body.get("extras") or {}
        
        logger.info("--- Decision Summary ---")
        logger.info(f"  Chosen action: {chosen.get('action') or chosen.get('title')}")
        
        rationale = chosen.get("rationale", "")
        if rationale:
            logger.info(f"  Rationale: {rationale[:100]}...")
        
        logger.info(f"  Telos score: {body.get('telos_score')}")
        logger.info(f"  FUJI status: {fuji.get('status')}")
        
        if fuji.get("reasons"):
            logger.info(f"  FUJI reasons: {fuji['reasons'][:3]}")
        
        # Planner extras
        planner_data = extras.get("planner", {})
        if planner_data:
            steps = planner_data.get("steps", [])
            logger.info(f"  Planner steps: {len(steps)}")
    
    def save_result(
        self,
        result: Dict[str, Any],
        output_path: Optional[Path] = None,
    ) -> Path:
        """結果をJSON保存"""
        if output_path is None:
            bench_id = result.get("bench_id", "unknown")
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = BENCH_RESULTS_DIR / f"{bench_id}_{timestamp}.json"
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Saved result: {output_path}")
        return output_path


# ===== ベンチ結果 → code_change_plan 変換 =====

def normalize_bench_to_change_plan(
    bench_result: Dict[str, Any]
) -> Dict[str, Any]:
    """
    ベンチマーク結果をcode_change_plan形式に変換
    
    Returns:
        {
            "bench_id": str,
            "changes": List[Dict],
            "tests": List[Dict],
            "world_snapshot": Dict,
            "doctor_summary": Dict,
            "bench_summary": Dict,
        }
    """
    bench_id = bench_result.get("bench_id", "unknown")
    response = bench_result.get("response_json", {})
    extras = response.get("extras", {})
    
    # Planner steps を changes に変換
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
        risks = step.get("risks", [])
        
        # 最初のartifactをtarget_pathとする
        target_path = artifacts[0] if artifacts else None
        
        # target_moduleを推定
        if target_path:
            if target_path.endswith(".md"):
                target_module = "docs"
            elif target_path.endswith(".py"):
                target_module = "core"
            else:
                target_module = "unknown"
        else:
            target_module = "docs"
        
        # リスク評価
        risk_level = "medium"
        if risks:
            if any("暴走" in str(r) or "破損" in str(r) for r in risks):
                risk_level = "high"
        
        changes.append({
            "id": step_id,
            "title": title,
            "description": objective,
            "target_module": target_module,
            "target_path": target_path,
            "risk": risk_level,
            "impact": "high" if "設計" in title or "ループ" in title else "medium",
            "reason": f"{bench_id} step",
            "suggested_functions": [],
            "tasks": tasks,
            "artifacts": artifacts,
        })
    
    # World snapshot（あれば）
    veritas_agi = extras.get("veritas_agi", {})
    world_snapshot = veritas_agi.get("snapshot", {})
    
    # Bench summary
    bench_summary = {
        "status_code": bench_result.get("status_code"),
        "elapsed_sec": bench_result.get("elapsed_sec"),
        "decision_status": response.get("decision_status"),
        "telos_score": response.get("telos_score"),
        "fuji_status": (response.get("fuji", {}) or {}).get("status"),
    }
    
    return {
        "bench_id": bench_id,
        "changes": changes,
        "tests": [],  # 現状は空
        "world_snapshot": world_snapshot,
        "doctor_summary": {},  # 別途統合可能
        "bench_summary": bench_summary,
    }


# ===== CLI メイン =====

def main():
    parser = argparse.ArgumentParser(
        description="VERITAS Benchmark Runner with self-heal integration"
    )
    parser.add_argument(
        "benchmarks",
        nargs="*",
        help="Benchmark YAML files to run (default: all in benchmarks/)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all benchmarks in benchmarks/ directory",
    )
    parser.add_argument(
        "--output-plan",
        action="store_true",
        help="Output code_change_plan JSON for each benchmark",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=180,
        help="Request timeout in seconds (default: 180)",
    )
    parser.add_argument(
        "--api-base",
        type=str,
        default=API_BASE,
        help=f"API base URL (default: {API_BASE})",
    )
    
    args = parser.parse_args()
    
    # ベンチマークファイルリストを作成
    if args.all or not args.benchmarks:
        if not BENCH_DIR.exists():
            logger.error(f"Benchmark directory not found: {BENCH_DIR}")
            return 1
        
        bench_files = sorted(BENCH_DIR.glob("*.yaml")) + sorted(BENCH_DIR.glob("*.yml"))
        
        if not bench_files:
            logger.error(f"No benchmark files found in {BENCH_DIR}")
            return 1
    else:
        bench_files = []
        for name in args.benchmarks:
            path = Path(name)
            if not path.exists():
                # benchmarks/ からの相対パスとして試す
                path = BENCH_DIR / name
                if not path.suffix:
                    path = path.with_suffix(".yaml")
            
            if not path.exists():
                logger.error(f"Benchmark file not found: {name}")
                continue
            
            bench_files.append(path)
    
    if not bench_files:
        logger.error("No valid benchmark files to run")
        return 1
    
    logger.info(f"Found {len(bench_files)} benchmark(s)")
    
    # ベンチマーク実行
    runner = BenchmarkRunner(
        api_base=args.api_base,
        api_key=API_KEY,
        timeout=args.timeout,
    )
    
    results = []
    
    for bench_file in bench_files:
        logger.info("=" * 60)
        logger.info(f"Loading: {bench_file.name}")
        
        try:
            bench_data = runner.load_benchmark(bench_file)
            result = runner.run_benchmark(bench_data)
            
            # 結果を保存
            runner.save_result(result)
            
            results.append(result)
            
            # code_change_plan 出力
            if args.output_plan and result.get("status_code") == 200:
                change_plan = normalize_bench_to_change_plan(result)
                
                plan_path = BENCH_RESULTS_DIR / f"{result['bench_id']}_plan.json"
                with open(plan_path, "w", encoding="utf-8") as f:
                    json.dump(change_plan, f, ensure_ascii=False, indent=2)
                
                logger.info(f"Saved change plan: {plan_path}")
                logger.info(f"  Changes: {len(change_plan['changes'])}")
            
        except Exception as e:
            logger.error(f"Failed to run benchmark {bench_file.name}: {e}")
            import traceback
            traceback.print_exc()
    
    # サマリ
    logger.info("\n" + "=" * 60)
    logger.info("Summary")
    logger.info("=" * 60)
    
    total = len(results)
    success = sum(1 for r in results if r.get("status_code") == 200)
    
    logger.info(f"Total: {total}")
    logger.info(f"Success: {success}")
    logger.info(f"Failed: {total - success}")
    
    if results:
        avg_elapsed = sum(r.get("elapsed_sec", 0) for r in results) / len(results)
        logger.info(f"Avg elapsed: {avg_elapsed:.2f}s")
    
    return 0 if success == total else 1


if __name__ == "__main__":
    sys.exit(main())
