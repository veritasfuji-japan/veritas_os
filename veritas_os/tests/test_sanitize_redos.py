# veritas_os/tests/test_sanitize_redos.py
"""ReDoS (Regular expression Denial of Service) fuzzing tests for sanitize.py.

Each test feeds a pathological input designed to trigger catastrophic
backtracking in common regex anti-patterns.  The time budget per case is
generous (5 seconds) so that a single run clearly distinguishes "fast" from
"catastrophic backtracking" (which would take seconds to minutes).

Patterns are sourced from OWASP ReDoS examples and adapted for the PII
regex set in sanitize.py.
"""
from __future__ import annotations

import time

import pytest

from veritas_os.core.sanitize import (
    PIIDetector,
    detect_pii,
    mask_pii,
    RE_EMAIL,
    RE_PHONE_JP_MOBILE,
    RE_PHONE_JP_LANDLINE,
    RE_PHONE_INTL,
    RE_PHONE_FREE,
    RE_ZIP_JP,
    RE_CREDIT_CARD,
    RE_MY_NUMBER,
    RE_ADDRESS_JP,
    RE_NAME_JP_HONORIFIC,
    RE_NAME_KANA_HONORIFIC,
    RE_NAME_EN_TITLE,
    RE_IPV4,
    RE_IPV6,
    RE_URL_CREDENTIAL,
    RE_BANK_ACCOUNT_JP,
    RE_PASSPORT_JP,
    _MAX_PII_INPUT_LENGTH,
)

# Maximum allowed time (seconds) for a single regex match against a
# pathological input.  If backtracking is catastrophic this will be
# exceeded by orders of magnitude.
_TIME_BUDGET = 5.0


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _assert_fast_match(pattern, text: str, label: str) -> None:
    """Assert *pattern*.search(text) completes within the time budget."""
    t0 = time.monotonic()
    pattern.search(text)
    elapsed = time.monotonic() - t0
    assert elapsed < _TIME_BUDGET, (
        f"{label}: regex took {elapsed:.2f}s on {len(text)}-char input "
        f"(budget {_TIME_BUDGET}s)"
    )


# ---------------------------------------------------------------------------
# Email — nested repetition attack: "a]" * N + "@"
# ---------------------------------------------------------------------------

class TestReDoSEmail:
    """RE_EMAIL uses character-class + quantifier; test nested-repeat payloads."""

    def test_long_local_part_no_at(self) -> None:
        payload = "a" * 50_000
        _assert_fast_match(RE_EMAIL, payload, "email-long-local-no-at")

    def test_repeated_dots_no_domain(self) -> None:
        payload = "a." * 25_000 + "@"
        _assert_fast_match(RE_EMAIL, payload, "email-dot-repeat")

    def test_almost_valid_long_domain(self) -> None:
        payload = "user@" + "a." * 25_000
        _assert_fast_match(RE_EMAIL, payload, "email-long-domain")


# ---------------------------------------------------------------------------
# Phone patterns — numeric repetition
# ---------------------------------------------------------------------------

class TestReDoSPhone:
    """Phone regexes use \\d repetitions with optional separators."""

    def test_jp_mobile_long_digits(self) -> None:
        payload = "090" + "1" * 50_000
        _assert_fast_match(RE_PHONE_JP_MOBILE, payload, "phone-mobile-digits")

    def test_jp_landline_long_digits(self) -> None:
        payload = "0" + "1" * 50_000
        _assert_fast_match(RE_PHONE_JP_LANDLINE, payload, "phone-landline-digits")

    def test_intl_plus_long_digits(self) -> None:
        payload = "+1" + "2" * 50_000
        _assert_fast_match(RE_PHONE_INTL, payload, "phone-intl-digits")

    def test_free_long_digits(self) -> None:
        payload = "0120" + "3" * 50_000
        _assert_fast_match(RE_PHONE_FREE, payload, "phone-free-digits")

    def test_mixed_separator_flood(self) -> None:
        payload = "090" + "-1" * 25_000
        _assert_fast_match(RE_PHONE_JP_MOBILE, payload, "phone-separator-flood")


# ---------------------------------------------------------------------------
# Zip code — simple digit patterns
# ---------------------------------------------------------------------------

class TestReDoSZip:
    def test_zip_long_digits(self) -> None:
        payload = "1" * 50_000
        _assert_fast_match(RE_ZIP_JP, payload, "zip-long-digits")


# ---------------------------------------------------------------------------
# Credit card — nested digit groups
# ---------------------------------------------------------------------------

class TestReDoSCreditCard:
    def test_long_digit_run(self) -> None:
        payload = "4" * 50_000
        _assert_fast_match(RE_CREDIT_CARD, payload, "cc-long-digits")

    def test_alternating_space_digits(self) -> None:
        payload = ("1234 " * 12_500).strip()
        _assert_fast_match(RE_CREDIT_CARD, payload, "cc-space-digits")


# ---------------------------------------------------------------------------
# My Number — digit groups
# ---------------------------------------------------------------------------

class TestReDoSMyNumber:
    def test_long_digit_run(self) -> None:
        payload = "9" * 50_000
        _assert_fast_match(RE_MY_NUMBER, payload, "mynumber-long-digits")


# ---------------------------------------------------------------------------
# Address (JP) — kanji/katakana repetition
# ---------------------------------------------------------------------------

class TestReDoSAddress:
    def test_repeated_prefecture_chars(self) -> None:
        payload = "東京都" + "新" * 50_000
        _assert_fast_match(RE_ADDRESS_JP, payload, "address-kanji-flood")

    def test_repeated_katakana_chars(self) -> None:
        payload = "北海道" + "ア" * 50_000
        _assert_fast_match(RE_ADDRESS_JP, payload, "address-katakana-flood")


# ---------------------------------------------------------------------------
# Name patterns — kanji/katakana/English repetition
# ---------------------------------------------------------------------------

class TestReDoSName:
    def test_jp_honorific_long_kanji(self) -> None:
        payload = "山" * 50_000 + "さん"
        _assert_fast_match(RE_NAME_JP_HONORIFIC, payload, "name-jp-kanji-flood")

    def test_kana_honorific_long_katakana(self) -> None:
        payload = "ア" * 50_000 + "様"
        _assert_fast_match(RE_NAME_KANA_HONORIFIC, payload, "name-kana-flood")

    def test_en_title_long_name(self) -> None:
        payload = "Mr. " + "A" * 50_000
        _assert_fast_match(RE_NAME_EN_TITLE, payload, "name-en-flood")


# ---------------------------------------------------------------------------
# IP address patterns
# ---------------------------------------------------------------------------

class TestReDoSIP:
    def test_ipv4_long_dots(self) -> None:
        payload = "1." * 25_000
        _assert_fast_match(RE_IPV4, payload, "ipv4-dot-flood")

    def test_ipv6_long_colons(self) -> None:
        payload = "a:" * 25_000
        _assert_fast_match(RE_IPV6, payload, "ipv6-colon-flood")

    def test_ipv4_repeated_octet_pattern(self) -> None:
        payload = "255." * 25_000
        _assert_fast_match(RE_IPV4, payload, "ipv4-octet-flood")


# ---------------------------------------------------------------------------
# URL credential pattern
# ---------------------------------------------------------------------------

class TestReDoSURLCredential:
    def test_long_userinfo(self) -> None:
        payload = "http://" + "a" * 50_000 + "@host"
        _assert_fast_match(RE_URL_CREDENTIAL, payload, "url-cred-long-user")

    def test_repeated_at(self) -> None:
        payload = "http://" + "a@" * 25_000 + "host"
        _assert_fast_match(RE_URL_CREDENTIAL, payload, "url-cred-at-flood")


# ---------------------------------------------------------------------------
# Bank account / Passport
# ---------------------------------------------------------------------------

class TestReDoSBankPassport:
    def test_bank_long_digits(self) -> None:
        payload = "口座番号: " + "1" * 50_000
        _assert_fast_match(RE_BANK_ACCOUNT_JP, payload, "bank-digit-flood")

    def test_passport_long_alpha_digits(self) -> None:
        payload = "AB" + "1" * 50_000
        _assert_fast_match(RE_PASSPORT_JP, payload, "passport-digit-flood")


# ---------------------------------------------------------------------------
# Full-pipeline integration: ensure detect_pii / mask_pii stay bounded
# ---------------------------------------------------------------------------

class TestReDoSFullPipeline:
    """End-to-end checks that the full PII pipeline completes promptly on
    adversarial input, including the _MAX_PII_INPUT_LENGTH segmentation."""

    def test_detect_pii_on_pathological_input(self) -> None:
        """detect_pii on a large payload with many near-miss patterns."""
        payload = ("090-" + "1" * 8 + " ") * 5_000
        t0 = time.monotonic()
        detect_pii(payload)
        elapsed = time.monotonic() - t0
        assert elapsed < _TIME_BUDGET, (
            f"detect_pii took {elapsed:.2f}s on {len(payload)}-char payload"
        )

    def test_mask_pii_on_pathological_input(self) -> None:
        """mask_pii on a large payload with embedded PII-like tokens."""
        payload = ("test@" + "x" * 60 + ".com ") * 2_000
        t0 = time.monotonic()
        mask_pii(payload)
        elapsed = time.monotonic() - t0
        assert elapsed < _TIME_BUDGET, (
            f"mask_pii took {elapsed:.2f}s on {len(payload)}-char payload"
        )

    def test_max_input_length_boundary(self) -> None:
        """Input at exactly _MAX_PII_INPUT_LENGTH should not crash or hang."""
        payload = "A" * _MAX_PII_INPUT_LENGTH
        t0 = time.monotonic()
        result = detect_pii(payload)
        elapsed = time.monotonic() - t0
        assert elapsed < _TIME_BUDGET
        assert isinstance(result, list)

    def test_above_max_input_triggers_segmentation(self, caplog) -> None:
        """Input above _MAX_PII_INPUT_LENGTH triggers segmented scanning."""
        payload = "B" * (_MAX_PII_INPUT_LENGTH + 100)
        t0 = time.monotonic()
        with caplog.at_level("WARNING"):
            detect_pii(payload)
        elapsed = time.monotonic() - t0
        assert elapsed < _TIME_BUDGET
        assert "PII input segmented for scanning" in caplog.text
