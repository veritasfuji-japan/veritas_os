# veritas_os/core/evidence.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Dict, List

# Evidence は dict ベースで扱う（テスト側が e["snippet"] アクセスを前提にしている）
Evidence = Dict[str, Any]


def _mk(
    *,
    source: str,
    kind: str,
    weight: float,
    snippet: str,
    tags: List[str] | None = None,
) -> Evidence:
    """内部用の小さなヘルパー。"""
    return {
        "source": source,
        "kind": kind,
        "weight": float(weight),
        "snippet": snippet,
        "tags": list(tags or []),
    }


def collect_local(intent: str, query: str, context: Dict[str, Any]) -> List[Evidence]:
    """
    DecisionOS が「ローカル・ヒューリスティクス」として追加するエビデンス群。

    - intent / query / context をざっくり見て、数件の Evidence(dict) を返す。
    - ここでは一切 LLM を呼ばず、決め打ちのルールだけを書く。
    """
    ev: List[Evidence] = []
    ctx = context or {}

    q = (query or "").strip()
    goals = ctx.get("goals") or []
    stakes_raw = ctx.get("stakes")
    constraints = ctx.get("constraints") or []

    # --- 疲労 / 健康まわりのヒューリスティクス ---------------------------
    if ("疲れ" in q) or any(g in ("健康", "回復") for g in goals):
        ev.append(
            _mk(
                source="local",
                kind="fatigue",
                weight=0.6,
                snippet=(
                    "疲労時は回復優先で判断した方が後悔が少ないことが多い。"
                    "最近の疲れ・体調・睡眠パターンもメモしておくと、後から自己分析しやすい。"
                ),
                tags=["selfcare", "health"],
            )
        )

    # --- stakes が高いときは『慎重側に倒す』という原則 --------------------
    stakes_val: float | None = None
    if stakes_raw is not None:
        try:
            stakes_val = float(stakes_raw)
        except (TypeError, ValueError):
            stakes_val = None

    if stakes_val is not None and stakes_val >= 0.7:
        ev.append(
            _mk(
                source="local",
                kind="stakes",
                weight=stakes_val,
                snippet=(
                    f"stakesが高いため慎重側に倒す方が後悔が少ないと想定する"
                    f"（現在のstakes={stakes_val:.2f}）。"
                ),
                tags=["stakes", "caution"],
            )
        )

    # --- 制約条件が指定されているときのメモ --------------------------------
    if constraints:
        if isinstance(constraints, str):
            constraints_list = [constraints]
        else:
            constraints_list = list(constraints)

        joined = " / ".join(str(c) for c in constraints_list)
        ev.append(
            _mk(
                source="local",
                kind="constraints",
                weight=0.5,
                snippet=f"制約: {joined} を前提に方針を組み立てる。",
                tags=["constraints"],
            )
        )

    # --- 天気関連（intent = weather） --------------------------------------
    if intent == "weather":
        ev.append(
            _mk(
                source="local",
                kind="weather",
                weight=0.5,
                snippet=(
                # ★ テストが "天候は影響大" を期待している
                    "天候は影響大なので、屋外活動・移動・体調への影響を"
                    "前提にスケジュールを組んだ方がよい。"
                ),
                tags=["weather", "context"],
            )
        )

        # --- 何もヒットしなかったときのフォールバック ------------------------
    if not ev:
        ev.append(
            _mk(
                source="local",
                kind="fallback",
                weight=0.2,
                snippet=(
                    "クエリの意図に沿うようスコアリング済みだが、"
                    "goals / stakes / constraints が指定されていないため、"
                    "まずは『どうなりたいか』『どれくらいリスクを取れるか』"
                    "『時間・お金などの制約』を一緒に整理すると意思決定の質が上がる。"
                ),
                tags=["meta", "fallback"],
            )
        )


    # 付けすぎてもノイズになるので 4 件まで
    return ev[:4]


