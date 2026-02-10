# veritas_os/core/utils.py
# -*- coding: utf-8 -*-
"""
VERITAS OS 共通ユーティリティモジュール

プロジェクト全体で使用される小さなヘルパー関数を集約。
重複コードを削減し、一貫した実装を提供する。
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from typing import Any, Union


# =============================================================================
# 数値変換・クリッピング関数
# =============================================================================


def _safe_float(x: Any, default: float = 0.0) -> float:
    """
    安全なfloat変換。変換できなければデフォルト値を返す。

    Args:
        x: 変換対象の値
        default: 変換失敗時のデフォルト値

    Returns:
        float値またはデフォルト値

    Examples:
        >>> _safe_float("3.14")
        3.14
        >>> _safe_float("invalid", 0.5)
        0.5
        >>> _safe_float(None)
        0.0
    """
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except Exception:
        return default


def _to_float(x: Any, default: float = 0.0) -> float:
    """
    任意の値をfloatに変換。_safe_floatのエイリアス。

    Args:
        x: 変換対象の値
        default: 変換失敗時のデフォルト値

    Returns:
        float値またはデフォルト値
    """
    return _safe_float(x, default)


def _clip01(x: Any, default: float = 0.0) -> float:
    """
    値を0.0〜1.0の範囲にクリップする。

    Args:
        x: クリップ対象の値（数値に変換可能な任意の型）
        default: 変換失敗時のデフォルト値

    Returns:
        0.0〜1.0にクリップされたfloat値

    Examples:
        >>> _clip01(0.5)
        0.5
        >>> _clip01(1.5)
        1.0
        >>> _clip01(-0.3)
        0.0
        >>> _clip01("0.7")
        0.7
    """
    v = _safe_float(x, default)
    if v < 0.0:
        return 0.0
    if v > 1.0:
        return 1.0
    return v


def _clamp(x: Union[int, float], lo: float = 0.0, hi: float = 1.0) -> float:
    """
    値を指定範囲にクランプする。

    Args:
        x: クランプ対象の数値
        lo: 下限値（デフォルト: 0.0）
        hi: 上限値（デフォルト: 1.0）

    Returns:
        lo〜hiにクランプされたfloat値

    Examples:
        >>> _clamp(0.5, 0.0, 1.0)
        0.5
        >>> _clamp(-5, -10, 10)
        -5.0
        >>> _clamp(100, 0, 50)
        50.0
    """
    return max(lo, min(hi, float(x)))


def _clamp01(x: float) -> float:
    """
    値を0.0〜1.0にクランプする。_clamp(x, 0.0, 1.0)のショートカット。

    Args:
        x: クランプ対象の数値

    Returns:
        0.0〜1.0にクランプされたfloat値
    """
    return _clamp(x, 0.0, 1.0)


# =============================================================================
# 文字列・辞書ユーティリティ
# =============================================================================


_MISSING = object()


def _get_nested(d: dict, *keys: str, default: Any = None) -> Any:
    """
    ネストした辞書から安全に値を取得する。

    Args:
        d: 対象の辞書
        *keys: 取得するキーのパス
        default: キーが存在しない場合のデフォルト値

    Returns:
        取得した値またはデフォルト値

    Examples:
        >>> d = {"a": {"b": {"c": 1}}}
        >>> _get_nested(d, "a", "b", "c")
        1
        >>> _get_nested(d, "a", "x", default=0)
        0
        >>> _get_nested({"a": None}, "a") is None
        True
    """
    current = d
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key, _MISSING)
        if current is _MISSING:
            return default
    return current


def _truncate(text: str, max_len: int = 100, suffix: str = "...") -> str:
    """
    文字列を指定長で切り詰める。

    Args:
        text: 対象文字列
        max_len: 最大長（suffix含む）
        suffix: 切り詰め時に付加する接尾辞

    Returns:
        切り詰められた文字列
    """
    if not text or len(text) <= max_len:
        return text or ""
    if max_len <= len(suffix):
        return text[:max_len]
    return text[:max_len - len(suffix)] + suffix


def _to_text(x: Any) -> str:
    """
    任意の値をテキスト文字列に変換する。

    辞書の場合は一般的なテキストフィールド（query, title, description等）を探索し、
    最初に見つかった非空文字列を返す。

    Args:
        x: 変換対象の値（None, str, dict, その他）

    Returns:
        テキスト文字列。Noneの場合は空文字列。

    Examples:
        >>> _to_text(None)
        ''
        >>> _to_text("hello")
        'hello'
        >>> _to_text({"title": "Test", "description": "Desc"})
        'Test'
        >>> _to_text({"query": "Search term"})
        'Search term'
        >>> _to_text(123)
        '123'
    """
    if x is None:
        return ""
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        # 一般的なテキストフィールドを優先順位で探索
        for k in ("query", "title", "text", "description", "prompt"):
            v = x.get(k)
            if isinstance(v, str) and v:
                return v
    return str(x)


# =============================================================================
# JSON抽出ユーティリティ
# =============================================================================


def _strip_code_block(raw: str) -> str:
    """
    LLM出力から```json ... ``` などのコードブロックを除去する。

    Args:
        raw: LLMからの生文字列

    Returns:
        コードブロックを除去したクリーンな文字列

    Examples:
        >>> _strip_code_block('```json\\n{"a": 1}\\n```')
        '{"a": 1}'
        >>> _strip_code_block('{"a": 1}')
        '{"a": 1}'
    """
    if not raw:
        return ""

    cleaned = raw.strip()
    if cleaned.startswith("```"):
        first_nl = cleaned.find("\n")
        if first_nl != -1:
            cleaned = cleaned[first_nl + 1:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()

    return cleaned


def _extract_json_object(raw: str) -> str:
    """
    文字列から最初のJSON objectを抽出する。

    json.JSONDecoder.raw_decode を使用して、ネストした括弧や
    エスケープされた文字を含む JSON も正しく扱う。

    Args:
        raw: JSON objectを含む可能性のある文字列

    Returns:
        抽出されたJSON文字列（見つからない場合は空文字列）

    Examples:
        >>> _extract_json_object('prefix {"a": 1} suffix')
        '{"a": 1}'
        >>> _extract_json_object('no json here')
        ''
    """
    if not raw:
        return ""

    try:
        # 最初の '{' を探す
        start = raw.index("{")
        decoder = json.JSONDecoder()
        obj, end = decoder.raw_decode(raw, start)
        return json.dumps(obj, ensure_ascii=False)
    except (ValueError, json.JSONDecodeError):
        return ""


# =============================================================================
# 時刻ユーティリティ（プロジェクト共通）
# =============================================================================


def utc_now() -> datetime:
    """UTC の現在時刻を返す（timezone-aware）"""
    return datetime.now(timezone.utc)


def utc_now_iso_z(*, timespec: str = "seconds") -> str:
    """UTC ISO8601 文字列を 'Z' サフィックスで返す（監査ログ等で使用）"""
    return utc_now().isoformat(timespec=timespec).replace("+00:00", "Z")


# =============================================================================
# PII マスキング（プロジェクト共通）
# =============================================================================

# sanitize.py のインポート（失敗してもフォールバックで動作）
try:
    from veritas_os.core.sanitize import mask_pii as _mask_pii_impl
    _HAS_SANITIZE_IMPL = True
except (ImportError, ModuleNotFoundError):
    _mask_pii_impl = None  # type: ignore
    _HAS_SANITIZE_IMPL = False


def _redact_text(text: str) -> str:
    """PII をマスクした文字列を返す（ログ・メモリ永続化用）"""
    if not text:
        return text
    if _HAS_SANITIZE_IMPL and _mask_pii_impl is not None:
        try:
            return _mask_pii_impl(text)
        except Exception:
            pass
    text = re.sub(r"\b[\w\.-]+@[\w\.-]+\.\w+\b", "[redacted@email]", text)
    text = re.sub(
        r"\b\d{2,4}[-・\s]?\d{2,4}[-・\s]?\d{3,4}\b",
        "[redacted:phone]",
        text,
    )
    return text


def redact_payload(value: Any) -> Any:
    """文字列中の PII を再帰的にマスクする"""
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, dict):
        return {k: redact_payload(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_payload(v) for v in value]
    if isinstance(value, tuple):
        return tuple(redact_payload(v) for v in value)
    return value


__all__ = [
    # 数値変換
    "_safe_float",
    "_to_float",
    "_clip01",
    "_clamp",
    "_clamp01",
    # 辞書・文字列
    "_get_nested",
    "_truncate",
    "_to_text",
    # JSON抽出
    "_strip_code_block",
    "_extract_json_object",
    # 時刻
    "utc_now",
    "utc_now_iso_z",
    # PII マスキング
    "_redact_text",
    "redact_payload",
]
