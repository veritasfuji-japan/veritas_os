# veritas_os/tests/test_reason.py

from __future__ import annotations

import json
import asyncio
from pathlib import Path
from typing import Any, Dict

import pytest

import veritas_os.core.reason as reason


# ------------------------------
# reflect
# ------------------------------

def test_reflect_basic_and_log_written(tmp_path, monkeypatch):
    """
    reflect:
      - 基本パスで next_value_boost がレンジ内
      - meta_log.jsonl に1行書き込まれる
    """
    # ログパスを一時ディレクトリに差し替え
    meta_path = tmp_path / "meta_log.jsonl"
    monkeypatch.setattr(reason, "META_LOG", meta_path, raising=False)

    decision: Dict[str, Any] = {
        "query": "Hello World",
        "chosen": {"title": "テストプラン"},
        "gate": {},
        "values": {},
    }

    out = reason.reflect(decision)

    assert out["query"] == "hello world"
    assert -0.1 <= out["next_value_boost"] <= 0.1
    assert out["chosen_title"] == "テストプラン"

    # ログファイルが作成されていること
    assert meta_path.exists()
    lines = meta_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1

    row = json.loads(lines[0])
    assert row["query"] == "hello world"
    assert "next_value_boost" in row


def test_reflect_high_risk_low_value_and_rejected(tmp_path, monkeypatch):
    """
    高リスク + 低EMA + rejected のとき:
      - 改善tipsが3つ入る
      - boost はマイナス寄りになる
    """
    meta_path = tmp_path / "meta_log.jsonl"
    monkeypatch.setattr(reason, "META_LOG", meta_path, raising=False)

    decision: Dict[str, Any] = {
        "query": "危険なクエリ",
        "chosen": {"title": "通常プラン"},
        "gate": {"risk": 0.7, "decision_status": "rejected"},
        "values": {"total": 0.2, "ema": 0.4},
    }

    out = reason.reflect(decision)

    tips = out["improvement_tips"]
    assert any("高リスク" in t for t in tips)
    assert any("低価値EMA" in t for t in tips)
    assert any("拒否" in t for t in tips)
    assert len(tips) == 3

    assert out["next_value_boost"] < 0.0


def test_reflect_info_gathering_boost(tmp_path, monkeypatch):
    """
    「情報収集」を含むタイトル + 高EMA のときは
    boost がプラス寄りになる。
    """
    meta_path = tmp_path / "meta_log.jsonl"
    monkeypatch.setattr(reason, "META_LOG", meta_path, raising=False)

    decision: Dict[str, Any] = {
        "query": "AGI ロードマップ",
        "chosen": {"title": "情報収集プランA"},
        "gate": {"risk": 0.1, "decision_status": "allow"},
        "values": {"total": 0.9, "ema": 0.8},
    }

    out = reason.reflect(decision)
    assert out["next_value_boost"] > 0.0


# ------------------------------
# generate_reason
# ------------------------------

def test_generate_reason_calls_llm_client(monkeypatch):
    """
    generate_reason が llm_client.chat を適切なペイロードで呼び出し、
    text / source をそのまま返すこと。
    """
    called = {}

    def stub_chat(system_prompt, user_prompt, temperature, max_tokens):
        called["system_prompt"] = system_prompt
        called["user_prompt"] = user_prompt
        called["temperature"] = temperature
        called["max_tokens"] = max_tokens
        return {
            "text": "これは理由です。",
            "source": "stub_llm",
        }

    monkeypatch.setattr(reason.llm_client, "chat", stub_chat)

    res = reason.generate_reason(
        query="なぜこの決定なのか？",
        planner={"steps": ["s1", "s2"]},
        values={"total": 0.8},
        gate={"risk": 0.2},
        context={"note": "test"},
    )

    assert res["text"] == "これは理由です。"
    assert res["source"] == "stub_llm"

    # user_prompt に各セクションが含まれていること
    up = called["user_prompt"]
    assert "# Query" in up
    assert "# Planner" in up
    assert "# Values" in up
    assert "# Gate" in up
    assert "# Context" in up


# ------------------------------
# generate_reflection_template
# ------------------------------

def test_generate_reflection_template_success(tmp_path, monkeypatch):
    """
    generate_reflection_template:
      - LLM が正しい JSON を返した場合にテンプレが生成される
      - meta_log.jsonl にも1行記録される
    """
    meta_path = tmp_path / "meta_log.jsonl"
    monkeypatch.setattr(reason, "META_LOG", meta_path, raising=False)

    def stub_chat(system_prompt, user_prompt, temperature, max_tokens):
        payload = {
            "pattern": "AGIロードマップ相談",
            "guidance": "まず現在の状況と ValueCore を要約してから回答すること。",
            "tags": ["agi", "veritas", "roadmap"],
            "priority": 0.9,
        }
        return {
            "text": json.dumps(payload, ensure_ascii=False),
            "source": "stub_llm",
        }

    monkeypatch.setattr(reason.llm_client, "chat", stub_chat)

    tmpl = asyncio.run(
        reason.generate_reflection_template(
            query="AGI ロードマップを相談したい",
            chosen={"title": "AGI ロードマップ案", "verdict": "ok"},
            gate={"risk": 0.2, "decision_status": "allow"},
            values={"total": 0.8, "ema": 0.7},
            planner={"steps": ["collect", "plan"]},
        )
    )

    assert tmpl["pattern"] == "AGIロードマップ相談"
    assert "ValueCore" in tmpl["guidance"]
    assert "agi" in tmpl["tags"]
    assert 0.0 <= tmpl["priority"] <= 1.0

    # メタログに reflection_template 行が書かれていること
    assert meta_path.exists()
    lines = meta_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    meta = json.loads(lines[0])
    assert meta["type"] == "reflection_template"
    assert meta["pattern"] == "AGIロードマップ相談"


def test_generate_reflection_template_llm_error(monkeypatch):
    """
    LLM 側で例外が出た場合は {} を返す。
    """

    def stub_chat(*args, **kwargs):
        raise RuntimeError("LLM error")

    monkeypatch.setattr(reason.llm_client, "chat", stub_chat)

    tmpl = asyncio.run(
        reason.generate_reflection_template(
            query="テスト",
            chosen={"title": "X"},
            gate={"risk": 0.1, "decision_status": "allow"},
            values={"total": 0.5, "ema": 0.5},
            planner={},
        )
    )

    assert tmpl == {}


def test_generate_reflection_template_bad_json(monkeypatch, tmp_path):
    """
    LLM から JSON でない文字列が返った場合も {} を返す。
    """
    meta_path = tmp_path / "meta_log.jsonl"
    monkeypatch.setattr(reason, "META_LOG", meta_path, raising=False)

    def stub_chat(system_prompt, user_prompt, temperature, max_tokens):
        return {
            "text": "これは JSON ではありません",
            "source": "stub_llm",
        }

    monkeypatch.setattr(reason.llm_client, "chat", stub_chat)

    tmpl = asyncio.run(
        reason.generate_reflection_template(
            query="テスト",
            chosen={"title": "X"},
            gate={"risk": 0.1, "decision_status": "allow"},
            values={"total": 0.5, "ema": 0.5},
            planner={},
        )
    )

    assert tmpl == {}
    # JSONパース失敗してもログには何も書かれないはず
    assert not meta_path.exists()


