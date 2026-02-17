# veritas_os/core/kernel_qa.py
# -*- coding: utf-8 -*-
"""
VERITAS Kernel - QA処理モジュール

Simple QA と Knowledge QA の検出・ハンドリングを担当。
責任分界: QA系の早期リターン処理に特化。

主要関数:
- detect_simple_qa: 時刻/曜日/日付などの単純QAを検出
- handle_simple_qa: 単純QAの即時回答生成
- detect_knowledge_qa: 知識系QAを検出
- handle_knowledge_qa: Web検索ベースの知識QA処理
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import adapt
from . import fuji as fuji_core
from .utils import _safe_float


# ============================================================
# ヘルパー関数
# ============================================================

def _safe_load_persona() -> Dict[str, Any]:
    """
    persona.json 破損などで adapt.load_persona() が失敗しても
    kernel 全体を落とさないためのラッパ。
    """
    try:
        p = adapt.load_persona()
        if isinstance(p, dict):
            return p
        return {}
    except Exception:
        return {}


# ============================================================
# 環境ツールラッパ（kernel.py からインポート）
# ============================================================

def _get_run_env_tool():
    """環境ツール関数を取得（循環インポート回避のため遅延インポート）"""
    from . import kernel
    return kernel.run_env_tool


# ============================================================
# Simple QA モード（事前コンパイル済み正規表現）
# ============================================================

SIMPLE_QA_PATTERNS = {
    "time": re.compile(r"^(今|いま).*(何時|なんじ)[？?]?$"),
    "weekday": re.compile(r"^(今日|きょう).*(何曜日|なんようび)[？?]?$"),
    "date": re.compile(r"^(今日|きょう).*(何日|なんにち|日付)[？?]?$"),
    "time_en": re.compile(r"^what time is it[？?]?$", re.I),
    "weekday_en": re.compile(r"^what day is it[？?]?$", re.I),
}

AGI_BLOCK_KEYWORDS = [
    "agi", "ＡＧＩ", "veritas", "ヴェリタス", "ベリタス",
    "プロトagi", "proto-agi",
]


def detect_simple_qa(q: str) -> str | None:
    """
    単純QA（時刻/曜日/日付）を検出する。

    Args:
        q: クエリ文字列

    Returns:
        検出されたQA種別（"time", "weekday", "date"）または None
    """
    q = (q or "").strip()
    ql = q.lower()

    # AGI関連クエリはブロック
    if any(k in ql for k in AGI_BLOCK_KEYWORDS):
        return None

    qj = q.replace("　", " ")
    normalized = " ".join(qj.split())
    normalized_lower = normalized.lower().rstrip("？?!.。")

    # 短いクエリのみ対象（ただし日英混在の短文QAは少し長くても許容）
    mixed_language_simple_qa = (
        "today" in normalized_lower
        and (
            "what time" in normalized_lower
            or "time is it" in normalized_lower
            or "what day" in normalized_lower
            or "what is the date" in normalized_lower
            or "what's the date" in normalized_lower
            or "date" in normalized_lower
        )
    )
    if len(normalized) > 25 and not mixed_language_simple_qa:
        return None

    if SIMPLE_QA_PATTERNS["time"].search(normalized):
        return "time"
    if SIMPLE_QA_PATTERNS["weekday"].search(normalized):
        return "weekday"
    if SIMPLE_QA_PATTERNS["date"].search(normalized):
        return "date"
    if SIMPLE_QA_PATTERNS["time_en"].search(normalized_lower):
        return "time"
    if SIMPLE_QA_PATTERNS["weekday_en"].search(normalized_lower):
        return "weekday"
    if (
        ("what's the date" in normalized_lower or "what is the date" in normalized_lower)
        and "today" in normalized_lower
    ):
        return "date"
    if "today" in normalized_lower and "date" in normalized_lower and len(normalized_lower) < 40:
        return "date"

    # 日英混在の短文クエリを許容（レビュー指摘の端境ケース対応）
    if "today" in normalized_lower and "what day" in normalized_lower:
        return "weekday"
    if "today" in normalized_lower and (
        "what time" in normalized_lower or "time is it" in normalized_lower
    ):
        return "time"

    return None


def handle_simple_qa(
    kind: str,
    q: str,
    ctx: Dict[str, Any],
    req_id: str,
    telos_score: float,
) -> Dict[str, Any]:
    """
    Simple QA の即時回答を生成する。

    Args:
        kind: QA種別 ("time", "weekday", "date")
        q: クエリ文字列
        ctx: コンテキスト
        req_id: リクエストID
        telos_score: Telos スコア

    Returns:
        DecideResponse 完全互換のレスポンス辞書
    """
    now = datetime.now(timezone.utc)
    answer_str = ""
    title = ""
    description = ""

    if kind == "time":
        answer_str = now.strftime("%H:%M")
        title = f"現在時刻は {answer_str} 頃です"
        description = "simple QA モード: システム時刻から現在時刻を直接回答しました。"
    elif kind == "weekday":
        weekdays = ["月", "火", "水", "木", "金", "土", "日"]
        wd = weekdays[now.weekday()]
        answer_str = wd + "曜日"
        title = f"今日は{answer_str}です"
        description = "simple QA モード: システム日付から曜日を直接回答しました。"
    elif kind == "date":
        answer_str = now.strftime("%Y-%m-%d")
        title = f"今日は {answer_str} 頃の日付です"
        description = "simple QA モード: システム日付から今日の日付を直接回答しました。"
    else:
        answer_str = ""
        title = "simple QA モードで回答できませんでした"
        description = "想定外のsimple QA種別のため、通常のdecisionパイプラインを利用してください。"

    chosen = {
        "id": uuid.uuid4().hex,
        "title": title,
        "description": description,
        "score": 1.0,
        "score_raw": 1.0,
    }

    evidence = [
        {
            "source": "internal:simple_qa",
            "uri": None,
            "snippet": f"simple_qa kind={kind} for query='{q}'",
            "confidence": 0.9,
        }
    ]

    extras: Dict[str, Any] = {
        "simple_qa": {
            "kind": kind,
            "answer": answer_str,
            "mode": "bypass_debate",
        }
    }

    # DecideResponse 完全互換
    return {
        "request_id": req_id,
        "chosen": chosen,
        "alternatives": [chosen],
        "evidence": evidence,
        "critique": [],
        "debate": [],
        "telos_score": telos_score,
        "fuji": {
            "status": "allow",
            "decision_status": "allow",
            "reasons": [],
            "violations": [],
            "risk": 0.05,
            "checks": [],
            "guidance": None,
            "modifications": [],
            "redactions": [],
            "safe_instructions": [],
        },
        "rsi_note": None,
        "summary": "simple QA モードで直接回答しました。",
        "description": description,
        "extras": extras,
        "gate": {
            "risk": 0.05,
            "telos_score": telos_score,
            "decision_status": "allow",
            "reason": None,
            "modifications": [],
        },
        "values": {
            "scores": {},
            "total": telos_score,
            "top_factors": [],
            "rationale": "simple QA",
        },
        "persona": _safe_load_persona(),
        "version": "veritas-api 1.x",
        "decision_status": "allow",
        "rejection_reason": None,
        "memory_citations": [],
        "memory_used_count": 0,
        "memory_evidence_count": 0,
        "meta": {
            "kind": "simple_qa",
            "memory_evidence_count": 0,
        },
    }


# ============================================================
# Knowledge QA モード
# ============================================================

def detect_knowledge_qa(q: str) -> bool:
    """
    知識系QA（定義、場所、人物など）を検出する。

    Args:
        q: クエリ文字列

    Returns:
        知識QAとして処理すべきかどうか
    """
    q = (q or "").strip()

    if len(q) < 4:
        return False

    if re.search(r"とは[？?]?$", q):
        return True
    if re.search(r"(どこ|どこにある)[？?]?$", q):
        return True
    if re.search(r"(誰|だれ)[？?]?$", q):
        return True
    if any(k in q for k in ["県庁所在地", "首都", "人口", "面積", "標高"]):
        return True

    ql = q.lower()
    if any(w in ql for w in ["what is", "who is", "where is"]):
        return True

    return False


def handle_knowledge_qa(
    q: str,
    ctx: Dict[str, Any],
    req_id: str,
    telos_score: float,
) -> Dict[str, Any]:
    """
    Web検索ベースの軽量な知識QA処理。

    Args:
        q: クエリ文字列
        ctx: コンテキスト
        req_id: リクエストID
        telos_score: Telos スコア

    Returns:
        DecideResponse 完全互換のレスポンス辞書
    """
    user_id = ctx.get("user_id") or "cli"
    stakes = _safe_float(ctx.get("stakes", 0.5), 0.5)
    mode = ctx.get("mode") or ""

    # kernel.run_env_tool を使用（テストでパッチ可能にするため）
    run_env_tool = _get_run_env_tool()
    search_res = run_env_tool(
        "web_search",
        query=q,
        max_results=3,
    )

    answer_title = ""
    answer_desc = ""

    if search_res.get("ok") and search_res.get("results"):
        top = search_res["results"][0]
        title = top.get("title") or ""
        url = top.get("url") or ""
        snippet = top.get("snippet") or ""

        answer_title = f"知識QA: {q}"
        answer_desc_parts = []
        if snippet:
            answer_desc_parts.append(f"要約: {snippet}")
        if title:
            answer_desc_parts.append(f"参考タイトル: {title}")
        if url:
            answer_desc_parts.append(f"参考URL: {url}")
        answer_desc = " / ".join(answer_desc_parts)
    else:
        answer_title = f"知識QA: {q} に対する明確な回答を取得できませんでした"
        answer_desc = f"error={search_res.get('error')}"

    chosen = {
        "id": uuid.uuid4().hex,
        "title": answer_title,
        "description": answer_desc,
        "score": 1.0,
        "score_raw": 1.0,
    }

    evidence = [
        {
            "source": "internal:knowledge_qa",
            "uri": None,
            "snippet": f"knowledge_qa for query='{q}'",
            "confidence": 0.8,
        }
    ]

    extras: Dict[str, Any] = {
        "knowledge_qa": {
            "mode": "bypass_debate",
            "web_search": search_res,
        }
    }

    # FUJI Gate を通す（高リスク用途での一貫性確保）
    try:
        fuji_result = fuji_core.evaluate(
            q,
            context={
                "user_id": user_id,
                "stakes": stakes,
                "mode": mode,
                "telos_score": telos_score,
                "fuji_safe_applied": ctx.get("fuji_safe_applied", False),
            },
            evidence=evidence,
            alternatives=[chosen],
        )
    except Exception as e:
        fuji_result = {
            "status": "allow",
            "decision_status": "allow",
            "rejection_reason": None,
            "reasons": [f"fuji_error:{repr(e)[:80]}"],
            "violations": [],
            "risk": 0.05,
            "checks": [],
            "guidance": None,
            "modifications": [],
            "redactions": [],
            "safe_instructions": [],
        }

    gate = {
        "risk": float(fuji_result.get("risk", 0.05)),
        "telos_score": float(telos_score),
        "decision_status": fuji_result.get("decision_status", fuji_result.get("status", "allow")),
        "reason": None,
        "modifications": fuji_result.get("modifications", []),
    }

    values = {
        "scores": {},
        "total": float(telos_score),
        "top_factors": [],
        "rationale": "knowledge QA",
    }

    # DecideResponse 完全互換
    return {
        "request_id": req_id,
        "chosen": chosen,
        "alternatives": [chosen],
        "evidence": evidence,
        "critique": [],
        "debate": [],
        "telos_score": telos_score,
        "fuji": fuji_result,
        "rsi_note": None,
        "summary": "knowledge_qa モードで直接回答しました。",
        "description": answer_desc,
        "extras": extras,
        "gate": gate,
        "values": values,
        "persona": _safe_load_persona(),
        "version": "veritas-api 1.x",
        "decision_status": gate["decision_status"],
        "rejection_reason": fuji_result.get("rejection_reason"),
        "memory_citations": [],
        "memory_used_count": 0,
        "memory_evidence_count": 0,
        "meta": {
            "kind": "knowledge_qa",
            "memory_evidence_count": 0,
        },
    }


# ============================================================
# 公開 API（後方互換性のため _prefix 付きも維持）
# ============================================================

# 新しい命名（推奨）
__all__ = [
    "detect_simple_qa",
    "handle_simple_qa",
    "detect_knowledge_qa",
    "handle_knowledge_qa",
    "SIMPLE_QA_PATTERNS",
    "AGI_BLOCK_KEYWORDS",
]

# 後方互換性のためのエイリアス
_detect_simple_qa = detect_simple_qa
_handle_simple_qa = handle_simple_qa
_detect_knowledge_qa = detect_knowledge_qa
_handle_knowledge_qa = handle_knowledge_qa
