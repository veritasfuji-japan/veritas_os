# veritas/core/sanitize.py
# -*- coding: utf-8 -*-
"""
PII (Personally Identifiable Information) 検出・マスク処理モジュール

対応するPII種別:
- メールアドレス
- 電話番号（日本国内・国際）
- 郵便番号
- 住所（日本）
- 個人名（日本語・英語）
- クレジットカード番号
- マイナンバー（個人番号）
- IPアドレス（IPv4・IPv6）
- URLクレデンシャル（パスワード埋め込みURL）
- 銀行口座番号
- パスポート番号

使用方法:
    from veritas_os.core.sanitize import mask_pii, detect_pii

    # マスク処理
    masked_text = mask_pii("山田太郎さんの電話は090-1234-5678です")
    # -> "〔個人名〕の電話は〔電話〕です"

    # 検出のみ
    detections = detect_pii("test@example.com")
    # -> [{"type": "email", "value": "test@example.com", "start": 0, "end": 16}]
"""
from __future__ import annotations

import logging
import re
import ipaddress
from dataclasses import dataclass
from typing import List, Dict, Any

_logger = logging.getLogger(__name__)

# Luhnチェック時の入力文字列長上限（DoS対策）
_MAX_CARD_INPUT_LENGTH = 256
# PII検査対象の入力長上限（ReDoS/CPU DoS対策）
_MAX_PII_INPUT_LENGTH = 1_000_000


# =============================================================================
# PII検出パターン定義
# =============================================================================

# --- メールアドレス ---
# RFC 5322 に近い形式（厳密ではないが実用的）
RE_EMAIL = re.compile(
    r'''
    \b
    [a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+   # ローカル部
    @
    [a-zA-Z0-9]                         # ドメイン先頭
    (?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?  # ドメイン中間
    (?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+  # サブドメイン
    \b
    ''',
    re.VERBOSE | re.IGNORECASE
)

# --- 電話番号（日本国内・国際） ---
# 偽陽性を減らすため、より厳密なパターンを使用
# --- 日本の携帯: 070/080/090-XXXX-XXXX
RE_PHONE_JP_MOBILE = re.compile(
    r'(?<!\d)0[789]0[-\s]?\d{4}[-\s]?\d{4}(?!\d)'
)
# 日本の固定電話: 0X-XXXX-XXXX または 0XX-XXX-XXXX
RE_PHONE_JP_LANDLINE = re.compile(
    r'\b0\d{1,4}[-\s]?\d{1,4}[-\s]?\d{3,4}\b'
)
# 国際電話: +XX-XXX... 形式
RE_PHONE_INTL = re.compile(
    r'(?<!\d)\+\d{1,3}[-\s]?\d{1,4}[-\s]?\d{1,4}[-\s]?\d{1,4}(?:[-\s]?\d{1,4})?(?!\d)'
)
# フリーダイヤル: 0120-XXX-XXX, 0800-XXX-XXXX
RE_PHONE_FREE = re.compile(
    r'\b(?:0120|0800)[-\s]?\d{3}[-\s]?\d{3,4}\b'
)

# --- 郵便番号（日本）---
RE_ZIP_JP = re.compile(r'\b\d{3}-?\d{4}\b')

# --- 住所（日本）---
# 都道府県
PREFECTURES = (
    '北海道|青森県|岩手県|宮城県|秋田県|山形県|福島県|'
    '茨城県|栃木県|群馬県|埼玉県|千葉県|東京都|神奈川県|'
    '新潟県|富山県|石川県|福井県|山梨県|長野県|岐阜県|静岡県|愛知県|'
    '三重県|滋賀県|京都府|大阪府|兵庫県|奈良県|和歌山県|'
    '鳥取県|島根県|岡山県|広島県|山口県|徳島県|香川県|愛媛県|高知県|'
    '福岡県|佐賀県|長崎県|熊本県|大分県|宮崎県|鹿児島県|沖縄県'
)
# 都道府県 + 市区町村 + 町名 + 番地
# 住所全体を貪欲にマッチ（スペース・句読点・改行で終了）
RE_ADDRESS_JP = re.compile(
    rf'(?:{PREFECTURES})'
    r'(?:[一-龯々ぁ-んァ-ヶa-zA-Z0-9ー−\-]{1,80})',  # 市区町村 + 町名 + 番地 (長さ制限でReDoS対策)
    re.UNICODE
)

# --- 個人名（日本語）---
# 漢字2〜4文字 + 敬称
RE_NAME_JP_HONORIFIC = re.compile(
    r'([一-龯々]{2,4})\s?(?:さん|様|氏|先生|殿)'
)
# カタカナ名 + 敬称
RE_NAME_KANA_HONORIFIC = re.compile(
    r'([ァ-ヶー]{3,12})\s?(?:さん|様|氏|先生|殿)'
)

# --- 個人名（英語）---
# 一般的な英語名パターン（Mr./Ms./Dr. + Name）
RE_NAME_EN_TITLE = re.compile(
    r'\b(?:Mr|Ms|Mrs|Miss|Dr|Prof)\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b'
)

# --- クレジットカード番号 ---
# 16桁（ハイフン/スペース区切り可）
RE_CREDIT_CARD = re.compile(
    r'\b(?:'
    r'\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}|'  # 4-4-4-4
    r'\d{4}[-\s]?\d{6}[-\s]?\d{5}|'              # AMEX: 4-6-5
    r'\d{16}'                                     # 連続16桁
    r')\b'
)

# --- マイナンバー（個人番号）---
# 12桁の数字（ハイフン区切り可）
RE_MY_NUMBER = re.compile(
    r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}\b'
)

# --- IPアドレス ---
# IPv4
RE_IPV4 = re.compile(
    r'\b(?:(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\.){3}'
    r'(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\b'
)
# IPv6（簡易版）
RE_IPV6 = re.compile(
    r'(?:'
    r'\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b'         # full form
    r'|\b(?:[0-9a-fA-F]{1,4}:){1,7}:'                         # trailing ::
    r'|::(?:[0-9a-fA-F]{1,4}:){0,6}[0-9a-fA-F]{1,4}\b'       # leading ::
    r'|::'                                                      # all-zeros
    r')'
)

# --- URLクレデンシャル ---
# http://userinfo@host / http://user:password@host 形式
# Security:
#   RFC 3986 では userinfo に ":" を含まない ``user@host`` 形式も許可される。
#   既存実装は ``user:password`` のみを検出しており、アクセストークン等を
#   user 部分に埋め込んだ URL を見逃す可能性があったため包括的に検出する。
RE_URL_CREDENTIAL = re.compile(
    r'(?:https?|ftp)://[^@\s/]+@[^\s/]+'
)

# --- 銀行口座番号（日本）---
# 7桁の数字（普通預金口座番号）- コンテキスト付きで検出
RE_BANK_ACCOUNT_JP = re.compile(
    r'(?:口座番号|口座|account)\s*[:：]?\s*\d{7}\b',
    re.IGNORECASE
)

# --- パスポート番号（日本）---
# 英字2文字 + 数字7桁
RE_PASSPORT_JP = re.compile(
    r'\b[A-Z]{2}\d{7}\b'
)


# =============================================================================
# Luhnアルゴリズム（クレジットカード検証）
# =============================================================================

def _luhn_check(card_number: str) -> bool:
    """
    Luhnアルゴリズムでクレジットカード番号を検証

    Args:
        card_number: ハイフン/スペースを除去した数字文字列

    Returns:
        True if valid, False otherwise
    """
    # ★ DoS対策: 極端に長い文字列のリスト変換を防止
    if len(card_number) > _MAX_CARD_INPUT_LENGTH:
        return False
    digits = [int(d) for d in card_number if d.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False

    # Luhn algorithm
    checksum = 0
    for i, digit in enumerate(reversed(digits)):
        if i % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit

    return checksum % 10 == 0


def _is_valid_credit_card(match: str) -> bool:
    """クレジットカード番号の妥当性を検証"""
    digits_only = re.sub(r'[-\s]', '', match)
    if not digits_only or not digits_only.isdigit():
        return False

    # 長さチェック
    if len(digits_only) < 13 or len(digits_only) > 19:
        return False

    # Luhnチェック
    return _luhn_check(digits_only)


# =============================================================================
# マイナンバー検証
# =============================================================================

def _is_valid_my_number(match: str) -> bool:
    """
    マイナンバーのチェックデジット検証

    マイナンバーは12桁で、最後の1桁がチェックデジット
    """
    digits_only = re.sub(r'[-\s]', '', match)
    if len(digits_only) != 12 or not digits_only.isdigit():
        return False

    # チェックデジット計算
    # 参考: https://www.digital.go.jp/policies/mynumber
    q = [6, 5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    total = sum(int(digits_only[i]) * q[i] for i in range(11))
    remainder = total % 11
    check_digit = 0 if remainder <= 1 else 11 - remainder

    return int(digits_only[11]) == check_digit


# =============================================================================
# 偽陽性フィルタリング
# =============================================================================

def _is_likely_phone(match: str, context: str = "") -> bool:
    """
    電話番号の偽陽性を減らすためのヒューリスティック

    - 連続する数字だけでなく、ハイフンやスペースで区切られているか
    - 前後の文脈に「電話」「TEL」「携帯」などがあるか
    """
    digits_only = re.sub(r'[-\s]', '', match)

    # 全て同じ数字は除外（例: 1111-1111-1111）
    if len(set(digits_only)) == 1:
        return False

    # 日付っぽいパターンは除外（例: 2024-01-15）
    if re.match(r'^(19|20)\d{2}[-/]\d{1,2}[-/]\d{1,2}$', match):
        return False

    # 区切り文字があれば電話番号の可能性が高い
    if '-' in match or ' ' in match:
        return True

    # 文脈に電話関連キーワードがあるか
    phone_keywords = ['電話', 'tel', 'phone', '携帯', '連絡先', 'fax', 'mobile']
    context_lower = context.lower()
    if any(kw in context_lower for kw in phone_keywords):
        return True

    # 10-11桁で0始まりは電話番号の可能性が高い
    if digits_only.startswith('0') and 10 <= len(digits_only) <= 11:
        return True

    return False


def _is_likely_ip(match: str) -> bool:
    """
    IPアドレスの偽陽性を減らす

    - プライベートIPは検出対象外にするオプション
    - バージョン番号っぽいものは除外
    """
    parts = match.split('.')
    if len(parts) != 4:
        return False

    # バージョン番号の可能性（例: 1.2.3.4 でアルファベットが前後にある）
    # この関数では単純なIPv4形式のみ判定

    # 各オクテットが0-255の範囲か確認
    try:
        octets = [int(p) for p in parts]
        return all(0 <= o <= 255 for o in octets)
    except ValueError:
        return False


def _is_likely_ipv6(match: str) -> bool:
    """Validate IPv6 candidates to reduce false positives."""
    # Bare "::" is a valid IPv6 notation but often appears as punctuation.
    if match == "::":
        return False

    try:
        ipaddress.IPv6Address(match)
    except ipaddress.AddressValueError:
        return False
    return True


# =============================================================================
# PII検出エンジン
# =============================================================================

@dataclass
class PIIMatch:
    """PII検出結果"""
    type: str           # PII種別
    value: str          # 検出された値
    start: int          # 開始位置
    end: int            # 終了位置
    confidence: float   # 信頼度 (0.0-1.0)


class PIIDetector:
    """
    PII検出器

    複数のPIIパターンを統合的に管理し、検出・マスク処理を行う
    """

    def __init__(self, validate_checksums: bool = True):
        """
        Args:
            validate_checksums: クレジットカード・マイナンバーのチェックサム検証を行うか
        """
        self.validate_checksums = validate_checksums

        # 検出パターン定義: (パターン名, 正規表現, マスクトークン, 検証関数, 信頼度)
        self._patterns: List[tuple] = [
            # 高信頼度パターン（先に処理）
            ("url_credential", RE_URL_CREDENTIAL, "URLクレデンシャル", None, 0.95),
            ("email", RE_EMAIL, "メール", None, 0.90),
            ("credit_card", RE_CREDIT_CARD, "クレジットカード",
             self._validate_credit_card if validate_checksums else None, 0.85),
            ("my_number", RE_MY_NUMBER, "マイナンバー",
             self._validate_my_number if validate_checksums else None, 0.80),

            # 電話番号（複数パターン）
            ("phone_mobile", RE_PHONE_JP_MOBILE, "電話", None, 0.85),
            ("phone_free", RE_PHONE_FREE, "電話", None, 0.90),
            ("phone_intl", RE_PHONE_INTL, "電話", None, 0.80),
            ("phone_landline", RE_PHONE_JP_LANDLINE, "電話",
             lambda m, ctx: _is_likely_phone(m, ctx), 0.70),

            # 銀行口座（コンテキスト付きなので郵便番号より先に処理）
            ("bank_account_jp", RE_BANK_ACCOUNT_JP, "口座番号", None, 0.90),

            # 住所・郵便番号
            ("zip_jp", RE_ZIP_JP, "郵便番号", None, 0.85),
            ("address_jp", RE_ADDRESS_JP, "住所", None, 0.80),

            # 個人名
            ("name_jp_honorific", RE_NAME_JP_HONORIFIC, "個人名", None, 0.85),
            ("name_kana_honorific", RE_NAME_KANA_HONORIFIC, "個人名", None, 0.85),
            ("name_en_title", RE_NAME_EN_TITLE, "個人名", None, 0.80),

            # IPアドレス
            ("ipv4", RE_IPV4, "IPアドレス", lambda m, _: _is_likely_ip(m), 0.75),
            ("ipv6", RE_IPV6, "IPアドレス", lambda m, _: _is_likely_ipv6(m), 0.80),

            # パスポート
            ("passport_jp", RE_PASSPORT_JP, "パスポート番号", None, 0.70),
        ]

    def _prepare_input_text(self, text: object | None) -> str:
        """Normalize input text for PII scanning.

        Args:
            text: Raw input value. ``None`` is treated as an empty string.

        Returns:
            String representation that is safe to scan.

        Security:
            API payloads can contain non-string values when validation is bypassed
            or when this utility is used directly. Converting unknown objects to
            bounded text avoids ``TypeError`` crashes that may otherwise leak
            internals through unhandled exceptions.
        """
        if text is None:
            return ""
        if isinstance(text, str):
            return text
        if isinstance(text, bytes):
            return text.decode("utf-8", errors="replace")
        return str(text)

    def _detect_in_segment(self, text: str, offset: int = 0) -> List[PIIMatch]:
        """Detect PII inside a single bounded text segment.

        Args:
            text: Segment text.
            offset: Absolute offset applied to resulting match positions.

        Returns:
            Detected matches with absolute positions.
        """
        if not text:
            return []

        results: List[PIIMatch] = []
        detected_ranges: List[tuple] = []  # 重複検出防止用

        for name, pattern, token, validator, confidence in self._iter_patterns_by_priority():
            for match in pattern.finditer(text):
                start, end = match.start(), match.end()
                value = match.group()

                # 重複範囲チェック（より高信頼度のパターンを優先）
                is_overlap = False
                for existing_start, existing_end in detected_ranges:
                    if start < existing_end and end > existing_start:
                        is_overlap = True
                        break

                if is_overlap:
                    continue

                # 検証関数があれば実行
                if validator is not None:
                    # コンテキスト抽出（前後50文字）
                    ctx_start = max(0, start - 50)
                    ctx_end = min(len(text), end + 50)
                    context = text[ctx_start:ctx_end]

                    if not validator(value, context):
                        continue

                results.append(PIIMatch(
                    type=name,
                    value=value,
                    start=start + offset,
                    end=end + offset,
                    confidence=confidence,
                ))
                detected_ranges.append((start, end))

        return results

    def _validate_credit_card(self, match: str, context: str) -> bool:
        return _is_valid_credit_card(match)

    def _validate_my_number(self, match: str, context: str) -> bool:
        return _is_valid_my_number(match)

    def _iter_patterns_by_priority(self) -> List[tuple]:
        """Return detection patterns ordered by confidence.

        Overlap resolution keeps the first accepted match, therefore scanning
        higher-confidence patterns first reduces false positives when multiple
        patterns can match the same substring.
        """
        return sorted(self._patterns, key=lambda item: item[4], reverse=True)

    def detect(self, text: str | None) -> List[PIIMatch]:
        """
        テキストからPIIを検出

        Args:
            text: 検査対象テキスト

        Returns:
            検出されたPIIのリスト
        """
        text = self._prepare_input_text(text)
        if not text:
            return []

        if len(text) <= _MAX_PII_INPUT_LENGTH:
            results = self._detect_in_segment(text)
        else:
            _logger.warning(
                "PII input segmented for scanning: %d chars (segment size=%d)",
                len(text),
                _MAX_PII_INPUT_LENGTH,
            )
            results = []
            overlap = 128
            segment_size = _MAX_PII_INPUT_LENGTH
            step = max(1, segment_size - overlap)
            seen_ranges: set[tuple[int, int]] = set()

            for start in range(0, len(text), step):
                end = min(len(text), start + segment_size)
                segment_matches = self._detect_in_segment(text[start:end], offset=start)
                for match in segment_matches:
                    span = (match.start, match.end)
                    if span not in seen_ranges:
                        seen_ranges.add(span)
                        results.append(match)

                if end == len(text):
                    break

        return self._resolve_global_overlaps(results)

    def _resolve_global_overlaps(self, matches: List[PIIMatch]) -> List[PIIMatch]:
        """Resolve overlapping spans using confidence across all segments.

        Segment-based scanning avoids CPU spikes for huge payloads, but the same
        region can still be detected by different patterns when matches are
        produced from neighboring segments. This pass enforces a single winner
        per overlapping range using confidence and then restores positional
        ordering for deterministic masking.

        Args:
            matches: Raw detection list from one-shot or segmented scanning.

        Returns:
            De-duplicated matches ordered by ``start`` offset.
        """
        if not matches:
            return []

        prioritized = sorted(
            matches,
            key=lambda item: (-item.confidence, item.start, item.end),
        )

        selected: List[PIIMatch] = []
        occupied_ranges: List[tuple[int, int]] = []

        for candidate in prioritized:
            has_overlap = any(
                candidate.start < existing_end
                and candidate.end > existing_start
                for existing_start, existing_end in occupied_ranges
            )
            if has_overlap:
                continue
            selected.append(candidate)
            occupied_ranges.append((candidate.start, candidate.end))

        selected.sort(key=lambda item: item.start)
        return selected

    def mask(self, text: object | None, mask_format: str = "〔{token}〕") -> str:
        """
        テキスト内のPIIをマスク

        Args:
            text: マスク対象テキスト
            mask_format: マスク形式（{token}がPII種別に置換される）

        Returns:
            マスク済みテキスト
        """
        normalized_text = self._prepare_input_text(text)
        if normalized_text == "":
            return ""

        detections = self.detect(normalized_text)
        if not detections:
            return normalized_text

        # 後ろから置換（インデックスがずれないように）
        result = normalized_text
        for det in reversed(detections):
            token = self._get_mask_token(det.type)
            mask_str = self._build_mask_text(mask_format, token)
            result = result[:det.start] + mask_str + result[det.end:]

        return result

    def _get_mask_token(self, pii_type: str) -> str:
        """PII種別からマスクトークンを取得"""
        token_map = {
            "email": "メール",
            "url_credential": "URLクレデンシャル",
            "credit_card": "クレジットカード",
            "my_number": "マイナンバー",
            "phone_mobile": "電話",
            "phone_landline": "電話",
            "phone_intl": "電話",
            "phone_free": "電話",
            "zip_jp": "郵便番号",
            "address_jp": "住所",
            "name_jp_honorific": "個人名",
            "name_kana_honorific": "個人名",
            "name_en_title": "個人名",
            "ipv4": "IPアドレス",
            "ipv6": "IPアドレス",
            "bank_account_jp": "口座番号",
            "passport_jp": "パスポート番号",
        }
        return token_map.get(pii_type, "PII")

    def _build_mask_text(self, mask_format: object, token: str) -> str:
        """Build mask text safely even when format strings are malformed.

        Args:
            mask_format: User-provided format template.
            token: Localized PII token.

        Returns:
            Interpolated mask text. Falls back to ``〔{token}〕`` when format
            parsing fails.

        Security:
            Invalid ``mask_format`` values from API inputs previously raised
            exceptions and could break sanitization endpoints. Recovering with a
            default format keeps masking available and avoids accidental 500s.
        """
        try:
            return str(mask_format).format(token=token)
        except (AttributeError, IndexError, KeyError, ValueError):
            _logger.warning("Invalid mask_format; falling back to default")
            return f"〔{token}〕"


# =============================================================================
# グローバルインスタンスと互換性関数
# =============================================================================

# デフォルトのPII検出器
_default_detector = PIIDetector(validate_checksums=True)


def detect_pii(text: object | None) -> List[Dict[str, Any]]:
    """
    テキストからPIIを検出

    Args:
        text: 検査対象テキスト

    Returns:
        検出結果のリスト [{type, value, start, end, confidence}, ...]
    """
    matches = _default_detector.detect(text)
    return [
        {
            "type": m.type,
            "value": m.value,
            "start": m.start,
            "end": m.end,
            "confidence": m.confidence,
        }
        for m in matches
    ]


def mask_pii(text: object | None) -> str:
    """
    テキスト内のPIIをマスク（後方互換性のため維持）

    Args:
        text: マスク対象テキスト

    Returns:
        マスク済みテキスト
    """
    if text is None:
        return ""
    return _default_detector.mask(text)


def get_detector(validate_checksums: bool = True) -> PIIDetector:
    """
    PII検出器インスタンスを取得

    Args:
        validate_checksums: チェックサム検証を行うか

    Returns:
        PIIDetector インスタンス
    """
    if validate_checksums:
        return _default_detector
    return PIIDetector(validate_checksums=False)


# =============================================================================
# 後方互換性のための旧パターン（非推奨）
# =============================================================================

# 旧パターン（後方互換性のため残す）
RE_PHONE = RE_PHONE_JP_MOBILE  # 最も一般的なパターン
RE_ZIP = RE_ZIP_JP
RE_ADDR = RE_ADDRESS_JP
RE_NAME = RE_NAME_JP_HONORIFIC
