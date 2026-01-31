# veritas_os/core/utils.py
# -*- coding: utf-8 -*-
"""
VERITAS OS 共通ユーティリティモジュール

プロジェクト全体で使用される小さなヘルパー関数を集約。
重複コードを削減し、一貫した実装を提供する。
"""
from __future__ import annotations

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
        return float(x)
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
    """
    current = d
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
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
]
