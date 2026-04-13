# -*- coding: utf-8 -*-
"""Sanitize 単体テスト

サニタイズ / PII 検出 / ReDoS 防御のテスト。"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


# ============================================================
# Source: test_sanitize.py
# ============================================================

from veritas_os.core import sanitize


def test_mask_pii_masks_email_phone_zip_address_and_name():
    text = "\n".join(
        [
            "連絡先: test.user@example.com",
            "電話は 090-1234-5678 にお願いします。",
            "郵便番号は 123-4567 です。",
            "住所は東京都新宿区西新宿2-8-1 になります。",
            "担当者は山田太郎さんです。",
            "カタカナ名: ヤマダタロウ様",
        ]
    )

    masked = sanitize.mask_pii(text)

    # メール
    assert "example.com" not in masked
    assert "〔メール〕" in masked

    # 電話
    assert "090-1234-5678" not in masked
    assert "〔電話〕" in masked

    # 郵便番号
    assert "123-4567" not in masked
    assert "〔郵便番号〕" in masked

    # 住所
    assert "東京都新宿区" not in masked
    assert "2-8-1" not in masked
    assert "〔住所〕" in masked

    # 個人名（漢字/カタカナ両方）
    assert "山田太郎" not in masked
    assert "ヤマダタロウ" not in masked
    assert "〔個人名〕" in masked


def test_mask_pii_handles_none_and_empty_safely():
    # None → 空文字扱いで例外出ないこと
    masked_none = sanitize.mask_pii(None)  # type: ignore[arg-type]
    assert masked_none == ""

    # 空文字 → そのまま
    masked_empty = sanitize.mask_pii("")
    assert masked_empty == ""


def test_mask_pii_does_not_change_non_pii_text():
    text = "これは個人情報を含まない単なる文章です。"
    masked = sanitize.mask_pii(text)
    assert masked == text


def test_detector_prepare_input_text_handles_none_and_truncates(caplog):
    detector = sanitize.PIIDetector()

    assert detector._prepare_input_text(None) == ""

    oversized = "a" * (sanitize._MAX_PII_INPUT_LENGTH + 10)
    with caplog.at_level("WARNING"):
        prepared = detector._prepare_input_text(oversized)

    assert prepared == oversized
    assert "PII input truncated" not in caplog.text


def test_detect_pii_scans_large_text_without_truncating(caplog):
    huge_prefix = "x" * sanitize._MAX_PII_INPUT_LENGTH
    email = "very.large.user@example.com"
    text = f"{huge_prefix}\n{email}"

    with caplog.at_level("WARNING"):
        matches = sanitize.detect_pii(text)

    assert any(match["type"] == "email" and match["value"] == email for match in matches)
    assert "PII input segmented for scanning" in caplog.text


def test_detector_mask_uses_fallback_on_invalid_mask_format(caplog):
    detector = sanitize.PIIDetector()
    text = "連絡先は test.user@example.com です"

    with caplog.at_level("WARNING"):
        masked = detector.mask(text, mask_format="{unknown}")

    assert masked == "連絡先は 〔メール〕 です"
    assert "Invalid mask_format; falling back to default" in caplog.text


def test_detector_mask_uses_fallback_on_broken_braces(caplog):
    detector = sanitize.PIIDetector()
    text = "連絡先は test.user@example.com です"

    with caplog.at_level("WARNING"):
        masked = detector.mask(text, mask_format="{token")

    assert masked == "連絡先は 〔メール〕 です"
    assert "Invalid mask_format; falling back to default" in caplog.text


def test_detector_mask_accepts_non_string_mask_format():
    detector = sanitize.PIIDetector()
    text = "連絡先は test.user@example.com です"

    masked = detector.mask(text, mask_format=123)  # type: ignore[arg-type]

    assert masked == "連絡先は 123 です"


def test_detector_mask_uses_fallback_on_positional_format(caplog):
    detector = sanitize.PIIDetector()
    text = "連絡先は test.user@example.com です"

    with caplog.at_level("WARNING"):
        masked = detector.mask(text, mask_format="{}")

    assert masked == "連絡先は 〔メール〕 です"
    assert "Invalid mask_format; falling back to default" in caplog.text


# ============================================================
# Source: test_sanitize_pii.py
# ============================================================


import re

import pytest

from veritas_os.core.sanitize import (
    mask_pii,
    detect_pii,
    PIIDetector,
    PIIMatch,
    _luhn_check,
    _is_valid_credit_card,
    _is_valid_my_number,
    _is_likely_phone,
    _is_likely_ip,
    _is_likely_ipv6,
)


def test_detector_prioritizes_high_confidence_on_overlap() -> None:
    """Higher-confidence patterns should win when matches overlap."""
    detector = PIIDetector(validate_checksums=False)
    detector._patterns = [
        ("low", re.compile(r"abc"), "LOW", None, 0.1),
        ("high", re.compile(r"abc"), "HIGH", None, 0.9),
    ]

    matches = detector.detect("abc")

    assert len(matches) == 1
    assert matches[0].type == "high"


def test_phone_patterns_do_not_match_embedded_digits() -> None:
    """Domestic phone regexes should not match when surrounded by digits."""
    text = "顧客ID1090123456789は連絡先ではない"
    result = detect_pii(text)

    phones = [r for r in result if r["type"] == "phone_mobile"]
    assert phones == []


def test_detect_pii_accepts_non_string_inputs() -> None:
    """detect_pii should safely coerce non-string payload values."""
    byte_result = detect_pii(b"mail: test@example.com")
    assert any(item["type"] == "email" for item in byte_result)

    int_result = detect_pii(12345)
    assert int_result == []


def test_mask_pii_handles_non_string_bytes_via_detector() -> None:
    """PIIDetector.mask should decode bytes before masking."""
    detector = PIIDetector()
    masked = detector.mask(b"contact: test@example.com")
    assert "test@example.com" not in masked
    assert "〔メール〕" in masked


def test_url_credential_detection_ignores_query_email_like_values() -> None:
    """Query strings containing emails must not be treated as URL credentials."""
    text = "参照: https://example.com?contact=a@b.com"

    result = detect_pii(text)

    assert not any(item["type"] == "url_credential" for item in result)


def test_url_credential_detection_keeps_authority_userinfo() -> None:
    """Actual userinfo@host URLs should still be detected."""
    text = "危険URL: https://token123@example.com/path"

    result = detect_pii(text)

    assert any(
        item["type"] == "url_credential"
        and item["value"] == "https://token123@example.com"
        for item in result
    )


def test_detect_resolves_cross_pattern_overlap_by_confidence() -> None:
    """Overlap resolution should keep only the highest-confidence match."""
    detector = PIIDetector(validate_checksums=False)
    detector._patterns = [
        ("low", re.compile(r"1234"), "LOW", None, 0.1),
        ("high", re.compile(r"1234"), "HIGH", None, 0.9),
    ]

    matches = detector.detect("abc1234xyz")

    assert len(matches) == 1
    assert matches[0].type == "high"


def test_detect_pii_caps_excessive_match_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Detector should cap results to avoid memory pressure on crafted input."""
    monkeypatch.setattr("veritas_os.core.sanitize._MAX_PII_MATCHES", 3)
    detector = PIIDetector(validate_checksums=False)

    # Repeated emails generate many valid matches without overlap.
    result = detector.detect("a@x.com b@x.com c@x.com d@x.com")

    assert len(result) == 3


def test_detect_pii_stops_segmented_scan_at_match_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Segmented scans should stop once the global match cap is reached."""
    monkeypatch.setattr("veritas_os.core.sanitize._MAX_PII_INPUT_LENGTH", 20)
    monkeypatch.setattr("veritas_os.core.sanitize._MAX_PII_MATCHES", 2)

    detector = PIIDetector(validate_checksums=False)
    text = " ".join(["a@x.com", "b@x.com", "c@x.com"])
    result = detector.detect(text)

    assert len(result) == 2


def test_segmented_scan_prefers_higher_confidence_for_duplicate_span(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When windows overlap, duplicate spans should keep the highest confidence."""
    monkeypatch.setattr("veritas_os.core.sanitize._MAX_PII_INPUT_LENGTH", 20)
    detector = PIIDetector(validate_checksums=False)
    detector._patterns = [
        ("low", re.compile(r"a@x\.com"), "LOW", None, 0.1),
        ("high", re.compile(r"a@x\.com"), "HIGH", None, 0.9),
    ]

    text = "z" * 12 + " a@x.com " + "z" * 20
    result = detector.detect(text)

    assert len(result) == 1
    assert result[0].type == "high"


def test_resolve_global_overlaps_scales_without_quadratic_checks() -> None:
    """Global overlap resolution should handle many disjoint matches efficiently."""
    detector = PIIDetector(validate_checksums=False)
    size = 2000
    matches = [
        PIIMatch(
            type="email",
            value=f"u{idx}@x.com",
            start=idx * 10,
            end=(idx * 10) + 5,
            confidence=0.5,
        )
        for idx in range(size)
    ]

    resolved = detector._resolve_global_overlaps(matches)

    assert len(resolved) == size


class TestEmailDetection:
    """Tests for email address detection."""

    def test_basic_email(self):
        text = "連絡先: test@example.com です"
        result = detect_pii(text)
        emails = [r for r in result if r["type"] == "email"]
        assert len(emails) == 1
        assert emails[0]["value"] == "test@example.com"

    def test_email_with_subdomains(self):
        text = "admin@mail.subdomain.example.co.jp"
        result = detect_pii(text)
        emails = [r for r in result if r["type"] == "email"]
        assert len(emails) == 1

    def test_email_with_special_chars(self):
        text = "user.name+tag@example.org"
        result = detect_pii(text)
        emails = [r for r in result if r["type"] == "email"]
        assert len(emails) == 1

    def test_email_masking(self):
        text = "Email: john@example.com"
        masked = mask_pii(text)
        assert "john@example.com" not in masked
        assert "〔メール〕" in masked


class TestPhoneDetection:
    """Tests for phone number detection."""

    def test_japanese_mobile(self):
        text = "電話番号: 090-1234-5678"
        result = detect_pii(text)
        phones = [r for r in result if "phone" in r["type"]]
        assert len(phones) >= 1
        assert "090-1234-5678" in [p["value"] for p in phones]

    def test_japanese_mobile_variants(self):
        variants = [
            "080-1234-5678",
            "070-1234-5678",
            "09012345678",
        ]
        for phone in variants:
            result = detect_pii(f"TEL: {phone}")
            phones = [r for r in result if "phone" in r["type"]]
            assert len(phones) >= 1, f"Failed to detect: {phone}"

    def test_freephone(self):
        text = "お問い合わせ: 0120-123-456"
        result = detect_pii(text)
        phones = [r for r in result if "phone" in r["type"]]
        assert len(phones) >= 1

    def test_international_phone(self):
        text = "Call: +81-90-1234-5678"
        result = detect_pii(text)
        phones = [r for r in result if "phone" in r["type"]]
        assert len(phones) >= 1

    def test_phone_masking(self):
        text = "携帯: 090-1234-5678"
        masked = mask_pii(text)
        assert "090-1234-5678" not in masked
        assert "〔電話〕" in masked

    def test_date_not_detected_as_phone(self):
        """Dates should not be falsely detected as phone numbers."""
        text = "日付: 2024-01-15"
        result = detect_pii(text)
        phones = [r for r in result if "phone" in r["type"]]
        # Should not detect date as phone
        detected_values = [p["value"] for p in phones]
        assert "2024-01-15" not in detected_values


class TestAddressDetection:
    """Tests for Japanese address detection."""

    def test_tokyo_address(self):
        text = "住所: 東京都渋谷区神南1-2-3"
        result = detect_pii(text)
        addresses = [r for r in result if r["type"] == "address_jp"]
        assert len(addresses) >= 1

    def test_osaka_address(self):
        text = "大阪府大阪市北区梅田1丁目"
        result = detect_pii(text)
        addresses = [r for r in result if r["type"] == "address_jp"]
        assert len(addresses) >= 1

    def test_hokkaido_address(self):
        text = "北海道札幌市中央区北1条西2丁目"
        result = detect_pii(text)
        addresses = [r for r in result if r["type"] == "address_jp"]
        assert len(addresses) >= 1

    def test_address_masking(self):
        text = "東京都港区六本木1-2-3"
        masked = mask_pii(text)
        assert "〔住所〕" in masked


class TestZipCodeDetection:
    """Tests for Japanese zip code detection."""

    def test_zip_with_hyphen(self):
        text = "〒123-4567"
        result = detect_pii(text)
        zips = [r for r in result if r["type"] == "zip_jp"]
        assert len(zips) == 1

    def test_zip_without_hyphen(self):
        text = "郵便番号: 1234567"
        result = detect_pii(text)
        # ハイフンなし7桁は zip_jp_no_hyphen タイプで検出される
        zips = [r for r in result if r["type"] in ("zip_jp", "zip_jp_no_hyphen")]
        assert len(zips) == 1


class TestNameDetection:
    """Tests for name detection."""

    def test_japanese_name_with_san(self):
        text = "担当者: 山田太郎さん"
        result = detect_pii(text)
        names = [r for r in result if "name" in r["type"]]
        assert len(names) >= 1

    def test_japanese_name_with_sama(self):
        text = "田中花子様へ"
        result = detect_pii(text)
        names = [r for r in result if "name" in r["type"]]
        assert len(names) >= 1

    def test_katakana_name(self):
        text = "ヤマダタロウさん"
        result = detect_pii(text)
        names = [r for r in result if "name" in r["type"]]
        assert len(names) >= 1

    def test_english_name_with_title(self):
        text = "Contact: Mr. John Smith"
        result = detect_pii(text)
        names = [r for r in result if "name" in r["type"]]
        assert len(names) >= 1

    def test_doctor_name(self):
        text = "Dr. Jane Wilson will see you"
        result = detect_pii(text)
        names = [r for r in result if "name" in r["type"]]
        assert len(names) >= 1


class TestCreditCardDetection:
    """Tests for credit card number detection."""

    def test_valid_visa(self):
        # Valid Visa test number
        text = "Card: 4111-1111-1111-1111"
        result = detect_pii(text)
        cards = [r for r in result if r["type"] == "credit_card"]
        assert len(cards) == 1

    def test_valid_mastercard(self):
        # Valid Mastercard test number
        text = "Card: 5500 0000 0000 0004"
        result = detect_pii(text)
        cards = [r for r in result if r["type"] == "credit_card"]
        assert len(cards) == 1

    def test_invalid_luhn_not_detected(self):
        """Invalid Luhn checksum should not be detected."""
        text = "Number: 1234-5678-9012-3456"  # Invalid Luhn
        result = detect_pii(text)
        cards = [r for r in result if r["type"] == "credit_card"]
        # With checksum validation, this should not be detected
        assert len(cards) == 0

    def test_credit_card_masking(self):
        text = "支払い: 4111-1111-1111-1111"
        masked = mask_pii(text)
        assert "4111-1111-1111-1111" not in masked
        assert "〔クレジットカード〕" in masked


class TestMyNumberDetection:
    """Tests for Japanese My Number detection."""

    def test_valid_my_number(self):
        # This is a test number that passes check digit validation
        # Format: XXXX-XXXX-XXXX (12 digits)
        # Using a known valid test number
        text = "マイナンバー: 1234-5678-9012"  # May or may not be valid
        result = detect_pii(text)
        # Note: Detection depends on checksum validation
        my_numbers = [r for r in result if r["type"] == "my_number"]
        # The detection depends on whether it passes checksum

    def test_my_number_masking(self):
        """Test that 12-digit numbers in My Number format are handled."""
        detector = PIIDetector(validate_checksums=False)
        text = "個人番号: 1234-5678-9012"
        masked = detector.mask(text)
        # Without checksum validation, it should be masked
        assert "1234-5678-9012" not in masked


class TestIPAddressDetection:
    """Tests for IP address detection."""

    def test_ipv4(self):
        text = "Server IP: 192.168.1.100"
        result = detect_pii(text)
        ips = [r for r in result if r["type"] == "ipv4"]
        assert len(ips) == 1
        assert ips[0]["value"] == "192.168.1.100"

    def test_ipv4_edge_cases(self):
        valid_ips = ["0.0.0.0", "255.255.255.255", "10.0.0.1"]
        for ip in valid_ips:
            result = detect_pii(f"IP: {ip}")
            ips = [r for r in result if r["type"] == "ipv4"]
            assert len(ips) == 1, f"Failed to detect: {ip}"

    def test_invalid_ipv4_not_detected(self):
        """Invalid IP addresses should not be detected."""
        text = "Version: 256.1.1.1"  # Invalid octet
        result = detect_pii(text)
        ips = [r for r in result if r["type"] == "ipv4"]
        assert len(ips) == 0


class TestURLCredentialDetection:
    """Tests for URL credential detection."""

    def test_http_credentials(self):
        text = "URL: http://user:password@example.com"
        result = detect_pii(text)
        creds = [r for r in result if r["type"] == "url_credential"]
        assert len(creds) == 1

    def test_https_credentials(self):
        text = "URL: https://admin:secret123@api.example.com"
        result = detect_pii(text)
        creds = [r for r in result if r["type"] == "url_credential"]
        assert len(creds) == 1

    def test_userinfo_without_password_detected(self):
        """Token-like userinfo URLs should be detected as credentials."""
        text = "URL: https://token123@example.com/path"
        result = detect_pii(text)
        creds = [r for r in result if r["type"] == "url_credential"]
        assert len(creds) == 1

    def test_uppercase_scheme_detected(self):
        """Credential URLs should be detected regardless of scheme casing."""
        text = "URL: HTTPS://user:pass@example.com/path"
        result = detect_pii(text)
        creds = [r for r in result if r["type"] == "url_credential"]
        assert len(creds) == 1

    def test_credential_masking(self):
        text = "ftp://user:pass@ftp.example.com"
        masked = mask_pii(text)
        assert "user:pass" not in masked
        assert "〔URLクレデンシャル〕" in masked


class TestBankAccountDetection:
    """Tests for bank account number detection."""

    def test_bank_account_with_label(self):
        text = "口座番号: 1234567"
        result = detect_pii(text)
        accounts = [r for r in result if r["type"] == "bank_account_jp"]
        assert len(accounts) == 1


class TestPassportDetection:
    """Tests for passport number detection."""

    def test_japanese_passport(self):
        text = "Passport: AB1234567"
        result = detect_pii(text)
        passports = [r for r in result if r["type"] == "passport_jp"]
        assert len(passports) == 1


class TestLuhnAlgorithm:
    """Tests for Luhn checksum algorithm."""

    def test_valid_numbers(self):
        valid = [
            "4111111111111111",  # Visa test
            "5500000000000004",  # Mastercard test
            "378282246310005",   # Amex test
        ]
        for num in valid:
            assert _luhn_check(num), f"Should be valid: {num}"

    def test_invalid_numbers(self):
        invalid = [
            "1234567890123456",
            "1111111111111112",  # Fails Luhn
            "9999999999999999",  # Fails Luhn
        ]
        for num in invalid:
            assert not _luhn_check(num), f"Should be invalid: {num}"


class TestMyNumberValidation:
    """Tests for My Number validation algorithm."""

    def test_my_number_validation(self):
        # Test the validation function directly
        # The check digit algorithm is specific
        # This tests the function logic
        result = _is_valid_my_number("000000000000")  # All zeros
        # Just ensure the function runs without error
        assert isinstance(result, bool)


class TestPhoneHeuristics:
    """Tests for phone number heuristics."""

    def test_date_excluded(self):
        assert not _is_likely_phone("2024-01-15", "")

    def test_repeated_digits_excluded(self):
        assert not _is_likely_phone("1111-1111-1111", "")

    def test_with_context(self):
        assert _is_likely_phone("0312345678", "電話番号は")

    def test_with_hyphen(self):
        assert _is_likely_phone("03-1234-5678", "")


class TestIPHeuristics:
    """Tests for IP address heuristics."""

    def test_valid_ip(self):
        assert _is_likely_ip("192.168.1.1")

    def test_invalid_octet(self):
        # This should fail at regex level, but test heuristic
        assert not _is_likely_ip("256.1.1.1")

    def test_non_ip_format(self):
        assert not _is_likely_ip("1.2.3")


class TestIPv6Heuristics:
    """Tests for IPv6 address heuristics."""

    def test_valid_ipv6(self):
        assert _is_likely_ipv6("2001:db8::1")

    def test_bare_double_colon_excluded(self):
        assert not _is_likely_ipv6("::")

    def test_invalid_ipv6(self):
        assert not _is_likely_ipv6("2001:::1")


class TestPIIDetector:
    """Tests for PIIDetector class."""

    def test_detect_empty_text(self):
        detector = PIIDetector()
        assert detector.detect("") == []
        assert detector.detect(None) == []

    def test_mask_empty_text(self):
        detector = PIIDetector()
        assert detector.mask("") == ""
        assert detector.mask(None) == ""

    def test_no_overlap_detection(self):
        """Overlapping patterns should not produce duplicate detections."""
        text = "test@example.com"
        result = detect_pii(text)
        # Should only detect email, not overlap with other patterns
        assert len(result) == 1
        assert result[0]["type"] == "email"

    def test_custom_mask_format(self):
        detector = PIIDetector()
        text = "Email: test@example.com"
        masked = detector.mask(text, mask_format="[REDACTED:{token}]")
        assert "[REDACTED:メール]" in masked

    def test_disable_checksum_validation(self):
        """With checksums disabled, more patterns should match."""
        detector_with = PIIDetector(validate_checksums=True)
        detector_without = PIIDetector(validate_checksums=False)

        # A number that looks like a credit card but fails Luhn
        text = "Card: 1234-5678-9012-3456"

        result_with = detector_with.detect(text)
        result_without = detector_without.detect(text)

        cards_with = [r for r in result_with if r.type == "credit_card"]
        cards_without = [r for r in result_without if r.type == "credit_card"]

        # Without validation, it should detect the pattern
        assert len(cards_without) >= len(cards_with)


class TestBackwardCompatibility:
    """Tests for backward compatibility with old API."""

    def test_mask_pii_function(self):
        """mask_pii function should work as before."""
        text = "山田太郎さんの電話は090-1234-5678です"
        masked = mask_pii(text)
        assert "山田太郎" not in masked
        assert "090-1234-5678" not in masked

    def test_old_regex_patterns_exist(self):
        """Old regex patterns should still be importable."""
        from veritas_os.core.sanitize import RE_EMAIL, RE_PHONE, RE_ZIP, RE_ADDR, RE_NAME
        assert RE_EMAIL is not None
        assert RE_PHONE is not None
        assert RE_ZIP is not None
        assert RE_ADDR is not None
        assert RE_NAME is not None


class TestComplexScenarios:
    """Tests for complex real-world scenarios."""

    def test_multiple_pii_types(self):
        text = """
        お客様情報:
        氏名: 山田太郎様
        メール: yamada@example.com
        電話: 090-1234-5678
        住所: 東京都渋谷区神南1-2-3
        """
        result = detect_pii(text)

        types_found = {r["type"] for r in result}
        assert "email" in types_found
        assert any("phone" in t for t in types_found)
        assert any("name" in t for t in types_found)

    def test_masking_preserves_structure(self):
        text = "Name: Mr. John Smith, Email: john@example.com"
        masked = mask_pii(text)
        assert "Name:" in masked
        assert "Email:" in masked
        assert "〔個人名〕" in masked
        assert "〔メール〕" in masked

    def test_no_false_positives_on_normal_text(self):
        """Normal text without PII should not be modified."""
        text = "これは普通の日本語テキストです。特に個人情報は含まれていません。"
        masked = mask_pii(text)
        assert masked == text


def test_detect_in_segment_uses_neighbor_overlap_checks() -> None:
    """In-segment overlap handling should keep adjacent non-overlapping spans."""
    detector = PIIDetector(validate_checksums=False)
    detector._patterns = [
        ("first", re.compile(r"abc"), "FIRST", None, 0.9),
        ("second", re.compile(r"def"), "SECOND", None, 0.8),
        ("overlap", re.compile(r"bcde"), "OVERLAP", None, 0.7),
    ]

    matches = detector.detect("abcdef")

    assert [m.type for m in matches] == ["first", "second"]


# ============================================================
# Source: test_sanitize_redos.py
# ============================================================


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
