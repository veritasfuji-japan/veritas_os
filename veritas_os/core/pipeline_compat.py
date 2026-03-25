# veritas_os/core/pipeline_compat.py
# -*- coding: utf-8 -*-
"""
Pipeline 後方互換ユーティリティ層。

pipeline.py の hot path から退避した純粋ユーティリティ関数群。
これらは module-level mutable state に依存せず、テストの monkeypatch 対象
でもないため、独立モジュールとして安全に切り出せる。

pipeline.py は後方互換のためこれらを re-export する。
``from veritas_os.core.pipeline import to_dict`` 等の既存 import は引き続き動作する。

退避理由:
- pipeline.py を orchestration coordinator に近づける
- hot path の可読性向上（ユーティリティと orchestration の関心分離）
"""
from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any, Dict, Optional
from uuid import uuid4

# Use the pipeline module's logger name so that tests capturing logs
# from "veritas_os.core.pipeline" continue to work after this extraction.
logger = logging.getLogger("veritas_os.core.pipeline")

from .utils import _safe_float
from .pipeline_helpers import _to_bool_local
from .pipeline_persistence import _UNSAFE_UNICODE_CATEGORIES


# =========================================================
# 型変換ユーティリティ（後方互換エイリアス）
# =========================================================

def _to_bool(v: Any) -> bool:
    """Convert value to bool (for env vars, config values, etc.).

    Delegates to ``_to_bool_local`` from pipeline_helpers to eliminate
    duplication while keeping the public name for backward compatibility.
    """
    return _to_bool_local(v)


def _to_float_or(v: Any, default: float) -> float:
    """_safe_float のエイリアス（後方互換性のため維持）"""
    return _safe_float(v, default)


def _clip01(x: float) -> float:
    """Clip a float to [0, 1] range.

    Backward-compat wrapper around ``utils._clip01``.
    """
    from .utils import _clip01 as _clip01_base
    return _clip01_base(x)


# =========================================================
# dict 変換ユーティリティ
# =========================================================

def to_dict(o: Any) -> Dict[str, Any]:
    """Convert an arbitrary object to a dict.

    Tries model_dump() (Pydantic v2), dict() (Pydantic v1), then __dict__.
    Filters out circular references (values that reference the original object).
    Returns {} for unconvertible objects.
    """
    if isinstance(o, dict):
        return o
    if hasattr(o, "model_dump"):
        try:
            return o.model_dump(exclude_none=True)
        except (TypeError, ValueError, RuntimeError):
            logger.debug("to_dict: model_dump() failed for %r", type(o).__name__, exc_info=True)
    if hasattr(o, "dict"):
        try:
            return o.dict()
        except (TypeError, ValueError, RuntimeError):
            logger.debug("to_dict: dict() failed for %r", type(o).__name__, exc_info=True)
    try:
        if hasattr(o, "__dict__"):
            raw = o.__dict__
            if isinstance(raw, dict):
                return {
                    k: v for k, v in raw.items()
                    if v is not o
                }
    except (TypeError, ValueError, AttributeError):
        logger.debug("to_dict: __dict__ fallback failed for %r", type(o).__name__, exc_info=True)
    return {}


# 後方互換エイリアス（テスト移行期間中に維持）
_to_dict = to_dict


# =========================================================
# リクエストパラメータ抽出
# =========================================================

def get_request_params(request: Any) -> Dict[str, Any]:
    """
    DummyRequest 互換:
    - request.query_params (starlette)
    - request.params (tests)
    の両方を吸って dict 化する
    """
    out: Dict[str, Any] = {}
    try:
        qp = getattr(request, "query_params", None)
        if qp is not None:
            out.update(dict(qp))
    except (TypeError, ValueError, AttributeError, KeyError, RuntimeError):
        logger.debug("get_request_params: query_params extraction failed", exc_info=True)
    try:
        pm = getattr(request, "params", None)
        if pm is not None:
            out.update(dict(pm))
    except (TypeError, ValueError, AttributeError, KeyError, RuntimeError):
        logger.debug("get_request_params: params extraction failed", exc_info=True)
    return out


# 後方互換エイリアス（テスト移行期間中に維持）
_get_request_params = get_request_params


# =========================================================
# alternative 正規化
# =========================================================

def _norm_alt(o: Any) -> Dict[str, Any]:
    """Normalize an alternative option dict.

    Ensures required fields (title, description, score, id) are present
    and sanitized. IDs are stripped of control characters and unsafe
    Unicode categories.
    """
    d = to_dict(o) or {}

    # text/title/description の整形
    text = d.get("text")
    if isinstance(text, str):
        text = text.strip()

    title = d.get("title")
    if not title and text:
        title = text
    d["title"] = str(title or "")

    desc = d.get("description")
    if not desc and text:
        desc = text
    d["description"] = str(desc or "")

    # score 系
    d["score"] = _to_float_or(d.get("score", 1.0), 1.0)
    d["score_raw"] = _to_float_or(d.get("score_raw", d["score"]), d["score"])

    # ★ id は「あるなら保持」、None/空/空白だけ新規発行
    # ★ 制御文字・null バイト・Unicode制御文字（bidiオーバーライド等）を除去し、
    #   長さを制限（downstream 安全性）
    _id = d.get("id")
    if _id is None or (isinstance(_id, str) and _id.strip() == ""):
        d["id"] = uuid4().hex
    else:
        _id_str = str(_id)
        # ASCII control chars + DEL
        _id_str = re.sub(r"[\x00-\x1f\x7f]", "", _id_str)
        # Filter out unsafe Unicode categories (bidi overrides, surrogates, etc.)
        _id_str = "".join(
            ch for ch in _id_str
            if unicodedata.category(ch) not in _UNSAFE_UNICODE_CATEGORIES
        )
        if len(_id_str) > 256:
            _id_str = _id_str[:256]
        d["id"] = _id_str if _id_str.strip() else uuid4().hex

    return d


# =========================================================
# persona フォールバック
# =========================================================

def _fallback_load_persona() -> dict:
    """Fallback persona loader when evolver module is unavailable."""
    return {"name": "fallback", "mode": "minimal"}


__all__ = [
    "_to_bool",
    "_to_float_or",
    "_clip01",
    "to_dict",
    "_to_dict",
    "get_request_params",
    "_get_request_params",
    "_norm_alt",
    "_fallback_load_persona",
]
