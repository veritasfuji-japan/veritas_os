# veritas_os/core/pipeline_helpers.py
# -*- coding: utf-8 -*-
"""
Pipeline 内部で使う小さなヘルパー関数群。

各 pipeline サブモジュール（pipeline_critique, pipeline_contracts 等）から
インポートされる。pipeline.py の run_decide_pipeline 内ネスト定義を統合したもの。
"""
from __future__ import annotations

import importlib
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# =========================================================
# 文字列 / 型変換
# =========================================================

def _as_str(x: Any, *, limit: int = 2000) -> str:
    """任意の値を文字列に変換し、limit 文字で切り詰める。"""
    try:
        s = "" if x is None else str(x)
    except Exception:
        s = repr(x)
    if limit and len(s) > limit:
        return s[:limit]
    return s


def _norm_severity(x: Any) -> str:
    """重要度文字列を high/med/low に正規化する。"""
    try:
        s = str(x).lower().strip()
    except Exception:
        s = "med"
    if s in ("high", "h", "critical", "crit"):
        return "high"
    if s in ("low", "l"):
        return "low"
    return "med"


def _now_iso() -> str:
    """UTC ISO8601 文字列を返す。"""
    return datetime.now(timezone.utc).isoformat()


def _to_bool_local(x: Any) -> bool:
    """pipeline 内で使う bool 変換（None -> False, 文字列は truthy set チェック）。"""
    if isinstance(x, bool):
        return x
    if x is None:
        return False
    if isinstance(x, (int, float)):
        return x != 0
    try:
        s = str(x).strip().lower()
    except Exception:
        return False
    return s in ("1", "true", "yes", "y", "on")


# =========================================================
# メトリクスセッター
# =========================================================

def _set_int_metric(
    extras: Dict[str, Any],
    key: str,
    value: Any,
    default: int = 0,
) -> None:
    """extras["metrics"][key] に int 値をセットする（安全版）。"""
    extras.setdefault("metrics", {})
    if not isinstance(extras["metrics"], dict):
        extras["metrics"] = {}
    try:
        extras["metrics"][key] = int(value)
    except Exception:
        extras["metrics"][key] = int(default)


def _set_bool_metric(
    extras: Dict[str, Any],
    key: str,
    value: Any,
    default: bool = False,
) -> None:
    """extras["metrics"][key] に bool 値をセットする（安全版）。"""
    extras.setdefault("metrics", {})
    if not isinstance(extras["metrics"], dict):
        extras["metrics"] = {}
    try:
        extras["metrics"][key] = _to_bool_local(value)
    except Exception:
        extras["metrics"][key] = bool(default)


# =========================================================
# 遅延インポート
# =========================================================

def _lazy_import(mod_path: str, attr: Optional[str] = None) -> Any:
    """ISSUE-4 style lazy import; インポート失敗時は None を返す（例外を出さない）。"""
    try:
        m = importlib.import_module(mod_path)
        if attr:
            return getattr(m, attr, None)
        return m
    except Exception as e:
        logger.debug("[lazy_import] %s%s skipped: %s", mod_path, f".{attr}" if attr else "", e)
        return None


# =========================================================
# self-healing ヘルパー
# =========================================================

def _extract_rejection(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """FUJI rejection dict を payload から取り出す（なければ None）。"""
    fuji_payload = payload.get("fuji") if isinstance(payload, dict) else None
    if not isinstance(fuji_payload, dict):
        return None
    rejection = fuji_payload.get("rejection")
    if not isinstance(rejection, dict):
        return None
    if rejection.get("status") != "REJECTED":
        return None
    return rejection


def _summarize_last_output(
    payload: Dict[str, Any],
    plan_payload: Dict[str, Any],
) -> Dict[str, Any]:
    """self-healing に渡す直前出力のサマリを生成する。"""
    chosen = payload.get("chosen") if isinstance(payload, dict) else None
    planner_obj = payload.get("planner") if isinstance(payload, dict) else None
    return {
        "chosen": chosen if isinstance(chosen, dict) else {},
        "plan": plan_payload if isinstance(plan_payload, dict) else {},
        "planner": planner_obj if isinstance(planner_obj, dict) else {},
    }


# =========================================================
# Step1 クエリヒント判定
# =========================================================

def _query_is_step1_hint(q: Any) -> bool:
    """クエリが Step1（現状棚卸し）を示唆するかどうか判定する。"""
    try:
        qs = q or ""
        ql = qs.lower()
        return (
            ("step1" in ql)
            or ("step 1" in ql)
            or ("inventory" in ql)
            or ("audit" in ql)
            or ("棚卸" in qs)
            or ("現状" in qs and ("棚卸" in qs or "整理" in qs))
        )
    except Exception:
        return False


def _has_step1_minimum_evidence(evs: Any) -> bool:
    """evidence リストが Step1 最低限証拠（inventory + known_issues）を含むか確認する。"""
    try:
        if not isinstance(evs, list):
            return False
        has_inv = False
        has_issues = False
        for e in evs:
            if not isinstance(e, dict):
                continue
            title = str(e.get("title") or "")
            uri = str(e.get("uri") or "")
            snip = str(e.get("snippet") or "")
            kind = str(e.get("kind") or "")

            if (
                ("inventory" in kind)
                or ("local:inventory" in title)
                or ("evidence:inventory" in uri)
                or ("現状機能（棚卸し）" in snip)
                or ("棚卸" in snip and "現状" in snip)
            ):
                has_inv = True

            if (
                ("known_issues" in kind)
                or ("local:known_issues" in title)
                or ("evidence:known_issues" in uri)
                or ("既知の課題/注意" in snip)
                or ("既知" in snip and "課題" in snip)
            ):
                has_issues = True

            if has_inv and has_issues:
                return True
        return False
    except Exception:
        return False


__all__ = [
    "_as_str",
    "_norm_severity",
    "_now_iso",
    "_to_bool_local",
    "_set_int_metric",
    "_set_bool_metric",
    "_lazy_import",
    "_extract_rejection",
    "_summarize_last_output",
    "_query_is_step1_hint",
    "_has_step1_minimum_evidence",
]
