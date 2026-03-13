# veritas_os/tests/test_reason.py

from __future__ import annotations

import json
import asyncio
from pathlib import Path
from typing import Any, Dict

import pytest

import veritas_os.core.reason as reason
from veritas_os.logging.paths import LOG_DIR as SHARED_LOG_DIR


# ------------------------------
# path configuration
# ------------------------------


def test_log_dir_uses_shared_logging_paths_config():
    """Reason モジュールが共通ログ設定を利用していることを検証する。"""
    assert reason.LOG_DIR == SHARED_LOG_DIR


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
    assert row["ts"].endswith("Z")
    assert "T" in row["ts"]
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


def test_reflect_boost_is_clamped_to_range(tmp_path, monkeypatch):
    """next_value_boost が上下限でクリップされることを検証する。"""
    meta_path = tmp_path / "meta_log.jsonl"
    monkeypatch.setattr(reason, "META_LOG", meta_path, raising=False)

    high = reason.reflect(
        {
            "query": "high",
            "chosen": {"title": "情報収集プラン"},
            "gate": {"risk": 0.0, "decision_status": "allow"},
            "values": {"total": 2.0, "ema": 1.0},
        }
    )
    low = reason.reflect(
        {
            "query": "low",
            "chosen": {"title": "通常プラン"},
            "gate": {"risk": 1.0, "decision_status": "allow"},
            "values": {"total": -1.0, "ema": 0.0},
        }
    )

    assert high["next_value_boost"] == 0.1
    assert low["next_value_boost"] == -0.1


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


def test_generate_reason_with_string_response(monkeypatch):
    """LLM が文字列を返した場合のフォールバック値を検証する。"""

    def stub_chat(*args, **kwargs):
        return "テキストのみの理由"

    monkeypatch.setattr(reason.llm_client, "chat", stub_chat)

    res = reason.generate_reason(query="fallback test")

    assert res == {
        "text": "テキストのみの理由",
        "source": "openai_llm",
    }


def test_generate_reason_llm_error(monkeypatch):
    """LLM 呼び出し例外時に error ソースで空文字を返す。"""

    def stub_chat(*args, **kwargs):
        raise ValueError("boom")

    monkeypatch.setattr(reason.llm_client, "chat", stub_chat)

    res = reason.generate_reason(query="error test")

    assert res == {"text": "", "source": "error"}


def test_generate_reason_without_text_uses_empty_string(monkeypatch):
    """LLMレスポンスがdictでも text 欠損時は空文字にフォールバックする。"""

    def stub_chat(*args, **kwargs):
        return {"source": "stub_only_source"}

    monkeypatch.setattr(reason.llm_client, "chat", stub_chat)

    res = reason.generate_reason(query="missing text")

    assert res == {"text": "", "source": "stub_only_source"}


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
        raise ValueError("LLM error")

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


def test_generate_reason_runtime_error_falls_back(monkeypatch):
    """RuntimeError 発生時も ReasonOS は安全にフォールバックする。"""

    def stub_chat(*args, **kwargs):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(reason.llm_client, "chat", stub_chat)

    res = reason.generate_reason(query="error test")

    assert res == {"text": "", "source": "error"}


def test_generate_reflection_template_runtime_error_falls_back(monkeypatch):
    """RuntimeError 発生時も空辞書へ安全にフォールバックする。"""

    def stub_chat(*args, **kwargs):
        raise RuntimeError("unexpected")

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


def test_generate_reflection_template_validates_required_inputs():
    """query または chosen が欠ける場合は即時に空辞書を返す。"""

    no_query = asyncio.run(
        reason.generate_reflection_template(
            query="",
            chosen={"title": "X"},
            gate={"risk": 0.1, "decision_status": "allow"},
            values={"total": 0.5, "ema": 0.5},
            planner={},
        )
    )
    no_chosen = asyncio.run(
        reason.generate_reflection_template(
            query="テスト",
            chosen={},
            gate={"risk": 0.1, "decision_status": "allow"},
            values={"total": 0.5, "ema": 0.5},
            planner={},
        )
    )

    assert no_query == {}
    assert no_chosen == {}


def test_generate_reflection_template_normalizes_tags_and_priority(monkeypatch):
    """tags 非配列と priority 範囲外値の正規化を検証する。"""

    def stub_chat(*args, **kwargs):
        payload = {
            "pattern": "相談パターン",
            "guidance": "追加ヒント",
            "tags": "not-a-list",
            "priority": "2.4",
        }
        return {"text": json.dumps(payload, ensure_ascii=False), "source": "stub"}

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

    assert tmpl["tags"] == ["reflection"]
    assert tmpl["priority"] == 1.0


def test_generate_reflection_template_accepts_string_llm_response(monkeypatch):
    """LLMが文字列JSONを返す場合もテンプレが生成される。"""

    def stub_chat(*args, **kwargs):
        return json.dumps(
            {
                "pattern": "文字列レスポンス",
                "guidance": "文字列JSONを許容する",
                "tags": ["reason"],
                "priority": "not-number",
            },
            ensure_ascii=False,
        )

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

    assert tmpl["pattern"] == "文字列レスポンス"
    assert tmpl["guidance"] == "文字列JSONを許容する"
    assert tmpl["tags"] == ["reason"]
    assert tmpl["priority"] == 0.5


def test_generate_reflection_template_missing_required_fields_returns_empty(monkeypatch):
    """pattern または guidance が空の場合は {} を返す。"""

    def stub_chat(*args, **kwargs):
        return {
            "text": json.dumps({"pattern": "", "guidance": ""}, ensure_ascii=False),
            "source": "stub",
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
