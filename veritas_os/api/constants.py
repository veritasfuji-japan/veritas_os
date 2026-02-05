#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Decision status constants for VERITAS API - Enum化修正版

Provides type-safe decision status values using Python Enum.
Also maintains backward compatibility with string constants.

- 想定用途: FUJI safety gate の status フィールド
- OpenAPI / FujiDecision.status:
    enum: ["allow", "modify", "block", "abstain"]
"""

from __future__ import annotations

from enum import Enum


class DecisionStatus(str, Enum):
    """
    Decision status values for FUJI safety gate.

    Enum化により型安全性とIDEサポートが向上します。
    str を継承しているため、文字列としても使用可能です。

    Example:
        # Enum として使用（推奨）
        if status == DecisionStatus.ALLOW:
            ...

        # 文字列として使用（後方互換）
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

    def __str__(self) -> str:
        """String representation returns the underlying value."""
        return self.value


# ===== Backward Compatibility (文字列定数) =====
# 既存コードとの互換性のため、string 定数も維持する。
# 以前 "rejected" を使っていた場合にも壊れないよう BLOCK に alias する。

DECISION_ALLOW: str = DecisionStatus.ALLOW.value
DECISION_MODIFY: str = DecisionStatus.MODIFY.value
DECISION_BLOCK: str = DecisionStatus.BLOCK.value
DECISION_ABSTAIN: str = DecisionStatus.ABSTAIN.value

# 旧名（内部的には BLOCK と同義）
DECISION_REJECTED: str = DecisionStatus.BLOCK.value


# ===== Helper Functions =====
def is_valid_status(status: str) -> bool:
    """
    Check if a string is a valid decision status.

    Args:
        status: Status string to validate

    Returns:
        True if valid, False otherwise

    Example:
        >>> is_valid_status("allow")
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
    Normalize a status string or Enum to DecisionStatus Enum.

    Args:
        status: Status string or Enum

    Returns:
        DecisionStatus Enum

    Raises:
        ValueError:
            If status is invalid (e.g. "invalid_status")

    Example:
        >>> normalize_status("allow")
        <DecisionStatus.ALLOW: 'allow'>
        >>> normalize_status(DecisionStatus.ALLOW)
        <DecisionStatus.ALLOW: 'allow'>
    """
    if isinstance(status, DecisionStatus):
        return status
    return DecisionStatus(status)


# ===== Export =====
__all__ = [
    "DecisionStatus",
    "DECISION_ALLOW",
    "DECISION_MODIFY",
    "DECISION_BLOCK",
    "DECISION_ABSTAIN",
    "DECISION_REJECTED",  # backward compatibility alias
    "is_valid_status",
    "normalize_status",
    # Security constants
    "SENSITIVE_SYSTEM_PATHS",
    "MAX_RAW_BODY_LENGTH",
    "MAX_LOG_FILE_SIZE",
    # Memory constants
    "VALID_MEMORY_KINDS",
]


# ===== Security Constants =====
# Sensitive system paths that should not be used for data storage
# These paths are used across the codebase for path validation
SENSITIVE_SYSTEM_PATHS: frozenset[str] = frozenset([
    "/etc",
    "/var/run",
    "/proc",
    "/sys",
    "/dev",
    "/boot",
])

# Maximum length of raw_body to include in error responses (to prevent large payloads)
MAX_RAW_BODY_LENGTH: int = 1000

# Maximum log file size to load (10 MB) to prevent memory exhaustion
MAX_LOG_FILE_SIZE: int = 10 * 1024 * 1024

# Valid memory kinds for /v1/memory/put
VALID_MEMORY_KINDS: frozenset[str] = frozenset([
    "semantic",
    "episodic",
    "skills",
    "doc",
    "plan",
])

