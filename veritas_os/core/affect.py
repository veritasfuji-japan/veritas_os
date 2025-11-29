# veritas/core/affect.py
from __future__ import annotations

KNOWN_STYLES = {
    "concise",
    "warm",
    "coach",
    "legal",
    "strategic",
    "friendly",
}

def choose_style(affect_hint: str | None) -> str:
    if not affect_hint:
        return "concise"
    key = str(affect_hint).strip().lower()
    if key in KNOWN_STYLES:
        return key
    # 部分一致とか日本語対応もここに追加できる
    if "優しく" in key or "やさしく" in key:
        return "warm"
    if "弁護士" in key or "法律" in key:
        return "legal"
    return "concise"
