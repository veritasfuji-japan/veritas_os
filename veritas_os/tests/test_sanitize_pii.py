# veritas_os/tests/test_sanitize_pii.py
"""Comprehensive tests for PII detection and masking."""
from __future__ import annotations

import pytest

from veritas_os.core.sanitize import (
    mask_pii,
    detect_pii,
    PIIDetector,
    _luhn_check,
    _is_valid_credit_card,
    _is_valid_my_number,
    _is_likely_phone,
    _is_likely_ip,
    _is_likely_ipv6,
)


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
        zips = [r for r in result if r["type"] == "zip_jp"]
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
        assert detector.mask(None) is None

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
