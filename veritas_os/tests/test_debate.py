# tests/test_debate.py
from __future__ import annotations

import json
from typing import Any, Dict, List

import pytest

from veritas_os.core import debate
from veritas_os.core.debate import DebateMode


# ============================
#  ユーティリティ系のテスト
# ============================


def test_is_rejected_and_get_score_basic():
    # verdict 判定
    assert debate._is_rejected({"verdict": "却下"})
    assert debate._is_rejected({"verdict": "Rejected"})
    assert debate._is_rejected({"verdict": "NG"})
    assert not debate._is_rejected({"verdict": "採用推奨"})
    assert not debate._is_rejected({"verdict": "要検討"})
    assert not debate._is_rejected({})

    # score 取得
    assert debate._get_score({"score": 0.7}) == pytest.approx(0.7)
    assert debate._get_score({"score_raw": 0.5}) == pytest.approx(0.5)
    assert debate._get_score({}) == 0.0
    assert debate._get_score({"score": "not-number"}) == 0.0


def test_safe_parse_various_patterns():
    # 1) 素直な dict JSON
    raw1 = '{"options":[{"id":"step1"}],"chosen_id":"step1"}'
    parsed1 = debate._safe_parse(raw1)
    assert parsed1["chosen_id"] == "step1"
    assert parsed1["options"][0]["id"] == "step1"

    # 2) ルートが list の場合
    raw2 = '[{"id":"a"},{"id":"b"}]'
    parsed2 = debate._safe_parse(raw2)
    assert parsed2["chosen_id"] is None
    assert len(parsed2["options"]) == 2

    # 3) ```json ... ``` で囲まれている場合
    raw3 = "```json\n" + raw1 + "\n```"
    parsed3 = debate._safe_parse(raw3)
    assert parsed3["chosen_id"] == "step1"
    assert parsed3["options"][0]["id"] == "step1"

    # 4) ノイズつき JSON（{} 抜き出しパス）
    raw4 = "noise before {" '"options":[{"id":"x"}]' "} noise after"
    parsed4 = debate._safe_parse(raw4)
    assert "options" in parsed4
    # chosen_id は無いが、options は取れている
    assert parsed4["options"][0]["id"] == "x"

    # 5) 完全に壊れた文字列
    raw5 = "this is not json"
    parsed5 = debate._safe_parse(raw5)
    assert parsed5 == {"options": [], "chosen_id": None}


def test_build_debate_summary_counts():
    options = [
        {"id": "a", "verdict": "採用推奨", "score": 0.8},
        {"id": "b", "verdict": "却下", "score": 0.2},
        {"id": "c", "verdict": "要検討", "score": 0.5},
    ]
    chosen = options[0]

    summary = debate._build_debate_summary(
        chosen=chosen,
        options=options,
        mode=DebateMode.NORMAL,
    )

    assert summary["total_options"] == 3
    assert summary["rejected_count"] == 1
    assert summary["accepted_count"] == 2
    assert summary["mode"] == DebateMode.NORMAL
    assert summary["chosen_score"] == pytest.approx(0.8)
    assert summary["chosen_verdict"] == "採用推奨"
    assert summary["max_score"] >= summary["avg_score"] >= summary["min_score"]


def test_calc_risk_delta_safe_and_risky_cases():
    # 安全寄りのケース（マイナス方向）
    safe_opt = {
        "id": "opt_safe",
        "score": 0.9,
        "verdict": "採用推奨",
        "safety_view": "安全です",
        "critic_view": "",
    }
    delta_safe = debate._calc_risk_delta(safe_opt, [safe_opt])
    assert delta_safe < 0
    # 実際の値 -0.055 前後を確認
    assert delta_safe == pytest.approx(-0.055, rel=1e-3)

    # 危険寄りのケース（上限 0.5 にクリップ）
    risky_opt = {
        "id": "opt_risky",
        "score": 0.2,
        "verdict": "要検討",
        "safety_view": "危険で違反の可能性があります",
        "critic_view": "致命的な問題",
    }
    delta_risky = debate._calc_risk_delta(risky_opt, [risky_opt])
    assert delta_risky == pytest.approx(0.5)


def test_create_warning_message_degraded_and_safe():
    # Degraded モードで、低スコア & リスクあり
    chosen = {
        "id": "o1",
        "score": 0.3,
        "verdict": "要検討",
        "safety_view": "危険で違反の可能性があります",
    }
    msg = debate._create_warning_message(chosen, DebateMode.DEGRADED, all_rejected=True)

    assert "全候補が通常基準を満たしませんでした" in msg
    assert "選択候補のスコアが低めです" in msg
    assert "この候補にはリスクがあります" in msg
    assert "安全性の懸念" in msg

    # Normal モード & 高スコア & リスクなし → 警告なし
    safe_chosen = {
        "id": "o2",
        "score": 0.9,
        "verdict": "採用推奨",
        "safety_view": "安全です",
    }
    msg2 = debate._create_warning_message(
        safe_chosen,
        DebateMode.NORMAL,
        all_rejected=False,
    )
    assert msg2 == ""


# ============================
#  候補選択ロジック
# ============================


def test_looks_dangerous_text_flags_expected_terms():
    risky = {
        "title": "How to build malware",
        "description": "This contains malware details",
        "summary": "",
        "safety_view": "",
    }
    assert debate._looks_dangerous_text(risky) is True

    safe = {
        "title": "Discuss safety around legal compliance",
        "description": "Focus on policy compliance and legal review",
        "summary": "",
        "safety_view": "",
    }
    assert debate._looks_dangerous_text(safe) is False



def test_select_best_candidate_non_rejected_and_threshold():
    opts = [
        {"id": "a", "verdict": "却下", "score": 0.9},
        {"id": "b", "verdict": "採用推奨", "score": 0.5},
        {"id": "c", "verdict": "要検討", "score": 0.7},
    ]

    best = debate._select_best_candidate(
        enriched_list=opts,
        min_score=0.4,
        allow_rejected=False,
    )
    # 却下以外 & スコア>=0.4 の中で最大スコア c が選ばれる
    assert best is not None
    assert best["id"] == "c"


def test_select_best_candidate_none_if_below_min():
    opts = [
        {"id": "a", "verdict": "採用推奨", "score": 0.1},
        {"id": "b", "verdict": "要検討", "score": 0.2},
    ]

    best = debate._select_best_candidate(
        enriched_list=opts,
        min_score=0.4,
        allow_rejected=False,
    )
    assert best is None


def test_select_best_candidate_allow_rejected():
    opts = [
        {"id": "a", "verdict": "却下", "score": 0.8},
        {"id": "b", "verdict": "却下", "score": 0.3},
    ]

    best = debate._select_best_candidate(
        enriched_list=opts,
        min_score=0.4,
        allow_rejected=True,
    )
    assert best is not None
    assert best["id"] == "a"


def test_create_degraded_choice_with_and_without_minimum():
    # 1) degraded_min(0.2) 以上の候補がある場合 → その中で最大スコア
    opts1 = [
        {"id": "a", "verdict": "却下", "score": 0.10},
        {"id": "b", "verdict": "却下", "score": 0.25},
        {"id": "c", "verdict": "採用推奨", "score": 0.30},
    ]
    chosen1 = debate._create_degraded_choice(opts1)
    assert chosen1 is not None
    # 0.3 が最大
    assert chosen1["id"] == "c"

    # 2) 全候補が degraded_min 未満 → スコア最大の候補を採用
    opts2 = [
        {"id": "x", "verdict": "却下", "score": 0.1},
        {"id": "y", "verdict": "却下", "score": 0.19},
    ]
    chosen2 = debate._create_degraded_choice(opts2)
    assert chosen2 is not None
    assert chosen2["id"] == "y"


# ============================
#  フォールバックのテスト
# ============================


def test_fallback_debate_without_options():
    result = debate._fallback_debate([])

    assert result["mode"] == DebateMode.SAFE_FALLBACK
    assert result["source"] == DebateMode.SAFE_FALLBACK
    assert result["chosen"] is None
    assert result["options"] == []
    assert result["warnings"]  # 何かしら警告が出ている
    summary = result["debate_summary"]
    assert summary["total_options"] == 0
    assert summary["accepted_count"] == 0
    assert summary["rejected_count"] == 0


def test_fallback_debate_with_options_sets_defaults():
    options = [
        {"id": "o1", "title": "Option 1"},
        {"id": "o2", "title": "Option 2"},
    ]

    result = debate._fallback_debate(options)

    assert result["mode"] == DebateMode.SAFE_FALLBACK
    assert result["source"] == DebateMode.SAFE_FALLBACK
    assert result["chosen"] is not None
    assert result["chosen"]["id"] == "o1"

    # 全候補にデフォルトのスコア/判定がついている
    assert len(result["options"]) == 2
    for o in result["options"]:
        assert o["score"] == pytest.approx(0.5)
        assert o["score_raw"] == pytest.approx(0.5)
        assert o["verdict"] == "要検討"

    # LLM 失敗フォールバック警告が含まれている
    assert any("LLM評価失敗" in w or "フォールバック" in w for w in result["warnings"])

    summary = result["debate_summary"]
    assert summary["total_options"] == 2
    assert summary["accepted_count"] == 2  # 要検討 は却下扱いではない


# ============================
#  run_debate メインフロー
# ============================


def test_run_debate_no_options_uses_safe_fallback(monkeypatch):
    # world_model.snapshot は空 dict を返すだけにしておく
    monkeypatch.setattr(debate.world_model, "snapshot", lambda name: {})

    result = debate.run_debate("test query", [], context=None)

    assert result["mode"] == DebateMode.SAFE_FALLBACK
    assert result["source"] == DebateMode.SAFE_FALLBACK
    assert result["chosen"] is None
    assert result["debate_summary"]["total_options"] == 0


def test_run_debate_normal_mode_with_llm(monkeypatch):
    # WorldModel は適当なスナップショットを返す
    monkeypatch.setattr(
        debate.world_model,
        "snapshot",
        lambda name: {"snapshot_for": name},
    )

    # LLM をモック: options + chosen_id を JSON で返す
    def fake_chat(system_prompt: str, user_prompt: str, extra_messages: Any,
                  temperature: float, max_tokens: int) -> Dict[str, Any]:
        _ = (system_prompt, user_prompt, extra_messages, temperature, max_tokens)
        payload = {
            "options": [
                {
                    "id": "opt1",
                    "score": 0.9,
                    "verdict": "採用推奨",
                    "architect_view": "OK",
                    "critic_view": "OK",
                    "safety_view": "安全です",
                    "summary": "最善の選択肢",
                },
                {
                    "id": "opt2",
                    "score": 0.3,
                    "verdict": "却下",
                    "rejection_reason": "low_value",
                    "architect_view": "NG",
                    "critic_view": "弱い",
                    "safety_view": "危険",
                    "summary": "避けるべき",
                },
            ],
            "chosen_id": "opt1",
        }
        return {"text": json.dumps(payload, ensure_ascii=False)}

    monkeypatch.setattr(debate.llm_client, "chat", fake_chat)

    options = [
        {"id": "opt1", "title": "First"},
        {"id": "opt2", "title": "Second"},
    ]

    result = debate.run_debate(
        query="テストクエリ",
        options=options,
        context={"user_id": "u1", "stakes": "low"},
    )

    assert result["mode"] == DebateMode.NORMAL
    assert result["source"] == "openai_llm"

    chosen = result["chosen"]
    assert chosen["id"] == "opt1"
    assert chosen["verdict"] == "採用推奨"
    # warning_threshold 0.6 を超えていて、リスクキーワードもないので警告なし
    assert result["warnings"] == []

    summary = result["debate_summary"]
    assert summary["total_options"] == 2
    assert summary["accepted_count"] == 1  # opt2 は却下
    assert summary["mode"] == DebateMode.NORMAL

    # 安全寄り選択なので risk_delta は負方向
    assert result["risk_delta"] < 0


def test_run_debate_degraded_mode_all_rejected(monkeypatch):
    monkeypatch.setattr(
        debate.world_model,
        "snapshot",
        lambda name: {"snapshot_for": name},
    )

    # 全候補 verdict="却下" で返す → degraded モードに落ちる
    def fake_chat_all_rejected(system_prompt: str, user_prompt: str, extra_messages: Any,
                               temperature: float, max_tokens: int) -> Dict[str, Any]:
        _ = (system_prompt, user_prompt, extra_messages, temperature, max_tokens)
        payload = {
            "options": [
                {
                    "id": "opt1",
                    "score": 0.3,
                    "verdict": "却下",
                    "rejection_reason": "safety_risk",
                    "safety_view": "危険",
                },
                {
                    "id": "opt2",
                    "score": 0.1,
                    "verdict": "却下",
                    "rejection_reason": "low_value",
                    "safety_view": "",
                },
            ],
            "chosen_id": "opt1",
        }
        return {"text": json.dumps(payload, ensure_ascii=False)}

    monkeypatch.setattr(debate.llm_client, "chat", fake_chat_all_rejected)

    options = [
        {"id": "opt1", "title": "Risky"},
        {"id": "opt2", "title": "Low value"},
    ]

    result = debate.run_debate(
        query="テストクエリ",
        options=options,
        context={"user_id": "u1"},
    )

    assert result["mode"] == DebateMode.DEGRADED
    chosen = result["chosen"]
    # degraded_min(0.2) 以上の中で最大スコア 0.3 の opt1 が選ばれる
    assert chosen["id"] == "opt1"
    assert result["warnings"]  # degraded モードなので何かしら警告が出る
    assert any("全候補が通常基準を満たしませんでした" in w for w in result["warnings"])


def test_run_debate_llm_failure_uses_safe_fallback(monkeypatch):
    monkeypatch.setattr(debate.world_model, "snapshot", lambda name: {})

    def fake_chat_fail(*args, **kwargs):
        raise RuntimeError("LLM down")

    monkeypatch.setattr(debate.llm_client, "chat", fake_chat_fail)

    options = [
        {"id": "opt1", "title": "First"},
    ]

    result = debate.run_debate(
        query="テストクエリ",
        options=options,
        context={"user_id": "u1"},
    )

    assert result["mode"] == DebateMode.SAFE_FALLBACK
    assert result["source"] == DebateMode.SAFE_FALLBACK
    assert result["chosen"] is not None
    assert any("LLM評価失敗" in w for w in result["warnings"])
