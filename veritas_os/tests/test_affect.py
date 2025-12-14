# tests/test_affect.py
# -*- coding: utf-8 -*-

import pytest

from veritas_os.core import affect as affect_mod
from veritas_os.core.affect import (
    choose_style,
    normalize_style,
    style_instructions,
    apply_style,
)


# =========================
# choose_style
# =========================

@pytest.mark.parametrize(
    "hint, expected",
    [
        (None, "concise"),        # デフォルト
        ("", "concise"),
        ("   ", "concise"),
        ("neutral", "neutral"),   # 既知スタイル
        ("warm", "warm"),
        ("WARM", "warm"),         # 大文字も normalize される前提
        (" legal  ", "legal"),    # 前後空白
        ("coach", "coach"),
    ],
)
def test_choose_style_known_and_default(hint, expected):
    assert choose_style(hint) == expected


@pytest.mark.parametrize(
    "hint",
    [
        "優しく教えて",
        "やさしく説明してほしい",
        "優しく丁寧に",
        "丁寧にお願いします",
    ],
)
def test_choose_style_japanese_warm(hint):
    assert choose_style(hint) == "warm"


@pytest.mark.parametrize(
    "hint",
    [
        "弁護士風でお願い",
        "法律家的なトーンで",
        "法的な観点から説明して",
        "法律の話として整理して",
    ],
)
def test_choose_style_japanese_legal(hint):
    assert choose_style(hint) == "legal"


def test_choose_style_fallback_for_unknown_hint():
    # 既知スタイルにも日本語パターンにもマッチしない場合は concise にフォールバック
    style = choose_style("超攻撃的にディベートして")
    assert style == "concise"


# =========================
# normalize_style
# =========================

@pytest.mark.parametrize(
    "raw, expected",
    [
        (None, "concise"),
        ("", "concise"),
        ("   ", "concise"),
        ("WARM", "warm"),
        (" legal ", "legal"),
        ("neutral", "neutral"),
        ("coach", "coach"),
        ("unknown-style", "concise"),  # 不明は落とさずデフォルトへ
    ],
)
def test_normalize_style(raw, expected):
    assert normalize_style(raw) == expected


# =========================
# style_instructions
# =========================

@pytest.mark.parametrize("style", ["concise", "neutral", "warm", "legal", "coach"])
def test_style_instructions_non_empty_and_contains_style_key(style):
    """
    仕様:
      - 既知 style なら空文字は返さない
      - 監査性/可観測性のため、返却テキスト内に style キー（小文字）が含まれること
        (例: "STYLE=legal" など。実装表現は自由だが、style文字列が含まれることを要求)
    """
    instr = style_instructions(style)
    assert isinstance(instr, str)
    assert instr.strip() != ""
    assert style in instr.lower()


def test_style_instructions_unknown_returns_default_or_non_empty():
    """
    未知 style は normalize_style を通す想定だが、
    style_instructions 単体でも壊れないこと（落とさない）を要求。
    """
    instr = style_instructions("unknown-style")
    assert isinstance(instr, str)
    assert instr.strip() != ""


# =========================
# apply_style
# =========================

def test_apply_style_prefixes_instructions_and_preserves_original_prompt():
    base = "You are a helpful assistant.\nReturn JSON."
    out = apply_style(base, "legal")
    assert isinstance(out, str)
    # instruction が先頭側に入り、元のbaseは消えない
    assert base in out
    # styleキーがどこかに含まれる（style_instructions仕様と整合）
    assert "legal" in out.lower()
    # 2つ以上のブロックに分かれている（注入されている）
    assert "\n\n" in out


def test_apply_style_when_system_prompt_is_empty_returns_instructions_only():
    out = apply_style("", "warm")
    assert isinstance(out, str)
    assert out.strip() != ""
    assert "warm" in out.lower()


def test_apply_style_unknown_style_falls_back_safely():
    out = apply_style("SYS", "unknown-style")
    assert isinstance(out, str)
    assert out.strip() != ""
    # unknown は concise に落ちる想定（normalize_style仕様）
    assert "concise" in out.lower()
    assert "SYS" in out


# =========================
# Backward compatibility wrappers
#   affect.generate_reason / affect.generate_reflection_template
# =========================

def test_generate_reason_delegates_to_reason_module(monkeypatch):
    """
    kernel.py が affect_core.generate_reason(...) を呼ぶ前提なので、
    affect.py 側に “薄い委譲” が存在することを要求。
    """

    calls = {"n": 0, "kwargs": None}

    def fake_generate_reason(**kwargs):
        calls["n"] += 1
        calls["kwargs"] = dict(kwargs)
        return {"ok": True, "reason": "dummy"}

    # affect_mod 内で reason_core を import している想定
    monkeypatch.setattr(affect_mod.reason_core, "generate_reason", fake_generate_reason, raising=False)

    res = affect_mod.generate_reason(query="Q", evidence=["E1"], style="legal")
    assert res == {"ok": True, "reason": "dummy"}
    assert calls["n"] == 1
    assert calls["kwargs"]["query"] == "Q"
    assert calls["kwargs"]["evidence"] == ["E1"]
    assert calls["kwargs"]["style"] == "legal"


@pytest.mark.anyio
async def test_generate_reflection_template_delegates_to_reason_module(monkeypatch):
    """
    kernel.py が await affect_core.generate_reflection_template(...) を呼ぶ前提なので、
    affect.py 側に async 委譲が存在することを要求。
    """

    calls = {"n": 0, "kwargs": None}

    async def fake_generate_reflection_template(**kwargs):
        calls["n"] += 1
        calls["kwargs"] = dict(kwargs)
        return {"template": "dummy", "ok": True}

    monkeypatch.setattr(
        affect_mod.reason_core,
        "generate_reflection_template",
        fake_generate_reflection_template,
        raising=False,
    )

    res = await affect_mod.generate_reflection_template(
        query="Q",
        decision={"x": 1},
        style="coach",
    )
    assert res == {"template": "dummy", "ok": True}
    assert calls["n"] == 1
    assert calls["kwargs"]["query"] == "Q"
    assert calls["kwargs"]["decision"] == {"x": 1}
    assert calls["kwargs"]["style"] == "coach"



