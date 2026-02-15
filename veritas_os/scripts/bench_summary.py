#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
VERITAS Bench Summary

- scripts/logs/benchmarks/*.json を集計してコンソールに表示
- 1ベンチマーク = 1行 くらいのざっくりサマリー
- 旧フォーマット / 新フォーマット (meta / bench_summary / world_snapshot / tasks) 両対応
"""

from pathlib import Path
import json
import statistics
import collections
import datetime
from typing import Any, Dict, List


# scripts/ から見て logs/benchmarks/ を見る
SCRIPT_DIR = Path(__file__).resolve().parent
BENCH_DIR = SCRIPT_DIR / "logs" / "benchmarks"


def _parse_single_bench(path: Path) -> Dict[str, Any] | None:
    """1つの bench JSON を読み込み、共通フォーマットの dict に正規化する。"""
    try:
        with path.open(encoding="utf-8") as f:
            j = json.load(f)
    except Exception:
        return None

    if not isinstance(j, dict):
        return None

    # ---- bench_id / name ----
    meta = j.get("meta", {}) if isinstance(j.get("meta"), dict) else {}
    bench_id = j.get("bench_id") or meta.get("bench_id") or "unknown"
    name = j.get("name") or meta.get("name") or ""

    # ---- status_code / elapsed / decision_status ----
    bench_summary = j.get("bench_summary") or {}
    if isinstance(bench_summary, dict):
        status_code = bench_summary.get("status_code")
        elapsed = bench_summary.get("elapsed_sec")
        decision_status = bench_summary.get("decision_status")
    else:
        # 旧形式: ルート直下に置いていたケース
        status_code = j.get("status_code")
        elapsed = j.get("elapsed_sec")
        decision_status = None

    # ---- telos_score / fuji_status (旧形式の bench 出力向け) ----
    resp = j.get("response_json") or {}
    fuji_obj = resp.get("fuji") or {}
    telos_score = resp.get("telos_score")
    fuji_status = fuji_obj.get("status")

    # ---- world_snapshot (新形式) ----
    world_snap = j.get("world_snapshot") or {}
    if not isinstance(world_snap, dict):
        world_snap = {}

    world_progress = world_snap.get("progress")
    world_last_risk = world_snap.get("last_risk")
    world_status = world_snap.get("status")
    world_decision_count = world_snap.get("decision_count")

    # ---- tasks (planner.generate_code_tasks 出力) ----
    tasks = j.get("tasks") or []
    tasks_count = len(tasks) if isinstance(tasks, list) else 0

    return {
        "path": str(path),
        "bench_id": bench_id,
        "name": name,
        "status_code": status_code,
        "elapsed_sec": elapsed,
        "decision_status": decision_status,
        "telos_score": telos_score,
        "fuji_status": fuji_status,
        "world_progress": world_progress,
        "world_last_risk": world_last_risk,
        "world_status": world_status,
        "world_decision_count": world_decision_count,
        "tasks_count": tasks_count,
    }


def load_bench_results() -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    if not BENCH_DIR.exists():
        return results

    for p in sorted(BENCH_DIR.glob("*.json")):
        r = _parse_single_bench(p)
        if r is not None:
            results.append(r)

    return results


def main() -> None:
    results = load_bench_results()
    if not results:
        print("ベンチマーク結果が見つかりませんでした:", BENCH_DIR)
        return

    # bench_id ごとに集計
    buckets: dict[str, list[Dict[str, Any]]] = collections.defaultdict(list)
    for r in results:
        buckets[r["bench_id"]].append(r)

    print("=== VERITAS Bench Summary ===")
    print("対象ディレクトリ:", BENCH_DIR)
    print("集計日時:", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print()

    for bench_id, rows in buckets.items():
        name = rows[0].get("name") or ""

        status_codes = [
            r["status_code"] for r in rows
            if r.get("status_code") is not None
        ]
        ok_count = sum(1 for s in status_codes if s == 200)

        elapsed_list = [
            r["elapsed_sec"] for r in rows
            if isinstance(r.get("elapsed_sec"), (int, float))
        ]
        telos_list = [
            r["telos_score"] for r in rows
            if isinstance(r.get("telos_score"), (int, float))
        ]
        fuji_list = [r["fuji_status"] for r in rows if r.get("fuji_status")]

        fuji_counter = collections.Counter(fuji_list)

        avg_elapsed = statistics.mean(elapsed_list) if elapsed_list else None
        avg_telos = statistics.mean(telos_list) if telos_list else None

        # WorldModel 関係（新形式があれば）
        progress_list = [
            r["world_progress"] for r in rows
            if isinstance(r.get("world_progress"), (int, float))
        ]
        risk_list = [
            r["world_last_risk"] for r in rows
            if isinstance(r.get("world_last_risk"), (int, float))
        ]
        decision_counts = [
            r["world_decision_count"] for r in rows
            if isinstance(r.get("world_decision_count"), int)
        ]
        tasks_counts = [
            r["tasks_count"] for r in rows
            if isinstance(r.get("tasks_count"), int)
        ]

        latest_row = rows[-1]  # 最後の 1 件を「最新」とみなす
        decision_status_set = {
            r["decision_status"] for r in rows
            if r.get("decision_status") is not None
        }

        print(f"[{bench_id}] {name}")
        print(f"  実行回数        : {len(rows)}")
        print(f"  200 OK          : {ok_count} / {len(status_codes)}")

        if decision_status_set:
            print(f"  decision_status : {dict(collections.Counter(decision_status_set))}")
        else:
            print("  decision_status : N/A")

        print(
            f"  平均 elapsed    : {avg_elapsed:.3f} sec"
            if avg_elapsed is not None else
            "  平均 elapsed    : N/A"
        )
        print(
            f"  平均 telos_score: {avg_telos:.3f}"
            if avg_telos is not None else
            "  平均 telos_score: N/A"
        )
        print(
            f"  FUJI 分布       : {dict(fuji_counter) if fuji_counter else 'N/A'}"
        )

        # WorldModel / tasks 情報
        if progress_list or risk_list or decision_counts or tasks_counts:
            latest_progress = progress_list[-1] if progress_list else None
            latest_risk = risk_list[-1] if risk_list else None
            latest_decisions = decision_counts[-1] if decision_counts else None
            latest_tasks_count = tasks_counts[-1] if tasks_counts else None

            print("  --- WorldModel / Tasks ---")
            if latest_progress is not None:
                print(f"  最新 progress   : {latest_progress}")
            if latest_risk is not None:
                print(f"  最新 last_risk  : {latest_risk}")
            if latest_decisions is not None:
                print(f"  累計 decision   : {latest_decisions}")
            if latest_tasks_count is not None:
                print(f"  tasks 件数      : {latest_tasks_count}")
        print()

    print("=== end ===")


if __name__ == "__main__":
    main()
