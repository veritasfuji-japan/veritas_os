# -*- coding: utf-8 -*-
"""テスト用ファクトリ関数

DecideRequest / Context / SafetyHeadResult などの頻出オブジェクトを
簡潔に生成するヘルパーを提供する。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from veritas_os.core import fuji


def safety_head_result(
    *,
    risk_score: float = 0.1,
    categories: Optional[List[str]] = None,
    rationale: str = "",
    model: str = "heuristic_fallback",
    raw: Optional[Dict[str, Any]] = None,
) -> fuji.SafetyHeadResult:
    """SafetyHeadResult を簡潔に生成するファクトリ"""
    return fuji.SafetyHeadResult(
        risk_score=risk_score,
        categories=categories or [],
        rationale=rationale,
        model=model,
        raw=raw or {},
    )


def decide_context(
    *,
    user_id: str = "test-user",
    session_id: str = "test-session",
    query: str = "テスト入力",
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """テスト用 Context 辞書を生成する"""
    ctx: Dict[str, Any] = {
        "user_id": user_id,
        "session_id": session_id,
        "query": query,
    }
    if extra:
        ctx.update(extra)
    return ctx


def decide_request(
    *,
    text: str = "テスト入力",
    chosen: Optional[Dict[str, Any]] = None,
    alternatives: Optional[List[Dict[str, Any]]] = None,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """テスト用 DecideRequest 相当の辞書を生成する"""
    return {
        "text": text,
        "chosen": chosen or {"id": "opt-1", "title": "選択肢A"},
        "alternatives": alternatives or [],
        "context": context or decide_context(),
    }


def trust_log_entry(
    *,
    request_id: str = "req-test-001",
    action: str = "decide",
    decision_status: str = "allow",
    risk_score: float = 0.1,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """テスト用 TrustLog エントリを生成する"""
    entry: Dict[str, Any] = {
        "request_id": request_id,
        "action": action,
        "decision_status": decision_status,
        "risk_score": risk_score,
        "timestamp": "2025-01-01T00:00:00Z",
    }
    if extra:
        entry.update(extra)
    return entry
