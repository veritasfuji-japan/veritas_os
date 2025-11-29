# veritas_os/core/code_planner.py
# -*- coding: utf-8 -*-
"""
VERITAS self-hosting 専用の「コード変更プランナー」

- world_state.json
- doctor_report.json
- bench結果 (bench_idごと)

をまとめて、
「どのモジュールをどう直すべきか」のブリーフ (plan dict) を返す。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import world as world_model

# ==== パス設定 ====

BASE_DIR = Path(__file__).resolve().parents[2]  # .../veritas_clean_test2
VERITAS_DIR = BASE_DIR / "veritas_os"

# doctor_report は env 優先、なければ veritas_os/reports
DEFAULT_DOCTOR = VERITAS_DIR / "reports" / "doctor_report.json"
DOCTOR_REPORT_PATH = Path(os.getenv("VERITAS_DOCTOR_REPORT", str(DEFAULT_DOCTOR)))

# bench ログディレクトリ (env 優先)
DEFAULT_BENCH_DIR = VERITAS_DIR / "scripts" / "logs"
BENCH_LOG_DIR = Path(os.getenv("VERITAS_BENCH_LOG_DIR", str(DEFAULT_BENCH_DIR)))


# ==== 小さなヘルパー群 ====

def _load_json(path: Path, default: Any = None) -> Any:
    try:
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"[code_planner] load_json error at {path}: {e}")
    return default


def _find_latest_bench_log(bench_id: str) -> Optional[Path]:
    """
    scripts/logs 配下から、指定 bench_id を含む「一番新しいファイル」を探す。
    例: bench_agi_veritas_self_hosting_20251119T010203.json など
    """
    if not BENCH_LOG_DIR.exists():
        return None

    candidates: List[Tuple[float, Path]] = []
    for p in BENCH_LOG_DIR.glob("*.json"):
        try:
            txt = p.read_text(encoding="utf-8")
        except Exception:
            continue
        if bench_id in txt:
            mtime = p.stat().st_mtime
            candidates.append((mtime, p))

    if not candidates:
        return None

    candidates.sort(key=lambda t: t[0], reverse=True)
    return candidates[0][1]


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


# ==== データ構造（コード変更プラン） ====

@dataclass
class ChangeTarget:
    """どのファイル / モジュールを触るか"""
    module: str                # 例: "kernel", "world", "planner", "api"
    path: str                  # 相対パス: "core/kernel.py" など
    reason: str                # なぜそこを触るのか（doctor / bench / world 由来）
    priority: str = "medium"   # low / medium / high


@dataclass
class CodeChange:
    """1つの具体的な変更案の枠"""
    title: str                 # 短いタイトル
    description: str           # もう少し長い説明
    target_module: str         # "kernel" / "world" / ...
    target_path: str           # "core/kernel.py" など
    suggested_functions: List[str]  # 関連しそうな関数名
    risk: str = "medium"       # low / medium / high
    impact: str = "medium"     # low / medium / high


@dataclass
class TestSuggestion:
    """どんなテストを足すべきかの枠"""
    title: str
    description: str
    kind: str                  # "unit" / "integration" / "bench"


@dataclass
class CodeChangePlan:
    """
    LLM に渡す前段階での「構造化プラン」。
    ここに world / doctor / bench のサマリも含めておく。
    """
    generated_at: str
    bench_id: str

    world_snapshot: Dict[str, Any]
    doctor_summary: Dict[str, Any]
    bench_summary: Dict[str, Any]

    targets: List[ChangeTarget]
    changes: List[CodeChange]
    tests: List[TestSuggestion]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "bench_id": self.bench_id,
            "world_snapshot": self.world_snapshot,
            "doctor_summary": self.doctor_summary,
            "bench_summary": self.bench_summary,
            "targets": [asdict(t) for t in self.targets],
            "changes": [asdict(c) for c in self.changes],
            "tests": [asdict(t) for t in self.tests],
        }


# ==== 入力サマライズ ====

def _summarize_doctor(doctor: Any) -> Dict[str, Any]:
    """
    doctor_report.json の「よくある形」を想定しつつ、存在しないフィールドにも耐える。
    """
    if not isinstance(doctor, dict):
        return {"has_report": False, "issues": []}

    issues = doctor.get("issues") or doctor.get("problems") or []
    if not isinstance(issues, list):
        issues = []

    top_issues = []
    for it in issues[:5]:
        if not isinstance(it, dict):
            continue
        top_issues.append(
            {
                "id": it.get("id"),
                "severity": it.get("severity", "info"),
                "area": it.get("area") or it.get("module"),
                "summary": it.get("summary") or it.get("title"),
            }
        )

    return {
        "has_report": True,
        "issue_count": len(issues),
        "top_issues": top_issues,
    }


def _summarize_bench(bench: Any) -> Dict[str, Any]:
    if not isinstance(bench, dict):
        return {"has_bench": False}

    resp = bench.get("response_json") or bench  # ログ形式によってはそのまま
    chosen = (resp or {}).get("chosen") or {}
    extras = (resp or {}).get("extras") or {}

    planner = extras.get("planner") or {}
    steps = planner.get("steps") or []
    metrics = extras.get("metrics") or {}

    return {
        "has_bench": True,
        "chosen_title": chosen.get("title"),
        "chosen_id": chosen.get("id"),
        "planner_step_count": len(steps),
        "planner_step_titles": [s.get("title") for s in steps[:5] if isinstance(s, dict)],
        "value_ema": metrics.get("value_ema"),
        "latency_ms": metrics.get("latency_ms"),
    }


# ==== メイン：コード変更プラン生成 ====

def generate_code_change_plan(
    bench_id: str,
    world_state: Optional[Dict[str, Any]] = None,
    doctor_report: Optional[Dict[str, Any]] = None,
    bench_log: Optional[Dict[str, Any]] = None,
) -> CodeChangePlan:
    """
    world / doctor / bench から「どこをどう直すか」の枠組みを作る。
    ここではまだ LLM は呼ばず、“構造化ブリーフ”を返す。
    """

    # 1) world_snapshot
    if world_state is None:
        world_state = world_model.get_state()
    world_snap = world_model.snapshot("veritas_agi")

    # 2) doctor_report
    if doctor_report is None:
        doctor_report = _load_json(DOCTOR_REPORT_PATH, default={})
    doctor_summary = _summarize_doctor(doctor_report)

    # 3) bench_log
    if bench_log is None:
        bench_path = _find_latest_bench_log(bench_id)
        if bench_path:
            bench_log = _load_json(bench_path, default={})
        else:
            bench_log = {}
    bench_summary = _summarize_bench(bench_log)

    # ==== ここからは「雑だが実用的なヒューリスティック」 ====

    targets: List[ChangeTarget] = []
    changes: List[CodeChange] = []
    tests: List[TestSuggestion] = []

    progress = _safe_float(world_snap.get("progress"), 0.0)
    decision_count = int(world_snap.get("decision_count") or 0)
    last_risk = _safe_float(world_snap.get("last_risk"), 0.3)

    # --- ターゲット選定（どのモジュールを触るか） ---

    # 1) world_model 関連 (進捗・hint・snapshot周り)
    targets.append(
        ChangeTarget(
            module="world",
            path="core/world.py",
            reason="veritas_agi プロジェクトの progress / hint / simulate を拡張し、自己改善ループをより因果モデルに近づけるため。",
            priority="high" if progress >= 0.3 else "medium",
        )
    )

    # 2) kernel / decide 周り (DecisionOS)
    targets.append(
        ChangeTarget(
            module="kernel",
            path="core/kernel.py",
            reason="決定ループに world_state と bench 結果をより強く反映し、『どのコードを直すか』まで踏み込んだプランを生成するため。",
            priority="high",
        )
    )

    # 3) planner 周り (AGI研究プランナー)
    targets.append(
        ChangeTarget(
            module="planner",
            path="core/planner.py",
            reason="bench の planner.steps をもとに、実際のコード変更タスクに分解するロジックを足すため。",
            priority="high",
        )
    )

    # 4) doctor / report 周り
    if doctor_summary.get("has_report"):
        targets.append(
            ChangeTarget(
                module="doctor",
                path="core/doctor.py",
                reason="doctor_report の issue を world_state/bench と接続し、再発防止のコード変更に結びつけるため。",
                priority="medium",
            )
        )

    # --- 変更案の枠 (changes) ---

    # A) world.py 強化案
    changes.append(
        CodeChange(
            title="world_state に『因果モデル用の履歴』を追加する",
            description=(
                "world_state.json に decision ごとの (query, chosen_id, risk, value_total, planner_step_count) "
                "を簡易履歴として保存するフィールドを追加し、simulate() で『このタイプの決定は過去にどう効いたか』"
                "を参照できるようにする。"
            ),
            target_module="world",
            target_path="core/world.py",
            suggested_functions=["update_from_decision", "simulate", "snapshot"],
            risk="medium",
            impact="high",
        )
    )

    # B) kernel.py で「コード変更プラン」モードを追加
    changes.append(
        CodeChange(
            title="kernel.decide に『code_change_plan』モードを追加する",
            description=(
                "intent が 'plan' かつ context['mode'] == 'code_change_plan' のとき、"
                "alternatives を『どのファイルをどう直すか』に限定したセットに差し替え、"
                "world_state / doctor / bench_summary をもとに Multi-Agent Debate させる。"
            ),
            target_module="kernel",
            target_path="core/kernel.py",
            suggested_functions=["decide", "_detect_intent", "_gen_options_by_intent"],
            risk="medium",
            impact="high",
        )
    )

    # C) planner.py に「コード変更ステップ展開」を追加
    changes.append(
        CodeChange(
            title="planner にコード変更タスク生成用ヘルパーを追加する",
            description=(
                "bench.extras.planner.steps を入力にして、"
                "各ステップを具体的なコードタスク (ファイル / 関数 / 変更概要 / テスト案) に分解する "
                "ヘルパー関数 generate_code_tasks(...) を追加する。"
            ),
            target_module="planner",
            target_path="core/planner.py",
            suggested_functions=["generate_plan", "generate_code_tasks"],
            risk="low",
            impact="medium",
        )
    )

    # D) doctor_report と self-healing の接続
    if doctor_summary.get("has_report"):
        changes.append(
            CodeChange(
                title="doctor_report の issue から self-healing プランを自動生成する",
                description=(
                    "doctor_report.json の issues を走査して、severity が high のものを優先し、"
                    "『どのモジュールをどう直すべきか』の候補リストを自動生成し world_state.meta に保存する。"
                ),
                target_module="doctor",
                target_path="core/doctor.py",
                suggested_functions=["generate_report", "self_heal_plan"],
                risk="medium",
                impact="medium",
            )
        )

    # --- テスト案 ---

    tests.append(
        TestSuggestion(
            title="world.update_from_decision の単体テスト",
            description=(
                "ダミーの決定結果 (values, planner.steps, gate.risk) を与えて "
                "world_state.json が期待通り更新されるか検証する。"
            ),
            kind="unit",
        )
    )

    tests.append(
        TestSuggestion(
            title="kernel.decide(code_change_planモード) の統合テスト",
            description=(
                "context['mode'] = 'code_change_plan' の状態で kernel.decide を呼び出し、"
                "alternatives が『コード変更案』になっていること、fuji.status=allow が維持されていることを検証する。"
            ),
            kind="integration",
        )
    )

    tests.append(
        TestSuggestion(
            title="bench + world_state + doctor_report を入力にした end-to-end テスト",
            description=(
                "ベンチログ・world_state.json・doctor_report.json のサンプルを用意し、本コードプランナーが "
                "一貫した CodeChangePlan を返すことを確認する。"
            ),
            kind="integration",
        )
    )

    plan = CodeChangePlan(
        generated_at=_now_iso(),
        bench_id=bench_id,
        world_snapshot=world_snap,
        doctor_summary=doctor_summary,
        bench_summary=bench_summary,
        targets=targets,
        changes=changes,
        tests=tests,
    )
    return plan


# ==== CLI 用エントリポイント ====

def main_cli(bench_id: str = "agi_veritas_self_hosting") -> None:
    """
    ローカルで:
        python -m veritas_os.core.code_planner
    みたいに叩けるようにするための簡易 CLI。
    """
    plan = generate_code_change_plan(bench_id=bench_id)
    print(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="VERITAS code change planner")
    parser.add_argument(
        "--bench-id",
        default="agi_veritas_self_hosting",
        help="対象とする bench_id (デフォルト: agi_veritas_self_hosting)",
    )
    args = parser.parse_args()
    main_cli(bench_id=args.bench_id)

