# veritas_os/scripts/bench_plan.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

from veritas_os.core import planner, world as world_model


# ===== パス設定 =====

SCRIPT_DIR = Path(__file__).resolve().parent
LOGS_DIR = SCRIPT_DIR / "logs"
BENCH_DIR = LOGS_DIR / "benchmarks"
DOCTOR_REPORT_PATH = LOGS_DIR / "doctor_report.json"


# ===== ロード系ユーティリティ =====

def _load_world_state() -> Dict[str, Any]:
    """world_state.json 全体（world.get_state()ラッパ）"""
    try:
        return world_model.get_state()
    except Exception as e:
        print("[bench_plan] world_state の読み込みに失敗:", repr(e))
        return {}


def _load_doctor_report() -> Dict[str, Any]:
    """doctor_report.json を読む（無ければ {}）"""
    if not DOCTOR_REPORT_PATH.exists():
        return {}
    try:
        with DOCTOR_REPORT_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print("[bench_plan] doctor_report の読み込みに失敗:", repr(e))
        return {}


def _resolve_bench_path(arg: str) -> Path | None:
    """
    --bench で渡された文字列から実ファイルパスを解決する。

    優先順:
      1. そのまま Path(arg) がファイルなら採用
      2. BENCH_DIR / arg
      3. BENCH_DIR / f"{arg}.json"
    """
    p = Path(arg)
    if p.is_file():
        return p

    candidate = BENCH_DIR / arg
    if candidate.is_file():
        return candidate

    candidate_json = BENCH_DIR / f"{arg}.json"
    if candidate_json.is_file():
        return candidate_json

    print("[bench_plan] 指定された bench ファイルが見つかりません:", arg)
    return None


def _load_latest_bench() -> Dict[str, Any]:
    """benchmarks ディレクトリから最新の JSON を 1つ読む（生 JSON のまま返す）"""
    if not BENCH_DIR.exists():
        print("[bench_plan] benchmarks ディレクトリがありません:", BENCH_DIR)
        return {}

    files = sorted(BENCH_DIR.glob("*.json"))
    if not files:
        print("[bench_plan] ベンチ結果 JSON が見つかりません:", BENCH_DIR)
        return {}

    latest = files[-1]
    print("[bench_plan] 最新ベンチファイル:", latest)
    try:
        with latest.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print("[bench_plan] ベンチ JSON の読み込みに失敗:", repr(e))
        return {}


def _load_bench(arg: str) -> Dict[str, Any]:
    """
    --bench 引数に応じてベンチ結果をロードする（生 JSON のまま返す）。
    - "latest" -> benchmarks/*.json の最新
    - それ以外 -> パス解決して該当ファイルを読む
    """
    if arg == "latest":
        return _load_latest_bench()

    path = _resolve_bench_path(arg)
    if path is None:
        return {}

    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print("[bench_plan] ベンチ JSON の読み込みに失敗:", repr(e))
        return {}


# ===== ★ 正規化ユーティリティ =====

def _normalize_bench_payload(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    run_benchmarks.py が吐いた「生 JSON」か、
    すでに changes/tests を持った bench_payload かを判定して、
    planner.generate_code_tasks() が期待する形に正規化する。
    """

    if not isinstance(raw, dict):
        return {"changes": [], "tests": []}

    # すでに changes / tests がある場合はそのまま使う（将来の拡張用）
    if "changes" in raw or "tests" in raw:
        return raw

    # run_benchmarks の生 JSON パターンを想定
    res = raw.get("response_json") or {}
    extras = res.get("extras") or {}
    planner_extras = extras.get("planner") or {}
    steps = planner_extras.get("steps") or []

    veritas_agi = extras.get("veritas_agi") or {}
    world_snap = veritas_agi.get("snapshot") or {}

    changes: list[Dict[str, Any]] = []

    # planner.steps を「ドキュメント作成タスク」として changes に落とし込む
    for idx, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            continue

        title = step.get("title") or f"bench_step_{idx}"
        objective = step.get("objective") or ""
        artifacts = step.get("artifacts") or []
        target_path = artifacts[0] if artifacts else None

        changes.append(
            {
                "title": title,
                "description": objective,
                "target_module": "docs",          # ドキュメント系タスクとして扱う
                "target_path": target_path,       # 例: docs/world_model.md
                "risk": "medium",
                "impact": "high",
                "reason": "agi_veritas_self_hosting planner step",
                "suggested_functions": [],
            }
        )

    # 現状このベンチでは tests 情報は無いので空
    tests: list[Dict[str, Any]] = []

    bench_payload: Dict[str, Any] = {
        "bench_id": raw.get("bench_id"),
        "world_snapshot": world_snap,
        "doctor_summary": {},  # doctor 系ベンチをマージする時にここを使う
        "bench_summary": {
            "status_code": raw.get("status_code"),
            "elapsed_sec": raw.get("elapsed_sec"),
            "decision_status": res.get("decision_status"),
        },
        "changes": changes,
        "tests": tests,
    }

    return bench_payload


# ===== メイン =====

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "AGI ベンチ結果 + world_state + doctor_report から、"
            "具体的なコード変更タスクリストを生成して JSON で出力するツール"
        )
    )
    parser.add_argument(
        "--bench",
        type=str,
        default="latest",
        help="使用するベンチ JSON。'latest' (デフォルト) か、ファイル名 / パスを指定。",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="コンパクトな1行JSONを出力（指定しなければインデント付き）。",
    )
    args = parser.parse_args()

    # 1) 生のベンチ JSON をロード
    raw_bench = _load_bench(args.bench)

    # 2) planner.generate_code_tasks() 用に正規化
    bench_payload = _normalize_bench_payload(raw_bench)

    world_state = _load_world_state()
    doctor_report = _load_doctor_report()

    # ★ Planner に投げて「実際のコード変更タスク」を生成
    tasks_plan = planner.generate_code_tasks(
        bench_payload,
        world_state=world_state,
        doctor_report=doctor_report,
    )

    # 出力
    if args.compact:
        print(json.dumps(tasks_plan, ensure_ascii=False, separators=(",", ":")))
    else:
        print(json.dumps(tasks_plan, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
