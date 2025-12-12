# veritas_os/tests/test_code_planner.py
from __future__ import annotations

import json
from pathlib import Path

from veritas_os.core import code_planner


# =========================
# 小さいヘルパー群
# =========================

def test_safe_float_various_inputs():
    assert code_planner._safe_float("1.23") == 1.23
    assert code_planner._safe_float(5) == 5.0
    # 変換できない → default
    assert code_planner._safe_float("not-a-number") == 0.0
    assert code_planner._safe_float("not-a-number", default=1.5) == 1.5


def test_load_json_success_and_default(tmp_path: Path):
    # 正常ケース
    ok_path = tmp_path / "ok.json"
    ok_path.write_text(json.dumps({"x": 1}), encoding="utf-8")
    assert code_planner._load_json(ok_path, default={"y": 2}) == {"x": 1}

    # 壊れた JSON → default にフォールバック
    bad_path = tmp_path / "bad.json"
    bad_path.write_text("{invalid_json", encoding="utf-8")
    default = {"fallback": True}
    assert code_planner._load_json(bad_path, default=default) == default

    # ファイルが無い → default
    missing = tmp_path / "missing.json"
    assert code_planner._load_json(missing, default={"none": True}) == {"none": True}


# =========================
# summarize 系
# =========================

def test_summarize_doctor_handles_invalid_and_normal():
    # dict 以外 → has_report=False
    assert code_planner._summarize_doctor("not-dict") == {
        "has_report": False,
        "issues": [],
    }

    doctor = {
        "issues": [
            {
                "id": "A",
                "severity": "high",
                "area": "world",
                "summary": "first issue",
            },
            {
                # alias キー (module/title) も拾えるか
                "id": "B",
                "module": "kernel",
                "title": "second issue",
            },
        ]
    }

    summary = code_planner._summarize_doctor(doctor)
    assert summary["has_report"] is True
    assert summary["issue_count"] == 2
    assert len(summary["top_issues"]) == 2

    first = summary["top_issues"][0]
    assert first["id"] == "A"
    assert first["severity"] == "high"
    assert first["area"] == "world"
    assert first["summary"] == "first issue"

    second = summary["top_issues"][1]
    assert second["id"] == "B"
    assert second["area"] == "kernel"
    assert second["summary"] == "second issue"


def test_summarize_bench_handles_non_dict_and_nested():
    # dict 以外 → has_bench=False
    assert code_planner._summarize_bench("not-dict") == {"has_bench": False}

    bench = {
        "response_json": {
            "chosen": {"title": "best-option", "id": "opt1"},
            "extras": {
                "planner": {
                    "steps": [
                        {"title": "step-1"},
                        {"title": "step-2"},
                    ]
                },
                "metrics": {"value_ema": 0.7, "latency_ms": 1234},
            },
        }
    }

    summary = code_planner._summarize_bench(bench)
    assert summary["has_bench"] is True
    assert summary["chosen_title"] == "best-option"
    assert summary["chosen_id"] == "opt1"
    assert summary["planner_step_count"] == 2
    assert summary["planner_step_titles"] == ["step-1", "step-2"]
    assert summary["value_ema"] == 0.7
    assert summary["latency_ms"] == 1234

    # response_json 直下形式でも動くか
    flat = bench["response_json"]
    summary2 = code_planner._summarize_bench(flat)
    assert summary2["planner_step_count"] == 2
    assert summary2["planner_step_titles"] == ["step-1", "step-2"]


# =========================
# bench ログ検索
# =========================

def test_find_latest_bench_log(tmp_path: Path, monkeypatch):
    # ディレクトリ自体が無い場合 → None
    monkeypatch.setattr(code_planner, "BENCH_LOG_DIR", tmp_path / "no-such-dir")
    assert code_planner._find_latest_bench_log("bench_x") is None

    # 実在ディレクトリにファイルを2つ作り、mtime で新しい方が選ばれるか
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    monkeypatch.setattr(code_planner, "BENCH_LOG_DIR", logs_dir)

    f1 = logs_dir / "log1.json"
    f2 = logs_dir / "log2.json"

    # どちらも bench_id を含む
    f1.write_text('{"bench": "bench_x"}', encoding="utf-8")
    f2.write_text('{"bench": "bench_x"}', encoding="utf-8")

    import os

    os.utime(f1, (1_000, 1_000))
    os.utime(f2, (2_000, 2_000))

    latest = code_planner._find_latest_bench_log("bench_x")
    assert latest == f2


# =========================
# CodeChangePlan / dataclass 系
# =========================

def test_code_change_plan_to_dict_basic():
    plan = code_planner.CodeChangePlan(
        generated_at="2025-01-01T00:00:00Z",
        bench_id="bench-1",
        world_snapshot={"progress": 0.1},
        doctor_summary={"has_report": False},
        bench_summary={"has_bench": False},
        targets=[
            code_planner.ChangeTarget(
                module="world",
                path="core/world.py",
                reason="for test",
                priority="high",
            )
        ],
        changes=[
            code_planner.CodeChange(
                title="change-title",
                description="change-desc",
                target_module="world",
                target_path="core/world.py",
                suggested_functions=["simulate"],
                risk="low",
                impact="high",
            )
        ],
        tests=[
            code_planner.TestSuggestion(
                title="test-title",
                description="test-desc",
                kind="unit",
            )
        ],
    )

    d = plan.to_dict()
    assert d["bench_id"] == "bench-1"
    assert d["world_snapshot"]["progress"] == 0.1
    assert d["targets"][0]["module"] == "world"
    assert d["changes"][0]["suggested_functions"] == ["simulate"]
    assert d["tests"][0]["kind"] == "unit"


# =========================
# generate_code_change_plan 本体
# =========================

def test_generate_code_change_plan_with_explicit_inputs(monkeypatch):
    # world_model.snapshot / get_state をモックして、ファイルI/Oを避ける
    dummy_world = {"progress": 0.5, "decision_count": 42, "last_risk": 0.2}

    monkeypatch.setattr(
        code_planner.world_model,
        "get_state",
        lambda: dummy_world,
    )
    monkeypatch.setattr(
        code_planner.world_model,
        "snapshot",
        lambda name: dummy_world,
    )

    doctor_report = {
        "issues": [
            {
                "id": "ISSUE-1",
                "severity": "high",
                "area": "kernel",
                "summary": "something bad",
            }
        ]
    }

    bench_log = {
        "response_json": {
            "chosen": {"title": "best", "id": "id-1"},
            "extras": {
                "planner": {"steps": [{"title": "do-X"}]},
                "metrics": {"value_ema": 0.9, "latency_ms": 111},
            },
        }
    }

    plan = code_planner.generate_code_change_plan(
        bench_id="bench_123",
        world_state=None,            # None → world_model.get_state() が呼ばれる
        doctor_report=doctor_report,
        bench_log=bench_log,
    )

    # ベーシックなフィールド
    assert plan.bench_id == "bench_123"
    assert plan.world_snapshot["decision_count"] == 42
    assert plan.doctor_summary["has_report"] is True
    assert plan.bench_summary["planner_step_count"] == 1

    # ターゲットモジュールが揃っているか
    modules = {t.module for t in plan.targets}
    assert {"world", "kernel", "planner"}.issubset(modules)
    # doctor_report があるので doctor も入る
    assert "doctor" in modules

    # 変更案に各モジュールのエントリが含まれているか
    change_modules = {c.target_module for c in plan.changes}
    assert "world" in change_modules
    assert "kernel" in change_modules
    assert "planner" in change_modules
    assert "doctor" in change_modules

    # テスト提案も少なくとも unit / integration がある
    kinds = {t.kind for t in plan.tests}
    assert "unit" in kinds
    assert "integration" in kinds


# =========================
# CLI エントリポイント
# =========================

def test_main_cli_uses_generate_code_change_plan(monkeypatch, capsys):
    class DummyPlan:
        def __init__(self, bench_id: str) -> None:
            self.bench_id = bench_id

        def to_dict(self) -> dict:
            return {"bench_id": self.bench_id, "generated_at": "dummy"}

    def fake_generate(bench_id: str, world_state=None, doctor_report=None, bench_log=None):
        return DummyPlan(bench_id)

    # generate_code_change_plan を差し替えて、副作用なしで CLI を検証
    monkeypatch.setattr(code_planner, "generate_code_change_plan", fake_generate)

    code_planner.main_cli(bench_id="cli_bench")
    out = capsys.readouterr().out
    data = json.loads(out)

    assert data["bench_id"] == "cli_bench"
    assert data["generated_at"] == "dummy"

