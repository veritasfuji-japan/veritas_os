# veritas_os/core/logging.py
"""
VERITAS TrustLog / Logging Core - 薄いラッパーモジュール

このモジュールは後方互換性のためのラッパーです。
正規実装は veritas_os.logging.trust_log にあります。

使用方法（推奨）:
    from veritas_os.logging.trust_log import (
        append_trust_log,
        verify_trust_log,
        iter_trust_log,
        load_trust_log,
        get_trust_log_entry,
        iso_now,
    )

使用方法（後方互換）:
    from veritas_os.core.logging import (
        append_trust_log,
        verify_trust_log,
        ...
    )
"""

from __future__ import annotations

# 正規実装からすべてをインポート
from veritas_os.logging.trust_log import (
    iso_now,
    append_trust_log as _append_trust_log,
    iter_trust_log,
    load_trust_log,
    get_trust_log_entry,
    verify_trust_log,
    LOG_JSON,
    LOG_JSONL,
)

from typing import Any, Dict, Iterable, List, Optional


def append_trust_log(entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    TrustLogに新規エントリを追加。論文準拠のハッシュ連鎖を計算。

    論文の式: hₜ = SHA256(hₜ₋₁ || rₜ)

    Args:
        entry: 追加するログエントリ（dict）

    Returns:
        sha256, sha256_prev が付与されたエントリ
    """
    # 正規実装を呼び出し（sha256/sha256_prevが付与されたエントリを返す）
    return _append_trust_log(entry)


# ---------------------------------
# 公開 API（後方互換性のため維持）
# ---------------------------------

__all__ = [
    "iso_now",
    "append_trust_log",
    "iter_trust_log",
    "load_trust_log",
    "get_trust_log_entry",
    "verify_trust_log",
]
