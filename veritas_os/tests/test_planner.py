# veritas_os/tests/test_planner.py

import json
from typing import Any, Dict, List

import pytest

from veritas_os.core import planner as planner_core


# -------------------------------
# _normalize_step / _normalize_steps_list
# -------------------------------

def test_normalize_step_fills_defaults_and_preserves():
    step = {
        "id": "s1",
        "eta_hours": 2.5,
        "dependencies": ["a", 2],
    }
    normalized = planner_core._normalize_step(
        step,
        default_eta_hours=10,
        default_risk=0.5,
    )

    # 既存値は尊重される
    assert normalized["eta_hours"] == 2.5
    # risk はデフォルトが入る
    assert normalized["risk"] == pytest.approx(0.5)
    # dependencies は str に正規化
    assert normalized["dependencies"] == ["a", "2"]


def test_normalize_steps_list_filters_invalid():
    steps = [
        {"id": "ok1"},
        "not-a-dict",
        123,
        {"id": "ok2", "risk": 0.3},
    ]

    normalized = planner_core._normalize_steps_list(
        steps,
        default_eta_hours=1.5,
        default_risk=0.2,
    )
    assert len(normalized) == 2
    assert {s["id"] for s in normalized} == {"ok1", "ok2"}
    for s in normalized:
        assert "eta_hours" in s
        assert "risk" in s
        assert "dependencies" in s


def test_normalize_step_handles_non_list_dependencies():
    step = {"id": "s1", "dependencies": "not-a-list"}
    normalized = planner_core._normalize_step(
        step,
        default_eta_hours="2",
        default_risk="0.2",
    )

    assert normalized["eta_hours"] == 2.0
    assert normalized["risk"] == pytest.approx(0.2)
    assert normalized["dependencies"] == []


# -------------------------------
# _is_simple_qa / _simple_qa_plan
# -------------------------------

@pytest.mark.parametrize(
    "query,ctx,expected",
    [
        ("今日は何日ですか？", {}, True),  # 短いQ&A
        ("どう進めたらいいですか？", {}, False),  # 「どう進め」が含まれると simple_qa にならない
        ("VERITAS の弱点を教えて", {}, False),  # AGI / VERITAS 系は除外
        ("VERITAS の弱点を教えて", {"simple_qa": True}, True),  # 明示フラグ優先
        ("what is this", {}, True),  # 英語の疑問文（?なし）
        ("料金を教えて", {}, True),  # 日本語の短い質問（?なし）
    ],
)
def test_is_simple_qa_variants(query, ctx, expected):
    assert planner_core._is_simple_qa(query, ctx) is expected


def test_simple_qa_plan_structure_and_stage():
    world_snap = {"progress": 0.2, "decision_count": 5}  # → S3_api_polish 想定
    plan = planner_core._simple_qa_plan(
        query="テスト質問ですか？",
        context={"foo": "bar"},
        world_snap=world_snap,
    )

    assert plan["meta"]["query_type"] == "simple_qa"
    assert plan["meta"]["stage"] == "S3_api_polish"
    assert plan["source"] == "simple_qa"
    steps = plan["steps"]
    assert [s["id"] for s in steps] == ["simple_qa", "note"]
    for s in steps:
        # normalize 済み
        assert "eta_hours" in s
        assert "risk" in s
        assert isinstance(s["dependencies"], list)


# -------------------------------
# _safe_json_extract
# -------------------------------

def test_safe_json_extract_plain_dict():
    raw = json.dumps({"steps": [{"id": "s1"}]})
    obj = planner_core._safe_json_extract(raw)
    assert isinstance(obj, dict)
    assert obj["steps"][0]["id"] == "s1"


def test_safe_json_extract_top_level_list():
    raw = json.dumps([{"id": "s1"}, {"id": "s2"}])
    obj = planner_core._safe_json_extract(raw)
    assert isinstance(obj, dict)
    assert [s["id"] for s in obj["steps"]] == ["s1", "s2"]


def test_safe_json_extract_top_level_list_with_prefix_noise():
    raw = 'RESULT: ' + json.dumps([{"id": "s1"}, {"id": "s2"}])
    obj = planner_core._safe_json_extract(raw)
    assert isinstance(obj, dict)
    assert [s["id"] for s in obj["steps"]] == ["s1", "s2"]


def test_safe_json_extract_code_block():
    inner = json.dumps({"steps": [{"id": "s1"}]})
    raw = f"```json\n{inner}\n```"
    obj = planner_core._safe_json_extract(raw)
    assert obj["steps"][0]["id"] == "s1"


def test_safe_json_extract_recovers_from_broken_but_embedded_steps():
    # 全体としては壊れているが、"steps" 配列内のオブジェクトは valid JSON
    raw = 'prefix "steps": [{"id": "ok1"}, {"id": "ok2"} BROKEN'
    obj = planner_core._safe_json_extract(raw)
    ids = [s["id"] for s in obj["steps"]]
    assert ids == ["ok1", "ok2"]


def test_safe_json_extract_ignores_leading_unbalanced_closing_brace():
    raw = '} noise "steps": [{"id": "ok1"}, {"id": "ok2"}] tail'
    obj = planner_core._safe_json_extract(raw)
    ids = [s["id"] for s in obj["steps"]]
    assert ids == ["ok1", "ok2"]


def test_safe_json_extract_truncates_oversized_input(caplog):
    payload = json.dumps({"steps": [{"id": "ok1"}]})
    raw = ("x" * (planner_core._MAX_JSON_EXTRACT_CHARS + 100)) + payload

    with caplog.at_level("WARNING"):
        obj = planner_core._safe_json_extract(raw)

    assert obj["steps"] == []
    assert any("input too large" in rec.message for rec in caplog.records)


def test_safe_parse_truncates_oversized_input(caplog):
    payload = json.dumps({"steps": [{"id": "ok1"}]})
    raw = ("x" * (planner_core._MAX_JSON_EXTRACT_CHARS + 100)) + payload

    with caplog.at_level("WARNING"):
        obj = planner_core._safe_parse(raw)

    assert obj["steps"] == []
    assert any("input too large" in rec.message for rec in caplog.records)


# -------------------------------
# _fallback_plan / _infer_veritas_stage / _fallback_plan_for_stage
# -------------------------------

def test_fallback_plan_basic():
    plan = planner_core._fallback_plan("テストクエリ")
    assert plan["source"] == "fallback_minimal"
    assert plan["meta"]["stage"] == "S1_bootstrap"
    assert len(plan["steps"]) == 2


@pytest.mark.parametrize(
    "progress,expected_stage",
    [
        (0.0, "S1_bootstrap"),
        (0.1, "S2_arch_doc"),
        (0.2, "S3_api_polish"),
        (0.4, "S4_decision_analytics"),
        (0.6, "S5_real_usecase"),
        (0.8, "S6_llm_integration"),
        (0.95, "S7_demo_review"),
    ],
)
def test_infer_veritas_stage(progress, expected_stage):
    snap = {"progress": progress, "decision_count": 10}
    assert planner_core._infer_veritas_stage(snap) == expected_stage


def test_fallback_plan_for_stage_uses_stage_and_world_snapshot():
    world_snap = {"progress": 0.55}
    plan = planner_core._fallback_plan_for_stage("クエリ", 
"S5_real_usecase", world_snap)
    assert plan["meta"]["stage"] == "S5_real_usecase"
    assert plan["raw"]["world_snapshot"] == world_snap
    # S5 プランでは usecase_select step が含まれる
    ids = {s["id"] for s in plan["steps"]}
    assert "usecase_select" in ids


# -------------------------------
# plan_for_veritas_agi: simple_qa パス
# -------------------------------

def test_plan_for_veritas_agi_simple_qa(monkeypatch):
    calls = {"snapshot": 0, "chat": 0}

    def fake_snapshot(project: str):
        calls["snapshot"] += 1
        assert project == "veritas_agi"
        return {"progress": 0.02, "decision_count": 1}

    def fake_chat(*args, **kwargs):
        calls["chat"] += 1
        return {"text": '{"steps":[{"id":"dummy"}]}'}

    monkeypatch.setattr(planner_core.world_model, "snapshot", fake_snapshot)
    monkeypatch.setattr(planner_core.llm_client, "chat", fake_chat)

    plan = planner_core.plan_for_veritas_agi(
        context={},
        query="今日は何日ですか？",
    )

    assert plan["meta"]["query_type"] == "simple_qa"
    assert plan["source"] == "simple_qa"
    assert calls["snapshot"] == 1
    # simple_qa モードでは LLM Planner は呼ばれない
    assert calls["chat"] == 0


# -------------------------------
# plan_for_veritas_agi: LLM パス（正常系 & フォールバック系）
# -------------------------------

def test_plan_for_veritas_agi_llm_success(monkeypatch):
    def fake_snapshot(project: str):
        assert project == "veritas_agi"
        return {"progress": 0.3, "decision_count": 10}  # → S3_api_polish

    def fake_chat(system_prompt, user_prompt, extra_messages, temperature, max_tokens):
        data = {
            "steps": [
                {
                    "id": "step1",
                    "title": "テストステップ",
                    "detail": "詳細",
                    "why": "理由",
                    "eta_hours": 1.2,
                    "risk": 0.2,
                    "dependencies": [],
                }
            ]
        }
        return {"text": json.dumps(data)}

    monkeypatch.setattr(planner_core.world_model, "snapshot", fake_snapshot)
    monkeypatch.setattr(planner_core.llm_client, "chat", fake_chat)

    plan = planner_core.plan_for_veritas_agi(
        context={},
        query="VERITAS の今後の設計レビューをどう進める？",
    )

    assert plan["meta"]["query_type"] == "llm"
    assert plan["meta"]["stage"] == "S3_api_polish"
    assert plan["source"] == "openai_llm"
    assert len(plan["steps"]) == 1
    step = plan["steps"][0]
    assert step["id"] == "step1"
    assert step["eta_hours"] == pytest.approx(1.2)
    assert step["risk"] == pytest.approx(0.2)


def test_plan_for_veritas_agi_llm_fallback_to_stage_plan(monkeypatch):
    def fake_snapshot(project: str):
        assert project == "veritas_agi"
        return {"progress": 0.75, "decision_count": 20}  # → S6_llm_integration

    def fake_chat(*args, **kwargs):
        # JSON として解釈できないテキスト（かつ steps 情報も無い）
        return {"text": "NOT JSON AND NO STEPS HERE"}

    monkeypatch.setattr(planner_core.world_model, "snapshot", fake_snapshot)
    monkeypatch.setattr(planner_core.llm_client, "chat", fake_chat)

    plan = planner_core.plan_for_veritas_agi(
        context={},
        query="AGI ベンチの計画を作りたい",
    )

    assert plan["source"] == "stage_fallback"
    assert plan["meta"]["stage"] == "S6_llm_integration"
    assert len(plan["steps"]) >= 1


# -------------------------------
# _priority_from_risk_impact / generate_code_tasks
# -------------------------------

@pytest.mark.parametrize(
    "risk,impact,expected",
    [
        ("high", "high", "high"),
        ("high", "medium", "high"),
        ("medium", "medium", "medium"),
        ("medium", "low", "low"),
        (None, None, "low"),
    ],
)
def test_priority_from_risk_impact(risk, impact, expected):
    assert planner_core._priority_from_risk_impact(risk, impact) == expected


def test_generate_code_tasks_creates_tasks_from_bench_and_doctor(monkeypatch):
    bench = {
        "bench_id": "test_bench",
        "world_snapshot": {"foo": "bar"},
        "bench_summary": {"score": 0.9},
        "changes": [
            {
                "target_module": "core.kernel",
                "target_path": "veritas_os/core/kernel.py",
                "title": "Kernel を改善",
                "description": "リファクタ",
                "risk": "high",
                "impact": "medium",
                "suggested_functions": ["decide"],
                "reason": "複雑すぎる",
            }
        ],
        "tests": [
            {
                "title": "Kernel 基本テスト",
                "description": "decide をテスト",
                "kind": "unit",
            }
        ],
    }

    doctor_report = {
        "issues": [
            {
                "severity": "high",
                "module": "core.memory",
                "summary": "Memory leak の疑い",
                "detail": "何らかの理由でメモリが解放されない",
                "recommendation": "cleanup を追加",
                "impact": "high",
            }
        ]
    }

    world_state = {
        "veritas": {
            "progress": 0.5,
            "decision_count": 42,
        }
    }

    result = planner_core.generate_code_tasks(
        bench=bench,
        world_state=world_state,
        doctor_report=doctor_report,
    )

    tasks = result["tasks"]
    # 1 change + 1 test + 1 doctor issue = 3 タスク
    assert len(tasks) == 3

    code_task = next(t for t in tasks if t["kind"] == "code_change")
    assert code_task["module"] == "core.kernel"
    assert code_task["priority"] == "high"  # risk=high, impact=medium → high
    assert "対象ファイル" in code_task["detail"]

    test_task = next(t for t in tasks if t["kind"] == "test")
    assert test_task["id"] == "test_1"
    assert test_task["priority"] == "medium"

    doctor_task = next(t for t in tasks if t["kind"] == "self_heal")
    assert doctor_task["priority"] == "high"
    assert doctor_task["module"] == "core.memory"

    meta = result["meta"]
    assert meta["bench_id"] == "test_bench"
    assert meta["progress"] == pytest.approx(0.5)
    assert meta["decision_count"] == 42
    assert meta["doctor_issue_count"] == 1
    assert meta["source"] == "planner.generate_code_tasks"


# -------------------------------
# generate_plan (後方互換)
# -------------------------------

def test_generate_plan_includes_expected_steps():
    chosen = {"title": "テストアクション", "description": "詳細説明"}
    steps = planner_core.generate_plan("情報を調べたい", chosen)

    ids = [s["id"] for s in steps]
    # 基本 5 ステップ
    assert ids[0] == "analyze"
    assert "execute_core" in ids
    assert "log" in ids
    assert "reflect" in ids
    # 「調べ」が含まれるクエリなので research ステップも含まれる
    assert "research" in ids
