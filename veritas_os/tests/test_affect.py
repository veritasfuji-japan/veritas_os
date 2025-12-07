# tests/test_affect.py

import pytest

from veritas_os.core.affect import choose_style


@pytest.mark.parametrize(
    "hint, expected",
    [
        (None, "concise"),        # デフォルト
        ("neutral", "neutral"),   # 既知スタイル
        ("warm", "warm"),
        ("WARM", "warm"),         # 大文字も normalize される前提
        ("legal", "legal"),
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
    ],
)
def test_choose_style_japanese_legal(hint):
    assert choose_style(hint) == "legal"


def test_choose_style_fallback_for_unknown_hint():
    # 既知スタイルにも日本語パターンにもマッチしない場合は concise にフォールバック
    style = choose_style("超攻撃的にディベートして")
    assert style == "concise"


