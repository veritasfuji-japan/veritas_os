# tests for veritas_os/core/eu_ai_act_prohibited.py
"""Tests for Article 5 prohibited-practice detection."""
from __future__ import annotations

import pytest

from veritas_os.core.eu_ai_act_prohibited import (
    EUAIActSafetyGateLayer4,
    classify_annex_iii_risk,
    _char_ngrams,
    _ngram_similarity,
    _semantic_ngram_check,
    ANNEX_III_RISK_KEYWORDS,
)


class TestCharNgrams:
    def test_basic(self):
        result = _char_ngrams("abcd", 3)
        assert result == {"abc", "bcd"}

    def test_short_text(self):
        result = _char_ngrams("ab", 3)
        assert result == {"ab"}

    def test_empty(self):
        assert _char_ngrams("", 3) == set()


class TestNgramSimilarity:
    def test_identical(self):
        assert _ngram_similarity("hello", "hello") == 1.0

    def test_different(self):
        sim = _ngram_similarity("hello", "zzzzz")
        assert sim < 0.5

    def test_empty(self):
        assert _ngram_similarity("", "hello") == 0.0

    def test_partial_overlap(self):
        sim = _ngram_similarity("hello world", "hello earth")
        assert 0.0 < sim < 1.0


class TestSemanticNgramCheck:
    def test_clean_text(self):
        violations = _semantic_ngram_check("the weather is nice today")
        assert violations == []

    def test_close_match_detected(self):
        # Very close to a prohibited description
        text = "subliminal technique beyond consciousness to distort behavior"
        violations = _semantic_ngram_check(text)
        assert len(violations) > 0


class TestEUAIActSafetyGateLayer4:
    def test_normalise_text(self):
        gate = EUAIActSafetyGateLayer4()
        result = gate._normalise_text("Sub\u200bliminal")
        assert "subliminal" in result

    def test_normalise_confusables(self):
        gate = EUAIActSafetyGateLayer4()
        # Cyrillic 'а' in 'mаss' should become 'mass'
        result = gate._normalise_text("mаss surveillance")
        assert "mass surveillance" in result

    def test_normalise_spaced_evasion(self):
        gate = EUAIActSafetyGateLayer4()
        result = gate._normalise_text("s u b l i m i n a l")
        assert "subliminal" in result

    def test_validate_article_5_clean(self):
        gate = EUAIActSafetyGateLayer4()
        result = gate.validate_article_5("This is a normal business report.")
        assert result["passed"] is True
        assert result["violations"] == []

    def test_validate_article_5_prohibited(self):
        gate = EUAIActSafetyGateLayer4()
        result = gate.validate_article_5("social scoring by the government")
        assert result["passed"] is False
        assert len(result["violations"]) > 0

    def test_validate_article_5_japanese(self):
        gate = EUAIActSafetyGateLayer4()
        result = gate.validate_article_5("サブリミナル技術を使った広告")
        assert result["passed"] is False

    def test_validate_article_5_input(self):
        gate = EUAIActSafetyGateLayer4()
        result = gate.validate_article_5_input("explain social scoring systems")
        assert result["passed"] is False
        assert result["scope"] == "input"

    def test_external_classifier_called(self):
        def ext_classifier(text):
            return {"violations": ["ext_violation"]}

        gate = EUAIActSafetyGateLayer4(external_classifier=ext_classifier)
        result = gate.validate_article_5("normal text")
        assert "ext_violation" in result["violations"]
        assert result["passed"] is False

    def test_external_classifier_error_handled(self):
        def bad_classifier(text):
            raise RuntimeError("boom")

        gate = EUAIActSafetyGateLayer4(external_classifier=bad_classifier)
        result = gate.validate_article_5("normal text")
        assert result.get("external_classifier_error") is True

    def test_external_classifier_on_input(self):
        def ext_classifier(text):
            return {"violations": ["ext_input_violation"]}

        gate = EUAIActSafetyGateLayer4(external_classifier=ext_classifier)
        result = gate.validate_article_5_input("test")
        assert "ext_input_violation" in result["violations"]


class TestClassifyAnnexIIIRisk:
    def test_high_risk_biometric(self):
        result = classify_annex_iii_risk("biometric identification system")
        assert result["risk_level"] == "HIGH"
        assert "biometric" in result["matched_categories"]

    def test_medium_default(self):
        result = classify_annex_iii_risk("weather forecast app")
        assert result["risk_level"] == "MEDIUM"
        assert result["risk_score"] == 0.4

    def test_hiring_detected(self):
        result = classify_annex_iii_risk("AI hiring tool for candidates")
        assert "hiring" in result["matched_categories"]

    def test_evasion_resistance(self):
        # Spaced evasion: "h i r i n g" -> "hiring"
        result = classify_annex_iii_risk("h i r i n g system")
        assert "hiring" in result["matched_categories"]

    def test_confusable_evasion(self):
        # Cyrillic chars in "biometric"
        result = classify_annex_iii_risk("bіоmetric")  # Cyrillic і and о
        assert result["risk_level"] == "HIGH"
