# veritas_os/core/affect.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, TypedDict, cast

# Backward-compat delegates (kernel.py から affect_core 経由で呼ばれるため)
from veritas_os.core import reason as reason_core


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


@dataclass(frozen=True)
class AffectConfig:
    """Affectの設定。

    style:
      - concise: 端的・箇条書き・冗長回避
      - neutral: 中立・説明的
      - warm: 丁寧・共感的
      - legal: 法務/フォレンジック調・事実と推測の峻別
      - coach: コーチ/伴走・次アクション重視
    """
    style: StyleKey = "concise"


@dataclass(frozen=True)
class AffectState:
    """パイプラインに渡すAffect状態（ログしやすい最小セット）。"""
    style: StyleKey
    hint: Optional[str] = None


class ChatMessage(TypedDict, total=False):
    role: str
    content: str
    name: str


def normalize_style(key: Optional[str]) -> StyleKey:
    """任意文字列→StyleKeyに正規化（不明は concise）。"""
    if not key:
        return "concise"
    k = str(key).strip().lower()
    if not k:
        return "concise"
    if k in KNOWN_STYLES:
        return cast(StyleKey, k)
    return "concise"


def choose_style(hint: Optional[str]) -> str:
    """ユーザーのトーン指定から style キーを推定する軽いヘルパ。

    - 未指定/空文字 -> "concise"
    - 既知のスタイル文字列 -> そのまま
    - 日本語のニュアンスから "legal" / "warm" にマップ
    """
    if not hint:
        return "concise"

    key = str(hint).strip().lower()
    if not key:
        return "concise"

    if key in KNOWN_STYLES:
        return key

    # 日本語のヒントから推定
    if "弁護士" in key or "法律" in key or "法的" in key:
        return "legal"

    if "丁寧" in key or "やさしく" in key or "優しく" in key:
        return "warm"

    return "concise"


def make_affect_state(hint: Optional[str], default: StyleKey = "concise") -> AffectState:
    """hint → AffectState を作る（パイプライン向け）。"""
    if hint is None or str(hint).strip() == "":
        return AffectState(style=default, hint=hint)

    style = normalize_style(choose_style(hint))
    return AffectState(style=style, hint=hint)


def style_instructions(style: Any) -> str:
    """LLMへ渡す「口調・出力規範」。

    - 監査性/テスト安定のため、必ず STYLE=<key> を含める
    - 引数は StyleKey 想定だが、外部からの生値混入に備えて normalize する
    """
    sk = normalize_style(str(style) if style is not None else None)

    # 必ず style キーを含める（テスト安定 + ログ追跡）
    tag = f"STYLE={sk}"

    if sk == "concise":
        body = (
            "Write concisely. Prefer bullet points. "
            "Avoid unnecessary filler. Be direct and actionable."
        )
    elif sk == "neutral":
        body = (
            "Write neutrally and clearly. "
            "Explain reasoning briefly. Avoid emotional tone."
        )
    elif sk == "warm":
        body = (
            "Write warmly and supportive. "
            "Be practical and kind. Use gentle wording, but stay clear."
        )
    elif sk == "legal":
        body = (
            "Write in a legal/forensic tone. "
            "Explicitly distinguish FACT vs INFERENCE. "
            "Use structured headings and precise language. "
            "Avoid overstating certainty."
        )
    elif sk == "coach":
        body = (
            "Write as a coach. "
            "Focus on next actions and checkpoints. "
            "If questions are needed, ask the minimum number of specific questions."
        )
    else:
        body = "Write concisely."

    return f"{tag}\n{body}"


def apply_style(prompt: str, style: Any) -> str:
    """単一prompt向け：style規範を先頭に付与して返す。

    - style が未知でも normalize して安全にフォールバック
    """
    instr = style_instructions(style).strip()
    if not instr:
        return prompt or ""
    if not prompt:
        return instr
    return f"{instr}\n\n{prompt}"


def apply_style_to_messages(messages: List[ChatMessage], style: Any) -> List[ChatMessage]:
    """Chat messages 先頭に system 規範を差し込む。"""
    instr = style_instructions(style).strip()
    if not instr:
        return list(messages or [])

    msgs = list(messages or [])
    if msgs and msgs[0].get("role") == "system":
        prev = msgs[0].get("content", "")
        merged = f"{instr}\n\n{prev}".strip() if prev else instr
        msgs[0] = {**msgs[0], "content": merged}
        return msgs

    return [{"role": "system", "content": instr}, *msgs]


def as_dict(state: AffectState) -> Dict[str, str]:
    """ログ/メトリクス用の軽い辞書化。"""
    return {
        "style": state.style,
        "hint": "" if state.hint is None else str(state.hint),
    }


# =========================
# Backward compatibility (ReasonOS delegate)
# =========================

def generate_reason(**kwargs: Any) -> Dict[str, Any]:
    """旧API互換：ReasonOS.generate_reason へ委譲。"""
    return reason_core.generate_reason(**kwargs)


async def generate_reflection_template(**kwargs: Any) -> Dict[str, Any]:
    """旧API互換：ReasonOS.generate_reflection_template へ委譲。"""
    return await reason_core.generate_reflection_template(**kwargs)


__all__ = [
    "StyleKey",
    "KNOWN_STYLES",
    "AffectConfig",
    "AffectState",
    "ChatMessage",
    "normalize_style",
    "choose_style",
    "make_affect_state",
    "style_instructions",
    "apply_style",
    "apply_style_to_messages",
    "as_dict",
    "generate_reason",
    "generate_reflection_template",
]


