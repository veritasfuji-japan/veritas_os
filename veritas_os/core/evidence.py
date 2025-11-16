# veritas/core/evidence.py
# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Any, Dict, List

Evidence = Dict[str, Any]

def _mk(source: str, snippet: str, confidence: float = 0.7, uri: str | None = None) -> Evidence:
    return {
        "source": source,
        "uri": uri,
        "snippet": snippet,
        "confidence": float(confidence),
    }

def collect_local(intent: str, query: str, context: Dict[str, Any]) -> List[Evidence]:
    """外部通信なし。クエリ/文脈から即席の妥当根拠を生成。"""
    ev: List[Evidence] = []
    stakes = (context or {}).get("stakes", 0.5)
    goals  = (context or {}).get("goals") or []
    constraints = (context or {}).get("constraints") or []

    if intent == "weather":
        ev.append(_mk("internal:model",
                      "明日の計画に天候は影響大。事前確認と装備準備でリスク低減。",
                      0.75))
    if intent == "health":
        if "疲れ" in (query or "") or any(g in ("健康","回復") for g in goals):
            ev.append(_mk("internal:model",
                          "疲労時は回復優先が生産性を総和で底上げする（翌日の成果へ寄与）。",
                          0.72))
    if stakes and float(stakes) >= 0.7:
        ev.append(_mk("internal:model", "stakesが高いため慎重側（情報収集/休息）を優遇。", 0.68))

    if constraints:
        ev.append(_mk("internal:policy", f"制約: {', '.join(constraints)} を遵守する。", 0.7))

    # 1件も作れなかった時の保険
    if not ev:
        ev.append(_mk("internal:model", "選択肢はクエリの意図に沿うようスコアリング済み。", 0.6))
    return ev[:4]  # 付けすぎない
