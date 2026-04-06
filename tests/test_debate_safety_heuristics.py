# -*- coding: utf-8 -*-
"""Unit tests for Debate safety heuristics and risk-delta negation handling."""

from __future__ import annotations

from veritas_os.core import debate


def test_looks_dangerous_text_allows_benign_security_context() -> None:
    """Security education context should not be flagged as dangerous."""
    option = {
        "title": "ウイルス対策の教育プラン",
        "description": "サイバーセキュリティ研修で malware と virus の検知を学ぶ",
        "summary": "防止と予防を重視した安全教育",
    }

    assert debate._looks_dangerous_text(option) is False


def test_looks_dangerous_text_blocks_explicit_harmful_intent() -> None:
    """Harmful intent patterns must remain blocked even with mixed context."""
    option = {
        "title": "爆弾の作り方",
        "description": "危険物の手順をまとめる",
        "summary": "安全教育という名目でも有害意図を含む",
    }

    assert debate._looks_dangerous_text(option) is True


def test_looks_dangerous_text_blocks_actionable_harm_even_with_safe_words() -> None:
    option = {
        "title": "セキュリティ訓練",
        "description": "教育目的だが malware を deploy する手順を説明する",
    }

    assert debate._looks_dangerous_text(option) is True


def test_calc_risk_delta_ignores_negated_risk_phrases() -> None:
    """Negated safety phrases should avoid risk keyword inflation."""
    chosen = {
        "score": 0.85,
        "verdict": "採用推奨",
        "safety_view": "リスクなし。問題なし。違反なし。安全に実施可能。",
        "critic_view": "軽微な注意点のみ",
    }

    delta = debate._calc_risk_delta(chosen, [chosen])

    assert delta < 0.0


def test_calc_risk_delta_still_increases_for_real_risk_signal() -> None:
    """Actual risk signals should continue to raise risk delta."""
    chosen = {
        "score": 0.45,
        "verdict": "要検討",
        "safety_view": "重大なリスクと違反の可能性がある",
        "critic_view": "深刻な懸念あり",
    }

    delta = debate._calc_risk_delta(chosen, [chosen])

    assert delta > 0.2


def test_calc_risk_delta_avoids_ascii_partial_keyword_false_positive() -> None:
    """English keyword `ban` should not match inside unrelated token like `bank`."""
    chosen = {
        "score": 0.85,
        "verdict": "採用推奨",
        "safety_view": "Bank transfer flow reviewed. No risk and safe operation.",
        "critic_view": "minor observations only",
    }

    delta = debate._calc_risk_delta(chosen, [chosen])

    assert delta < 0.0
