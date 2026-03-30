# -*- coding: utf-8 -*-
"""テスト用検証ヘルパー

FUJI 判定結果 / TrustLog エントリの検証を簡潔に記述するためのヘルパー。
"""
from __future__ import annotations

from typing import Any, Dict, Optional


def assert_fuji_allow(result: Dict[str, Any], *, msg: str = "") -> None:
    """FUJI Gate の結果が allow であることを検証する"""
    status = result.get("decision_status") or result.get("status")
    assert status in ("allow", "ok"), (
        f"Expected allow/ok but got {status!r}. {msg}"
    )


def assert_fuji_deny(result: Dict[str, Any], *, msg: str = "") -> None:
    """FUJI Gate の結果が deny であることを検証する"""
    status = result.get("decision_status") or result.get("status")
    assert status in ("deny", "rejected"), (
        f"Expected deny/rejected but got {status!r}. {msg}"
    )


def assert_fuji_warn(result: Dict[str, Any], *, msg: str = "") -> None:
    """FUJI Gate の結果が warn であることを検証する"""
    status = result.get("decision_status") or result.get("status")
    assert status in ("warn", "modify"), (
        f"Expected warn/modify but got {status!r}. {msg}"
    )


def assert_risk_above(
    result: Dict[str, Any], threshold: float, *, msg: str = ""
) -> None:
    """リスクスコアが閾値以上であることを検証する"""
    risk = result.get("risk", result.get("risk_score", 0.0))
    assert risk >= threshold, (
        f"Expected risk >= {threshold} but got {risk}. {msg}"
    )


def assert_risk_below(
    result: Dict[str, Any], threshold: float, *, msg: str = ""
) -> None:
    """リスクスコアが閾値未満であることを検証する"""
    risk = result.get("risk", result.get("risk_score", 0.0))
    assert risk < threshold, (
        f"Expected risk < {threshold} but got {risk}. {msg}"
    )


def assert_trustlog_entry_valid(
    entry: Dict[str, Any],
    *,
    expected_action: Optional[str] = None,
    expected_status: Optional[str] = None,
) -> None:
    """TrustLog エントリが必要なフィールドを持つことを検証する"""
    assert "sha256" in entry, "TrustLog entry missing sha256 hash"
    if expected_action:
        assert entry.get("action") == expected_action, (
            f"Expected action={expected_action!r}, got {entry.get('action')!r}"
        )
    if expected_status:
        assert entry.get("decision_status") == expected_status, (
            f"Expected status={expected_status!r}, "
            f"got {entry.get('decision_status')!r}"
        )


def assert_has_violations(
    result: Dict[str, Any], *, min_count: int = 1, msg: str = ""
) -> None:
    """FUJI 判定結果にバイオレーションが含まれることを検証する"""
    violations = result.get("violations", [])
    assert len(violations) >= min_count, (
        f"Expected >= {min_count} violations, got {len(violations)}. {msg}"
    )
