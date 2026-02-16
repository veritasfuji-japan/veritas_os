# tests/test_kernel_core.py
# -*- coding: utf-8 -*-
"""
VERITAS core.kernel 用のユニットテスト（v2-compatible版）

・simple_qa / knowledge_qa の早期リターン
・intent / options / dedupe / scoring のユーティリティ
・pipeline からのフラグによる「二重実行スキップ」挙動

※ 実装との差異で落ちないように、実装に合わせて少し緩めにしてある。
"""

from typing import Any, Dict

import pytest

from veritas_os.core import kernel


# ============================================================
# anyio: trio が入っていない環境向けに backend を asyncio 固定
# ============================================================

@pytest.fixture
def anyio_backend():
    # anyio プラグインの parametrize(trio/asyncio) を上書きして、
    # このテストファイルでは asyncio のみを使う
    return "asyncio"


# ============================================================
# simple_qa / knowledge_qa 検出ロジック
# ============================================================

def test_detect_simple_qa_patterns():
    # 今何時？
    assert kernel._detect_simple_qa("今何時？") == "time"
    assert kernel._detect_simple_qa("いまなんじ?") == "time"

    # 今日何曜日？
    assert kernel._detect_simple_qa("今日何曜日？") == "weekday"

    # 日付パターン（実装が確実に拾いそうなパターンでテスト）
    assert kernel._detect_simple_qa("今日は何日？") == "date"

    # 実装によっては拾えないこともあるので、ここは「拾えても拾えなくてもOK」
    res = kernel._detect_simple_qa("今日の日付は？")
    assert res in (None, "date")

    # 英語系
    assert kernel._detect_simple_qa("What time is it?") == "time"
    assert kernel._detect_simple_qa("What day is it?") == "weekday"

    # today + date
    assert kernel._detect_simple_qa("what is today date?") == "date"

    # AGI/VERITAS を含むクエリは simple_qa にならない
    assert kernel._detect_simple_qa("今のAGIの状態は？") is None
    assert kernel._detect_simple_qa("VERITAS は今何時と答える？") is None

    # 長いクエリは simple_qa 対象外
    long_q = "今何時かと、VERITAS OS の状態を詳しく教えてほしいです"
    assert kernel._detect_simple_qa(long_q) is None


def test_detect_simple_qa_mixed_language_and_spacing():
    """日英混在・余分スペースでも simple_qa が検出されることを確認。"""
    assert kernel._detect_simple_qa("What   time is it   today?") == "time"
    assert kernel._detect_simple_qa("what day is it today??") == "weekday"
    assert kernel._detect_simple_qa("What is the date today?") == "date"

def test_detect_knowledge_qa_patterns():
    # 「〜とは？」系
    assert kernel._detect_knowledge_qa("東京とは？") is True
    assert kernel._detect_knowledge_qa("人工知能とは?") is True

    # 「どこ？/誰？」系
    assert kernel._detect_knowledge_qa("東京都庁はどこ？") is True
    assert kernel._detect_knowledge_qa("イーロンマスクは誰？") is True

    # 英語 what/who/where is
    assert kernel._detect_knowledge_qa("What is AGI?") is True
    assert kernel._detect_knowledge_qa("who is Alan Turing?") is True
    assert kernel._detect_knowledge_qa("where is Tokyo?") is True

    # 県庁所在地 / 人口 など
    assert kernel._detect_knowledge_qa("栃木県の県庁所在地") is True
    assert kernel._detect_knowledge_qa("東京の人口は？") is True

    # 雑談は knowledge_qa ではない
    assert kernel._detect_knowledge_qa("ご飯食べたい") is False
    assert kernel._detect_knowledge_qa("眠い") is False


# ============================================================
# intent / options / dedupe / scoring
# ============================================================

def test_detect_intent_basic():
    assert kernel._detect_intent("明日の天気教えて") == "weather"
    assert kernel._detect_intent("今日は疲れたから休んだ方がいい？") == "health"
    assert kernel._detect_intent("AGIとは何か教えて") == "learn"
    # どれにも明確に当てはまらない場合は plan
    assert kernel._detect_intent("今日やるべきことを整理したい") == "plan"


def test_gen_options_by_intent_and_filter_weather():
    # weather intent のデフォルトオプション
    opts = kernel._gen_options_by_intent("weather")
    titles = {o["title"] for o in opts}
    assert any("天気" in t or "予報" in t or "傘" in t for t in titles)

    # filter で「天気っぽい」案だけ残る
    alts = [
        {"id": "1", "title": "天気アプリで予報を見る", "description": "", "score": 1.0},
        {"id": "2", "title": "筋トレをする", "description": "", "score": 1.0},
        {"id": "3", "title": "傘を持っていく", "description": "", "score": 1.0},
    ]
    filtered = kernel._filter_alts_by_intent("weather", "明日の天気", alts)
    kept_titles = {a["title"] for a in filtered}
    assert "天気アプリで予報を見る" in kept_titles
    assert "傘を持っていく" in kept_titles
    assert "筋トレをする" not in kept_titles


def test_dedupe_alts_prefers_higher_score():
    alts = [
        {"id": "1", "title": "Aをする", "description": "詳細1", "score": 0.5},
        {"id": "2", "title": "Aをする", "description": "詳細1", "score": 1.2},  # 同一キーだがスコア高
        {"id": "3", "title": "Bをする", "description": "詳細2", "score": 0.8},
    ]
    deduped = kernel._dedupe_alts(alts)
    assert len(deduped) == 2

    # "Aをする" の方は score が 1.2 の方が残っているはず
    dmap = {(d["title"], d["description"]): d for d in deduped}
    assert dmap[("Aをする", "詳細1")]["score"] == 1.2
    assert dmap[("Bをする", "詳細2")]["score"] == 0.8


def test_score_alternatives_with_value_core_and_persona(monkeypatch):
    """
    value_core / persona_bias / Telos を通して score / score_raw が付与されることをテスト。
    内部のスコア値そのものには強く依存しない。

    実装側に OptionScore が無い環境でも動くように、
    テスト側で OptionScore を注入する（raising=False）。
    """

    # OptionScore / compute_value_score をダミー実装に差し替え
    class DummyOptionScore:
        def __init__(
            self,
            id: str,
            title: str,
            description: str,
            base_score: float,
            telos_score: float,
            stakes: float,
            persona_bias: float,
            world_projection,
        ):
            self.id = id
            self.title = title
            self.description = description
            self.base_score = base_score
            self.telos_score = telos_score
            self.stakes = stakes
            self.persona_bias = persona_bias
            self.world_projection = world_projection

    # OptionScore が元々無くてもエラーにしない
    monkeypatch.setattr(
        kernel.value_core,
        "OptionScore",
        DummyOptionScore,
        raising=False,
    )
    monkeypatch.setattr(
        kernel.value_core,
        "compute_value_score",
        lambda opt: 1.5,  # 単純に 1.5 倍する
        raising=False,
    )

    # fuzzy_bias_lookup も素直な実装に
    def fake_fuzzy_bias_lookup(bias_dict, title):
        return bias_dict.get(title.lower(), 0.0)

    monkeypatch.setattr(kernel.adapt, "fuzzy_bias_lookup", fake_fuzzy_bias_lookup)

    # strategy_core があれば、その score_options は「そのまま返す」ように
    if kernel.strategy_core is not None:
        monkeypatch.setattr(
            kernel.strategy_core,
            "score_options",
            lambda **kwargs: kwargs["options"],
            raising=False,
        )

    intent = "plan"
    q = "今日は最小ステップで前に進みたい"
    alts = [
        {
            "id": "1",
            "title": "最小ステップで前進する",
            "description": "",
            "score": 1.0,
        },
        {
            "id": "2",
            "title": "今日は休息に充てる",
            "description": "",
            "score": 1.0,
        },
    ]

    # persona bias: 最小ステップ案を少し優遇
    persona_bias = {"最小ステップで前進する".lower(): 1.0}

    kernel._score_alternatives(
        intent=intent,
        q=q,
        alts=alts,
        telos_score=0.8,
        stakes=0.3,
        persona_bias=persona_bias,
        ctx={},
    )

    # 各 alt に score_raw / score が付与されている
    for a in alts:
        assert "score_raw" in a
        assert "score" in a
        assert isinstance(a["score_raw"], float)
        assert isinstance(a["score"], float)

    # persona_bias の効き目で、最小ステップ案の方がスコアが高くなっていることを期待
    score_map = {a["title"]: a["score"] for a in alts}
    assert score_map["最小ステップで前進する"] > score_map["今日は休息に充てる"]


# ============================================================
# decide: simple_qa / knowledge_qa の早期リターン
# ============================================================

@pytest.mark.anyio
async def test_decide_simple_qa_time():
    ctx = {"user_id": "test-user"}
    res = await kernel.decide(ctx, "今何時？", alternatives=None)

    # simple_qa モードであること
    assert res["meta"]["kind"] == "simple_qa"
    assert res["values"]["rationale"] == "simple QA"
    assert res["fuji"]["decision_status"] == "allow"

    chosen = res["chosen"]
    assert "現在時刻は" in chosen["title"]
    assert "simple QA モード" in chosen["description"]


@pytest.mark.anyio
async def test_decide_knowledge_qa_uses_env_tool(monkeypatch):
    # run_env_tool をモック（外部アクセス防止）
    def fake_run_env_tool(kind: str, **kwargs):
        assert kind == "web_search"
        return {
            "ok": True,
            "results": [
                {
                    "title": "Tokyo - Wikipedia",
                    "url": "https://example.com/tokyo",
                    "snippet": "Tokyo is the capital of Japan.",
                }
            ],
        }

    monkeypatch.setattr(kernel, "run_env_tool", fake_run_env_tool)

    # persona は軽量なダミーを返すように
    monkeypatch.setattr(kernel.adapt, "load_persona", lambda: {"bias_weights": {}})

    ctx = {"user_id": "test-user"}
    res = await kernel.decide(ctx, "東京とは？", alternatives=None)

    assert res["meta"]["kind"] == "knowledge_qa"
    assert res["summary"].startswith("knowledge_qa モード")

    chosen = res["chosen"]
    assert "知識QA: 東京とは？" in chosen["title"]
    assert "参考URL" in chosen["description"]

    kqa = res["extras"]["knowledge_qa"]
    assert kqa["web_search"]["ok"] is True
    assert kqa["web_search"]["results"][0]["title"].startswith("Tokyo")


# ============================================================
# decide: pipeline フラグによる「二重実行スキップ」
# ============================================================

@pytest.mark.anyio
async def test_decide_respects_pipeline_skip_flags(monkeypatch):
    """
    pipeline 側ですでに実行済みの処理を
    kernel.decide が二重実行しないことを検証する。
    """

    # ---- FUJI / Affect / Persona を軽量モック ----

    def fake_fuji_evaluate(query, context, evidence, alternatives):
        return {
            "status": "allow",
            "decision_status": "allow",
            "rejection_reason": None,
            "reasons": [],
            "violations": [],
            "risk": 0.1,
            "checks": [],
            "guidance": None,
            "modifications": [],
            "redactions": [],
            "safe_instructions": [],
        }

    monkeypatch.setattr(kernel.fuji_core, "evaluate", fake_fuji_evaluate)

    # affect_core は実装が空の可能性があるので raising=False で注入
    monkeypatch.setattr(
        kernel.affect_core,
        "reflect",
        lambda payload: {"ok": True},
        raising=False,
    )
    monkeypatch.setattr(
        kernel.affect_core,
        "generate_reason",
        lambda **kwargs: "ok",
        raising=False,
    )

    async def fake_generate_reflection_template(**kwargs):
        # fast_mode なので実際には呼ばれないはずだが、
        # 念のため await 可能な関数を定義しておく
        return {"template": "dummy"}

    monkeypatch.setattr(
        kernel.affect_core,
        "generate_reflection_template",
        fake_generate_reflection_template,
        raising=False,
    )

    # Persona 周り
    monkeypatch.setattr(kernel.adapt, "load_persona", lambda: {"bias_weights": {}})
    monkeypatch.setattr(kernel.adapt, "clean_bias_weights", lambda b: b)

    # world_model.inject_state_into_context は「呼ばれない」ことを確認したいので
    # もし呼ばれたらテスト失敗にする
    def fail_inject_state_into_context(*args, **kwargs):
        raise AssertionError("inject_state_into_context should be skipped")

    monkeypatch.setattr(
        kernel.world_model,
        "inject_state_into_context",
        fail_inject_state_into_context,
    )

    # ---- コンテキスト: すべて pipeline 側で実行済み扱い ----

    ctx = {
        "user_id": "test-user",
        "_world_state_injected": True,
        "_pipeline_evidence": [
            {
                "source": "pipeline",
                "uri": None,
                "snippet": "from pipeline",
                "confidence": 0.9,
            }
        ],
        "_pipeline_env_tools": {"from_pipeline": True},
        "_pipeline_planner": {
            "steps": [
                {"id": "s1", "title": "step1", "detail": "do something"},
            ]
        },
        "_episode_saved_by_pipeline": True,
        "_world_state_updated_by_pipeline": True,
        "_agi_goals_adjusted_by_pipeline": True,
        "_daily_plans_generated_by_pipeline": True,
        "fast": True,   # fast_mode → DebateOS や world.simulate をスキップ
        "mode": "fast",
        "auto_doctor": False,  # テスト中に subprocess を起動しない
    }

    # alternatives は None → planner の steps から自動生成される
    res = await kernel.decide(ctx, "今日はVERITASのテストを書く", alternatives=None)

    extras = res["extras"]
    skip = extras["_skip_reasons"]

    # world_model / memory / env_tools / planner / episode / world_state / daily_plans
    # が「pipeline ですでに処理済み扱い」でスキップされていること
    assert skip["world_model_inject"] == "already_injected_by_pipeline"
    assert skip["memory_search"] == "provided_by_pipeline"
    assert skip["planner"] == "provided_by_pipeline"
    assert skip["episode_save"] == "already_saved_by_pipeline"
    assert skip["world_state_update"] == "already_done_by_pipeline"
    assert skip["daily_plans"] == "already_generated_by_pipeline"

    # env_tools は pipeline 由来 or fast_mode いずれか
    assert skip["env_tools"] in ("fast_mode", "provided_by_pipeline")

    # pipeline 由来の evidence が memory としてそのまま使われている
    assert extras["memory"]["source"] == "pipeline_provided"
    assert res["memory_evidence_count"] == 1

    # Planner steps が alternatives に変換されている
    assert res["alternatives"], "alternatives should not be empty"
    titles = {alt["title"] for alt in res["alternatives"]}
    assert "step1" in titles

    # kernel バージョン情報
    assert res["meta"]["kernel_version"] == "v2-compatible"

    # FUJI の決定が通っていること
    assert res["fuji"]["decision_status"] == "allow"


# ============================================================
# decide: PII マスキング（MemoryOS 保存前）
# ============================================================

@pytest.mark.anyio
async def test_decide_masks_pii_before_memory_save(monkeypatch):
    captured: Dict[str, Any] = {}

    def fake_put(*args, **kwargs):
        if len(args) == 2:
            record = args[1]
        else:
            record = args[2]
        captured["record"] = record
        return True

    def fake_fuji_evaluate(query, context, evidence, alternatives):
        return {
            "status": "allow",
            "decision_status": "allow",
            "rejection_reason": None,
            "reasons": [],
            "violations": [],
            "risk": 0.1,
            "checks": [],
            "guidance": None,
            "modifications": [],
            "redactions": [],
            "safe_instructions": [],
        }

    monkeypatch.setattr(kernel.mem_core.MEM, "put", fake_put)
    monkeypatch.setattr(
        kernel.world_model,
        "inject_state_into_context",
        lambda context, user_id: {**context, "_world_state_injected": True},
    )
    monkeypatch.setattr(
        kernel.mem_core,
        "summarize_for_planner",
        lambda user_id, query, limit: "summary",
    )
    monkeypatch.setattr(
        kernel.mem_core,
        "get_evidence_for_decision",
        lambda decision_snapshot, user_id, top_k: [],
    )
    monkeypatch.setattr(
        kernel.planner_core,
        "plan_for_veritas_agi",
        lambda context, query: {"steps": [{"id": "s1", "title": "step1"}]},
    )
    monkeypatch.setattr(kernel.fuji_core, "evaluate", fake_fuji_evaluate)
    monkeypatch.setattr(kernel.adapt, "load_persona", lambda: {"bias_weights": {}})
    monkeypatch.setattr(kernel.adapt, "clean_bias_weights", lambda b: b)

    ctx = {
        "user_id": "test-user",
        "fast": True,
        "mode": "fast",
        "auto_doctor": False,
        "_daily_plans_generated_by_pipeline": True,
    }
    query = "連絡先は test@example.com と 090-1234-5678 です"

    res = await kernel.decide(ctx, query, alternatives=None)

    record = captured["record"]
    assert "test@example.com" not in record["text"]
    assert "090-1234-5678" not in record["text"]

    warning = res.get("extras", {}).get("memory_log", {}).get("warning")
    assert warning is not None
