# tests/test_kernel_core_extra.py
# -*- coding: utf-8 -*-
"""
kernel カバレッジを底上げする追加テスト群。

- decide() の複数モードの分岐
- simple QA 判定のネガティブパス
- ValueCore 経由のオプションスコアリング
などを叩いて、core/kernel.py の分岐を広くカバーする。

ここでは pytest-anyio / anyio / trio には一切依存しない。
すべて同期テストの中で asyncio.run() を使って decide() を呼び出す。
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Dict, List

import pytest

from veritas_os.core import kernel


# ------------------------------------------------------------
# ヘルパー: decide() を「シグネチャに追従しながら」安全に呼び出す
# ------------------------------------------------------------

def _call_decide_generic(
    query: str,
    base_context: Dict[str, Any] | None = None,
    **extra_kwargs: Any,
) -> Any:
    """
    kernel.decide のシグネチャを動的に解析して、
    存在する引数だけを詰めて呼び出す汎用ヘルパー。

    - query は基本必須
    - context があれば base_context を渡す
    - extra_kwargs（fast / mode / return_pipeline 等）は、
      decide のシグネチャに存在するものだけを渡す
    """
    decide = kernel.decide
    sig = inspect.signature(decide)

    kwargs: Dict[str, Any] = {}

    for name, param in sig.parameters.items():
        if name == "query":
            kwargs["query"] = query
        elif name == "context":
            kwargs["context"] = base_context or {}
        elif name in extra_kwargs:
            kwargs[name] = extra_kwargs[name]
        elif (
            param.default is inspect._empty
            and name not in ("query", "context")
            and name not in extra_kwargs
        ):
            # その他の必須引数はとりあえず None を渡す（多くの場合許容される）
            kwargs[name] = None

    if inspect.iscoroutinefunction(decide):
        # decide が async def の場合は asyncio.run() で実行
        return asyncio.run(decide(**kwargs))
    else:
        # sync 関数なら普通に呼ぶ
        return decide(**kwargs)


# ------------------------------------------------------------
# 1. simple_qa 判定のネガティブパス (fallback パス)
# ------------------------------------------------------------

def test_detect_simple_qa_non_matching_returns_none():
    """
    時刻・日付・曜日などにマッチしない質問は None になるパスを明示的に通す。
    """
    if not hasattr(kernel, "_detect_simple_qa"):
        pytest.skip("_detect_simple_qa が存在しないバージョン")

    assert kernel._detect_simple_qa("カレーは好き？") is None
    assert kernel._detect_simple_qa("VERITAS OS って何色？") is None


# ------------------------------------------------------------
# 2. decide(): fast / 通常 / デバッグ系フラグを叩く
# ------------------------------------------------------------

def test_decide_fast_flag_path():
    """
    fast=True（が存在する場合）で、通常より軽い経路に入る分岐を通す。
    decide 側に fast パラメータが無い場合は単に無視される。
    """
    base_ctx = {
        "env": {},
        "pipeline": {},
        "meta": {"test_case": "fast_mode"},
    }

    result = _call_decide_generic(
        "今何時？",
        base_context=base_ctx,
        fast=True,
    )

    assert result is not None
    assert isinstance(result, dict)


def test_decide_plan_or_debug_mode_path():
    """
    mode / debug 的なフラグがある場合に、
    そちらの分岐に入ることだけを確認するテスト。

    - mode="plan_only" や mode="debug" 等があればそこに乗る
    - 無ければ通常パスで実行されるだけなので、それでも OK
    """
    base_ctx = {
        "env": {},
        "pipeline": {},
        "meta": {"test_case": "plan_or_debug"},
    }

    candidate_modes = ["plan_only", "debug", "self_coach"]
    mode_to_try = candidate_modes[0]

    result = _call_decide_generic(
        "明日のタスクを整理して",
        base_context=base_ctx,
        mode=mode_to_try,
        return_pipeline=True,
    )

    assert result is not None
    assert isinstance(result, dict)


def test_decide_with_existing_pipeline_context():
    """
    すでに pipeline の一部が走った前提（例: evidence 済み）で decide を呼ぶパス。

    これにより kernel 側の
    「既存 pipeline 状態を尊重してスキップする」枝が増えてカバレッジが上がる。
    """
    base_ctx = {
        "env": {},
        "pipeline": {
            "evidence_already_collected": True,
            "plan_already_built": False,
        },
        "meta": {"test_case": "existing_pipeline"},
    }

    result = _call_decide_generic(
        "VERITAS OS の今日のタスクを 3 つに整理して",
        base_context=base_ctx,
    )

    assert result is not None
    assert isinstance(result, dict)


# ------------------------------------------------------------
# 3. ValueCore 経由のオプションスコアリングを複数パターンで叩く
# ------------------------------------------------------------

def test_score_alternatives_with_value_core_multi(monkeypatch):
    """
    _score_alternatives_with_value_core_and_persona() を
    「候補3つ」「persona 有 / 無」の両パターンで叩いて、
    内部ループと条件分岐を広くカバーする。
    """
    if not hasattr(kernel, "_score_alternatives_with_value_core_and_persona"):
        pytest.skip("_score_alternatives_with_value_core_and_persona が存在しないバージョン")

    scored_calls: List[Dict[str, Any]] = []

    class DummyOptionScore:
        def __init__(self, **kwargs: Any) -> None:
            scored_calls.append(kwargs)
            self.total = kwargs.get("raw_score", 0.0)
            self.label = kwargs.get("label", "")

    # kernel モジュール経由で value_core.OptionScore を差し替える
    monkeypatch.setattr(kernel.value_core, "OptionScore", DummyOptionScore)

    alts = [
        {"id": "A", "text": "Option A"},
        {"id": "B", "text": "Option B"},
        {"id": "C", "text": "Option C"},
    ]

    # persona / telos あり
    res1 = kernel._score_alternatives_with_value_core_and_persona(
        alternatives=alts,
        persona={"traits": ["慎重", "長期志向"]},
        telos={"goals": ["AGI 安全", "可監査性"]},
        value_prefs={"risk_tolerance": 0.2},
    )

    # persona / telos なし（fallback パス）
    res2 = kernel._score_alternatives_with_value_core_and_persona(
        alternatives=alts,
        persona=None,
        telos=None,
        value_prefs={},
    )

    assert len(res1) == len(alts)
    assert len(res2) == len(alts)
    assert len(scored_calls) >= 3


# ------------------------------------------------------------
# 4. simple QA ヘルパがあれば叩いておく（存在しない場合は skip）
# ------------------------------------------------------------

def test_simple_qa_helper_if_available():
    """
    kernel 側に simple QA 用の公開ヘルパがあれば叩いておく。
    これにより simple_qa 系の分岐をさらに増やせる。
    """
    simple_qa_fn = getattr(kernel, "simple_qa", None)
    if simple_qa_fn is None:
        pytest.skip("simple_qa ヘルパが存在しないバージョン")

    result = simple_qa_fn("今日の日付を教えて")
    assert result is not None
    assert isinstance(result, dict)



