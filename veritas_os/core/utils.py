# veritas_os/core/utils.py
# -*- coding: utf-8 -*-
"""
VERITAS OS 共通ユーティリティモジュール

プロジェクト全体で使用される小さなヘルパー関数を集約。
"""
from __future__ import annotations

from typing import Any


def _safe_float(x: Any, default: float = 0.0) -> float:
    """
    安全なfloat変換。変換できなければデフォルト値を返す。

    Args:
        x: 変換対象の値
        default: 変換失敗時のデフォルト値

    Returns:
        float値またはデフォルト値
    """
    try:
        return float(x)
    except Exception:
        return default


__all__ = [
    "_safe_float",
]
