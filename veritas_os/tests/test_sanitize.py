# veritas_os/tests/test_sanitize.py
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
