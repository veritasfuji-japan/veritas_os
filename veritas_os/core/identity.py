# veritas_os/core/identity.py
"""
オプションタイトルの整合性 (integrity) チェック。

安全ゲートの前段として、選択肢タイトルが基本的な整合性要件を
満たしているかを検証する:
  1. 空文字・空白のみではないこと
  2. 長さ上限を超えていないこと (DoS / バッファ溢れ防止)
  3. 制御文字 (NUL, BEL など) を含まないこと
  4. 危険キーワード (FUJI 禁止リストに準拠) を含まないこと
"""
from __future__ import annotations

import re
from typing import FrozenSet

# API スキーマ (veritas_os/api/schemas.py) と統一した上限値
try:
    from veritas_os.api.schemas import MAX_TITLE_LENGTH  # 1000
except ImportError:  # pragma: no cover — schemas が無い環境用フォールバック
    MAX_TITLE_LENGTH = 1000

# FUJI Gate (fuji.py) の BANNED_KEYWORDS_FALLBACK と整合を取る
_BANNED_KEYWORDS: FrozenSet[str] = frozenset({
    "harm", "kill", "exploit", "illegal", "weapon",
    "malware", "bomb", "doxx",
    "毒", "殺", "爆弾", "銃", "兵器", "ハッキング", "違法",
})

# ASCII 制御文字 (タブ・改行・CR を除く) の検出パターン
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def integrity_ok(option_title: str) -> bool:
    """
    オプションタイトルの整合性を検証する。

    Returns:
        True  — タイトルが安全要件を満たしている
        False — タイトルに問題がある (空・過長・制御文字・禁止語)
    """
    # 1) 型チェック: str 以外は拒否
    if not isinstance(option_title, str):
        return False

    # 2) 空文字・空白のみ
    stripped = option_title.strip()
    if not stripped:
        return False

    # 3) 長さ上限
    if len(option_title) > MAX_TITLE_LENGTH:
        return False

    # 4) 制御文字
    if _CONTROL_CHAR_RE.search(option_title):
        return False

    # 5) 危険キーワード (大文字小文字を無視、部分一致)
    lower = stripped.lower()
    for kw in _BANNED_KEYWORDS:
        if kw in lower:
            return False

    return True
