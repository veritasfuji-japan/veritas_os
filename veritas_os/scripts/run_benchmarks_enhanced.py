#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
VERITAS Benchmark Runner (Enhanced)

benchmarks/*.yaml を一括で /v1/decide に投げて、
結果を scripts/logs/benchmarks/ 以下に保存するスクリプト。

【改善点】
- CLI引数対応（特定ベンチ指定可能）
- code_change_plan自動生成オプション
- 詳細なログ・エラーハンドリング
- タイムアウト設定
- サマリ出力の充実
"""

import os
import sys
import json
import time
import glob
import argparse
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
import yaml

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==== 設定 ====
BASE_URL = os.getenv("VERITAS_API_BASE", "http://127.0.0.1:8000")
API_KEY = os.getenv("VERITAS_API_KEY", "YOUR_API_KEY_HERE")
DEFAULT_TIMEOUT = 180  # 秒

REPO_ROOT = Path(__file__).resolve().parents[1]          # .../veritas_os
BENCH_DIR = REPO_ROOT / "benchmarks"
LOG_ROOT  = REPO_ROOT / "scripts" / "logs" / "benchmarks"
LOG_ROOT.mkdir(parents=True, exist_ok=True)


def run_one_bench(
    path: Path,
    timeout: int = DEFAULT_TIMEOUT,
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    単一 YAML ベンチを実行して結果を保存
    
    Returns:
        {
            "bench_id": str,
            "name": str,
            "status_code": int,
            "elapsed_sec": float,
            "success": bool,
            "output_path": str,
            "error": str or None,
        }
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            bench = yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to load {path}: {e}")
        return {
            "bench_id": path.stem,
            "name": "",
            "status_code": 0,
            "elapsed_sec": 0.0,
            "success": False,
            "output_path": None,
            "error": f"YAML load error: {e}",
        }

    bench_id = bench.get("id") or path.stem
    name     = bench.get("name", "")
    req_body = bench.get("request")

    if not isinstance(req_body, dict):
        logger.warning(f"[SKIP] {path} - invalid request format")
        return {
            "bench_id": bench_id,
            "name": name,
            "status_code": 0,
            "elapsed_sec": 0.0,
            "success": False,
            "output_path": None,
            "error": "Invalid request format",
        }

    url = f"{BASE_URL}/v1/decide"
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY,
    }

    logger.info(f"Running: {bench_id} ({name})")
    if verbose:
        logger.info(f"  URL: {url}")
        logger.info(f"  Timeout: {timeout}s")

    t0 = time.time()
    
    try:
        resp = requests.post(
            url,
            headers=headers,
            json=req_body,  # json= の方が安全
            timeout=timeout
        )
        dt = time.time() - t0
        
        logger.info(f"  Status: {resp.status_code}, Elapsed: {dt:.2f}s")
        
        # レスポンスパース
        try:
            response_json = resp.json()
        except Exception:
            response_json = {"raw_text": resp.text[:1000]}
        
        # 結果保存
        out = {
            "bench_id": bench_id,
            "name": name,
            "yaml_path": str(path),
            "request": req_body,
            "status_code": resp.status_code,
            "elapsed_sec": round(dt, 3),
            "response_json": response_json,
            "run_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        
        ts = time.strftime("%Y%m%d_%H%M%S")
        out_path = LOG_ROOT / f"{bench_id}_{ts}.json"
        
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        
        logger.info(f"  Saved: {out_path.name}")
        
        # サマリ出力
        if resp.ok and verbose:
            _print_bench_summary(response_json)
        
        return {
            "bench_id": bench_id,
            "name": name,
            "status_code": resp.status_code,
            "elapsed_sec": dt,
            "success": resp.ok,
            "output_path": str(out_path),
            "error": None if resp.ok else f"HTTP {resp.status_code}",
        }
    
    except requests.Timeout:
        dt = time.time() - t0
        logger.error(f"  Timeout after {dt:.2f}s")
        
        return {
            "bench_id": bench_id,
            "name": name,
            "status_code": 0,
            "elapsed_sec": dt,
            "success": False,
            "output_path": None,
            "error": "Timeout",
        }
    
    except Exception as e:
        dt = time.time() - t0
        logger.error(f"  Exception: {e}")
        
        return {
            "bench_id": bench_id,
            "name": name,
            "status_code": 0,
            "elapsed_sec": dt,
            "success": False,
            "output_path": None,
            "error": str(e),
        }


def _print_bench_summary(response_json: Dict[str, Any]):
    """ベンチ結果のサマリを表示"""
    chosen = response_json.get("chosen") or {}
    fuji = response_json.get("fuji") or {}
    extras = response_json.get("extras") or {}
    
    logger.info("  --- Summary ---")
    logger.info(f"    Action: {chosen.get('action') or chosen.get('title', 'N/A')}")
    logger.info(f"    Telos: {response_json.get('telos_score', 'N/A')}")
    logger.info(f"    FUJI: {fuji.get('status', 'N/A')}")
    
    planner_data = extras.get("planner", {})
    steps = planner_data.get("steps", [])
    if steps:
        logger.info(f"    Steps: {len(steps)}")


def generate_change_plan(result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    ベンチ結果からcode_change_planを生成
    
    Returns:
        change_plan dict or None
    """
    if not result.get("success"):
        return None
    
    output_path = result.get("output_path")
    if not output_path or not Path(output_path).exists():
        return None
    
    try:
        with open(output_path, "r", encoding="utf-8") as f:
            bench_result = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load result file: {e}")
        return None
    
    # 正規化
    response = bench_result.get("response_json", {})
    extras = response.get("extras", {})
    planner_data = extras.get("planner", {})
    steps = planner_data.get("steps", [])
    
    if not steps:
        return None
    
    changes = []
    
    for idx, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            continue
        
        step_id = step.get("id", f"step{idx}")
        title = step.get("title", f"Step {idx}")
        objective = step.get("objective", "")
        tasks = step.get("tasks", [])
        artifacts = step.get("artifacts", [])
        
        target_path = artifacts[0] if artifacts else None
        
        # モジュール推定
        if target_path:
            if ".md" in target_path:
                target_module = "docs"
            elif "core/" in target_path:
                target_module = "core"
            elif "api/" in target_path:
                target_module = "api"
            else:
                target_module = "unknown"
        else:
            target_module = "docs"
        
        changes.append({
            "id": step_id,
            "title": title,
            "description": objective,
            "target_module": target_module,
            "target_path": target_path,
            "tasks": tasks,
            "artifacts": artifacts,
        })
    
    plan = {
        "bench_id": result["bench_id"],
        "changes": changes,
        "tests": [],
        "bench_summary": {
            "status_code": result["status_code"],
            "elapsed_sec": result["elapsed_sec"],
        },
    }
    
    return plan


def main():
    parser = argparse.ArgumentParser(
        description="VERITAS Benchmark Runner (Enhanced)"
    )
    parser.add_argument(
        "benchmarks",
        nargs="*",
        help="Specific benchmark files to run (default: all)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all benchmarks in benchmarks/ directory",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"Request timeout in seconds (default: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "--output-plan",
        action="store_true",
        help="Generate code_change_plan.json for each benchmark",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output",
    )
    
    args = parser.parse_args()
    
    # ログレベル調整
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # ベンチマークファイルリスト作成
    if args.benchmarks:
        files = []
        for name in args.benchmarks:
            path = Path(name)
            if not path.exists():
                # benchmarks/ からの相対パス
                path = BENCH_DIR / name
                if not path.suffix:
                    path = path.with_suffix(".yaml")
            
            if not path.exists():
                logger.error(f"Benchmark not found: {name}")
                continue
            
            files.append(path)
    else:
        # デフォルト: 全ベンチ
        files = sorted(BENCH_DIR.glob("*.yaml"))
    
    if not files:
        logger.error(f"No benchmark files found in {BENCH_DIR}")
        return 1
    
    logger.info(f"Running {len(files)} benchmark(s)")
    logger.info(f"Timeout: {args.timeout}s")
    logger.info("")
    
    results = []
    
    for bench_file in files:
        result = run_one_bench(
            bench_file,
            timeout=args.timeout,
            verbose=args.verbose,
        )
        results.append(result)
        
        # code_change_plan生成
        if args.output_plan and result.get("success"):
            plan = generate_change_plan(result)
            
            if plan:
                plan_path = LOG_ROOT / f"{result['bench_id']}_plan.json"
                with open(plan_path, "w", encoding="utf-8") as f:
                    json.dump(plan, f, ensure_ascii=False, indent=2)
                
                logger.info(f"  Plan: {plan_path.name} ({len(plan['changes'])} changes)")
    
    # サマリ
    logger.info("")
    logger.info("=" * 60)
    logger.info("Summary")
    logger.info("=" * 60)
    
    total = len(results)
    success = sum(1 for r in results if r["success"])
    failed = total - success
    
    logger.info(f"Total: {total}")
    logger.info(f"Success: {success}")
    logger.info(f"Failed: {failed}")
    
    if results:
        avg_elapsed = sum(r["elapsed_sec"] for r in results) / len(results)
        logger.info(f"Avg elapsed: {avg_elapsed:.2f}s")
    
    # 失敗したベンチを表示
    if failed > 0:
        logger.info("")
        logger.info("Failed benchmarks:")
        for r in results:
            if not r["success"]:
                logger.info(f"  - {r['bench_id']}: {r['error']}")
    
    return 0 if success == total else 1


if __name__ == "__main__":
    sys.exit(main())
