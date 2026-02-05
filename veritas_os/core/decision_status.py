#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Decision status constants for VERITAS API - Enum化修正版

FUJI Gate が返す「意思決定ステータス」を Enum で一元管理するモジュール。

- "allow"   : そのまま実行してよい
- "modify"  : 修正して実行（マスク・要約など）
- "block"   : 安全上の理由でブロック（旧: rejected）
- "abstain" : 判断を保留・回答回避（高リスク・不確実）

NOTE: api/constants.py と整合性を保つため、BLOCK/ABSTAINを追加。
      REJECTEDはBLOCKのaliasとして後方互換性を維持。

Enum 化により:
- 型安全
- IDE 補完
- 誤字の検知

がしやすくなる。
"""

from __future__ import annotations

from enum import Enum


class DecisionStatus(str, Enum):
    """
    Decision status values for FUJI safety gate.

    str を継承しているので、そのまま JSON にもシリアライズしやすい。

    Example:
        # Enum として使用（推奨）
        if status is DecisionStatus.ALLOW:
            ...

        # 文字列との比較（後方互換）
        if status == "allow":
            ...
    """

    #: FUJI が内容に問題なしと判断した場合
    ALLOW = "allow"

    #: 軽微な修正を入れれば許可できる場合
    MODIFY = "modify"

    #: 安全上の理由でブロック（旧: rejected）
    BLOCK = "block"

    #: 判断を保留・回答回避（高リスク・不確実）
    ABSTAIN = "abstain"

    #: 後方互換性のための alias（BLOCKと同値）
    REJECTED = "rejected"

    def __str__(self) -> str:  # pragma: no cover - 単純なのでテスト省略可
        """String representation returns the raw value."""
        return self.value


# ===== Backward Compatibility (文字列定数) =====
# 既存コードが "allow" などの生文字列を import していても壊れないように保持する。
DECISION_ALLOW: str = DecisionStatus.ALLOW.value
DECISION_MODIFY: str = DecisionStatus.MODIFY.value
DECISION_BLOCK: str = DecisionStatus.BLOCK.value
DECISION_ABSTAIN: str = DecisionStatus.ABSTAIN.value

# 旧名（後方互換性のため維持）
DECISION_REJECTED: str = DecisionStatus.REJECTED.value


# ===== Helper Functions =====

def is_valid_status(status: str) -> bool:
    """
    与えられた文字列が有効な decision status かを判定。

    Args:
        status: "allow" / "modify" / "block" / "abstain" / "rejected" など

    Returns:
        True  : 有効
        False : 不正な値

    Example:
        >>> is_valid_status("allow")
        True
        >>> is_valid_status("block")
        True
        >>> is_valid_status("rejected")
        True
        >>> is_valid_status("invalid")
        False
    """
    try:
        DecisionStatus(status)
        return True
    except ValueError:
        return False


def normalize_status(status: str | DecisionStatus) -> DecisionStatus:
    """
    文字列 or Enum を必ず DecisionStatus Enum に正規化する。

    Args:
        status: "allow" のような文字列 or DecisionStatus

    Returns:
        DecisionStatus Enum インスタンス

    Raises:
        ValueError: 不正な文字列の場合

    Example:
        >>> normalize_status("allow")
        <DecisionStatus.ALLOW: 'allow'>
        >>> normalize_status(DecisionStatus.ALLOW)
        <DecisionStatus.ALLOW: 'allow'>
        >>> normalize_status("rejected")
        <DecisionStatus.REJECTED: 'rejected'>
    """
    if isinstance(status, DecisionStatus):
        return status
    return DecisionStatus(status)


__all__ = [
    "DecisionStatus",
    "DECISION_ALLOW",
    "DECISION_MODIFY",
    "DECISION_BLOCK",
    "DECISION_ABSTAIN",
    "DECISION_REJECTED",  # backward compatibility
    "is_valid_status",
    "normalize_status",
]

