# veritas_os/core/kernel_intent.py
# -*- coding: utf-8 -*-
"""Intent heuristics helper for the kernel decision flow.

Ownership boundary:
- This module owns lightweight, non-core heuristics such as intent detection
  and hardcoded fallback option templates.
- ``kernel.py`` remains the core decision engine and consumes these helpers
  via compatibility wrappers.
- ``pipeline.py`` remains the orchestration layer and must not depend on
  heuristics from this module directly.
"""
from __future__ import annotations

import re
import uuid
from typing import List

from .types import OptionDict

INTENT_PATTERNS = {
    "weather": re.compile(r"(天気|気温|降水|雨|晴れ|weather|forecast)", re.I),
    "health": re.compile(r"(疲れ|だる|体調|休む|回復|睡眠|寝|サウナ)", re.I),
    "learn": re.compile(r"(とは|仕組み|なぜ|how|why|教えて|違い|比較)", re.I),
    "plan": re.compile(r"(計画|進め|やるべき|todo|最小ステップ|スケジュール|plan)", re.I),
}

INTENT_OPTION_TEMPLATES = {
    "weather": [
        "天気アプリ/サイトで明日の予報を確認する",
        "降水確率が高い時間にリマインドを設定する",
        "傘・レインウェア・防水靴を準備する",
    ],
    "health": [
        "今日は休息し回復を最優先にする",
        "15分の軽い散歩で血流を上げる",
        "短時間サウナ＋十分な水分補給を行う",
    ],
    "learn": [
        "一次情報（公式/論文）を調べる",
        "要点を3行に要約する",
        "学んだことを1つだけ行動に落とす",
    ],
    "plan": [
        "最小ステップで前進する",
        "情報収集を優先する",
        "今日は休息し回復に充てる",
    ],
}


def _mk_option(title: str, description: str = "") -> OptionDict:
    return OptionDict(
        id=uuid.uuid4().hex,
        title=title,
        description=description,
        score=1.0,
    )


def detect_intent(query: str) -> str:
    """Detect coarse intent for fallback alternative generation."""
    normalized = (query or "").strip().lower()
    for name, pattern in INTENT_PATTERNS.items():
        if pattern.search(normalized):
            return name
    return "plan"


def gen_options_by_intent(intent: str) -> List[OptionDict]:
    """Generate fallback alternatives from a small intent template map."""
    templates = INTENT_OPTION_TEMPLATES.get(intent, INTENT_OPTION_TEMPLATES["plan"])
    return [_mk_option(title) for title in templates]
