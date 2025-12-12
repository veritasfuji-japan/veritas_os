from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional


StyleKey = Literal[
    "concise",
    "neutral",
    "warm",
    "legal",
    "coach",
]

KNOWN_STYLES = {
    "concise",
    "neutral",
    "warm",
    "legal",
    "coach",
}


@dataclass
class AffectConfig:
    style: StyleKey = "concise"


def choose_style(hint: Optional[str]) -> str:
    """ユーザーのトーン指定から style キーを推定する軽いヘルパ。

    - 未指定/空文字 -> "concise"
    - 既知のスタイル文字列 -> そのまま
    - 日本語のニュアンスから "legal" / "warm" にマップ
    """
    if not hint:
        return "concise"

    # normalize
    key = str(hint).strip().lower()

    if not key:
        return "concise"

    # すでに既知のスタイルならそのまま返す
    if key in KNOWN_STYLES:
        return key

    # 日本語のヒントから推定
    if "弁護士" in key or "法律" in key or "法的" in key:
        return "legal"

    if "丁寧" in key or "やさしく" in key or "優しく" in key:
        return "warm"

    # それ以外はとりあえず簡潔モード
    return "concise"
