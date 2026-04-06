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


def test_looks_dangerous_text_blocks_instructional_harm_cues() -> None:
    """Instructional cues near dangerous terms should be blocked."""
    option = {
        "title": "教育用セキュリティ教材",
        "description": "研究目的と記載しつつ、ハッキングの具体的手順とコードを提示する",
        "summary": "training context",
    }

    assert debate._looks_dangerous_text(option) is True


def test_looks_dangerous_text_keeps_block_when_only_weak_benign_label_exists() -> None:
    """Weak labels like training alone must not bypass dangerous detection."""
    option = {
        "title": "training material",
        "description": "malware virus handling notes",
        "summary": "education only",
    }

    assert debate._looks_dangerous_text(option) is True


def test_looks_dangerous_text_blocks_obfuscated_danger_terms() -> None:
    option = {
        "title": "training material",
        "detail": "m.a.l.w.a.r.e の配布を想定した説明",
        "summary": "安全な運用のための訓練",
        "safety_view": "weak label only",
    }

    assert debate._looks_dangerous_text(option) is True


def test_looks_dangerous_text_blocks_financial_fraud_related_terms() -> None:
    """Expanded danger dictionary should catch fraud/hacking adjacent terms."""
    option = {
        "title": "闇バイト募集の手順",
        "description": "不正アクセスと口座売買で資金化する流れを説明する",
    }

    assert debate._looks_dangerous_text(option) is True


def test_looks_dangerous_text_blocks_zero_width_obfuscated_terms() -> None:
    """Zero-width split danger terms should still be detected."""
    option = {
        "title": "education material",
        "detail": "m\u200ba\u200bl\u200bw\u200ba\u200br\u200be distribution plan",
        "summary": "training notes",
    }

    assert debate._looks_dangerous_text(option) is True


def test_looks_dangerous_text_blocks_confusable_obfuscated_terms() -> None:
    """Unicode confusable letters should not bypass danger-term checks."""
    option = {
        "title": "research memo",
        "detail": "mаlwаre execution guidance",  # cyrillic "а"
        "summary": "education only",
    }

    assert debate._looks_dangerous_text(option) is True


def test_looks_dangerous_text_allows_obfuscated_term_in_strong_defensive_context() -> None:
    option = {
        "title": "cybersecurity defense update",
        "detail": "m-a-l-w-a-r-e 対策の検知ルールを改善する",
        "summary": "防御観点の運用改善",
        "safety_view": "defensive prevention plan",
    }

    assert debate._looks_dangerous_text(option) is False


def test_looks_dangerous_text_allows_refusal_context_with_danger_terms() -> None:
    """Refusal wording with danger terms should not be treated as harmful intent."""
    option = {
        "summary": "I cannot provide malware guidance or hacking assistance because it is harmful and illegal.",
    }

    assert debate._looks_dangerous_text(option) is False


def test_looks_dangerous_text_blocks_refusal_preface_with_actionable_details() -> None:
    """Refusal preface must not suppress actionable harmful instructions."""
    option = {
        "summary": (
            "I cannot provide malware help, but here is a malware tutorial "
            "with a deploy script and execution steps."
        ),
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


def test_calc_risk_delta_does_not_negate_illegal_with_generic_no_risk() -> None:
    """Generic 'no risk' text must not cancel explicit illegal signals."""
    chosen = {
        "score": 0.82,
        "verdict": "採用推奨",
        "safety_view": "No risk in performance, but this flow is illegal in many regions.",
        "critic_view": "requires legal review",
    }

    delta = debate._calc_risk_delta(chosen, [chosen])

    assert delta >= 0.15


def test_calc_risk_delta_increases_for_regulatory_ambiguity() -> None:
    """Regulatory ambiguity phrases should be treated as residual legal risk."""
    chosen = {
        "score": 0.84,
        "verdict": "採用推奨",
        "safety_view": "規制の例外を使うグレーゾーン運用で、短期的には実施可能です。",
        "critic_view": "benefit exists but legal review required",
    }

    delta = debate._calc_risk_delta(chosen, [chosen])

    assert delta >= 0.10


def test_calc_risk_delta_skips_ambiguity_penalty_when_explicitly_avoiding_gray_zone() -> None:
    """Mitigated wording around gray-zone terms should not be over-penalized."""
    chosen = {
        "score": 0.84,
        "verdict": "採用推奨",
        "safety_view": "グレーゾーンは回避し、適法かつcompliantな手順のみを採用する。",
        "critic_view": "legal review completed",
    }

    delta = debate._calc_risk_delta(chosen, [chosen])

    assert delta <= 0.0
